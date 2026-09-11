"""Sumo-API → Postgres 수집 배치.

    python -m pyxisumo.ingest bootstrap --from 201801 --to 202609
    python -m pyxisumo.ingest basho --basho 202609            # 반즈케만
    python -m pyxisumo.ingest live  --basho 202609            # 장중 결과 갱신
    python -m pyxisumo.ingest kimarite

모든 쓰기는 멱등하다 — cron 이 겹쳐 뜨거나 재실행돼도 결과가 같다.
자체 Postgres 를 정본으로 두고 API 는 갱신용으로만 쓴다 (설계서 九장).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from typing import Any, Iterable

from . import checkpoint, db, fieldmap
from .ranks import RankParseError, normalize_division, normalize_side, parse_rank
from .sumoapi import SumoApi, pick, rows_of

log = logging.getLogger("ingest")

DIVISIONS_SEKITORI = ("Makuuchi", "Juryo")
DIVISIONS_FULL = ("Makuuchi", "Juryo", "Makushita")


class IngestError(RuntimeError):
    """수집 결과가 명백히 잘못됐을 때. 조용히 넘어가면 안 되는 상황."""


# ---------------------------------------------------------------------
#  유틸
# ---------------------------------------------------------------------
def slugify(name: str) -> str:
    """헤야 영문명 → slug. 'Isegahama' → 'isegahama'."""
    s = unicodedata.normalize("NFKD", str(name or "")).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


def as_int(v: Any, default: int | None = None) -> int | None:
    if v is None or v == "":
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def as_num(v: Any) -> float | None:
    if v in (None, "", 0):
        return None if v in (None, "") else 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def as_basho_id(v: Any) -> str | None:
    """'2026.09', '202609', '2026-09' → '202609'."""
    if v in (None, ""):
        return None
    digits = re.sub(r"\D", "", str(v))
    return digits[:6] if len(digits) >= 6 else None


def as_date(v: Any) -> str | None:
    if v in (None, ""):
        return None
    s = str(v)
    m = re.match(r"(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_record(row: dict) -> tuple[int, int, int]:
    """승/패/휴장. 분리 필드가 있으면 그걸 쓰고, 없으면 'record' 문자열을 판다."""
    w = as_int(pick(row, "wins", required=False))
    l = as_int(pick(row, "losses", required=False))
    a = as_int(pick(row, "absences", required=False), 0)
    if w is not None and l is not None:
        return w, l, a or 0

    rec = pick(row, "record", required=False)
    if isinstance(rec, dict):
        return (
            as_int(rec.get("wins"), 0) or 0,
            as_int(rec.get("losses"), 0) or 0,
            as_int(rec.get("absences"), 0) or 0,
        )
    if isinstance(rec, str):
        nums = [int(x) for x in re.findall(r"\d+", rec)]
        if len(nums) >= 2:
            return nums[0], nums[1], (nums[2] if len(nums) > 2 else 0)
    if isinstance(rec, list):
        # 일별 결과 배열 ['win','loss','absent', ...]
        wins = sum(1 for x in rec if str(x).lower().startswith(("w", "○", "勝")))
        losses = sum(1 for x in rec if str(x).lower().startswith(("l", "●", "負")))
        absences = sum(1 for x in rec if str(x).lower().startswith(("a", "k", "休")))
        return wins, losses, absences
    return 0, 0, 0


def side_of(row: dict, rank_obj) -> str:
    """반즈케 응답이 east/west 배열로 올 때 넣어둔 _side 를 우선한다."""
    if row.get("_side") in ("E", "W"):
        return row["_side"]
    raw = row.get("side") or row.get("Side")
    if raw:
        try:
            return normalize_side(raw)
        except RankParseError:
            pass
    return rank_obj.side


# ---------------------------------------------------------------------
#  수집 단계
# ---------------------------------------------------------------------
def ingest_kimarite(api: SumoApi, conn: Any) -> int:
    rows = rows_of(api.kimarite())
    payload = []
    for r in rows:
        code = r.get("kimarite") or r.get("code") or r.get("name")
        if not code:
            continue
        payload.append((
            str(code).strip().lower(),
            r.get("nameJp") or r.get("name_ja") or r.get("kanji"),
            r.get("nameEn") or r.get("name_en") or str(code),
            r.get("category") or r.get("type"),
        ))
    n = db.executemany(conn, db.UPSERT_KIMARITE, payload)
    log.info("kimarite: %d건", n)
    return n


def ingest_rikishis(api: SumoApi, conn: Any, *, include_retired: bool = True) -> int:
    heya_rows: dict[str, tuple] = {}
    rikishi_rows: list[tuple] = []
    shikona_rows: list[tuple] = []

    for r in api.iter_rikishis(intai=str(include_retired).lower()):
        rid = as_int(pick(r, "rikishi_id"))
        if rid is None:
            continue

        heya_en = pick(r, "heya", required=False)
        slug = slugify(heya_en) if heya_en else None
        if slug and slug not in heya_rows:
            heya_rows[slug] = (slug, None, str(heya_en), None)

        debut = as_basho_id(pick(r, "debut", required=False))
        retired = as_basho_id(pick(r, "retired", required=False))

        rikishi_rows.append((
            rid,
            as_date(pick(r, "birth_date", required=False)),
            pick(r, "shusshin", required=False),
            as_num(pick(r, "height", required=False)),
            as_num(pick(r, "weight", required=False)),
            slug,
            debut,
            retired,
        ))
        name_ja = pick(r, "shikona_ja", required=False)
        name_en = pick(r, "shikona_en", required=False)
        if name_ja or name_en:
            shikona_rows.append((
                rid,
                debut or "000000",
                retired,
                name_ja,
                r.get("shikonaKana") or r.get("shikona_kana"),
                name_en,
            ))
        else:
            log.warning("리키시 %s: 시코나가 없어 건너뜁니다", rid)

    db.executemany(conn, db.UPSERT_HEYA, list(heya_rows.values()))
    db.executemany(conn, db.UPSERT_RIKISHI, rikishi_rows)
    db.executemany(conn, db.UPSERT_SHIKONA, shikona_rows)
    log.info("rikishi: %d명, heya: %d개", len(rikishi_rows), len(heya_rows))
    return len(rikishi_rows)


def ingest_basho_meta(api: SumoApi, conn: Any, basho_id: str) -> None:
    data = api.basho(basho_id)
    if not isinstance(data, dict):
        log.warning("basho %s: 메타 없음", basho_id)
        return
    db.executemany(conn, db.UPSERT_BASHO, [(
        basho_id,
        data.get("name") or data.get("nameJp"),
        as_date(pick(data, "start_date", required=False)),
        as_date(pick(data, "end_date", required=False)),
    )])


def ingest_banzuke(
    api: SumoApi, conn: Any, basho_id: str, divisions: Iterable[str] = DIVISIONS_SEKITORI
) -> int:
    total = 0
    for div in divisions:
        rows = rows_of(api.banzuke(basho_id, div))
        payload, skipped = [], 0
        for r in rows:
            rid = as_int(pick(r, "rikishi_id", required=False))
            if rid is None:
                skipped += 1
                continue
            rank_raw = pick(r, "rank", required=False)
            try:
                rank = parse_rank(rank_raw, division_hint=div)
            except RankParseError as e:
                # 조용히 넘기지 않는다 — 반즈케가 통째로 틀어진다
                log.error("지위 해석 실패 (%s, rikishi=%s): %s", basho_id, rid, e)
                skipped += 1
                continue
            w, l, a = parse_record(r)
            payload.append((
                basho_id, rid,
                rank.division, rank.kind, rank.num, side_of(r, rank),
                str(rank_raw), w, l, a,
            ))
        db.executemany(conn, db.UPSERT_BANZUKE, payload)
        total += len(payload)
        log.info("banzuke %s/%s: %d건 적재, %d건 건너뜀", basho_id, div, len(payload), skipped)

        # 행은 받았는데 한 건도 못 넣었다면 해석이 틀린 것이다.
        # 조용히 0건으로 '완료' 처리하면 반즈케가 통째로 빈 채 설치가 끝난다.
        if rows and not payload:
            raise IngestError(
                f"{basho_id}/{div}: {len(rows)}행을 받았지만 한 건도 해석하지 못했습니다. "
                f"실제 키: {sorted(rows[0].keys())} — "
                f"sumoapi.FIELD_ALIASES 의 rikishi_id / rank 를 확인하세요"
            )
    return total


def ingest_torikumi(
    api: SumoApi,
    conn: Any,
    basho_id: str,
    days: Iterable[int] = range(1, 16),
    divisions: Iterable[str] = DIVISIONS_SEKITORI,
) -> int:
    total = 0
    for div in divisions:
        for day in days:
            rows = rows_of(api.torikumi(basho_id, div, day))
            payload = []
            unmapped = 0
            for i, r in enumerate(rows, start=1):
                east = as_int(pick(r, "east_id", required=False))
                west = as_int(pick(r, "west_id", required=False))
                if east is None and west is None:
                    # 행은 왔는데 대전자 항목을 못 찾은 것 — 조용히 넘기면
                    # 취조 테이블이 통째로 비는데 아무도 눈치채지 못한다
                    unmapped += 1
                    continue
                winner = as_int(pick(r, "winner_id", required=False))
                kim = pick(r, "kimarite", required=False)
                kim = str(kim).strip().lower() if kim else None
                payload.append((
                    basho_id, day, normalize_division(div),
                    as_int(pick(r, "match_no", required=False), i) or i,
                    east, west, winner,
                    kim if kim and kim not in ("fusen", "fusensho", "fusenpai") else None,
                    bool(kim and str(kim).startswith("fusen")),
                ))
            if unmapped and not payload:
                log.warning(
                    "torikumi %s/%s %d일차: %d행을 받았지만 대전자 항목을 찾지 못했습니다. "
                    "실제 키: %s — sumoapi.FIELD_ALIASES 의 east_id/west_id 를 확인하세요",
                    basho_id, div, day, unmapped, sorted(rows[0].keys()))

            # 용어집에 없는 기술 코드를 먼저 등록한다 (외래키 위반 방지)
            codes = {p[7] for p in payload if p[7]}
            if codes:
                db.executemany(conn, db.UPSERT_KIMARITE_STUB,
                               [(c, c.replace("-", " ").title()) for c in sorted(codes)])

            db.executemany(conn, db.UPSERT_TORIKUMI, payload)
            total += len(payload)
    log.info("torikumi %s: %d건", basho_id, total)
    return total


def basho_ids_between(start: str, end: str) -> list[str]:
    """본바쇼는 홀수월(1,3,5,7,9,11)에만 열린다."""
    out = []
    y, m = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    while (y, m) <= (ey, em):
        if m % 2 == 1:
            out.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ---------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sumo-API → Postgres 수집")
    ap.add_argument("command",
                    choices=["bootstrap", "basho", "live", "kimarite", "rikishi"])
    ap.add_argument("--basho", help="바쇼 ID (YYYYMM)")
    ap.add_argument("--from", dest="from_basho", default="201801")
    ap.add_argument("--to", dest="to_basho", default=None)
    ap.add_argument("--days", default="1-15", help="'1-15' 또는 '3'")
    ap.add_argument("--with-makushita", action="store_true",
                    help="마쿠시타까지 수집 (쥬료 승격 후보 예측에 필요)")
    ap.add_argument("--force", action="store_true",
                    help="체크포인트를 무시하고 이미 끝난 단위도 다시 받는다")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    api = SumoApi()
    divs = DIVISIONS_FULL if args.with_makushita else DIVISIONS_SEKITORI

    if "-" in args.days:
        lo, hi = args.days.split("-", 1)
        days = range(int(lo), int(hi) + 1)
    else:
        days = [int(args.days)]

    with db.connect() as conn:
        # probe 가 학습해 둔 필드 대응을 적용한다 (없으면 기본 후보로 진행)
        n = fieldmap.autoload(conn)
        if n:
            log.debug("학습된 필드 대응 %d건 적용", n)

        if args.command == "kimarite":
            ingest_kimarite(api, conn)

        elif args.command == "rikishi":
            ingest_rikishis(api, conn)

        elif args.command == "basho":
            if not args.basho:
                ap.error("--basho 가 필요합니다")
            ingest_basho_meta(api, conn, args.basho)
            ingest_banzuke(api, conn, args.basho, divs)

        elif args.command == "live":
            if not args.basho:
                ap.error("--basho 가 필요합니다")
            # 장중: 반즈케(성적 포함) + 당일 취조만 갱신한다
            ingest_banzuke(api, conn, args.basho, DIVISIONS_SEKITORI)
            ingest_torikumi(api, conn, args.basho, days, DIVISIONS_SEKITORI)

        elif args.command == "bootstrap":
            bootstrap(api, conn, args.from_basho,
                      args.to_basho or args.from_basho, divs,
                      force=args.force)

        conn.commit()
    return 0


def bootstrap(
    api: SumoApi,
    conn: Any,
    from_basho: str,
    to_basho: str,
    divisions: Iterable[str] = DIVISIONS_SEKITORI,
    *,
    force: bool = False,
    on_progress: Any = None,
) -> dict[str, int]:
    """초기 전량 적재. 체크포인트로 중단 지점부터 재개한다.

    바쇼 하나가 끝날 때마다 커밋하고 기록하므로, 네트워크가 끊기거나
    Actions 러너가 죽어도 다시 돌리면 끝난 바쇼는 건너뛴다.
    """
    stats = {"skipped": 0, "basho": 0, "banzuke_rows": 0, "torikumi_rows": 0,
             "optional_failed": []}

    # 키마리테는 기술 용어집이다 — 없어도 반즈케와 예측은 돌아간다.
    # 없어서는 안 되는 것(리키시·반즈케)과 구분해, 실패해도 멈추지 않는다.
    try:
        with checkpoint.step(conn, "reference", "kimarite", force=force) as s:
            if not s.skip:
                s.rows = ingest_kimarite(api, conn)
                conn.commit()
    except Exception as e:                            # noqa: BLE001
        log.warning("키마리테 용어집을 받지 못했습니다 (%s). "
                    "대전 기술 이름만 비고 나머지는 정상 진행합니다.", e)
        stats["optional_failed"].append(f"kimarite: {e}")

    with checkpoint.step(conn, "reference", "rikishi", force=force) as s:
        if not s.skip:
            s.rows = ingest_rikishis(api, conn)
            conn.commit()

    ids = basho_ids_between(from_basho, to_basho)
    done = checkpoint.completed(conn, "basho")
    log.info("대상 바쇼 %d개 (완료 %d개 건너뜀)",
             len(ids), len([b for b in ids if b in done]))

    for i, bid in enumerate(ids, start=1):
        with checkpoint.step(conn, "basho", bid, force=force) as s:
            if s.skip:
                stats["skipped"] += 1
                continue
            log.info("[%d/%d] %s 수집 중…", i, len(ids), bid)
            ingest_basho_meta(api, conn, bid)
            n_b = ingest_banzuke(api, conn, bid, divisions)
            n_t = ingest_torikumi(api, conn, bid, range(1, 16), DIVISIONS_SEKITORI)
            conn.commit()
            s.rows = n_b + n_t
            stats["basho"] += 1
            stats["banzuke_rows"] += n_b
            stats["torikumi_rows"] += n_t
        if on_progress:
            on_progress(i, len(ids), bid, stats)

    return stats


if __name__ == "__main__":
    sys.exit(main())
