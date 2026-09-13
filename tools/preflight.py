"""GitHub Actions 에서 먼저 돌리는 점검 — 무엇이 잘못됐는지 화면에 적는다.

    python tools/preflight.py

왜 따로 두는가
--------------
워크플로 YAML 안에 파이썬을 끼워 넣으면 **아무도 실행해 보지 않은 코드**가
된다. 정작 사고가 났을 때 그 코드가 또 틀려서 원인을 못 알려주면 최악이다.
그래서 파일로 빼고 tests/check_preflight.py 가 경우마다 돌려 본다.

출력은 GitHub 의 `::error::` 형식으로 낸다. 실행 로그 전체는 로그인해야
보이지만 **Annotations 상자는 로그인 없이도 보이기 때문이다.**
"""

from __future__ import annotations

import os
import sys


def annotate(title: str, body: str) -> str:
    one_line = " ".join(body.split())
    return f"::error title={title}::{one_line}"


def masked(dsn: str) -> str:
    """비밀번호를 가린 접속 주소.

    안내문은 **공개 저장소의 화면에 그대로 남는다.** 그러므로 주소를 보여줄 때
    사용자 이름·비밀번호 부분은 반드시 지운다. 주소의 '모양'만 보이면 된다.
    """
    try:
        head, rest = dsn.split("://", 1)
    except ValueError:
        return "(주소 모양 아님)"
    if "@" in rest:
        rest = "****:****@" + rest.rsplit("@", 1)[1]
    return f"{head}://{rest}"


def check_query(dsn: str) -> str | None:
    """주소 끝의 ?옵션 부분이 성한가.

    복사할 때 일부를 두 번 붙여 넣으면 '?sslmode=require?sslmode=require' 처럼
    되고, psycopg 는 "extra key/value separator" 라는 알아볼 수 없는 말로 죽는다.
    그 상태를 여기서 알아보게 말해 준다.
    """
    if "?" not in dsn:
        return None
    query = dsn.split("?", 1)[1]

    if "?" in query:
        return annotate(
            "주소가 두 번 겹쳐 붙여 넣어진 것 같습니다",
            f"물음표(?)가 두 개 이상 있습니다. 지금 값의 모양: {masked(dsn)} — "
            "시크릿을 지우고 .env 의 한 줄을 다시, 한 번만 붙여 넣어 주세요.")

    for part in query.split("&"):
        if not part:
            continue
        if part.count("=") > 1:
            return annotate(
                "주소 끝의 옵션이 깨져 있습니다",
                f"'{part}' 에 등호(=)가 두 번 들어 있습니다. "
                f"지금 값의 모양: {masked(dsn)} — 시크릿을 지우고 "
                ".env 의 한 줄을 다시 붙여 넣어 주세요.")
    return None


def check_dsn(dsn: str | None) -> str | None:
    """접속 주소 자체의 문제를 본다. 문제가 없으면 None."""
    dsn = (dsn or "").strip()

    if not dsn:
        return annotate(
            "DATABASE_URL 시크릿이 없습니다",
            "저장소 Settings → Secrets and variables → Actions 에서 "
            "New repository secret 을 눌러 Name=DATABASE_URL 로 추가해 주세요. "
            "값은 PC의 .env 파일 안에 있습니다.")

    # 여러 줄이 들어간 경우 — .env 에서 두 줄 이상을 긁어 붙인 것이다.
    # (실제로 'SHEET_ID=' 줄까지 같이 들어갔다. 그러면 psycopg 는
    #  "extra key/value separator" 라는 엉뚱한 말로 죽는다.)
    if "\n" in dsn or "\r" in dsn:
        first = dsn.splitlines()[0].strip()
        extra = [l.strip() for l in dsn.splitlines()[1:] if l.strip()]
        return annotate(
            "시크릿에 여러 줄이 들어갔습니다",
            f"접속 주소는 한 줄입니다. 지금은 {len(dsn.splitlines())}줄이고 "
            f"두 번째 줄부터 '{extra[0][:20] if extra else ''}...' 이 붙어 있습니다. "
            f"첫 줄({masked(first)})만 남기고 다시 넣어 주세요.")

    # 가장 흔한 실수 — .env 한 줄을 통째로 붙여 넣은 경우
    if dsn.upper().startswith("DATABASE_URL"):
        return annotate(
            "시크릿 값에 'DATABASE_URL=' 이 같이 들어갔습니다",
            "값에는 postgresql:// 부터 끝까지만 넣어야 합니다. "
            "시크릿을 지우고 다시 추가해 주세요.")

    # 따옴표째 붙여 넣은 경우.
    # 접두어 검사보다 **먼저** 봐야 한다 — 안 그러면 따옴표 때문에
    # "주소 모양이 아닙니다" 라는 엉뚱한 안내가 나가서 더 헤매게 된다.
    if dsn[0] in "\"'" or dsn[-1] in "\"'":
        return annotate(
            "시크릿 값에 따옴표가 붙어 있습니다",
            "앞뒤의 \" 나 ' 를 빼고 값만 넣어 주세요.")

    if not dsn.lower().startswith(("postgres://", "postgresql://")):
        return annotate(
            "시크릿 값이 접속 주소 모양이 아닙니다",
            f"postgresql:// 로 시작해야 합니다. 지금은 '{dsn[:12]}...' 로 시작합니다.")

    return check_query(dsn)


def check_connection(dsn: str) -> str | None:
    """실제로 붙어 본다. 붙으면 None."""
    try:
        import psycopg
    except ImportError:                                # pragma: no cover
        return annotate("psycopg 가 설치되지 않았습니다",
                        "requirements.txt 설치 단계를 확인해 주세요.")
    try:
        with psycopg.connect(dsn.strip(), connect_timeout=20) as c:
            c.execute("SELECT 1")
    except Exception as e:                             # noqa: BLE001
        return annotate(
            "데이터베이스에 접속하지 못했습니다",
            f"{type(e).__name__}: {e} — 지금 값의 모양: {masked(dsn)} · "
            "시크릿의 주소가 PC의 .env 와 같은지, "
            "Supabase 프로젝트가 일시중지(pause) 되지 않았는지 확인해 주세요.")
    return None


def check_data(dsn: str) -> str | None:
    """웹페이지를 만들 재료가 있는가."""
    try:
        import psycopg
    except ImportError:                                # pragma: no cover
        return annotate("psycopg 가 설치되지 않았습니다",
                        "requirements.txt 설치 단계를 확인해 주세요.")
    try:
        with psycopg.connect(dsn.strip()) as c, c.cursor() as cur:
            cur.execute("SELECT count(*) FROM banzuke_entry")
            n = int(cur.fetchone()[0])
    except Exception as e:                             # noqa: BLE001
        return annotate(
            "데이터를 읽지 못했습니다",
            f"{type(e).__name__}: {e} — PC에서 1_설치하기.bat 을 먼저 "
            "끝까지 실행하셨는지 확인해 주세요.")
    if not n:
        return annotate(
            "반즈케 데이터가 비어 있습니다",
            "PC에서 1_설치하기.bat 으로 데이터를 먼저 받아 주세요. "
            "웹페이지는 그 데이터를 읽어 만듭니다.")
    print(f"반즈케 {n:,}행")
    return None


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")

    for problem in (check_dsn(dsn),):
        if problem:
            print(problem)
            return 1

    assert dsn is not None
    for step in (check_connection, check_data):
        problem = step(dsn)
        if problem:
            print(problem)
            return 1

    print("접속 확인 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
