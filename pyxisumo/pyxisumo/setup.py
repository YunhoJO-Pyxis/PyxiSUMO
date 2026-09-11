"""초기설정 자동화.

    python -m pyxisumo.setup init                    # 전 과정 한 번에
    python -m pyxisumo.setup init --from 201801      # 적재 범위 지정
    python -m pyxisumo.setup doctor                  # 현재 상태 점검
    python -m pyxisumo.setup resume                  # 중단된 적재 이어받기
    python -m pyxisumo.setup retry-failed            # 실패한 단위만 재시도

init 은 다음을 순서대로 한다. 각 단계는 재실행해도 안전하다.

    1. 환경 점검      파이썬/드라이버/psql, DATABASE_URL 접속
    2. 마이그레이션   db/*.sql 순서대로 적용 + 체크섬 기록
    3. 필드맵 학습    Sumo-API 실제 응답에서 필드 대응 추론 → DB 저장
    4. 참조 데이터    바쇼 일정·헤야·뉴스 소스 정책(002 시드에 포함)
    5. 적재           체크포인트 기반, 중단되면 이어받기
    6. 검증           행 수·용량·무결성 점검 후 리포트
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

from . import checkpoint, fieldmap, migrate
from .sqlrunner import Runner, SqlError, backend_name

SUPABASE_FREE_BYTES = 500 * 1024 * 1024


# ---------------------------------------------------------------------
#  출력
# ---------------------------------------------------------------------
def h1(s: str) -> None:
    print(f"\n\033[1m{s}\033[0m")
    print("─" * 66)


def ok(s: str) -> None:
    print(f"  \033[32m✓\033[0m {s}")


def warn(s: str) -> None:
    print(f"  \033[33m!\033[0m {s}")


def bad(s: str) -> None:
    print(f"  \033[31m✗\033[0m {s}")


def say(s: str = "") -> None:
    print(f"    {s}" if s else "")


def human_bytes(n: int | float | None) -> str:
    if not n:
        return "0 B"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


@dataclass
class Result:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.problems)


# ---------------------------------------------------------------------
#  1. 환경 점검
# ---------------------------------------------------------------------
def check_env(dsn: str | None, res: Result) -> Runner | None:
    h1("1. 환경 점검")

    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        ok(f"Python {major}.{minor}")
    else:
        bad(f"Python {major}.{minor} — 3.10 이상이 필요합니다")
        res.problems.append("python<3.10")

    backend = backend_name()
    if backend == "psycopg":
        ok("psycopg 드라이버")
    elif backend == "psql":
        warn("psycopg 이 없어 psql 로 진행합니다. "
             "적재를 하려면 pip install -r requirements.txt 가 필요합니다")
        res.warnings.append("no-psycopg")
    else:
        bad("psycopg 도 psql 도 없습니다 — pip install -r requirements.txt")
        res.problems.append("no-sql-backend")
        return None

    if not dsn:
        bad("DATABASE_URL 이 비어 있습니다. .env.example 를 참고해 설정하세요")
        res.problems.append("no-dsn")
        return None

    safe = dsn
    if "@" in dsn:
        head, tail = dsn.split("@", 1)
        if ":" in head:
            safe = head.rsplit(":", 1)[0] + ":***@" + tail
    ok(f"DATABASE_URL = {safe}")

    if dsn.startswith("postgres") and "sslmode" not in dsn and "localhost" not in dsn:
        warn("sslmode 가 지정되지 않았습니다. Supabase 는 ?sslmode=require 를 권장합니다")
        res.warnings.append("no-sslmode")

    try:
        runner = Runner(dsn)
        version = runner.ping()
        ok(f"접속 성공 — {version.split(',')[0]}")
        return runner
    except SqlError as e:
        bad(f"접속 실패: {e}")
        res.problems.append("connect-failed")
        return None


# ---------------------------------------------------------------------
#  2. 마이그레이션
# ---------------------------------------------------------------------
def run_migrations(runner: Runner, res: Result) -> None:
    h1("2. 스키마 마이그레이션")
    try:
        n = migrate.up(runner, verbose=False)
    except SqlError as e:
        bad(f"실패: {e}")
        res.problems.append("migration-failed")
        return
    applied = migrate.applied(runner)
    for m in migrate.discover():
        state = "적용됨" if m.filename in applied else "미적용"
        ok(f"{m.filename:<28}{state}")
    if n:
        ok(f"이번에 {n}건 새로 적용")
    else:
        ok("이미 최신 상태")


# ---------------------------------------------------------------------
#  3. 필드맵 학습
# ---------------------------------------------------------------------
def learn_fieldmap(res: Result, *, basho: str, skip: bool = False) -> dict[str, str]:
    h1("3. Sumo-API 필드 대응 학습")
    if skip:
        warn("--skip-probe 지정 — 저장된 대응을 그대로 씁니다")
        return {}

    try:
        from . import db as dbmod
        from .probe import run_probe
    except ImportError as e:                          # noqa: BLE001
        bad(f"모듈 로드 실패: {e}")
        res.problems.append("probe-import")
        return {}

    try:
        mapping, unresolved, report = run_probe(basho=basho, verbose=False)
    except Exception as e:                            # noqa: BLE001
        bad(f"API 호출 실패: {e}")
        warn("네트워크나 API 상태를 확인한 뒤 다시 실행하세요")
        res.problems.append("probe-failed")
        return {}

    for logical, key in sorted(mapping.items()):
        ok(f"{logical:<14} → {key}")

    # 일부가 미해결이어도 배운 것은 먼저 저장한다 — 다시 실행할 때 중복 학습을 피한다
    empty_eps = [
        name for name, r in report.items()
        if isinstance(r, dict) and r.get("empty")
    ]
    for name in empty_eps:
        warn(f"{name}: 응답이 비어 있어 학습하지 못했습니다 "
             f"(해당 데이터가 아직 없는 시점일 수 있습니다)")
        res.warnings.append(f"probe-empty:{name}")

    if unresolved:
        # 핵심 데이터(리키시·반즈케)가 아니면 멈추지 않는다.
        # 취조(대전 기록)는 아카이브용이고 반즈케 예측에는 쓰이지 않는다.
        blocking = set(report.get("_blocking_unresolved") or [])
        for f in unresolved:
            (bad if f in blocking else warn)(
                f"{f:<14} 미해결"
                + ("" if f in blocking else " — 대전 기록만 빠집니다. 진행합니다"))
        say()
        say("실제 응답 모양입니다. 이대로 알려주시면 고쳐드릴 수 있습니다:")
        for name, r in report.items():
            if not (isinstance(r, dict) and r.get("missing_required")):
                continue
            src = f" [{r.get('source')}]" if r.get("source") else ""
            if r.get("envelope"):
                say(f"  {name}{src}: 바깥 키 {r.get('outer_keys')} · "
                    f"목록 키 {r.get('envelope')}  (봉투를 못 벗김)")
            else:
                say(f"  {name}{src}: {r.get('keys')}")
        if blocking:
            res.problems.append("fieldmap-unresolved")
        else:
            res.warnings.append("fieldmap-partial")

    fieldmap.save_local(mapping)
    ok(f"로컬 캐시 저장 — {fieldmap.CACHE_PATH}")
    try:
        with dbmod.connect() as conn:
            fieldmap.save_db(conn, mapping)
        ok("DB(app_setting) 저장 — Actions 러너도 같은 대응을 씁니다")
    except Exception as e:                            # noqa: BLE001
        warn(f"DB 저장 생략: {e}")
        res.warnings.append("fieldmap-db-save")
    return mapping


# ---------------------------------------------------------------------
#  5. 적재
# ---------------------------------------------------------------------
def _missing_makushita(conn: Any) -> list[str]:
    """마쿠시타 반즈케가 없는 바쇼 목록.

    없으면 쥬료 하위를 밀어낼 승격 후보가 존재하지 않아 예측이 구조적으로 틀린다.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT b.basho_id
            FROM banzuke_entry b
            WHERE b.division IN ('Makuuchi','Juryo')
              AND NOT EXISTS (
                SELECT 1 FROM banzuke_entry m
                WHERE m.basho_id = b.basho_id AND m.division = 'Makushita')
            ORDER BY 1
        """)
        return [r[0] for r in cur.fetchall()]


def _backfill_makushita(conn: Any, basho_ids: list[str]) -> int:
    """이미 받은 바쇼에 마쿠시타 반즈케만 덧붙인다 (전체 재적재 없이)."""
    from .ingest import ingest_banzuke
    from .sumoapi import SumoApi

    api = SumoApi()
    n = 0
    for k, bid in enumerate(basho_ids, start=1):
        try:
            n += ingest_banzuke(api, conn, bid, ("Makushita",))
            conn.commit()
        except Exception as e:                        # noqa: BLE001
            conn.rollback()
            warn(f"{bid} 마쿠시타 수집 실패: {e}")
        if k % 5 == 0 or k == len(basho_ids):
            print(f"    [{k}/{len(basho_ids)}] 마쿠시타 {n:,}행", flush=True)
    return n


def _heal_empty_banzuke_checkpoints(conn: Any) -> int:
    """'완료' 로 기록됐는데 반즈케가 비어 있는 바쇼의 기록을 지운다.

    예전 버전은 한 건도 해석하지 못해도 0건으로 '완료' 처리했다.
    그 기록이 남아 있으면 고친 뒤에도 영영 건너뛰게 된다.
    """
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM ingest_checkpoint c
            WHERE c.task = 'basho' AND c.status = 'done'
              AND NOT EXISTS (
                SELECT 1 FROM banzuke_entry b WHERE b.basho_id = c.item
              )
        """)
        n = cur.rowcount
    conn.commit()
    if n:
        warn(f"반즈케가 비어 있는데 완료로 기록된 바쇼 {n}개를 찾았습니다. "
             f"다시 받습니다.")
    return n


