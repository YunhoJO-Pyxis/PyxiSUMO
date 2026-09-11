"""GitHub 저장소에 올리기 — 비밀번호가 새 나가지 않는지 먼저 본다.

    python tools/publish.py --repo https://github.com/<사용자>/<저장소>

저장소는 **공개**일 수 있다. `.env` 에는 Supabase 비밀번호가 들어 있으므로
한 번 올라가면 되돌릴 수 없다 (커밋 기록에 남는다). 그래서 올리기 전에
막는 것이 이 파일의 주된 일이고, git 명령은 그 다음이다.

검사 세 가지
    1) .env 가 올라갈 목록에 있는가
    2) 올라갈 파일 어딘가에 .env 의 비밀번호 문자열이 들어 있는가
    3) 올라갈 파일에 접속 주소(DSN) 모양의 문자열이 있는가

하나라도 걸리면 **올리지 않고 멈춘다.**
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 비밀번호가 아니어도 새면 안 되는 파일들
NEVER_UPLOAD = {".env", "schema_probe.json"}

# 접속 주소 모양을 찾는다. 문서에 쓰는 예시는 걸리면 안 되므로,
# 비밀번호 자리가 자리표시자(***, <...>, pass, password …)면 넘긴다.
DSN_RE = re.compile(
    r"postgres(?:ql)?://[^\s:'\"<>]+:([^\s@'\"]+)@([^\s/:'\"]+)",
    re.I,
)
PLACEHOLDER_PW = {
    "pass", "password", "passwd", "pw", "yourpassword", "your_password",
    "xxx", "xxxx", "secret", "changeme", "hunter2",
    "비밀번호", "패스워드",
}


# 예시·테스트에 쓰는 주소. 진짜 DB 가 아니다.
PLACEHOLDER_HOST = {
    "host", "dbhost", "yourhost", "localhost", "127.0.0.1", "db", "database",
    "example.com", "db.example.com", "example.org", "server",
}


def looks_like_example(password: str, host: str = "") -> bool:
    """문서·테스트에 적힌 예시인가 — 진짜 접속 정보가 아닌가.

    위험한 것은 **사용자의 실제 접속 주소**다. 소스에 들어 있는 가짜 DSN
    (tests/test_wizard.py 의 user:secret123@host 같은 것)까지 막으면
    경고가 늘 떠서 아무도 안 보게 된다 — 그게 더 위험하다.
    """
    h = host.strip().lower().rstrip(".")
    if h in PLACEHOLDER_HOST or h.endswith(".example.com") or h.endswith(".invalid"):
        return True
    pw = password.strip()
    if not pw or len(pw) < 4:
        return True
    if set(pw) <= {"*", "x", "X", "."}:          # ***, xxxx
        return True
    if pw.startswith("<") or pw.endswith(">"):   # <비밀번호>
        return True
    if "[" in pw or "{" in pw:                   # [PASSWORD], {{ secrets.X }}
        return True
    return pw.lower() in PLACEHOLDER_PW


class Stop(RuntimeError):
    """올리면 안 되는 상태 — 메시지를 그대로 사용자에게 보인다."""


def run(args: list[str], *, check: bool = True, quiet: bool = False):
    #  encoding 을 반드시 못박는다. Windows 한국어판에서 text=True 만 주면
    #  파이썬이 cp949 로 읽으려 하는데, git 은 파일명을 UTF-8 로 내보낸다.
    #  '1_설치하기.bat' 한 줄에서 읽기 스레드가 죽고 stdout 이 None 이 된다.
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise Stop(((r.stderr or "") or (r.stdout or "")).strip())
    if not quiet and (r.stdout or "").strip():
        print(r.stdout.rstrip())
    return r


def have_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True,
                       encoding="utf-8", errors="replace")
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def secrets_from_env_file() -> list[str]:
    """.env 안에서 절대 새면 안 되는 문자열들."""
    out: list[str] = []
    f = ROOT / ".env"
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        val = line.split("=", 1)[1].strip().strip('"').strip("'")
        if not val:
            continue
        out.append(val)
        # DSN 안의 비밀번호만 따로 — 주소 전체가 아니라 비밀번호 조각이 새는 경우
        m = re.match(r"postgres(?:ql)?://[^:]+:([^@]+)@", val, re.I)
        if m:
            pw = m.group(1)
            if len(pw) >= 6:
                out.append(pw)
                # URL 인코딩된 형태도 함께 본다
                from urllib.parse import unquote
                if unquote(pw) != pw:
                    out.append(unquote(pw))
    # 너무 짧은 값은 오탐이 많다
    return [s for s in dict.fromkeys(out) if len(s) >= 6]


def files_to_upload() -> list[str]:
    """git 이 실제로 올릴 파일 목록 (.gitignore 적용 후)."""
    #  core.quotepath=false 가 없으면 git 이 한글 파일명을 "\355\225..." 로
    #  이스케이프해 내보낸다. 그러면 그 파일을 열지 못해 **검사에서 통째로
    #  빠진다** — 한글 이름의 메모 파일에 비밀번호를 적어 두면 그냥 올라간다.
    r = run(["git", "-c", "core.quotepath=false",
             "ls-files", "--cached", "--others", "--exclude-standard"],
            quiet=True)
    if r.stdout is None:
        # 여기까지 오면 출력을 읽다가 죽은 것이다 (인코딩 문제).
        # 예전에는 이 자리에서 AttributeError 가 나서 원인을 알 수 없었다.
        raise Stop("git 의 출력을 읽지 못했습니다.\n"
                   "  파일 이름에 한글이 섞여 있고 인코딩이 맞지 않을 때 납니다.\n"
                   "  이 내용을 그대로 알려 주시면 고쳐 드리겠습니다.")
    return [p for p in r.stdout.splitlines() if p.strip()]


def audit(paths: list[str]) -> None:
    """올리기 전 마지막 방어선. 하나라도 걸리면 Stop."""
    problems: list[str] = []

    # 1) 올리면 안 되는 파일
    for p in paths:
        if Path(p).name in NEVER_UPLOAD:
            problems.append(f"{p} 가 올라갈 목록에 있습니다 (비밀번호가 들어 있습니다)")

    # 2) .env 의 값이 다른 파일에 복사돼 있는가
    secrets = secrets_from_env_file()
    for p in paths:
        f = ROOT / p
        try:
            if f.stat().st_size > 2_000_000:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for s in secrets:
            if s in text:
                problems.append(f"{p} 안에 .env 의 값이 그대로 들어 있습니다")
                break
        else:
            # 3) 접속 주소 모양
            for m in DSN_RE.finditer(text):
                if looks_like_example(m.group(1), m.group(2)):
                    continue
                problems.append(f"{p} 안에 접속 주소로 보이는 문자열이 있습니다 "
                                f"({m.group(0)[:34]}…)")
                break

    if problems:
        raise Stop(
            "올리지 않았습니다 — 비밀번호가 새 나갈 수 있습니다.\n\n  "
            + "\n  ".join(f"· {p}" for p in problems)
            + "\n\n저장소가 공개라면 한 번 올라간 비밀번호는 되돌릴 수 없습니다.\n"
              "해당 파일에서 비밀번호를 지우고 다시 실행해 주세요."
        )


# 패키지 폴더(pyxisumo/) 안에 있으면 안 되는 것들.
# 압축을 C:\pyxisumo 가 아니라 C:\pyxisumo\pyxisumo 에 풀면 프로젝트 한 벌이
# 통째로 그 안에 들어간다. 실행에는 지장이 없어서 눈치채기 어렵고, 그대로
# 올리면 저장소에 옛 파일이 60개쯤 섞여 무엇이 진짜인지 알 수 없게 된다.
NESTED_MARKS = ("pyxisumo/pyxisumo", "pyxisumo/tests", "pyxisumo/tools",
                "pyxisumo/db", "pyxisumo/.github", "pyxisumo/docs")


def find_nested() -> list[Path]:
    """패키지 폴더 안에 잘못 들어간 프로젝트 사본을 찾는다."""
    found: list[Path] = []
    pkg = ROOT / "pyxisumo"
    if not pkg.is_dir():
        return found
    for mark in NESTED_MARKS:
        d = ROOT / mark
        if d.is_dir():
            found.append(d)
    for f in pkg.iterdir():
        if f.is_file() and (f.suffix == ".bat" or
                            f.name in ("README.md", "requirements.txt",
                                       ".gitignore", ".env.example")):
            found.append(f)
    return found


def move_nested_aside(items: list[Path]) -> Path:
    """지우지 않고 한곳으로 옮긴다 — 되돌릴 수 있게."""
    bin_dir = ROOT / "_중복파일_확인후삭제"
    bin_dir.mkdir(exist_ok=True)
    import shutil
    for it in items:
        dest = bin_dir / it.name
        n = 1
        while dest.exists():
            dest = bin_dir / f"{it.name}_{n}"
            n += 1
        shutil.move(str(it), str(dest))
    return bin_dir


def normalize_repo(url: str) -> str:
    u = url.strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    if not re.match(r"^https://github\.com/[^/]+/[^/]+$", u):
        raise Stop(f"저장소 주소 모양이 아닙니다: {url}\n"
                   "  https://github.com/<사용자>/<저장소> 형태여야 합니다.")
    return u


def publish(repo: str, *, message: str, dry_run: bool = False,
            fix_nested: bool = False) -> int:
    if not have_git():
        raise Stop(
            "git 이 설치되어 있지 않습니다.\n"
            "  https://git-scm.com/download/win 에서 받아 설치한 뒤\n"
            "  이 파일을 다시 실행해 주세요 (설치 중 선택지는 모두 기본값이면 됩니다)."
        )

    repo = normalize_repo(repo)

    # 저장소 준비
    if not (ROOT / ".git").exists():
        run(["git", "init", "-b", "main"])
    else:
        run(["git", "checkout", "-B", "main"], check=False, quiet=True)

    # 원격 주소 맞추기
    cur = run(["git", "remote", "get-url", "origin"], check=False, quiet=True)
    if cur.returncode == 0:
        if (cur.stdout or "").strip().rstrip("/").removesuffix(".git") != repo:
            run(["git", "remote", "set-url", "origin", repo + ".git"])
    else:
        run(["git", "remote", "add", "origin", repo + ".git"])

    # 잘못 들어간 사본 정리 (있으면)
    nested = find_nested()
    if nested:
        print("\n  ! 패키지 폴더 안에 프로젝트 사본이 들어가 있습니다.")
        print("    (압축을 C:\\pyxisumo 가 아니라 그 안의 pyxisumo 폴더에 푼 것 같습니다)")
        for it in nested:
            print(f"      · {it.relative_to(ROOT)}")
        if fix_nested:
            bin_dir = move_nested_aside(nested)
            print(f"    → '{bin_dir.name}' 폴더로 옮겼습니다. "
                  "확인하시고 통째로 지우시면 됩니다.")
        else:
            raise Stop(
                "올리지 않았습니다 — 위 항목이 저장소에 옛 파일을 섞어 넣습니다.\n"
                "  --fix-nested 를 주면 지우지 않고 '_중복파일_확인후삭제' 폴더로 "
                "옮겨 드립니다."
            )

    run(["git", "add", "-A"], quiet=True)

    paths = files_to_upload()
    if not paths:
        raise Stop("올릴 파일이 없습니다.")

    print(f"  올라갈 파일 {len(paths)}개를 확인합니다…")
    audit(paths)
    print("  ✓ 비밀번호가 새 나갈 파일은 없습니다")
    print(f"  ✓ .env 는 올라가지 않습니다 "
          f"({'있음' if (ROOT / '.env').exists() else '없음'})")

    if dry_run:
        print("\n  (--dry-run: 여기까지만 하고 올리지 않았습니다)")
        return 0

    st = run(["git", "status", "--porcelain"], quiet=True)
    if (st.stdout or "").strip():
        run(["git", "commit", "-m", message], quiet=True)
        print("  ✓ 변경 내용을 기록했습니다")
    else:
        print("  · 바뀐 것이 없습니다 (이미 최신)")

    print("\n  GitHub 에 올리는 중…")
    print("  (처음이면 브라우저가 열리며 GitHub 로그인을 묻습니다)")
    #  push 는 진행 상황을 그대로 보여줘야 하므로 출력을 잡지 않는다
    r = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=ROOT)
    if r.returncode != 0:
        raise Stop(
            "올리지 못했습니다.\n"
            "  · 로그인 창이 떴다가 취소되었을 수 있습니다 — 다시 실행해 보세요.\n"
            "  · 저장소 주소가 맞는지 확인해 주세요: " + repo
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GitHub 에 올리기")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--message", default="PyxiSumo 갱신")
    ap.add_argument("--dry-run", action="store_true",
                    help="검사만 하고 올리지는 않는다")
    ap.add_argument("--fix-nested", action="store_true",
                    help="잘못 들어간 사본을 '_중복파일_확인후삭제' 로 옮긴다")
    args = ap.parse_args(argv)
    try:
        return publish(args.repo, message=args.message, dry_run=args.dry_run,
                       fix_nested=args.fix_nested)
    except Stop as e:
        print(f"\n{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
