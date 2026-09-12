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


def check_dsn(dsn: str | None) -> str | None:
    """접속 주소 자체의 문제를 본다. 문제가 없으면 None."""
    dsn = (dsn or "").strip()

    if not dsn:
        return annotate(
            "DATABASE_URL 시크릿이 없습니다",
            "저장소 Settings → Secrets and variables → Actions 에서 "
            "New repository secret 을 눌러 Name=DATABASE_URL 로 추가해 주세요. "
            "값은 PC의 .env 파일 안에 있습니다.")

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

    return None


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
            f"{type(e).__name__}: {e} — 시크릿의 주소가 PC의 .env 와 같은지, "
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
