"""체크포인트 재개 로직을 실제 Postgres로 검증한다.

psycopg 가 없는 환경에서도 돌도록 psql 위에 최소 DB-API 셰임을 얹었다.
(셰임은 autocommit 이라 rollback 이 no-op 이다. 실제 psycopg 경로에서는
 트랜잭션이 정상 동작한다 — 여기서 보는 건 체크포인트 상태 전이다.)

    $ PSQL_DSN="postgresql://..." python tests/check_checkpoint.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import checkpoint  # noqa: E402
from pyxisumo.sqlrunner import quote_literal  # noqa: E402


# ---------------------------------------------------------------------
#  psql 셰임
# ---------------------------------------------------------------------
class Cursor:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._rows: list[tuple] = []
        self.rowcount = -1

    def execute(self, sql: str, params=None) -> None:
        text = sql
        if params:
            if isinstance(params, dict):
                # 이름 있는 파라미터 %(b0)s — psycopg 는 지원하지만 psql 은 아니다
                import re as _re

                text = _re.sub(
                    r"%\((\w+)\)s",
                    lambda m: quote_literal(params[m.group(1)]),
                    text,
                )
            else:
                out, i, idx = [], 0, 0
                seq = list(params)
                while i < len(text):
                    if text.startswith("%s", i):
                        out.append(quote_literal(seq[idx]))
                        idx += 1
                        i += 2
                    else:
                        out.append(text[i])
                        i += 1
                text = "".join(out)
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                         encoding="utf-8") as f:
            f.write(text if text.rstrip().endswith(";") else text + ";")
            path = f.name
        try:
            proc = subprocess.run(
                f'psql "{self.dsn}" -At -F "\x1f" -v ON_ERROR_STOP=1 -f {path}',
                shell=True, capture_output=True, text=True)
        finally:
            os.unlink(path)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout).strip())

        rows, tag = [], ""
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            if line.split()[0] in ("INSERT", "UPDATE", "DELETE", "SELECT"):
                tag = line
                continue
            rows.append(tuple(None if c == "" else c for c in line.split("\x1f")))
        self._rows = rows
        self.rowcount = int(tag.split()[-1]) if tag and tag.split()[-1].isdigit() else -1

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Conn:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def cursor(self) -> Cursor:
        return Cursor(self.dsn)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


# ---------------------------------------------------------------------
def main() -> int:
    dsn = os.environ.get("PSQL_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("PSQL_DSN 또는 DATABASE_URL 을 지정하세요.", file=sys.stderr)
        return 2

    conn = Conn(dsn)
    checkpoint.reset(conn, task="_test")
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        print(("  ✓ " if cond else "  ✗ ") + label)
        if not cond:
            failures.append(label)

    # 1) 첫 실행 — skip=False, done 기록
    with checkpoint.step(conn, "_test", "202609") as s:
        check("첫 실행은 skip 이 아니다", s.skip is False)
        s.rows = 42
    check("완료 후 done 에 들어간다", "202609" in checkpoint.completed(conn, "_test"))

    # 2) 재실행 — skip=True
    with checkpoint.step(conn, "_test", "202609") as s:
        check("두 번째 실행은 건너뛴다", s.skip is True)

    # 3) force — skip 무시
    with checkpoint.step(conn, "_test", "202609", force=True) as s:
        check("force 는 체크포인트를 무시한다", s.skip is False)
        s.rows = 7

    # 4) 실패 — failed 로 기록되고 예외는 다시 올라온다
    raised = False
    try:
        with checkpoint.step(conn, "_test", "202607"):
            raise ValueError("네트워크 끊김")
    except ValueError:
        raised = True
    check("예외는 삼키지 않고 다시 올린다", raised)
    fails = {(t, i) for t, i, _ in checkpoint.failed(conn, "_test")}
    check("실패가 failed 로 기록된다", ("_test", "202607") in fails)
    check("실패한 단위는 done 에 없다",
          "202607" not in checkpoint.completed(conn, "_test"))

    # 5) 실패한 단위는 다음 실행에서 다시 시도된다
    with checkpoint.step(conn, "_test", "202607") as s:
        check("실패한 단위는 재시도 대상이다", s.skip is False)
        s.rows = 1
    check("재시도 성공 후 done 으로 바뀐다",
          "202607" in checkpoint.completed(conn, "_test"))
    check("done 으로 바뀌면 failed 목록에서 빠진다",
          ("_test", "202607") not in
          {(t, i) for t, i, _ in checkpoint.failed(conn, "_test")})

    # 6) only_failed 리셋은 done 을 건드리지 않는다
    try:
        with checkpoint.step(conn, "_test", "202605"):
            raise RuntimeError("타임아웃")
    except RuntimeError:
        pass
    checkpoint.reset(conn, task="_test", only_failed=True)
    check("only_failed 리셋 후 done 은 남는다",
          {"202609", "202607"} <= checkpoint.completed(conn, "_test"))
    check("only_failed 리셋 후 failed 는 비었다",
          not checkpoint.failed(conn, "_test"))

    checkpoint.reset(conn, task="_test")
    check("전체 리셋 후 비어 있다", not checkpoint.completed(conn, "_test"))

    if failures:
        print(f"\nFAIL — {len(failures)}건: {failures}")
        return 1
    print("\nOK — 체크포인트 재개 로직 정상")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
