"""GitHub 에 올릴 때 **비밀번호가 새 나가지 않는지** 본다.

    python tests/check_publish.py

저장소는 공개일 수 있다. 한 번 올라간 비밀번호는 커밋 기록에 남아 되돌릴 수
없으므로, 이 검사는 "막아야 할 것을 실제로 막는가" 를 확인한다. 통과가 아니라
**실패를 확인하는 검사**다 — 위험한 파일을 일부러 만들어 두고 publish 가
멈추는지 본다.

  1) .env 는 올라가는 목록에 아예 없다
  2) .env 가 목록에 들어오면 멈춘다
  3) 다른 파일에 비밀번호가 복사돼 있으면 멈춘다
  4) 접속 주소 모양의 문자열이 있으면 멈춘다
  5) README 의 예시(`***`, `<...>`)는 오탐하지 않는다
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

FAIL: list[str] = []
#  이 파일 자체가 검사 대상 폴더에 복사되므로, 비밀번호를 통째로 적어 두면
#  "테스트 파일에 비밀번호가 들어 있다" 고 스스로에게 걸린다. 조각으로 나눈다.
PW = "s3cr3t-" + "Passw0rd" + "-XYZ"
DSN = f"postgresql://postgres.abcdef:{PW}@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


def sandbox() -> Path:
    """이 저장소를 임시 폴더로 복사해 진짜 git 을 돌린다."""
    tmp = Path(tempfile.mkdtemp(prefix="publish-"))
    dst = tmp / "pyxisumo"
    shutil.copytree(
        ROOT, dst,
        ignore=shutil.ignore_patterns("__pycache__", ".venv", ".git", "docs",
                                      "*.pyc"))
    (dst / ".env").write_text(
        f"# 테스트용\nDATABASE_URL={DSN}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dst, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=dst)
    subprocess.run(["git", "config", "user.name", "test"], cwd=dst)
    return dst


def publish_here(d: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/publish.py", "--dry-run",
         "--repo", "https://github.com/test/PyxiSumo"],
        cwd=d, capture_output=True, text=True)


def main() -> int:
    if shutil.which("git") is None:
        print("git 이 없어 건너뜁니다.", file=sys.stderr)
        return 0

    print("올리기 안전장치 검증")

    # ---------- 1) 평소 상태 --------------------------------------------
    d = sandbox()
    subprocess.run(["git", "add", "-A"], cwd=d, capture_output=True)
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=d, capture_output=True, text=True).stdout.split()
    check(".env 가 올라갈 목록에 없음", ".env" not in listed)
    check("schema_probe.json 도 없음", "schema_probe.json" not in listed)

    r = publish_here(d)
    check("평소 상태에서는 통과", r.returncode == 0,
          (r.stdout + r.stderr).strip()[-160:])
    shutil.rmtree(d.parent, ignore_errors=True)

    # ---------- 2) .env 가 목록에 들어온 경우 ----------------------------
    #  .gitignore 를 누가 지웠거나 git add -f 를 쓴 상황
    d = sandbox()
    (d / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    r = publish_here(d)
    check(".env 가 올라가려 하면 멈춤", r.returncode != 0,
          "통과해 버렸습니다 — 비밀번호가 공개될 뻔했습니다")
    check("  이유를 알려줌", ".env" in (r.stdout + r.stderr))
    shutil.rmtree(d.parent, ignore_errors=True)

    # ---------- 3) 비밀번호가 다른 파일에 복사된 경우 --------------------
    d = sandbox()
    (d / "메모.txt").write_text(f"비밀번호는 {PW} 입니다\n", encoding="utf-8")
    r = publish_here(d)
    check("비밀번호가 복사돼 있으면 멈춤", r.returncode != 0,
          "통과해 버렸습니다")
    check("  파일 이름을 알려줌", "메모.txt" in (r.stdout + r.stderr))
    shutil.rmtree(d.parent, ignore_errors=True)

    # ---------- 4) 접속 주소가 소스에 박힌 경우 --------------------------
    d = sandbox()
    #  실제 호스트 + 실제로 보이는 비밀번호. 이것이 진짜 위험한 경우다.
    (d / "setup_backup.py").write_text(
        'DSN = "postgresql://postgres.qwerty:Tr0ub4dor-3x@'
        'aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"\n',
        encoding="utf-8")
    r = publish_here(d)
    check("접속 주소가 박혀 있으면 멈춤", r.returncode != 0, "통과해 버렸습니다")
    shutil.rmtree(d.parent, ignore_errors=True)

    # ---------- 5) 문서의 예시는 오탐하지 않는다 -------------------------
    d = sandbox()
    (d / "안내.md").write_text(
        "예) postgresql://postgres.xxxx:***@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres\n"
        "예) postgresql://<사용자>:<비밀번호>@<주소>:5432/postgres\n"
        "테스트용) postgresql://user:secret123@host:5432/db\n",
        encoding="utf-8")
    r = publish_here(d)
    check("문서의 예시(***, <...>)는 통과", r.returncode == 0,
          (r.stdout + r.stderr).strip()[-160:])
    shutil.rmtree(d.parent, ignore_errors=True)

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print("올리기 안전장치 — 비밀번호가 새 나가는 경우를 모두 막습니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
