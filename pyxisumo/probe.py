"""Sumo-API 실제 응답 스키마를 읽어 **필드 대응을 자동 학습**한다.

Sumo-API 는 응답 필드를 문서화하지 않는다(webhooks 문서도 "Execute tests to
see the formats" 라고만 쓴다). 그래서 손으로 맞추는 대신 실제 응답을 보고
논리 필드 → 실제 키 대응을 추론해 DB(app_setting)와 로컬 캐시에 저장한다.

    python -m pyxisumo.probe                 # 학습 + 저장
    python -m pyxisumo.probe --dry-run       # 저장하지 않고 보기만
    python -m pyxisumo.probe --show          # 저장된 대응 확인

여기서 미해결로 남는 필드가 있으면 그때만 sumoapi.FIELD_ALIASES 에 후보를 추가하면 된다.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import fieldmap
from .sumoapi import FIELD_ALIASES, SumoApi, rows_of

# 엔드포인트별로 "이 응답에서 찾아야 하는" 논리 필드.
# required=True 인 건 하나라도 못 찾으면 셋업을 멈춘다.
EXPECTED: dict[str, dict[str, bool]] = {
    "rikishis": {
        "rikishi_id": True, "shikona_en": True, "shikona_ja": False,
        "heya": True, "birth_date": False, "height": False,
        "weight": False, "debut": False, "retired": False, "shusshin": False,
    },
    "basho": {"start_date": False, "end_date": False},
    "banzuke": {
        "rikishi_id": True, "rank": True,
        "wins": False, "losses": False, "absences": False, "record": False,
    },
    "torikumi": {
        "east_id": True, "west_id": True, "winner_id": False,
        "kimarite": False, "day": False, "match_no": False,
    },
    "kimarite": {},
}


# 단일 레코드를 돌려주는 엔드포인트. 나머지는 전부 '목록' 이 온다.
#   목록 엔드포인트가 딕셔너리를 돌려주면 그것은 레코드가 아니라 **빈 봉투** 다.
#   예) 아직 시작하지 않은 바쇼의 취조를 물으면
#       {"date":"202609","startDate":"...","endDate":"..."} 만 온다.
#       이걸 레코드로 착각하면 '키를 못 알아봤다' 는 엉뚱한 진단이 나오고,
#       끝난 바쇼로 되짚어 보지도 못한다.
SINGLE_RECORD_ENDPOINTS = {"basho"}

# 이 엔드포인트들이 해석되지 않으면 설치를 멈춘다 — 핵심 데이터이기 때문이다.
# 취조(대전 기록)는 아카이브용이고 반즈케 예측에는 쓰이지 않으므로,
# 해석에 실패해도 경고만 하고 나머지는 진행한다.
BLOCKING_ENDPOINTS = {"rikishis", "banzuke"}


def _dict_list_keys(data: Any) -> list[str]:
    """딕셔너리 안에서 'dict 들의 리스트' 를 값으로 가진 키 이름들."""
    if not isinstance(data, dict):
        return []
    return [
        k for k, v in data.items()
        if isinstance(v, list) and v and all(isinstance(r, dict) for r in v)
    ]


def _sample_rows(data: Any, *, expect_list: bool = True) -> list[dict]:
    """응답에서 학습에 쓸 행들을 꺼낸다.

    expect_list=True 인 엔드포인트에서는 **딕셔너리를 레코드로 보지 않는다.**
    목록이 와야 할 자리에 온 딕셔너리는 내용물 없는 봉투이기 때문이다.
    """
    rows = rows_of(data)
    if rows:
        return rows
    if not expect_list and isinstance(data, dict) and not _dict_list_keys(data):
        return [data]
    return []


def probe_endpoint(name: str, data: Any, *, verbose: bool = True) -> dict:
    expect_list = name not in SINGLE_RECORD_ENDPOINTS
    rows = _sample_rows(data, expect_list=expect_list)
    spec = EXPECTED.get(name, {})
    learned = fieldmap.learn(rows, spec.keys(), FIELD_ALIASES)

    keys: set[str] = set()
    for r in rows[:20]:
        keys |= set(r.keys())

    # 봉투는 벗겼는데 목록이 여러 개라 어느 것이 내용물인지 모르는 경우
    envelope = _dict_list_keys(data) if not rows else []
    empty = not rows
    # 응답이 비어 있으면 배울 것이 없다 — '해석 실패' 와 구분해야 한다.
    # (아직 시작하지 않은 바쇼의 취조를 물으면 빈 배열이 온다)
    missing_required = (
        [] if empty else [f for f, req in spec.items() if req and f not in learned]
    )
    missing_optional = [f for f, req in spec.items() if not req and f not in learned]

    if envelope:
        # 내용물을 못 꺼낸 것이지 데이터가 없는 것이 아니다 — 확실히 문제로 잡는다
        missing_required = [f for f, req in spec.items() if req]

    if verbose:
        print(f"\n── {name} " + "─" * (58 - len(name)))
        if envelope:
            print(f"   응답이 감싸여 있는데 내용물을 못 꺼냈습니다. "
                  f"바깥 키: {sorted(data.keys()) if isinstance(data, dict) else data}")
            print(f"   목록으로 보이는 키: {envelope}")
        elif empty:
            print("   응답이 비어 있습니다 (해당 데이터가 아직 없는 시점)")
        else:
            print(f"   행 수 {len(rows)} · 키 {sorted(keys)}")
        for logical, key in sorted(learned.items()):
            mark = "=" if key in FIELD_ALIASES.get(logical, [])[:1] else "~"
            print(f"     {mark} {logical:<14} → {key}")
        for f in missing_optional:
            print(f"     · {f:<14} (없음 — 선택 항목)")
        for f in missing_required:
            print(f"     ! {f:<14} 미해결 — FIELD_ALIASES 에 후보 추가 필요"
                  f"  (시도: {FIELD_ALIASES.get(f, [f])})")
        if rows:
            print("     샘플: " + json.dumps(rows[0], ensure_ascii=False)[:400])

    return {
        "keys": sorted(keys), "n_rows": len(rows), "learned": learned,
        "empty": empty and not envelope,
        "envelope": envelope,
        "outer_keys": sorted(data.keys()) if isinstance(data, dict) else [],
        "missing_required": missing_required, "missing_optional": missing_optional,
        "sample": rows[0] if rows else None,
    }


def prev_basho(basho_id: str, back: int = 1) -> str:
    """본바쇼는 홀수월. 한 바쇼 전 = 2개월 전."""
    y, m = int(basho_id[:4]), int(basho_id[4:])
    for _ in range(back):
        m -= 2
        if m < 1:
            y, m = y - 1, m + 12
    return f"{y:04d}{m:02d}"


def run_probe(
    api: SumoApi | None = None,
    *,
    basho: str = "202609",
    day: int = 1,
    verbose: bool = True,
) -> tuple[dict[str, str], list[str], dict]:
    """(학습된 대응, 미해결 필수 필드, 전체 리포트)."""
    api = api or SumoApi()
    report: dict[str, Any] = {"basho": basho}
    mapping: dict[str, str] = {}
    unresolved: set[str] = set()
    blocking: set[str] = set()

    # 아직 시작하지 않은 바쇼는 반즈케만 있고 취조(대전 결과)가 없다.
    # 빈 응답에서는 배울 것이 없으므로 끝난 바쇼로 되짚어 내려간다.
    def with_fallback(name: str, call, candidates: list[tuple]) -> tuple[Any, tuple]:
        last: Any = None
        for args in candidates:
            try:
                data = call(*args)
            except Exception as e:                   # noqa: BLE001
                if verbose:
                    print(f"   ({name} {args} 호출 실패: {e})", file=sys.stderr)
                continue
            if _sample_rows(data, expect_list=True):
                return data, args
            if _dict_list_keys(data):
                # 목록은 들어 있는데 어느 것이 내용물인지 모르는 경우.
                # 되짚어도 해결되지 않으므로 그대로 올려보내 문제를 드러낸다.
                return data, args
            last = data
            if verbose:
                print(f"   ({name} {args[0]} 은(는) 비어 있어 이전 바쇼로 되짚습니다)")
        return last, (candidates[-1] if candidates else ())

    banzuke_cands = [(basho,), (prev_basho(basho),), (prev_basho(basho, 2),)]
    torikumi_cands = [(basho, day)] + [
        (prev_basho(basho, b), d) for b in (1, 2, 3) for d in (1, 8)
    ]

    sources: dict[str, tuple] = {}

    def probe_banzuke() -> Any:
        data, args = with_fallback(
            "banzuke", lambda b: api.banzuke(b, "Makuuchi"), banzuke_cands)
        sources["banzuke"] = args
        return data

    def probe_torikumi() -> Any:
        data, args = with_fallback(
            "torikumi", lambda b, d: api.torikumi(b, "Makuuchi", d), torikumi_cands)
        sources["torikumi"] = args
        return data

    probes = [
        ("rikishis", lambda: api.rikishis(limit=20)),
        ("basho", lambda: api.basho(basho)),
        ("banzuke", probe_banzuke),
        ("torikumi", probe_torikumi),
        ("kimarite", lambda: api.kimarite()),
    ]

    for name, fn in probes:
        try:
            data = fn()
        except Exception as e:                       # noqa: BLE001
            if verbose:
                print(f"\n── {name} — 호출 실패: {e}", file=sys.stderr)
            report[name] = {"error": str(e)}
            missing = {f for f, req in EXPECTED.get(name, {}).items() if req}
            unresolved.update(missing)
            if name in BLOCKING_ENDPOINTS:
                blocking.update(missing)
            continue
        res = probe_endpoint(name, data, verbose=verbose)
        if name in sources:
            res["source"] = sources[name]
        report[name] = res
        # 먼저 학습된 값을 우선한다 (엔드포인트마다 키가 조금씩 다를 수 있음)
        for logical, key in res["learned"].items():
            mapping.setdefault(logical, key)
        unresolved.update(res["missing_required"])
        if name in BLOCKING_ENDPOINTS:
            blocking.update(res["missing_required"])
        if res.get("empty") and verbose:
            print(f"   ! {name}: 끝까지 비어 있어 이 엔드포인트는 학습하지 못했습니다.")

    # 학습된 대응을 즉시 적용해야 rikishi 상세 조회에 쓸 id 를 꺼낼 수 있다
    fieldmap.install(mapping)

    first_id = None
    sample = report.get("rikishis", {}).get("sample")
    key = mapping.get("rikishi_id")
    if isinstance(sample, dict) and key and key in sample:
        first_id = sample[key]

    if first_id is not None:
        try:
            detail = api.rikishi(first_id)
            res = probe_endpoint("rikishis", detail, verbose=False)
            for logical, key in res["learned"].items():
                mapping.setdefault(logical, key)
            report["rikishi_detail"] = res
        except Exception as e:                       # noqa: BLE001
            report["rikishi_detail"] = {"error": str(e)}

    fieldmap.install(mapping)
    report["_blocking_unresolved"] = sorted(blocking)
    return mapping, sorted(unresolved), report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sumo-API 필드 대응 자동 학습")
    ap.add_argument("--basho", default="202609")
    ap.add_argument("--day", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않음")
    ap.add_argument("--show", action="store_true", help="저장된 대응만 출력")
    ap.add_argument("--out", default=None, help="리포트 JSON 저장 경로")
    args = ap.parse_args(argv)

    if args.show:
        local = fieldmap.load_local()
        db_map: dict[str, str] = {}
        try:
            from . import db as dbmod

            with dbmod.connect() as conn:
                db_map = fieldmap.load_db(conn)
        except Exception as e:                        # noqa: BLE001
            print(f"(DB 조회 생략: {e})")
        print("로컬 캐시:", json.dumps(local, ensure_ascii=False, indent=2))
        print("DB 저장분:", json.dumps(db_map, ensure_ascii=False, indent=2))
        return 0

    mapping, unresolved, report = run_probe(basho=args.basho, day=args.day)

    print("\n" + "═" * 66)
    print(f"  학습된 필드 대응 {len(mapping)}건")
    for logical, key in sorted(mapping.items()):
        print(f"    {logical:<14} → {key}")

    if unresolved:
        print(f"\n  ! 미해결 필수 필드 {len(unresolved)}건: {unresolved}")
        print("    pyxisumo/sumoapi.py 의 FIELD_ALIASES 에 실제 키를 추가한 뒤 다시 실행하세요.")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  리포트 저장: {args.out}")

    if args.dry_run:
        print("\n  --dry-run: 저장하지 않았습니다.")
        return 1 if unresolved else 0

    fieldmap.save_local(mapping)
    print(f"  로컬 캐시 저장: {fieldmap.CACHE_PATH}")
    try:
        from . import db as dbmod

        with dbmod.connect() as conn:
            fieldmap.save_db(conn, mapping)
        print("  DB(app_setting) 저장 완료 — GitHub Actions 러너도 같은 대응을 씁니다.")
    except Exception as e:                            # noqa: BLE001
        print(f"  (DB 저장 생략: {e})")

    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
