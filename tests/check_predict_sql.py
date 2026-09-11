"""run_predict.py 의 조회 SQL을 실제 데이터로 검증한다.

합성 반즈케 3바쇼를 넣고 FETCH_RESULTS_SQL 이
 - 카도반 오제키(직전 마케코시)
 - 특례 복귀 대상 세키와케(직전 오제키)
 - 3바쇼 연속 산야쿠 + 합계 승수
를 제대로 뽑아내는지 본다. psycopg 없이 psql 로 돌린다.

    $ PSQL="psql -h /tmp/pgrun -p 5433 -U postgres -d pyxisumo_test" python tests/check_predict_sql.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.run_predict import FETCH_RESULTS_SQL, prev_basho  # noqa: E402

B0, B1, B2 = "202609", "202607", "202605"

SEED = f"""
BEGIN;
-- 외래키 순서대로 지운다 (torikumi 가 rikishi 를 참조한다)
DELETE FROM torikumi;
DELETE FROM prediction_entry;
DELETE FROM prediction_run;
DELETE FROM banzuke_entry;
DELETE FROM basho_award;
DELETE FROM shikona;
DELETE FROM rikishi;

INSERT INTO basho (id) VALUES ('{B2}'), ('{B1}'), ('{B0}') ON CONFLICT DO NOTHING;

-- 1: 요코즈나, 2: 카도반이 될 오제키, 3: 특례 복귀 대상, 4: 오제키 승격 후보
INSERT INTO rikishi (id, sumo_api_id) VALUES (1,1001),(2,1002),(3,1003),(4,1004);
SELECT setval(pg_get_serial_sequence('rikishi','id'), 100);

INSERT INTO banzuke_entry (basho_id, rikishi_id, division, rank_kind, rank_num, side, wins, losses, absences) VALUES
  -- 요코즈나: 3바쇼 내내 요코즈나
  ('{B2}',1,'Makuuchi','Yokozuna',1,'E',13,2,0),
  ('{B1}',1,'Makuuchi','Yokozuna',1,'E',12,3,0),
  ('{B0}',1,'Makuuchi','Yokozuna',1,'E', 2,13,0),

  -- 오제키 2: B1 에서 마케코시(6-9) → B0 는 카도반 상태여야 한다
  ('{B2}',2,'Makuuchi','Ozeki',1,'E',9,6,0),
  ('{B1}',2,'Makuuchi','Ozeki',1,'E',6,9,0),
  ('{B0}',2,'Makuuchi','Ozeki',1,'E',5,10,0),

  -- 3: B1 에 오제키였다가 B0 에 세키와케 → returning
  ('{B2}',3,'Makuuchi','Ozeki',2,'E',7,8,0),
  ('{B1}',3,'Makuuchi','Ozeki',2,'E',4,11,0),
  ('{B0}',3,'Makuuchi','Sekiwake',1,'E',10,5,0),

  -- 4: 3바쇼 연속 산야쿠, 합계 11+11+12 = 34승
  ('{B2}',4,'Makuuchi','Komusubi',1,'E',11,4,0),
  ('{B1}',4,'Makuuchi','Sekiwake',1,'W',11,4,0),
  ('{B0}',4,'Makuuchi','Sekiwake',1,'W',12,3,0);

INSERT INTO basho_award (basho_id, rikishi_id, award, division)
VALUES ('{B0}', 4, 'yusho', 'Makuuchi');
COMMIT;
"""

EXPECT = {
    # rikishi_id: (kind, p1_kind, wins_3basho, sanyaku_3, yusho)
    1: ("Yokozuna", "Yokozuna", 2 + 12 + 13, True, False),
    2: ("Ozeki", "Ozeki", 5 + 6 + 9, True, False),
    3: ("Sekiwake", "Ozeki", 10 + 4 + 7, True, False),
    4: ("Sekiwake", "Sekiwake", 12 + 11 + 11, True, True),
}


def run(psql: str, sql: str, tuples_only: bool = False) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
        path = f.name
    flags = "-At" if tuples_only else "-q"
    proc = subprocess.run(f"{psql} {flags} -v ON_ERROR_STOP=1 -f {path}",
                          shell=True, capture_output=True, text=True)
    os.unlink(path)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(1)
    return proc.stdout


def main() -> int:
    psql = os.environ.get("PSQL")
    if not psql:
        print("PSQL 을 지정하세요.", file=sys.stderr)
        return 2

    assert prev_basho(B0) == B1, prev_basho(B0)
    assert prev_basho(B0, 2) == B2, prev_basho(B0, 2)

    run(psql, SEED)

    sql = (FETCH_RESULTS_SQL
           .replace("%(b0)s", f"'{B0}'")
           .replace("%(b1)s", f"'{B1}'")
           .replace("%(b2)s", f"'{B2}'"))
    out = run(psql, sql + ";", tuples_only=True)

    rows = [line.split("|") for line in out.strip().splitlines() if line.strip()]
    if len(rows) != 4:
        print(f"FAIL — 4행을 기대했는데 {len(rows)}행")
        print(out)
        return 1

    failures = []
    for r in rows:
        rid = int(r[0])
        kind, p1_kind, wins3 = r[2], r[8], int(r[11])
        # 컬럼 순서: 0 id, 1 division, 2 kind, 3 num, 4 side, 5 w, 6 l, 7 a,
        #            8 p1_kind, 9 p1_net, 10 p2_kind, 11 wins_3basho,
        #            12 sanyaku_3, 13 yusho, 14 retired
        sanyaku3, yusho = r[12] == "t", r[13] == "t"
        want = EXPECT[rid]
        got = (kind, p1_kind, wins3, sanyaku3, yusho)
        if got != want:
            failures.append((rid, want, got))

    # 상태머신 판정을 파이썬 쪽에서도 확인
    kadoban = [int(r[0]) for r in rows
               if r[2] == "Ozeki" and r[8] == "Ozeki" and int(r[9] or 0) < 0]
    returning = [int(r[0]) for r in rows if r[2] == "Sekiwake" and r[8] == "Ozeki"]

    if kadoban != [2]:
        failures.append(("kadoban", [2], kadoban))
    if returning != [3]:
        failures.append(("returning", [3], returning))

    if failures:
        print("FAIL")
        for k, want, got in failures:
            print(f"  {k}: want={want} got={got}")
        return 1

    print("OK — FETCH_RESULTS_SQL 이 카도반/특례복귀/3바쇼 합계를 정확히 뽑아냅니다.")
    print(f"     카도반 오제키: {kadoban},  특례 복귀 대상: {returning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
