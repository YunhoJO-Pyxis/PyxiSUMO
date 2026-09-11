"""설치 마법사 — 프로그래밍을 몰라도 따라올 수 있게 만든 대화형 설정 도구.

.bat 파일이 이 스크립트를 부른다. 배치 파일에는 영문만 넣고 한글 안내는
전부 여기 파이썬 쪽에 둔다 (Windows 명령 프롬프트의 한글 인코딩 문제 회피).

    python tools/wizard.py install    설치 + 초기 적재
    python tools/wizard.py doctor     상태 점검
    python tools/wizard.py resume     중단된 적재 이어받기
    python tools/wizard.py predict    반즈케 예측 실행
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# 적재 범위 선택지: (라벨, 시작 바쇼, 대략 바쇼 수, 예상 분)
RANGES = [
    ("최근 3년만  — 가장 빠름. 예측만 돌려보려면 이걸로 충분합니다", "202301", 22, 8),
    ("최근 10년   — 추천. 예측 정확도 검증에 쓸 과거 데이터가 충분합니다", "201601", 64, 22),
    ("2000년부터 — 아카이브(은퇴 선수 전적)까지 보여주려면", "200001", 160, 55),
    ("1958년 전체 — 가능한 전부. 2~3시간 걸립니다", "195801", 412, 140),
]


# ---------------------------------------------------------------------
#  화면 출력
# ---------------------------------------------------------------------
def title(s: str) -> None:
    print()
    print("=" * 64)
    print(f"  {s}")
    print("=" * 64)


def step(n: int, total: int, s: str) -> None:
    print()
    print(f"[{n}/{total}] {s}")
    print("-" * 64)


def say(s: str = "") -> None:
    print(f"   {s}" if s else "")


def okmsg(s: str) -> None:
    print(f"   [OK] {s}")


def errmsg(s: str) -> None:
    print(f"   [!!] {s}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" (그냥 Enter = {default})" if default else ""
    try:
        v = input(f"   {prompt}{suffix}\n   > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1)
    return v or default


def ask_yes(prompt: str, default_yes: bool = True) -> bool:
    d = "Y/n" if default_yes else "y/N"
    while True:
        v = ask(f"{prompt} [{d}]").lower()
        if not v:
            return default_yes
        if v in ("y", "yes", "ㅛ", "네", "ㅇ"):
            return True
        if v in ("n", "no", "ㅜ", "아니오", "ㄴ"):
            return False
        say("y 또는 n 으로 답해 주세요.")


def pause() -> None:
    try:
        input("\n   계속하려면 Enter 를 누르세요...")
    except (EOFError, KeyboardInterrupt):
        pass


# ---------------------------------------------------------------------
#  .env 다루기
# ---------------------------------------------------------------------
def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def write_env(values: dict[str, str]) -> None:
    lines = [
        "# PyxiSumo 설정 파일",
        "# 이 파일에는 데이터베이스 비밀번호가 들어 있습니다.",
        "# 다른 사람에게 보내거나 GitHub 에 올리지 마세요.",
        "",
    ]
    for k, v in values.items():
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError:
        pass


def mask(dsn: str) -> str:
    if "@" not in dsn:
        return dsn
    head, tail = dsn.split("@", 1)
    if ":" in head:
        head = head.rsplit(":", 1)[0] + ":********"
    return head + "@" + tail


# ---------------------------------------------------------------------
#  연결 문자열 받기
# ---------------------------------------------------------------------
PLACEHOLDER = re.compile(r"\[YOUR-PASSWORD\]", re.IGNORECASE)


def classify_dsn(dsn: str) -> str:
    """붙여넣은 주소가 어떤 연결 방식인지 주소 모양만 보고 판정한다.

    Supabase 화면의 라벨은 수시로 바뀐다. 주소 자체는 안 바뀌므로 이쪽을 믿는다.

      db.<프로젝트>.supabase.co:5432       → direct      (일부 인터넷에서 연결 안 됨)
      <리전>.pooler.supabase.com:6543      → transaction (배치 작업에 부적합)
      <리전>.pooler.supabase.com:5432      → session     ← 우리가 쓸 것
    """
    low = dsn.lower()
    if "pooler.supabase.com" in low:
        if ":6543" in low:
            return "transaction"
        if ":5432" in low:
            return "session"
        return "pooler"
    if ".supabase.co" in low:
        return "direct"
    return "other"


def fix_supabase_mode(dsn: str) -> tuple[str, list[str]]:
    """Transaction pooler 주소를 Session pooler 로 바꾸고, Direct 는 경고한다."""
    notes: list[str] = []
    kind = classify_dsn(dsn)

    if kind == "transaction":
        # 포트만 다르고 호스트는 같다. 6543(Transaction) → 5432(Session).
        # 호스트 바로 뒤의 포트만 바꾼다 — 비밀번호에 6543 이 들어 있어도 안전하게.
        dsn = re.sub(r"(pooler\.supabase\.com):6543\b", r"\1:5432", dsn,
                     flags=re.IGNORECASE)
        notes.append(
            "Transaction pooler 주소를 붙여넣으셨습니다. "
            "이 프로그램에는 Session pooler 가 맞아서 포트를 5432 로 바꿨습니다."
        )
    elif kind == "direct":
        notes.append(
            "Direct connection 주소입니다. 이 방식은 일부 가정·회사 인터넷에서 "
            "연결되지 않습니다. 연결에 실패하면 Session pooler 주소로 다시 시도하세요."
        )
    return dsn, notes


def normalize_dsn(raw: str) -> tuple[str, list[str]]:
    """붙여넣은 연결 문자열을 다듬고, 알려줄 점을 함께 돌려준다."""
    notes: list[str] = []
    dsn = raw.strip()

    # Supabase 화면에서 'psql "postgresql://..."' 를 통째로 복사하는 일이 흔하다.
    # 공백을 없애기 '전에' 떼어내야 한다.
    if dsn.lower().startswith("psql"):
        dsn = dsn[4:].lstrip()
        notes.append("맨 앞의 'psql' 을 떼어냈습니다.")

    dsn = dsn.strip('"').strip("'")

    # 메모장·엑셀을 거치면 줄바꿈이나 공백이 끼어든다
    dsn = "".join(dsn.split())
    dsn = dsn.strip('"').strip("'")

    if not dsn.startswith(("postgresql://", "postgres://")):
        notes.append("주소가 postgresql:// 로 시작하지 않습니다. 다시 확인해 주세요.")

    dsn, mode_notes = fix_supabase_mode(dsn)
    notes.extend(mode_notes)

    if "sslmode" not in dsn and "localhost" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
        notes.append("보안 접속 옵션(sslmode=require)을 자동으로 붙였습니다.")

    return dsn, notes


def fill_password(dsn: str) -> str:
    """[YOUR-PASSWORD] 자리를 실제 비밀번호로 채운다.

    비밀번호에 @ # ? / 같은 기호가 있으면 주소가 깨지므로 반드시 인코딩한다.
    이게 초보자가 가장 많이 막히는 지점이다.
    """
    if not PLACEHOLDER.search(dsn):
        return dsn

    say()
    say("주소 안에 [YOUR-PASSWORD] 라고 적힌 부분이 있습니다.")
    say("여기에 Supabase 프로젝트를 만들 때 정한 데이터베이스 비밀번호를 넣어야 합니다.")
    say("(로그인 비밀번호가 아니라, 프로젝트 만들 때 따로 정한 그 비밀번호입니다)")
    say()

    while True:
        pw = ask("비밀번호를 입력하세요")
        if not pw:
            errmsg("비밀번호가 비어 있습니다.")
            continue
        if PLACEHOLDER.search(pw):
            errmsg("[YOUR-PASSWORD] 라는 글자 그대로가 아니라, 실제 비밀번호를 넣어주세요.")
            continue
        break

    encoded = urllib.parse.quote(pw, safe="")
    if encoded != pw:
        okmsg("비밀번호에 특수문자가 있어 주소용으로 변환했습니다.")
    return PLACEHOLDER.sub(encoded, dsn)


def get_dsn(existing: str | None) -> str | None:
    if existing:
        say(f"저장된 접속 주소가 있습니다: {mask(existing)}")
        if ask_yes("이 주소를 그대로 쓸까요?"):
            return existing

    say()
    say("Supabase 접속 주소가 필요합니다. 받는 방법:")
    say()
    say("  1. supabase.com 에 로그인해 프로젝트를 엽니다")
    say("  2. 화면 위쪽 [Connect] 버튼을 누릅니다")
    say("  3. 'Direct - Connection string' 을 누릅니다")
    say("  4. 다음 화면에서 'Session pooler' 의 주소를 복사합니다")
    say()
    say("  postgresql:// 로 시작하는 긴 주소 한 줄입니다.")
    say("  어느 것인지 헷갈려도 괜찮습니다 — 일단 붙여넣으시면")
    say("  맞는 방식인지 확인하고 필요하면 자동으로 고쳐드립니다.")
    say()
    say("  ※ 명령 프롬프트에 붙여넣기: 마우스 오른쪽 버튼 클릭")
    say()

    for attempt in range(3):
        raw = ask("주소를 붙여넣고 Enter")
        if not raw:
            errmsg("아무것도 입력되지 않았습니다.")
            continue
        dsn, notes = normalize_dsn(raw)
        for n in notes:
            say(f"· {n}")
        dsn = fill_password(dsn)
        return dsn
    return None


# ---------------------------------------------------------------------
#  하위 명령 실행
# ---------------------------------------------------------------------
def run(args: list[str], env: dict[str, str] | None = None) -> int:
    full = dict(os.environ)
    if env:
        full.update(env)
    full.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run([sys.executable, *args], cwd=str(ROOT), env=full)
    return proc.returncode


def test_connection(dsn: str) -> bool:
    say("접속을 확인하는 중입니다...")
    code = subprocess.run(
        [sys.executable, "-c",
         "import sys,psycopg\n"
         "try:\n"
         "    with psycopg.connect(sys.argv[1], connect_timeout=15) as c:\n"
         "        c.execute('select 1')\n"
         "except Exception as e:\n"
         "    print(type(e).__name__ + ': ' + str(e)[:300]); sys.exit(1)\n",
         dsn],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if code.returncode == 0:
        okmsg("데이터베이스에 연결되었습니다.")
        return True
    msg = (code.stdout or code.stderr).strip()
    errmsg("연결하지 못했습니다.")
    say(f"  {msg[:240]}")
    say()
    if "password authentication" in msg.lower():
        say("→ 비밀번호가 틀렸습니다. Supabase 프로젝트를 만들 때 정한 "
            "'데이터베이스 비밀번호' 를 확인해 주세요.")
        say("  기억이 안 나면 Supabase 에서 새로 설정할 수 있습니다 "
            "(Settings → Database → Reset database password).")
    elif "could not translate" in msg.lower() or "name or service" in msg.lower():
        say("→ 주소가 잘못 복사된 것 같습니다. 앞뒤가 잘리지 않았는지 확인해 주세요.")
    elif "timeout" in msg.lower() or "unreachable" in msg.lower():
        say("→ 인터넷 연결을 확인하시고, 'Session pooler' 주소를 쓰고 있는지 "
            "확인해 주세요. 'Direct connection' 주소는 일부 인터넷 환경에서 "
            "연결되지 않습니다.")
    return False


# ---------------------------------------------------------------------
#  명령
# ---------------------------------------------------------------------
def cmd_install() -> int:
    title("PyxiSumo 설치")
    say("스모 데이터를 받아 저장할 준비를 합니다.")
    say("중간에 창을 닫아도 괜찮습니다 — 다시 실행하면 이어서 진행됩니다.")

    total = 4

    # 1 ── 접속 주소
    step(1, total, "데이터베이스 접속 주소 확인")
    env = read_env()
    dsn = get_dsn(env.get("DATABASE_URL"))
    if not dsn:
        errmsg("접속 주소를 받지 못해 중단합니다.")
        return 1

    if not test_connection(dsn):
        say()
        say("주소를 고쳐서 다시 시도하려면 이 창을 닫고 설치 파일을 다시 실행하세요.")
        return 1

    env["DATABASE_URL"] = dsn
    env.setdefault("SHEET_ID", "")
    write_env(env)
    okmsg(f"설정을 저장했습니다 → {ENV_PATH.name}")

    # 2 ── 적재 범위
    step(2, total, "어느 시기 데이터를 받을지 고르기")
    say("과거 데이터를 많이 받을수록 시간이 오래 걸립니다.")
    say("나중에 더 받을 수 있으니 처음에는 짧게 시작해도 됩니다.")
    say()
    for i, (label, _, n, mins) in enumerate(RANGES, start=1):
        say(f"  {i}. {label}")
        say(f"     (대회 약 {n}개 · 예상 {mins}분)")
    say()
    choice = ask("번호를 고르세요", "2")
    try:
        idx = max(1, min(len(RANGES), int(choice))) - 1
    except ValueError:
        idx = 1
    label, from_basho, n_basho, mins = RANGES[idx]
    okmsg(f"'{label.split('—')[0].strip()}' 을(를) 선택했습니다. 예상 {mins}분")

    # 3 ── 실행
    step(3, total, "설치와 데이터 받기")
    say("이제부터 자동으로 진행됩니다. 진행 상황이 아래에 표시됩니다.")
    say("시간이 걸리니 창을 열어둔 채 다른 일을 하셔도 됩니다.")
    say()

    code = run(["-m", "pyxisumo.setup", "init",
                "--from", from_basho, "--to", "202609"],
               env={"DATABASE_URL": dsn})

    # 4 ── 마무리
    step(4, total, "마무리")
    if code == 0:
        okmsg("설치가 끝났습니다.")
        say()
        say("이제 할 수 있는 것:")
        say("  · 2_상태확인.bat  — 지금 데이터가 얼마나 들어있는지 봅니다")
        say("  · 4_예측하기.bat  — 다음 대회 순위표를 예측합니다")
    else:
        errmsg("중간에 문제가 있었습니다. 위에 [!!] 로 표시된 줄을 봐주세요.")
        say()
        say("데이터를 받다가 끊긴 것이라면 '3_이어받기.bat' 을 실행하면")
        say("받은 데까지는 건너뛰고 나머지만 이어서 받습니다.")
    return code


def cmd_simple(name: str, sub: list[str], intro: str) -> int:
    title(name)
    env = read_env()
    dsn = env.get("DATABASE_URL")
    if not dsn:
        errmsg("아직 설치가 되지 않았습니다.")
        say("먼저 '1_설치하기.bat' 을 실행해 주세요.")
        return 1
    say(intro)
    say()
    return run(sub, env={"DATABASE_URL": dsn})


def cmd_tune() -> int:
    title("예측 설정 맞추기")
    env = read_env()
    dsn = env.get("DATABASE_URL")
    if not dsn:
        errmsg("아직 설치가 되지 않았습니다. 먼저 '1_설치하기.bat' 을 실행해 주세요.")
        return 1

    say("가지고 있는 과거 대회를 전부 써서 예측 설정을 맞춥니다.")
    say()
    say("반즈케 편성에는 성문 규칙이 거의 없어서, 계수는 정해진 값이 아니라")
    say("**측정해서 고르는 값**입니다. 데이터가 늘면 다시 돌리세요.")
    say()
    say("몇 분 걸립니다. 설정 조합을 하나씩 채점하며 진행 상황을 보여줍니다.")
    say()

    code = run(["-m", "pyxisumo.run_predict", "tune", "--save"],
               env={"DATABASE_URL": dsn})
    if code == 0:
        say()
        okmsg("가장 잘 맞는 설정을 저장했습니다. 앞으로 예측은 이 설정을 씁니다.")
        say("'6_예측정확도확인.bat' 으로 결과를 다시 확인해 보세요.")
    else:
        say()
        errmsg("맞추지 못했습니다. 성적이 있는 대회가 연속 2개 이상 필요합니다.")
    return code


def cmd_publish() -> int:
    """GitHub 에 올리기. 저장소 주소는 한 번만 물어보고 .env 에 기억한다."""
    title("GitHub 에 올리기")
    env = read_env()

    repo = env.get("GITHUB_REPO", "")
    if not repo:
        say("웹페이지를 인터넷에 공개하려면 GitHub 저장소가 필요합니다.")
        say("아직 없다면 github.com 에서 새 저장소(New repository)를 만들어 주세요.")
        say()
        say("저장소 주소를 붙여 넣어 주세요.")
        say("  예) https://github.com/hong/PyxiSumo")
        say()
        repo = ask("저장소 주소")
        if not repo.strip():
            errmsg("주소가 없어 중단합니다.")
            return 1
        env["GITHUB_REPO"] = repo.strip()
        write_env(env)
        say()
        okmsg("주소를 기억했습니다. 다음부터는 묻지 않습니다.")
        say()

    say(f"저장소: {repo}")
    say()
    say("올리기 전에 비밀번호가 새 나갈 파일이 없는지 먼저 확인합니다.")
    say()

    code = run(["tools/publish.py", "--repo", repo], env={})
    if code != 0:
        return code

    say()
    okmsg("올렸습니다.")
    say()
    say("이제 GitHub 쪽에서 세 가지만 해주시면 웹페이지가 켜집니다.")
    say()
    say(f"  1) {repo}/settings/secrets/actions 에서")
    say("     [New repository secret] 을 눌러")
    say("       이름  DATABASE_URL")
    say("       값    1_설치하기 때 넣었던 접속 주소 (.env 안에 있습니다)")
    say("     를 추가합니다.")
    say()
    say(f"  2) {repo}/settings/pages 에서")
    say("     Source 를 [GitHub Actions] 로 바꿉니다.")
    say()
    say(f"  3) {repo}/actions 에서 '웹페이지 공개' 를 골라")
    say("     [Run workflow] 를 누릅니다.")
    say()
    say("몇 분 뒤 주소가 열립니다:")
    owner_repo = repo.rstrip("/").split("github.com/")[-1]
    owner, _, name = owner_repo.partition("/")
    say(f"  https://{owner}.github.io/{name}/")
    say()
    say("이후로는 매일 아침 자동으로 다시 만들어 올립니다.")
    return 0


def cmd_update() -> int:
    """새 버전을 받은 뒤 한 번 누르면 되는 것."""
    title("새 버전 적용하기")
    env = read_env()
    dsn = env.get("DATABASE_URL")
    if not dsn:
        errmsg("아직 설치가 되지 않았습니다.")
        say("먼저 '1_설치하기.bat' 을 실행해 주세요.")
        return 1

    say("새로 받은 버전을 지금 데이터에 맞춥니다.")
    say()
    say("  · 이미 받아 둔 대회 데이터는 그대로 둡니다 (다시 받지 않습니다)")
    say("  · 바뀐 스키마가 있으면 적용하고, 비어 있는 이름 표기를 채웁니다")
    say("  · 마지막에 웹페이지를 다시 만듭니다")
    say()

    code = run(["-m", "pyxisumo.setup", "update"], env={"DATABASE_URL": dsn})
    if code != 0:
        errmsg("적용하지 못했습니다. 위 내용을 확인해 주세요.")
        return code

    say()
    say("이어서 웹페이지를 다시 만듭니다.")
    say()
    return cmd_site(skip_names=True)


def cmd_site(skip_names: bool = False) -> int:
    title("웹페이지 만들기")
    env = read_env()
    dsn = env.get("DATABASE_URL")
    if not dsn:
        errmsg("아직 설치가 되지 않았습니다. 먼저 '1_설치하기.bat' 을 실행해 주세요.")
        return 1

    say("DB에 들어 있는 데이터로 웹페이지를 만듭니다.")
    say("만들어진 파일은 docs 폴더에 들어갑니다.")
    say()

    # 이름이 영문으로 들어온 선수·헤야에 한국어 표기를 채운다.
    # 이미 값이 있으면 건드리지 않으므로 몇 번을 돌려도 안전하다.
    if not skip_names:
        say("[1/2] 한국어 이름 채우는 중...")
        run(["-m", "pyxisumo.setup", "names"], env={"DATABASE_URL": dsn})
        say()
        say("[2/2] 페이지 만드는 중...")

    code = run(["-m", "pyxisumo.site.build", "--out", "docs"],
               env={"DATABASE_URL": dsn})
    if code != 0:
        errmsg("만들지 못했습니다. 위 내용을 확인해 주세요.")
        return code

    index = ROOT / "docs" / "index.html"
    say()
    okmsg(f"완성 — {index}")
    say()
    say("브라우저로 열어 확인해 보세요. 지금 바로 열어드립니다.")
    try:
        import webbrowser

        webbrowser.open(index.as_uri())
    except Exception:                                  # noqa: BLE001
        say("(자동으로 열지 못했습니다. docs 폴더의 index.html 을 더블클릭하세요)")

    say()
    say("인터넷에 공개하려면 GitHub 에 올리면 됩니다.")
    say("방법은 README 의 '웹페이지 공개하기' 부분을 보세요.")
    return 0


def cmd_backtest() -> int:
    title("예측 정확도 확인")
    env = read_env()
    dsn = env.get("DATABASE_URL")
    if not dsn:
        errmsg("아직 설치가 되지 않았습니다. 먼저 '1_설치하기.bat' 을 실행해 주세요.")
        return 1

    say("이미 끝난 대회로 예측 엔진을 채점합니다.")
    say("다음 대회를 기다릴 필요 없이, 지금 이 엔진이 쓸 만한지 알 수 있습니다.")
    say()
    say("방법: 한 대회 전 성적만 가지고 다음 반즈케를 예측한 뒤,")
    say("      실제로 발표됐던 반즈케와 맞춰봅니다.")
    say()
    say("보게 될 세 가지 숫자:")
    say("  · 완전 일치   지위·매수·동서까지 정확히 맞힌 비율 (가장 엄격)")
    say("  · ±1매 이내   한 칸 차이까지 인정 — 체감 정확도, 주 지표")
    say("  · 평균 오차   평균 몇 매나 빗나갔는지")
    say()

    code = run(["-m", "pyxisumo.run_predict", "backtest"],
               env={"DATABASE_URL": dsn})
    if code == 0:
        say()
        say("±1매 이내가 70%% 를 넘으면 공개해도 부끄럽지 않은 수준입니다.")
        say("낮게 나오면 계수를 바꿔가며 조정할 수 있습니다 — 알려주세요.")
    else:
        say()
        errmsg("채점하지 못했습니다.")
        say("성적이 들어 있는 대회가 연속 2개 이상 필요합니다.")
        say("'2_상태확인.bat' 으로 어느 대회까지 들어와 있는지 확인해 보세요.")
    return code


def cmd_predict() -> int:
    title("반즈케 예측")
    env = read_env()
    dsn = env.get("DATABASE_URL")
    if not dsn:
        errmsg("아직 설치가 되지 않았습니다. 먼저 '1_설치하기.bat' 을 실행해 주세요.")
        return 1

    say("직전 대회 성적을 근거로 다음 대회 순위표를 예측합니다.")
    say()
    say("대회 번호는 '연도4자리 + 월2자리' 입니다. 예: 2026년 9월 = 202609")
    say("스모 본대회는 홀수 달(1·3·5·7·9·11월)에만 열립니다.")
    say()
    source = ask("근거로 쓸 대회 (끝난 대회)", "202609")
    target = ask("예측할 대회 (다음 대회)", "202611")

    code = run(["-m", "pyxisumo.run_predict", "predict",
                "--source", source, "--target", target],
               env={"DATABASE_URL": dsn})
    if code != 0:
        say()
        errmsg("예측하지 못했습니다.")
        say(f"{source} 대회 데이터가 아직 없을 수 있습니다.")
        say("'2_상태확인.bat' 으로 어느 대회까지 들어와 있는지 확인해 보세요.")
    return code


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    try:
        if cmd == "install":
            code = cmd_install()
        elif cmd == "doctor":
            code = cmd_simple(
                "상태 확인", ["-m", "pyxisumo.setup", "doctor"],
                "지금 데이터가 얼마나 들어있고 이상은 없는지 확인합니다.")
        elif cmd == "resume":
            code = cmd_simple(
                "이어받기", ["-m", "pyxisumo.setup", "resume"],
                "받다 만 데이터를 이어서 받습니다. 이미 받은 것은 건너뜁니다.")
        elif cmd == "retry":
            code = cmd_simple(
                "실패한 부분 다시 받기", ["-m", "pyxisumo.setup", "retry-failed"],
                "받지 못한 대회만 골라 다시 받습니다.")
        elif cmd == "predict":
            code = cmd_predict()
        elif cmd == "backtest":
            code = cmd_backtest()
        elif cmd == "site":
            code = cmd_site()
        elif cmd == "tune":
            code = cmd_tune()
        elif cmd == "update":
            code = cmd_update()
        elif cmd == "publish":
            code = cmd_publish()
        elif cmd == "names":
            code = cmd_simple(
                "이름 표기 채우기", ["-m", "pyxisumo.setup", "names"],
                "한국어 이름이 비어 있는 선수와 헤야를 채웁니다. "
                "직접 고친 이름은 그대로 둡니다.")
        else:
            errmsg(f"알 수 없는 명령: {cmd}")
            code = 2
    except KeyboardInterrupt:
        print()
        say("중단했습니다. 다시 실행하면 이어서 진행됩니다.")
        code = 1
    return code


if __name__ == "__main__":
    rc = main()
    if os.name == "nt" and not os.environ.get("PYXISUMO_NO_PAUSE"):
        pause()
    raise SystemExit(rc)
