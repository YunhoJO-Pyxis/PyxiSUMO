"""비어 있는 한국어·일본어 표기를 채운다.

    python -m pyxisumo.fill_names

무엇을 채우는가
    shikona.name_ko   ← name_en 을 음역 (사람이 넣은 값은 건드리지 않는다)
    heya.name_ko      ← name_en 을 음역
    heya.name_ja      ← 표에 있는 한자 (모르면 비워 둔다)

**이미 값이 있는 행은 덮어쓰지 않는다.** 스프레드시트로 손수 고친 표기가
기계 음역에 지워지면 안 되기 때문이다.

한 번에 몰아서 보낸다
---------------------
처음에는 이름 하나마다 UPDATE 를 한 번씩 보냈다. Runner.execute() 는 호출
때마다 **새 접속을 연다.** 로컬 DB에서는 눈에 안 띄었지만 Supabase 처럼
인터넷 너머에 있는 DB 에서는 접속 + TLS 악수에 한 건당 0.2~0.5초가 들어서,
시코나 9천 건이면 30분을 훌쩍 넘겼다. 화면은 멈춘 것처럼 보인다.

그래서 CHUNK 건씩 묶어 UPDATE ... FROM (VALUES ...) 한 문장으로 보낸다.
접속 횟수가 9천 번에서 스무 번 아래로 줄어든다.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Callable, Iterable, Sequence

from .heya_names import japanese_for, romaji_for_ja
from .romaji import shikona_only, to_hangul
from .sqlrunner import Runner, SqlError

log = logging.getLogger("fill_names")

# 한 문장에 묶을 행 수. 너무 키우면 SQL 문장이 길어져 오히려 느려진다.
CHUNK = 500

FETCH_SHIKONA = """
SELECT id, name_en
FROM shikona
WHERE name_ko IS NULL AND name_en IS NOT NULL AND name_en <> ''
"""

# 이름에 공백이 있는 것 = 본명이 붙어 있을 수 있는 것
FETCH_SPACED = """
SELECT id, name_en, name_ko
FROM shikona
WHERE name_ko LIKE '% %' AND name_en IS NOT NULL AND name_en <> ''
"""

FETCH_HEYA = """
SELECT id, name_en, name_ja, name_ko
FROM heya
WHERE name_ko IS NULL OR name_ja IS NULL
"""

# UPDATE ... FROM (VALUES ...) — 한 번에 여러 행을 고친다.
# 조건에 'IS NULL' 을 남겨 두는 것이 중요하다. 이 문장이 도는 사이에 사람이
# 값을 넣었더라도 덮어쓰지 않는다.
BULK = """
UPDATE {table} AS t
SET {column} = v.val
FROM (VALUES {values}) AS v(id, val)
WHERE t.id = v.id::bigint AND t.{column} IS NULL
"""


def _bulk_update(runner: Runner, table: str, column: str,
                 pairs: Sequence[tuple[Any, str]],
                 progress: Callable[[int], None] | None = None) -> int:
    """(id, 값) 쌍을 CHUNK 건씩 묶어 갱신한다. 고친 행 수를 돌려준다."""
    done = 0
    for i in range(0, len(pairs), CHUNK):
        part = pairs[i:i + CHUNK]
        values = ", ".join(["(%s, %s)"] * len(part))
        params: list[Any] = []
        for pid, val in part:
            params.extend([pid, val])
        runner.execute(
            BULK.format(table=table, column=column, values=values), params)
        done += len(part)
        if progress:
            progress(done)
    return done


REPAIR = """
UPDATE shikona AS t
SET name_ko = v.val
FROM (VALUES {values}) AS v(id, val)
WHERE t.id = v.id::bigint
"""


def _bulk_repair(runner: Runner, pairs: Sequence[tuple[Any, str]]) -> int:
    """이미 있는 값을 고쳐 쓴다 (IS NULL 조건 없이)."""
    done = 0
    for i in range(0, len(pairs), CHUNK):
        part = pairs[i:i + CHUNK]
        values = ", ".join(["(%s, %s)"] * len(part))
        params: list[Any] = []
        for pid, val in part:
            params.extend([pid, val])
        runner.execute(REPAIR.format(values=values), params)
        done += len(part)
    return done


def fill(runner: Runner, *, verbose: bool = True,
         on_progress: Callable[[str, int, int], None] | None = None
         ) -> dict[str, int]:
    """비어 있는 표기를 채운다.

    on_progress(단계, 끝난 수, 전체 수) 로 진행 상황을 알린다 — 수천 건이
    도는 동안 화면이 멈춘 것처럼 보이지 않게 하기 위한 것이다.
    """
    stats = {"shikona_ko": 0, "shikona_fixed": 0,
             "heya_ko": 0, "heya_ja": 0, "heya_unknown": 0}

    def report(stage: str, done: int, total: int) -> None:
        if on_progress:
            on_progress(stage, done, total)

    # --- 시코나 ---------------------------------------------------------
    rows = runner.query(FETCH_SHIKONA)
    pairs = [(sid, ko) for sid, name_en in rows
             if (ko := to_hangul(shikona_only(name_en)))]
    report("시코나", 0, len(pairs))
    if pairs:
        stats["shikona_ko"] = _bulk_update(
            runner, "shikona", "name_ko", pairs,
            lambda n: report("시코나", n, len(pairs)))

    # --- 이미 넣어 둔 값 중 본명이 붙은 것 고치기 -----------------------
    #  예전 판은 'Terunofuji Haruo' 를 통째로 옮겨 '테루노후지 하루오' 로 넣었다.
    #  **기계가 넣은 값일 때만** 고친다 — 사람이 손으로 고친 이름은 건드리지 않는다.
    #  (옛 규칙으로 만든 값과 정확히 같을 때만 기계가 넣은 것으로 본다)
    fix: list[tuple[Any, str]] = []
    for sid, name_en, old in runner.query(FETCH_SPACED):
        if old != to_hangul(name_en):          # 사람이 고친 값 — 그대로 둔다
            continue
        new = to_hangul(shikona_only(name_en))
        if new and new != old:
            fix.append((sid, new))
    if fix:
        stats["shikona_fixed"] = _bulk_repair(runner, fix)

    # --- 헤야 -----------------------------------------------------------
    ko_pairs: list[tuple[Any, str]] = []
    ja_pairs: list[tuple[Any, str]] = []
    unknown: list[str] = []
    for hid, name_en, name_ja, name_ko in runner.query(FETCH_HEYA):
        if not name_ko:
            # 영문이 없으면 한자에서 로마자를 되찾아 음역한다
            ko = to_hangul(name_en or romaji_for_ja(name_ja) or "")
            if ko:
                ko_pairs.append((hid, ko))
        if not name_ja and name_en:
            ja = japanese_for(name_en)
            if ja:
                ja_pairs.append((hid, ja))
            else:
                unknown.append(str(name_en))
                stats["heya_unknown"] += 1

    if ko_pairs:
        stats["heya_ko"] = _bulk_update(runner, "heya", "name_ko", ko_pairs)
    if ja_pairs:
        stats["heya_ja"] = _bulk_update(runner, "heya", "name_ja", ja_pairs)
    report("헤야", len(ko_pairs), len(ko_pairs))

    if verbose:
        log.info("시코나 한국어 %d건 (본명 정리 %d건) · 헤야 한국어 %d건 · 헤야 한자 %d건",
                 stats["shikona_ko"], stats["shikona_fixed"],
                 stats["heya_ko"], stats["heya_ja"])
        if unknown:
            log.info("한자를 모르는 헤야 %d곳 (한국어만 표시됩니다): %s",
                     len(unknown), ", ".join(sorted(set(unknown))[:12]))
            log.info("  → pyxisumo/heya_names.py 의 표에 추가하면 채워집니다")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="비어 있는 표기 채우기")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.dsn:
        print("DATABASE_URL 이 없습니다.", file=sys.stderr)
        return 2

    def show(stage: str, done: int, total: int) -> None:
        if total:
            print(f"    {stage} {done:,}/{total:,}", flush=True)

    try:
        fill(Runner(args.dsn), on_progress=show)
    except SqlError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