def run_ingest(
    res: Result, *, from_basho: str, to_basho: str, with_makushita: bool,
    force: bool = False,
) -> None:
    h1("5. 데이터 적재")
    try:
        from . import db as dbmod
        from .ingest import DIVISIONS_FULL, DIVISIONS_SEKITORI, bootstrap
        from .sumoapi import SumoApi
    except ImportError as e:                          # noqa: BLE001
        bad(f"드라이버가 없어 적재를 건너뜁니다: {e}")
        res.problems.append("ingest-import")
        return

    divs = DIVISIONS_FULL if with_makushita else DIVISIONS_SEKITORI
    started = time.time()
    last = [started]

    def progress(i: int, total: int, bid: str, stats: dict) -> None:
        now = time.time()
        if now - last[0] < 5 and i != total:
            return
        last[0] = now
        elapsed = now - started
        rate = i / elapsed if elapsed else 0
        eta = (total - i) / rate if rate else 0
        print(f"    [{i}/{total}] {bid}  "
              f"반즈케 {stats['banzuke_rows']:,} · 취조 {stats['torikumi_rows']:,} · "
              f"건너뜀 {stats['skipped']}  "
              f"남은 예상 {eta/60:.0f}분", flush=True)

    try:
        with dbmod.connect() as conn:
            fieldmap.autoload(conn)
            _heal_empty_banzuke_checkpoints(conn)

            if with_makushita:
                missing = _missing_makushita(conn)
                if missing:
                    warn(f"마쿠시타 반즈케가 없는 대회 {len(missing)}개를 찾았습니다.")
                    warn("  쥬료 승격 후보가 없으면 예측이 구조적으로 틀립니다. 채웁니다.")
                    _backfill_makushita(conn, missing)

            stats = bootstrap(SumoApi(), conn, from_basho, to_basho, divs,
                              force=force, on_progress=progress)
            fails = checkpoint.failed(conn)
    except Exception as e:                            # noqa: BLE001
        bad(f"적재 중단: {e}")
        warn("`python -m pyxisumo.setup resume` 로 이어받을 수 있습니다")
        res.problems.append("ingest-failed")
        return

    for msg in stats.get("optional_failed") or []:
        warn(f"선택 데이터 실패 — {msg}")
        warn("  핵심 데이터에는 영향이 없습니다. "
             "`5_실패한것만다시받기` 로 나중에 재시도할 수 있습니다.")
        res.warnings.append("optional-data")

    ok(f"바쇼 {stats['basho']}개 적재 · {stats['skipped']}개 건너뜀")
    ok(f"반즈케 {stats['banzuke_rows']:,}행 · 취조 {stats['torikumi_rows']:,}행")
    ok(f"소요 {(time.time()-started)/60:.1f}분")

    if fails:
        for task, item, err in fails[:10]:
            warn(f"실패 {task}/{item}: {err[:80]}")
        warn("`python -m pyxisumo.setup retry-failed` 로 재시도하세요")
        res.warnings.append("ingest-partial")


