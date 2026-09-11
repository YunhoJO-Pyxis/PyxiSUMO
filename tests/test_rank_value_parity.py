"""Python 의 rank_value() 와 Postgres 의 rank_value() 가 같은 값을 내는지 검증.

두 구현이 갈라지면 예측 결과와 DB 정렬이 어긋나 조용히 틀린 반즈케가 나온다.
이 테스트가 그걸 막는다.

    $ PSQL="psql -h /tmp/pgrun -p 5433 -U postgres -d pyxisumo" python tests/test_rank_value_parity.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.ranks import rank_value  # noqa: E402

CASES: list[tuple[str, str, int | None, str]] = []
for side in ("E", "W"):
    for num in (1, 2, 3):
        for kind in ("Yokozuna", "Ozeki", "Sekiwake", "Komusubi"):
            CASES.append(("Makuuchi", kind, num, side))
    for num in range(1, 22):
        CASES.append(("Makuuchi", "Maegashira", num, side))
    for num in range(1, 15):
        CASES.append(("Juryo", "Numbered", num, side))
    for num in range(1, 61):
        CASES.append(("Makushita", "Numbered", num, side))
    for div in ("Sandanme", "Jonidan", "Jonokuchi"):
        for num in (1, 50, 100):
            CASES.append((div, "Numbered", num, side))


def main() -> int:
    psql = os.environ.get("PSQL")
    if not psql:
        dsn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
        if not dsn:
            print("PSQL 또는 DATABASE_URL 을 지정하세요.", file=sys.stderr)
            return 2
        psql = f'psql "{dsn}"'

    values = ",\n".join(
        f"('{d}'::division_t,'{k}'::rank_kind_t,{n}::smallint,'{s}'::side_t)"
        for d, k, n, s in CASES
    )
    sql = (
        "SELECT rank_value(d,k,n,s) FROM (VALUES\n"
        f"{values}\n) AS t(d,k,n,s);"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql)
        path = f.name

    proc = subprocess.run(
        f"{psql} -At -v ON_ERROR_STOP=1 -f {path}",
        shell=True, capture_output=True, text=True,
    )
    os.unlink(path)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return 1

    sql_vals = [int(x) for x in proc.stdout.split() if x.strip()]
    py_vals = [rank_value(d, k, n, s) for d, k, n, s in CASES]

    if len(sql_vals) != len(py_vals):
        print(f"FAIL — 행 수 불일치: sql={len(sql_vals)} py={len(py_vals)}")
        return 1

    bad = [
        (CASES[i], py_vals[i], sql_vals[i])
        for i in range(len(py_vals))
        if py_vals[i] != sql_vals[i]
    ]
    if bad:
        print(f"FAIL — {len(bad)}건 불일치")
        for case, p, s in bad[:20]:
            print(f"  {case}: python={p} postgres={s}")
        return 1

    # 전 케이스에서 값이 유일한지도 함께 본다 (슬롯 충돌 방지)
    if len(set(py_vals)) != len(py_vals):
        print("FAIL — rank_value 가 중복되는 지위 조합이 있다")
        return 1

    print(f"OK — {len(CASES)}개 지위 조합에서 Python == Postgres, 값 중복 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
