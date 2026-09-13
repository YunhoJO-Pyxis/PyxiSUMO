"""새 버전 적용(`setup update`)이 **받아 둔 데이터를 건드리지 않는가**.

    DATABASE_URL=... python tests/check_update.py

왜 필요한가
-----------
사용자는 대회 데이터를 받는 데 몇 시간을 쓴다. 새 버전을 받았을 때 "무엇을
실행해야 하나" 를 헷갈려 `1_설치하기` 를 누르면 전부 다시 받게 된다.
그래서 "이것만 누르면 된다" 는 명령을 따로 두었는데, 그 명령이 **정말로
데이터를 손대지 않는지**는 말로 보장할 수 없다. 여기서 확인한다.

  1) 행 수가 하나도 변하지 않는다 (반즈케·취조·리키시·시코나)
  2) 새 마이그레이션이 생기면 그것만 적용된다 — 데이터는 그대로
  3) 두 번 돌려도 결과가 같다
  4) 사람이 손으로 고친 이름을 덮어쓰지 않는다
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import migrate                       # noqa: E402
from pyxisumo.sqlrunner import Runner, SqlError    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TABLES = ("banzuke_entry", "torikumi", "rikishi", "shikona", "heya",
          "prediction_entry", "prediction_run")

FAIL: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAIL.append(label)


def counts(rn: Runner) -> dict[str, int]:
    return {t: int(rn.query(f"SELECT count(*) FROM {t}")[0][0]) for t in TABLES}


def run_update(dsn: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pyxisumo.setup", "update"],
        cwd=ROOT, env=dict(os.environ, DATABASE_URL=dsn),
        capture_output=True, text=True)


# 새 버전에 마이그레이션이 하나 늘어난 상황을 흉내 낸다.
NEW_MIGRATION = """-- 새 버전에서 추가된 스키마 변경을 흉내 낸 임시 마이그레이션
BEGIN;
CREATE TABLE IF NOT EXISTS _update_probe (id INT PRIMARY KEY);
COMMIT;
"""


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 필요합니다.", file=sys.stderr)
        return 2
    rn = Runner(dsn)

    print("새 버전 적용 검증")
    before = counts(rn)
    if not before.get("banzuke_entry"):
        print("  (데이터가 비어 있습니다 — 먼저 tests/seed_demo.py 를 돌리세요)",
              file=sys.stderr)
        return 2

    # 사람이 손으로 고친 이름을 하나 심어 둔다.
    #  끝나면 반드시 되돌린다 — 안 그러면 뒤에 도는 검사가 요코즈나 자리에서
    #  '손으로 고친 이름' 을 보고 엉뚱하게 실패한다 (실제로 그랬다).
    rid = rn.query("SELECT rikishi_id FROM shikona ORDER BY rikishi_id LIMIT 1")[0][0]
    orig_name = rn.query("SELECT name_ko FROM shikona WHERE rikishi_id = %s",
                         (rid,))[0][0]
    rn.execute("UPDATE shikona SET name_ko = %s WHERE rikishi_id = %s",
               ("손으로 고친 이름", rid))

    # --- 1) 그냥 한 번 --------------------------------------------------
    r = run_update(dsn)
    check("정상 종료", r.returncode == 0, (r.stdout + r.stderr)[-200:])
    after = counts(rn)
    diff = {t: (before[t], after[t]) for t in TABLES if before[t] != after[t]}
    check("행 수가 하나도 안 변함", not diff, str(diff))

    kept = rn.query("SELECT name_ko FROM shikona WHERE rikishi_id = %s", (rid,))
    check("손으로 고친 이름 유지", kept and kept[0][0] == "손으로 고친 이름",
          str(kept))

    # --- 2) 새 마이그레이션이 생긴 경우 ---------------------------------
    probe = Path(migrate.MIGRATIONS_DIR)
    if not probe.is_absolute():
        probe = ROOT / migrate.MIGRATIONS_DIR
    newfile = probe / "999_update_probe.sql"
    newfile.write_text(NEW_MIGRATION, encoding="utf-8")
    try:
        r2 = run_update(dsn)
        check("새 마이그레이션이 있어도 정상 종료", r2.returncode == 0,
              (r2.stdout + r2.stderr)[-200:])
        applied = migrate.applied(rn)
        check("새 마이그레이션이 적용됨", "999_update_probe.sql" in applied,
              f"적용 목록에 없음")
        exists = rn.query("""
            SELECT count(*) FROM information_schema.tables
            WHERE table_name = '_update_probe'
        """)
        check("스키마 변경이 실제로 반영됨", int(exists[0][0]) == 1)

        after2 = counts(rn)
        diff2 = {t: (before[t], after2[t]) for t in TABLES if before[t] != after2[t]}
        check("마이그레이션 뒤에도 행 수 그대로", not diff2, str(diff2))
    finally:
        newfile.unlink(missing_ok=True)
        try:
            rn.execute("DROP TABLE IF EXISTS _update_probe")
            rn.execute("DELETE FROM schema_migrations WHERE filename = %s",
                       ("999_update_probe.sql",))
        except SqlError as ex:
            print(f"  (정리 실패: {ex})")

    # --- 3) 두 번 돌려도 같은가 -----------------------------------------
    r3 = run_update(dsn)
    check("두 번째 실행도 정상", r3.returncode == 0, (r3.stdout + r3.stderr)[-200:])
    after3 = counts(rn)
    diff3 = {t: (before[t], after3[t]) for t in TABLES if before[t] != after3[t]}
    check("두 번 돌려도 행 수 그대로", not diff3, str(diff3))

    # --- 4) 데이터를 받으러 나가지 않았는가 ------------------------------
    #  네트워크를 쓰면 적재 단계가 돌았다는 뜻이다.
    out = r.stdout + r3.stdout
    check("적재 단계가 돌지 않음",
          "데이터 적재" not in out and "받는 중" not in out,
          "출력에 적재 흔적이 있습니다")

    # 심어 둔 값을 원래대로 돌려놓는다
    rn.execute("UPDATE shikona SET name_ko = %s WHERE rikishi_id = %s",
               (orig_name, rid))
    back = rn.query("SELECT name_ko FROM shikona WHERE rikishi_id = %s", (rid,))
    check("검사가 DB를 원래대로 돌려놓음", back and back[0][0] == orig_name,
          f"'{back[0][0] if back else '?'}' 로 남았습니다")

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}건: {', '.join(FAIL)}")
        return 1
    print("새 버전 적용 — 받아 둔 데이터를 건드리지 않습니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