# ---------------------------------------------------------------------
#  6. 검증
# ---------------------------------------------------------------------
# (라벨, SQL, 치명적인가)
#   치명적    = 데이터가 잘못 들어간 것. 고치지 않으면 예측이 틀어진다.
#   비치명적  = 적재가 덜 됐을 뿐일 수 있다. 알려만 준다.
CHECKS: list[tuple[str, str, bool]] = [
    ("같은 슬롯에 두 명이 배치된 바쇼",
     "SELECT count(*) FROM (SELECT basho_id, rank_value FROM banzuke_entry "
     "GROUP BY 1,2 HAVING count(*) > 1) t", True),
    ("승패합이 16 이상인 성적",
     "SELECT count(*) FROM banzuke_entry WHERE wins + losses + absences > 15", True),
    ("승자가 대전자가 아닌 취조",
     "SELECT count(*) FROM torikumi WHERE winner_id IS NOT NULL "
     "AND winner_id NOT IN (COALESCE(east_id,-1), COALESCE(west_id,-1))", True),
    ("시코나가 없는 리키시",
     "SELECT count(*) FROM rikishi r WHERE NOT EXISTS "
     "(SELECT 1 FROM shikona s WHERE s.rikishi_id = r.id)", True),
    ("마쿠우치가 43명 이상인 바쇼",
     "SELECT count(*) FROM (SELECT basho_id FROM banzuke_entry "
     "WHERE division = 'Makuuchi' GROUP BY 1 HAVING count(*) > 42) t", True),
    ("마쿠우치가 42명에 못 미치는 바쇼(적재 누락 가능)",
     "SELECT count(*) FROM (SELECT basho_id FROM banzuke_entry "
     "WHERE division = 'Makuuchi' GROUP BY 1 HAVING count(*) < 42) t", False),
    ("쥬료가 28명이 아닌 바쇼",
     "SELECT count(*) FROM (SELECT basho_id FROM banzuke_entry "
     "WHERE division = 'Juryo' GROUP BY 1 HAVING count(*) <> 28) t", False),
]


