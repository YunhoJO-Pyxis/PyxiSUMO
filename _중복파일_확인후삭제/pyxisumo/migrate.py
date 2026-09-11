"""마이그레이션 러너.

db/*.sql 을 파일명 순서대로 적용하고 schema_migrations 에 체크섬과 함께 기록한다.
몇 번을 다시 돌려도 안전하며(이미 적용된 건 건너뜀), **적용 후 파일이 바뀌면
경고**한다 — 스키마가 조용히 갈라지는 사고를 막기 위해서다.

    python -m pyxisumo.migrate up       # 미적용분 적용
    python -m pyxisumo.migrate status   # 현재 상태
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass

from .sqlrunner import Runner, SqlError

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db"
)

BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  checksum    TEXT NOT NULL,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True, slots=True)
class Migration:
    filename: str
    path: str
    checksum: str


def discover(directory: str = MIGRATIONS_DIR) -> list[Migration]:
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".sql"):
            continue
        path = os.path.join(directory, name)
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()[:16]
        out.append(Migration(name, path, digest))
    return out


def applied(runner: Runner) -> dict[str, str]:
    runner.execute(BOOTSTRAP_SQL)
    rows = runner.query("SELECT filename, checksum FROM schema_migrations")
    return {r[0]: r[1] for r in rows}


def up(runner: Runner, *, directory: str = MIGRATIONS_DIR, verbose: bool = True) -> int:
    done = applied(runner)
    pending = [m for m in discover(directory) if m.filename not in done]
    drifted = [
        m for m in discover(directory)
        if m.filename in done and done[m.filename] != m.checksum
    ]

    for m in drifted:
        print(f"  ! {m.filename} — 적용 후 파일이 변경되었습니다 "
              f"(기록 {done[m.filename]} ≠ 현재 {m.checksum}). "
              f"새 마이그레이션 파일로 분리하세요.", file=sys.stderr)

    if not pending:
        if verbose:
            print(f"  마이그레이션 최신 상태 ({len(done)}건 적용됨)")
        return 0

    for m in pending:
        if verbose:
            print(f"  → {m.filename} 적용 중…")
        runner.run_file(m.path)
        runner.execute(
            "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s) "
            "ON CONFLICT (filename) DO UPDATE SET "
            "checksum = EXCLUDED.checksum, applied_at = now()",
            (m.filename, m.checksum),
        )
        if verbose:
            print(f"    ✓ {m.filename}")
    return len(pending)


def status(runner: Runner, *, directory: str = MIGRATIONS_DIR) -> None:
    done = applied(runner)
    print(f"{'파일':<34}{'상태':<12}체크섬")
    print("-" * 66)
    for m in discover(directory):
        if m.filename not in done:
            state = "미적용"
        elif done[m.filename] != m.checksum:
            state = "변경됨(!)"
        else:
            state = "적용됨"
        print(f"{m.filename:<34}{state:<12}{m.checksum}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="스키마 마이그레이션")
    ap.add_argument("command", choices=["up", "status"], nargs="?", default="up")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args(argv)

    if not args.dsn:
        print("DATABASE_URL 이 없습니다.", file=sys.stderr)
        return 2
    try:
        runner = Runner(args.dsn)
        if args.command == "up":
            up(runner)
        else:
            status(runner)
    except SqlError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
