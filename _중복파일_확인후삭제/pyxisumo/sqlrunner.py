"""DDL·마이그레이션용 SQL 실행기.

드라이버가 아직 설치되지 않은 상태에서도 스키마를 올릴 수 있어야 하므로
psycopg 가 있으면 그걸 쓰고, 없으면 psql 로 떨어진다.
(파라미터 바인딩이 필요한 일반 쿼리는 db.py 쪽 psycopg 경로를 쓴다.)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Sequence


class SqlError(RuntimeError):
    pass


def quote_literal(v: Any) -> str:
    """psql 백엔드용 리터럴 인용.

    마이그레이션 기록처럼 내부에서 만든 값에만 쓴다.
    사용자 입력이 섞이는 경로는 psycopg 의 파라미터 바인딩을 쓸 것.
    """
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if "\x00" in s:
        raise SqlError("NUL 문자는 SQL 리터럴에 넣을 수 없습니다")
    return "'" + s.replace("'", "''") + "'"


def _have_psycopg() -> bool:
    try:
        import psycopg  # noqa: F401
        return True
    except ImportError:
        return False


def backend_name() -> str:
    if _have_psycopg():
        return "psycopg"
    if shutil.which("psql"):
        return "psql"
    return "none"


class Runner:
    """DSN 하나에 묶인 실행기. 백엔드 선택을 감춘다."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.backend = backend_name()
        if self.backend == "none":
            raise SqlError(
                "psycopg 도 psql 도 없습니다.\n"
                "  pip install -r requirements.txt   또는\n"
                "  apt-get install postgresql-client"
            )

    # -- 내부 -------------------------------------------------------
    def _psql(self, args: str, sql_path: str | None = None) -> str:
        cmd = f'psql "{self.dsn}" -v ON_ERROR_STOP=1 {args}'
        if sql_path:
            cmd += f" -f {sql_path}"
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SqlError((proc.stderr or proc.stdout).strip())
        return proc.stdout

    # -- 공개 -------------------------------------------------------
    def ping(self) -> str:
        """접속 확인 겸 서버 버전 반환."""
        rows = self.query("SELECT version()")
        return rows[0][0] if rows else ""

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        if self.backend == "psycopg":
            import psycopg

            with psycopg.connect(self.dsn, autocommit=True) as conn, conn.cursor() as cur:
                cur.execute(sql, params)
            return
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                         encoding="utf-8") as f:
            f.write(self._inline(sql, params))
            path = f.name
        try:
            self._psql("-q", path)
        finally:
            os.unlink(path)

    @staticmethod
    def _inline(sql: str, params: Any | None) -> str:
        """%s 와 %(이름)s 두 형식 모두 리터럴로 바꾼다 (psql 백엔드용)."""
        if not params:
            return sql

        # 이름 있는 형식: %(me)s
        if isinstance(params, dict):
            def repl(m: "re.Match") -> str:
                key = m.group(1)
                if key not in params:
                    raise SqlError(f"파라미터 '{key}' 가 없습니다")
                return quote_literal(params[key])

            out = re.sub(r"%\((\w+)\)s", repl, sql)
            if "%s" in out:
                raise SqlError("이름 있는 파라미터와 %s 를 섞어 쓸 수 없습니다")
            return out

        # 위치 형식: %s
        seq = list(params)
        parts: list[str] = []
        idx = 0
        i = 0
        while i < len(sql):
            if sql.startswith("%s", i):
                if idx >= len(seq):
                    raise SqlError("플레이스홀더보다 파라미터가 적습니다")
                parts.append(quote_literal(seq[idx]))
                idx += 1
                i += 2
            else:
                parts.append(sql[i])
                i += 1
        if idx != len(seq):
            raise SqlError("파라미터가 플레이스홀더보다 많습니다")
        return "".join(parts)

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[tuple]:
        if self.backend == "psycopg":
            import psycopg

            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                         encoding="utf-8") as f:
            f.write(self._inline(sql, params))
            path = f.name
        try:
            out = self._psql("-At -F '\x1f'", path)
        finally:
            os.unlink(path)
        rows = []
        for line in out.splitlines():
            if not line.strip():
                continue
            rows.append(tuple(
                None if c == "" else c for c in line.split("\x1f")
            ))
        return rows

    def run_file(self, path: str) -> None:
        if self.backend == "psycopg":
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            import psycopg

            with psycopg.connect(self.dsn, autocommit=True) as conn:
                conn.execute(sql)
            return
        self._psql("-q", path)

    def scalar(self, sql: str) -> Any:
        rows = self.query(sql)
        return rows[0][0] if rows and rows[0] else None