def verify(runner: Runner, res: Result) -> None:
    h1("6. 검증")
    cols = [
        "rikishi_rows", "heya_rows", "shikona_rows", "basho_rows", "banzuke_rows",
        "torikumi_rows", "kimarite_rows", "prediction_runs", "shikona_ko_rows",
        "ckpt_done", "ckpt_failed", "latest_banzuke", "field_map", "db_bytes",
    ]
    # SELECT * 로 받으면 뷰의 컬럼 순서가 바뀔 때 조용히 어긋난다. 명시한다.
    try:
        row = runner.query(f"SELECT {', '.join(cols)} FROM v_setup_status")
    except SqlError as e:
        bad(f"v_setup_status 를 읽지 못했습니다: {e}")
        res.problems.append("no-status-view")
        return
    if not row:
        bad("v_setup_status 가 비어 있습니다")
        res.problems.append("no-status-view")
        return
    st = dict(zip(cols, row[0]))

    def n(key: str) -> int:
        try:
            return int(st.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    print(f"    리키시 {n('rikishi_rows'):>9,}    헤야     {n('heya_rows'):>6,}")
    print(f"    시코나 {n('shikona_rows'):>9,}    바쇼     {n('basho_rows'):>6,}")
    print(f"    반즈케 {n('banzuke_rows'):>9,}    키마리테 {n('kimarite_rows'):>6,}")
    print(f"    취조   {n('torikumi_rows'):>9,}    예측     {n('prediction_runs'):>6,}")
    print(f"    최신 반즈케: {st.get('latest_banzuke') or '없음'}")
    print()

    if n("banzuke_rows") == 0:
        bad("반즈케가 비어 있습니다 — 적재가 되지 않았습니다")
        res.problems.append("empty-banzuke")
    else:
        ok(f"반즈케 {n('banzuke_rows'):,}행")

    if n("ckpt_failed"):
        warn(f"실패한 적재 단위 {n('ckpt_failed')}개 — retry-failed 로 재시도")
        res.warnings.append("ckpt-failed")

    if not st.get("field_map"):
        warn("필드 대응이 저장되어 있지 않습니다 (probe 미실행)")
        res.warnings.append("no-fieldmap")

    if n("shikona_ko_rows") == 0:
        warn("한국어 시코나 표기가 0건입니다 — sync_sheets 로 채우세요")

    # 무결성
    for label, sql, fatal in CHECKS:
        try:
            cnt = int(runner.scalar(sql) or 0)
        except SqlError as e:
            warn(f"{label}: 점검 실패 ({e})")
            continue
        if not cnt:
            ok(f"{label}: 없음")
        elif fatal:
            bad(f"{label}: {cnt}건")
            res.problems.append(f"integrity:{label}")
        else:
            warn(f"{label}: {cnt}건")
            res.warnings.append(f"partial:{label}")

    # 용량
    size = n("db_bytes")
    pct = size / SUPABASE_FREE_BYTES * 100
    line = f"DB 용량 {human_bytes(size)} — 무료 티어 500MB의 {pct:.0f}%"
    if pct >= 80:
        bad(line + " · 뉴스 본문을 저장하고 있지 않은지 확인하세요")
        res.problems.append("db-size")
    elif pct >= 50:
        warn(line)
        res.warnings.append("db-size")
    else:
        ok(line)


# ---------------------------------------------------------------------
#  명령
# ---------------------------------------------------------------------
def fill_display_names(runner: Runner, res: "Result", *, step: str = "6") -> None:
    """한국어 표기가 비어 있으면 로마자에서 만들어 채운다.

    API 는 시코나와 헤야를 영문으로도 주기 때문에, 이 단계를 건너뛰면
    한국어 페이지에 'Hoshoryu' 와 'Nishonoseki' 가 그대로 나온다.
    이미 값이 있는 행은 절대 덮어쓰지 않는다.
    """
    h1(f"{step}. 한국어·일본어 표기 채우기" if step else "한국어·일본어 표기 채우기")
    say("  (선수 이름이 수천 건이면 조금 걸립니다 — 진행 상황을 함께 보여드립니다)")
    try:
        from .fill_names import fill

        def progress(stage: str, done: int, total: int) -> None:
            if total:
                say(f"  {stage} {done:,}/{total:,}")

        st = fill(runner, verbose=False, on_progress=progress)
    except Exception as exc:                      # 표기는 부가 기능 — 막지 않는다
        warn(f"표기 채우기를 건너뜁니다: {exc}")
        res.problems.append("fill-names")
        return
    ok(f"선수 이름 {st['shikona_ko']}건 · 헤야 한국어 {st['heya_ko']}건 · "
       f"헤야 한자 {st['heya_ja']}건")
    if st["heya_unknown"]:
        warn(f"한자를 모르는 헤야 {st['heya_unknown']}곳 — 한국어만 표시됩니다")


def cmd_init(args) -> int:
    res = Result()
    runner = check_env(args.dsn, res)
    if runner is None:
        summary(res)
        return 1

    run_migrations(runner, res)
    if res.failed:
        summary(res)
        return 1

    learn_fieldmap(res, basho=args.probe_basho, skip=args.skip_probe)
    if res.failed:
        summary(res)
        return 1

    h1("4. 참조 데이터")
    ok("바쇼 일정·헤야 채널·뉴스 소스 정책은 002 마이그레이션에 포함되어 적용됨")
    cnt = runner.scalar("SELECT count(*) FROM basho")
    ok(f"바쇼 {cnt}건 · 헤야 "
       f"{runner.scalar('SELECT count(*) FROM heya')}건 · 뉴스 소스 "
       f"{runner.scalar('SELECT count(*) FROM news_source')}건")

    if not args.skip_ingest:
        run_ingest(res, from_basho=args.from_basho, to_basho=args.to_basho,
                   with_makushita=args.with_makushita, force=args.force)
    else:
        h1("5. 데이터 적재")
        warn("--skip-ingest 지정 — 건너뜁니다")

    fill_display_names(runner, res)
    verify(runner, res)
    summary(res)
    return 1 if res.failed else 0


def cmd_doctor(args) -> int:
    res = Result()
    runner = check_env(args.dsn, res)
    if runner is None:
        summary(res)
        return 1
    h1("2. 스키마 마이그레이션")
    migrate.status(runner)
    verify(runner, res)
    summary(res)
    return 1 if res.failed else 0


def cmd_resume(args) -> int:
    res = Result()
    runner = check_env(args.dsn, res)
    if runner is None:
        return 1
    run_ingest(res, from_basho=args.from_basho, to_basho=args.to_basho,
               with_makushita=args.with_makushita)
    fill_display_names(runner, res)
    verify(runner, res)
    summary(res)
    return 1 if res.failed else 0


def cmd_retry_failed(args) -> int:
    from . import db as dbmod

    with dbmod.connect() as conn:
        fails = checkpoint.failed(conn)
        if not fails:
            print("실패한 단위가 없습니다.")
            return 0
        print(f"실패 {len(fails)}건을 초기화하고 다시 받습니다:")
        for task, item, err in fails:
            print(f"  {task}/{item}: {err[:70]}")
        checkpoint.reset(conn, only_failed=True)
    return cmd_resume(args)


def cmd_reset(args) -> int:
    from . import db as dbmod

    if not args.yes:
        print("체크포인트를 모두 지웁니다. 데이터는 지우지 않습니다.")
        print("정말 진행하려면 --yes 를 붙이세요.")
        return 1
    with dbmod.connect() as conn:
        n = checkpoint.reset(conn, task=args.task)
    print(f"체크포인트 {n}건 삭제. 다음 적재는 처음부터 받습니다.")
    return 0


def summary(res: Result) -> None:
    h1("결과")
    if res.failed:
        bad(f"문제 {len(res.problems)}건: {', '.join(res.problems)}")
        print("\n  위 ✗ 항목을 해결한 뒤 같은 명령을 다시 실행하세요. "
              "이미 끝난 단계는 자동으로 건너뜁니다.")
    elif res.warnings:
        warn(f"경고 {len(res.warnings)}건: {', '.join(res.warnings)}")
        print("\n  설정은 완료되었습니다. 경고는 나중에 처리해도 됩니다.")
    else:
        ok("모든 점검 통과 — 설정이 완료되었습니다")
        print("\n  다음 단계:")
        print("    python -m pyxisumo.run_predict predict --source 202609 --target 202611")


def cmd_update(args) -> int:
    """새 버전을 받은 뒤 한 번 돌린다.

    **데이터는 다시 받지 않는다.** 받아 둔 것은 그대로 두고, 프로그램이 바뀌면서
    필요해진 것만 맞춘다:

        새 스키마(마이그레이션) 적용 → 비어 있는 표기 채우기

    웹페이지 다시 만들기는 이어서 마법사가 한다. 그래서 데이터를 몇 시간 받아 둔
    상태에서 새 버전을 받아도 안심하고 돌릴 수 있다.
    """
    res = Result()
    runner = check_env(args.dsn, res)
    if runner is None:
        summary(res)
        return 1

    run_migrations(runner, res)
    if res.failed:
        summary(res)
        return 1

    fill_display_names(runner, res, step="3")

    h1("4. 데이터")
    n = runner.scalar("SELECT count(*) FROM banzuke_entry")
    ok(f"반즈케 {int(n or 0):,}행 — 그대로 두었습니다 (다시 받지 않습니다)")

    summary(res)
    return 1 if res.failed else 0


def cmd_names(args) -> int:
    """표기만 다시 채운다 — heya_names.py 에 한자를 추가한 뒤 쓴다."""
    res = Result()
    runner = check_env(args.dsn, res)
    if runner is None:
        return 1
    fill_display_names(runner, res, step="")
    summary(res)
    return 1 if res.failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m pyxisumo.setup",
        description="PyxiSumo 초기설정 자동화",
    )
    ap.add_argument("command",
                    choices=["init", "doctor", "resume", "retry-failed",
                             "reset", "names", "update"],
                    nargs="?", default="init")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--from", dest="from_basho", default="201801",
                    help="적재 시작 바쇼 (기본 201801). 전량은 195801")
    ap.add_argument("--to", dest="to_basho", default="202609")
    ap.add_argument("--probe-basho", default="202609",
                    help="필드맵 학습에 쓸 바쇼")
    # 마쿠시타 반즈케는 바쇼당 API 호출 1번만 더 들 뿐인데, 없으면 예측이
    # 구조적으로 틀린다 — 쥬료 하위를 밀어낼 승격 후보가 아예 존재하지 않게 된다.
    ap.add_argument("--with-makushita", action="store_true", default=True)
    ap.add_argument("--no-makushita", dest="with_makushita", action="store_false")
    ap.add_argument("--skip-probe", action="store_true")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="체크포인트를 무시하고 전부 다시 받는다")
    ap.add_argument("--task", default=None, help="reset 대상 task")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    print("\033[1mPyxiSumo 초기설정\033[0m")

    return {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "resume": cmd_resume,
        "retry-failed": cmd_retry_failed,
        "reset": cmd_reset,
        "names": cmd_names,
        "update": cmd_update,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
