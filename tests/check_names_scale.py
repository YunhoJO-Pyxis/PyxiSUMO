"""표기 채우기가 **실제 규모에서 끝나는가**를 잰다.

    DATABASE_URL=... python tests/check_names_scale.py

왜 필요한가
-----------
로컬 DB에서는 이름 하나마다 UPDATE 를 보내도 빨랐다. 그런데 Runner.execute()
는 호출마다 **새 접속을 연다.** Supabase 처럼 인터넷 너머에 있는 DB 에서는
한 건당 접속+TLS 에 0.2~0.5초가 붙어, 시코나 9천 건이 30분을 넘겼다.
사용자 화면은 그냥 멈춘 것처럼 보였다.

그래서 이 검사는 **결과가 맞는가** 가 아니라 **접속을 몇 번 여는가** 를 본다.
로컬에서는 느려지지 않으니 시간만 재서는 이 사고를 다시 잡을 수 없다.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import fill_names                    # noqa: E402
from pyxisumo.sqlrunner import Runner, SqlError    # noqa: E402

N = 9000              # 사용자의 실제 규모 (1958년부터 받으면 이 정도)
MAX_ROUNDTRIPS = 40   # 이 이상이면 한 건씩 보내고 있다는 뜻이다

FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


SEED = f"""
BEGIN;
INSERT INTO rikishi (id)
SELECT g FROM generate_series(900000, {900000 + N - 1}) g
ON CONFLICT (id) DO NOTHING;

INSERT INTO shikona (rikishi_id, from_basho, name_en, name_ja, name_ko)
SELECT g, '201801', 'Hoshoryu' || g, NULL, NULL
FROM generate_series(900000, {900000 + N - 1}) g
ON CONFLICT (rikishi_id, from_basho) DO NOTHING;
COMMIT;
"""

CLEANUP = f"""
DELETE FROM shikona WHERE rikishi_id BETWEEN 900000 AND {900000 + N - 1};
DELETE FROM rikishi WHERE id BETWEEN 900000 AND {900000 + N - 1};
"""


class CountingRunner(Runner):
    """접속(= execute/query 호출)을 세는 Runner."""

    def __init__(self, dsn: str):
        super().__init__(dsn)
        self.executes = 0
        self.queries = 0

    def execute(self, sql, params=None):
        self.executes += 1
        return super().execute(sql, params)

    def query(self, sql, params=None):
        self.queries += 1
        return super().query(sql, params)


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2

    rn = CountingRunner(dsn)
    print(f"표기 채우기 규모 검증 — 시코나 {N:,}건")
    try:
        rn.execute(CLEANUP)
    except SqlError:
        pass
    rn.execute(SEED)
    rn.executes = rn.queries = 0          # 준비 과정은 세지 않는다

    t0 = time.monotonic()
    try:
        stats = fill_names.fill(rn, verbose=False)
    finally:
        elapsed = time.monotonic() - t0

    trips = rn.executes + rn.queries
    print(f"  (채운 이름 {stats['shikona_ko']:,}건 · "
          f"DB 왕복 {trips}회 · {elapsed:.1f}초)")

    check("전부 채워짐", stats["shikona_ko"] >= N,
          f"{stats['shikona_ko']:,}/{N:,}")
    check(f"DB 왕복 {MAX_ROUNDTRIPS}회 이하", trips <= MAX_ROUNDTRIPS,
          f"{trips}회 — 한 건씩 보내고 있습니다. "
          f"원격 DB에서는 여기에 {trips * 0.3 / 60:.0f}분이 걸립니다")

    # 실제로 값이 들어갔는지 표본으로 확인
    got = rn.query("SELECT name_ko FROM shikona WHERE rikishi_id = 900000")
    check("값이 실제로 맞음", bool(got) and got[0][0].startswith("호쇼류"),
          str(got))

    # 남은 것이 없어야 한다
    left = rn.query(f"""
        SELECT count(*) FROM shikona
        WHERE rikishi_id BETWEEN 900000 AND {900000 + N - 1}
          AND name_ko IS NULL
    """)
    check("빠진 행 없음", int(left[0][0]) == 0, f"{left[0][0]}건 남음")

    rn.execute(CLEANUP)

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print("표기 채우기 — 실제 규모에서도 왕복 횟수가 일정합니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
