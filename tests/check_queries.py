"""사이트 조회문을 전부 실제 DB에 던져 본다.

    DATABASE_URL=... python tests/check_queries.py

queries.py 의 SQL 은 사이트 생성기에서만 쓰이기 때문에, 컬럼을 하나 추가하고
build.py 의 언패킹을 고치지 않으면 **사이트를 만들 때가 되어서야** 터진다.
여기서 미리 던져 보고, 나오는 컬럼 수가 build.py 가 기대하는 수와 같은지 본다.

파라미터는 DB에서 실제 값을 꺼내 쓴다 — 타입이 맞지 않으면 (문자열을 bigint
자리에 넣는 등) 조회문이 아니라 검사 쪽이 틀린 것이므로 여기서 걸러야 한다.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.site import queries as Q            # noqa: E402
from pyxisumo.sqlrunner import Runner, SqlError   # noqa: E402

# build.py 가 실제로 언패킹하는 컬럼 수. 둘이 어긋나면 사이트가 깨진다.
EXPECTED_COLS = {
    "BASHO_LIST": 9,
    "BANZUKE": 17,
    "TORIKUMI_LATEST_DAY": 1,
    "TORIKUMI_DAY": 22,
    "LATEST_PREDICTION": 5,
    "PREDICTION_ENTRIES": 25,
    "ACCURACY_HISTORY": 8,
    "PROFILE_RIKISHI": 25,
    "RIKISHI_HISTORY": 11,
    "RIKISHI_OPPONENTS": 5,
    "HEYA_LIST": 10,
    "HEYA_MEMBERS": 9,
    "SITE_STATS": 6,
    # 한 번에 다 받아오는 판 (선수마다 묻지 않기 위한 것)
    "RIKISHI_HISTORY_ALL": 12,
    "RIKISHI_OPPONENTS_ALL": 6,
    "HEYA_MEMBERS_ALL": 10,
}

FAIL: list[str] = []


def scalar(rn: Runner, sql: str, default=None):
    try:
        rows = rn.query(sql)
    except SqlError:
        return default
    return rows[0][0] if rows and rows[0] else default


def params_for(rn: Runner) -> dict[str, object]:
    """각 조회문에 넣을 **타입이 맞는** 표본 파라미터."""
    basho = scalar(rn, "SELECT max(basho_id) FROM banzuke_entry", "202609")
    rikishi = scalar(rn, "SELECT min(rikishi_id) FROM banzuke_entry", 1)
    # 0행이 나오면 컬럼 수를 확인할 수 없으므로, 실제로 소속 선수가 있는 헤야를 고른다
    slug = scalar(rn, """
        SELECT h.slug FROM heya h JOIN rikishi r ON r.heya_id = h.id
        GROUP BY h.slug ORDER BY count(*) DESC LIMIT 1
    """, "demo1")
    # 상대 전적도 마찬가지 — 실제로 대전 기록이 있는 선수를 고른다
    rikishi = scalar(rn, """
        SELECT east_id FROM torikumi GROUP BY east_id
        ORDER BY count(*) DESC LIMIT 1
    """, rikishi)
    # run_id 는 bigint 다 — 바쇼 ID 문자열을 넣으면 조회문이 아니라 검사가 틀린다
    run_id = scalar(rn, "SELECT max(id) FROM prediction_run", 0)
    # 실제로 대전이 들어 있는 (대회, 날) 을 고른다 — 0행이면 컬럼 수를 못 본다
    tk = rn.query("""
        SELECT basho_id, max(day) FROM torikumi
        GROUP BY basho_id ORDER BY basho_id DESC LIMIT 1
    """)
    tk_basho, tk_day = (tk[0][0], tk[0][1]) if tk else (basho, 1)
    return {
        "BASHO_LIST": None,
        "BANZUKE": (basho,),
        "TORIKUMI_LATEST_DAY": (tk_basho,),
        "TORIKUMI_DAY": (tk_basho, tk_day),
        "LATEST_PREDICTION": None,
        "PREDICTION_ENTRIES": (run_id,),
        "ACCURACY_HISTORY": None,
        "PROFILE_RIKISHI": None,
        "RIKISHI_HISTORY": (rikishi,),
        "RIKISHI_OPPONENTS": {"me": rikishi},
        "HEYA_LIST": None,
        "HEYA_MEMBERS": (slug,),
        "SITE_STATS": None,
        "RIKISHI_HISTORY_ALL": None,
        "RIKISHI_OPPONENTS_ALL": None,
        "HEYA_MEMBERS_ALL": None,
    }


ALL = {
    "BASHO_LIST": Q.BASHO_LIST,
    "BANZUKE": Q.BANZUKE,
    "TORIKUMI_LATEST_DAY": Q.TORIKUMI_LATEST_DAY,
    "TORIKUMI_DAY": Q.TORIKUMI_DAY,
    "LATEST_PREDICTION": Q.LATEST_PREDICTION,
    "PREDICTION_ENTRIES": Q.PREDICTION_ENTRIES,
    "ACCURACY_HISTORY": Q.ACCURACY_HISTORY,
    "PROFILE_RIKISHI": Q.PROFILE_RIKISHI,
    "RIKISHI_HISTORY": Q.RIKISHI_HISTORY,
    "RIKISHI_OPPONENTS": Q.RIKISHI_OPPONENTS,
    "HEYA_LIST": Q.HEYA_LIST,
    "HEYA_MEMBERS": Q.HEYA_MEMBERS,
    "SITE_STATS": Q.SITE_STATS,
    "RIKISHI_HISTORY_ALL": Q.RIKISHI_HISTORY_ALL,
    "RIKISHI_OPPONENTS_ALL": Q.RIKISHI_OPPONENTS_ALL,
    "HEYA_MEMBERS_ALL": Q.HEYA_MEMBERS_ALL,
}


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    rn = Runner(dsn)
    par = params_for(rn)

    print("사이트 조회문 검증")
    missing = set(ALL) - set(Q.ALL_QUERIES)
    extra = set(Q.ALL_QUERIES) - set(ALL)
    if missing or extra:
        FAIL.append(f"ALL_QUERIES 목록 불일치 (빠짐 {sorted(missing)} / 남음 {sorted(extra)})")

    for name, sql in ALL.items():
        try:
            rows = rn.query(sql, par[name])
        except SqlError as ex:
            first = str(ex).splitlines()[0][:90]
            print(f"  FAIL {name:<20} {first}")
            FAIL.append(name)
            continue

        want = EXPECTED_COLS[name]
        got = len(rows[0]) if rows else None
        if got is None:
            # 0행이면 컬럼 수를 확인할 수 없다 — 검사가 조용히 통과해 버리므로
            # 이것도 실패로 본다. seed_demo.py 가 표본을 만들어 주어야 한다.
            print(f"  FAIL {name:<20} 0행 — 컬럼 수를 확인할 수 없음")
            FAIL.append(f"{name}:0행")
        elif got != want:
            print(f"  FAIL {name:<20} 컬럼 {got}개 — build.py 는 {want}개를 기대함")
            FAIL.append(f"{name}:컬럼수")
        else:
            print(f"  OK   {name:<20} {len(rows)}행 · 컬럼 {got}")

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(map(str, FAIL))}")
        return 1
    print("사이트 조회문 — 모두 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
