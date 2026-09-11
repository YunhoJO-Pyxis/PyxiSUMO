"""db.py 의 모든 SQL 을 실제 Postgres 에 PREPARE 로 던져 검증한다.

드라이버(psycopg) 없이도 돌도록 psql 을 통해 실행한다.
PREPARE 는 구문·테이블/컬럼명·타입 캐스팅을 전부 확인해 주므로,
오타난 컬럼명이 배포 후에야 터지는 사고를 막는다.

    $ python tests/check_sql.py "postgresql://..."          # 또는
    $ PSQL="psql -h /tmp/pgrun -p 5433 -U postgres -d pyxisumo" python tests/check_sql.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.db import ALL_STATEMENTS  # noqa: E402


def to_numbered(sql: str) -> str:
    """psycopg 의 %s 플레이스홀더를 psql 의 $1, $2 ... 로 바꾼다."""
    n = 0

    def repl(_m: re.Match) -> str:
        nonlocal n
        n += 1
        return f"${n}"

    return re.sub(r"%s", repl, sql)


def main() -> int:
    psql = os.environ.get("PSQL")
    if not psql:
        dsn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
        if not dsn:
            print("PSQL 또는 DATABASE_URL 을 지정하세요.", file=sys.stderr)
            return 2
        psql = f'psql "{dsn}"'

    lines = ["\\set ON_ERROR_STOP on"]
    for name, sql in ALL_STATEMENTS.items():
        lines.append(f"-- {name}")
        lines.append(f"PREPARE p_{name.lower()} AS {to_numbered(sql).strip()};")
        lines.append(f"DEALLOCATE p_{name.lower()};")

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines))
        path = f.name

    proc = subprocess.run(
        f"{psql} -q -v ON_ERROR_STOP=1 -f {path}",
        shell=True, capture_output=True, text=True,
    )
    os.unlink(path)

    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        print(f"\nFAIL — {len(ALL_STATEMENTS)}개 중 일부가 PREPARE 되지 않았습니다.")
        return 1

    print(f"OK — {len(ALL_STATEMENTS)}개 SQL 이 모두 PREPARE 되었습니다.")
    for name in ALL_STATEMENTS:
        print(f"  ✓ {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
