"""사고가 났을 때 **원인을 제대로 알려주는가**.

    DATABASE_URL=... python tests/check_preflight.py

웹페이지 공개가 실패했는데 화면에 "Process completed with exit code 1" 만
뜨면, 로그를 볼 수 없는 사람은 아무것도 할 수 없다. 그래서 실패 경우마다
Annotations 상자에 무엇을 어떻게 고치라고 적는다 — 그 문구가 실제로 나오는지
여기서 확인한다.

안내문은 기능이다. 틀리면 사용자가 멈춘다.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.preflight import check_data, check_dsn  # noqa: E402

FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


#  일부러 example.com 을 쓴다. 진짜 같은 호스트를 적으면 올리기 안전장치
#  (tests/check_publish.py)가 "접속 주소가 소스에 박혔다" 고 막는다 — 맞는 동작이다.
REAL = "postgresql://postgres.abc:pw12345@db.example.com:5432/postgres"

CASES = [
    # (설명, 넣은 값, 안내문에 반드시 들어가야 할 말)
    ("시크릿을 아예 안 넣음", None, "시크릿이 없습니다"),
    ("빈 값", "   ", "시크릿이 없습니다"),
    ("DATABASE_URL= 까지 붙여 넣음", f"DATABASE_URL={REAL}", "DATABASE_URL="),
    ("소문자로 붙여 넣음", f"database_url={REAL}", "DATABASE_URL="),
    ("엉뚱한 값", "여기에 붙여넣기", "접속 주소 모양이 아닙니다"),
    ("따옴표째 붙여 넣음", f'"{REAL}"', "따옴표"),
]


def main() -> int:
    print("실패 안내 검증")

    for label, value, must in CASES:
        msg = check_dsn(value)
        ok = bool(msg) and must in msg and msg.startswith("::error title=")
        check(label, ok, (msg or "안내문이 없습니다")[:110])

    # 정상 값은 통과해야 한다 — 멀쩡한 설정에 경고가 뜨면 아무도 안 믿는다
    check("정상 값은 통과", check_dsn(REAL) is None, str(check_dsn(REAL))[:110])
    check("앞뒤 공백은 봐준다", check_dsn(f"  {REAL}  ") is None)

    # 안내문이 한 줄인가 — 여러 줄이면 Annotations 상자에서 잘린다
    multi = [m for _, v, _ in CASES if (m := check_dsn(v)) and "\n" in m]
    check("안내문이 한 줄", not multi, "줄바꿈이 들어 있습니다")

    # --- 실제 DB 가 필요한 부분 -----------------------------------------
    try:
        import psycopg  # noqa: F401
        have_driver = True
    except ImportError:
        have_driver = False

    dsn = os.environ.get("DATABASE_URL")
    if dsn and have_driver:
        check("데이터가 있으면 통과", check_data(dsn) is None,
              str(check_data(dsn))[:110])

        from tools.preflight import check_connection
        bad = REAL.replace("db.example.com", "no-such-host.invalid")
        msg = check_connection(bad)
        check("접속 실패 시 안내가 나옴",
              bool(msg) and "접속하지 못했습니다" in msg, str(msg)[:110])
    else:
        print("  · psycopg 나 DATABASE_URL 이 없어 접속 검사는 건너뜁니다")

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print("실패 안내 — 경우마다 무엇을 고쳐야 하는지 알려줍니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
