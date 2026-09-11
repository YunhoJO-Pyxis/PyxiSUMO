"""예측 실행과 적중률 평가 (DB 연동).

    python -m pyxisumo.run_predict predict  --source 202609 --target 202611
    python -m pyxisumo.run_predict evaluate --target 202611

predict  : 직전 바쇼 결과로 차기 반즈케를 예측해 prediction_run/entry 에 저장
evaluate : 실제 반즈케가 들어온 뒤 적중률을 계산해 prediction_accuracy 에 저장

순수 로직은 predict.py 에 있고, 여기는 DB 입출력만 한다.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from . import db
from .predict import (
    PredictParams,
    Prediction,
    RikishiResult,
    evaluate,
    predict_banzuke,
)
from .ranks import Rank

log = logging.getLogger("predict")


def prev_basho(basho_id: str, back: int = 1) -> str:
    """본바쇼는 홀수월. 한 바쇼 전 = 2개월 전."""
    y, m = int(basho_id[:4]), int(basho_id[4:])
    for _ in range(back):
        m -= 2
        if m < 1:
            y, m = y - 1, m + 12
    return f"{y:04d}{m:02d}"


def next_basho(basho_id: str) -> str:
    y, m = int(basho_id[:4]), int(basho_id[4:])
    m += 2
    if m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}{m:02d}"


# 직전 3바쇼를 한 번에 끌어온다.
#   b0 = 예측 근거가 되는 바쇼(source), b1 = 그 전, b2 = 그 전전
#   오제키 상태머신과 "3바쇼 33승" 신호 판정에 b1/b2 가 필요하다.
FETCH_RESULTS_SQL = """
WITH cur AS (
  SELECT be.rikishi_id, be.division, be.rank_kind, be.rank_num, be.side,
         be.wins, be.losses, be.absences
  FROM banzuke_entry be
  WHERE be.basho_id = %(b0)s
    AND be.division IN ('Makuuchi','Juryo','Makushita')
),
p1 AS (
  SELECT rikishi_id, rank_kind, wins, losses, absences
  FROM banzuke_entry WHERE basho_id = %(b1)s
),
p2 AS (
  SELECT rikishi_id, rank_kind, wins, losses, absences
  FROM banzuke_entry WHERE basho_id = %(b2)s
),
yusho AS (
  SELECT rikishi_id FROM basho_award
  WHERE basho_id = %(b0)s AND award = 'yusho' AND division = 'Makuuchi'
)
SELECT
  cur.rikishi_id,
  cur.division::text, cur.rank_kind::text, cur.rank_num, cur.side::text,
  cur.wins, cur.losses, cur.absences,
  p1.rank_kind::text AS p1_kind,
  (p1.wins - p1.losses - p1.absences) AS p1_net,
  p2.rank_kind::text AS p2_kind,
  (cur.wins + COALESCE(p1.wins,0) + COALESCE(p2.wins,0)) AS wins_3basho,
  (cur.rank_kind IN ('Yokozuna','Ozeki','Sekiwake','Komusubi')
   AND p1.rank_kind IN ('Yokozuna','Ozeki','Sekiwake','Komusubi')
   AND p2.rank_kind IN ('Yokozuna','Ozeki','Sekiwake','Komusubi')) AS sanyaku_3,
  (yusho.rikishi_id IS NOT NULL) AS yusho,
  (r.retired_basho IS NOT NULL AND r.retired_basho <= %(b0)s) AS retired
FROM cur
JOIN rikishi r ON r.id = cur.rikishi_id
LEFT JOIN p1 ON p1.rikishi_id = cur.rikishi_id
LEFT JOIN p2 ON p2.rikishi_id = cur.rikishi_id
LEFT JOIN yusho ON yusho.rikishi_id = cur.rikishi_id
ORDER BY cur.rikishi_id
"""

# 과거 검증에 쓸 대회 고르기.
#   target = 실제 반즈케가 DB에 있는 대회
#   source = 그 직전 대회 (성적이 실제로 들어 있어야 근거가 된다)
FETCH_BACKTEST_CANDIDATES_SQL = """
SELECT basho_id,
       count(*) AS n,
       COALESCE(sum(wins + losses + absences), 0) AS played
FROM banzuke_entry
WHERE division IN ('Makuuchi','Juryo')
GROUP BY basho_id
ORDER BY basho_id DESC
"""

FETCH_ACTUAL_SQL = """
SELECT rikishi_id, division::text, rank_kind::text, rank_num, side::text
FROM banzuke_entry
WHERE basho_id = %(basho)s AND division IN ('Makuuchi','Juryo')
"""

FETCH_RUN_SQL = """
SELECT pr.id, pe.rikishi_id, pe.division::text, pe.rank_kind::text,
       pe.rank_num, pe.side::text, pe.confidence, pe.basis
FROM prediction_run pr
JOIN prediction_entry pe ON pe.run_id = pr.id
WHERE pr.target_basho_id = %(target)s
  AND pr.id = (SELECT MAX(id) FROM prediction_run WHERE target_basho_id = %(target)s)
"""


def _int(v: Any, default: int = 0) -> int:
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _bool(v: Any) -> bool:
    """드라이버에 따라 참/거짓이 bool 로도, 't'/'f' 문자열로도 온다.

    bool('f') 는 파이썬에서 참이다 — 이걸 놓치면 전원이 은퇴자로 판정되어
    예측이 **조용히 0명**이 된다. 실제로 그렇게 됐었다.
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("t", "true", "y", "yes", "1")


def build_results(rows: list[tuple]) -> list[RikishiResult]:
    out: list[RikishiResult] = []
    for (
        rid, div, kind, num, side, w, l, a,
        p1_kind, p1_net, _p2_kind, wins3, sanyaku3, yusho, retired,
    ) in rows:
        rank = Rank(division=div, kind=kind,
                    num=_int(num, 1) or 1, side=side)

        # [확정] 番付編成要領 8조 상태 판정
        ozeki_state = "normal"
        if kind == "Ozeki" and p1_kind == "Ozeki" and _int(p1_net) < 0:
            ozeki_state = "kadoban"          # 직전에도 마케코시 → 이번에 지면 강등
        elif kind == "Sekiwake" and p1_kind == "Ozeki":
            ozeki_state = "returning"        # 직전 바쇼에 강등된 전 오제키

        out.append(RikishiResult(
            rikishi_id=_int(rid),
            rank=rank,
            wins=_int(w), losses=_int(l), absences=_int(a),
            ozeki_state=ozeki_state,          # type: ignore[arg-type]
            sanyaku_3basho_wins=_int(wins3) if wins3 is not None else None,
            sanyaku_3basho_all=_bool(sanyaku3),
            yusho=_bool(yusho),
            retired=_bool(retired),
        ))
    return out


def cmd_predict(conn: Any, source: str, target: str, params: PredictParams) -> int:
    with conn.cursor() as cur:
        cur.execute(FETCH_RESULTS_SQL, {
            "b0": source, "b1": prev_basho(source), "b2": prev_basho(source, 2)
        })
        rows = cur.fetchall()

    if not rows:
        log.error("%s 바쇼의 반즈케가 DB에 없습니다. 먼저 ingest 를 돌리세요.", source)
        return 1

    results = build_results(rows)
    preds = predict_banzuke(results, params)
    log.info("예측 %d명 (입력 %d명)", len(preds), len(results))

    # 입력이 있는데 결과가 비면 조용히 넘어가면 안 된다 —
    # 예전에 전원이 은퇴자로 잘못 판정되어 0명이 나온 적이 있다.
    if results and not preds:
        n_retired = sum(1 for r in results if r.retired)
        log.error("입력 %d명인데 예측이 0명입니다 (은퇴 판정 %d명). "
                  "데이터나 판정 로직을 확인하세요.", len(results), n_retired)
        return 1

    with conn.cursor() as cur:
        cur.execute(db.INSERT_PREDICTION_RUN, (
            target, source, params.model_version, json.dumps(params.to_json()),
        ))
        run_id = cur.fetchone()[0]

    db.executemany(conn, db.INSERT_PREDICTION_ENTRY, [
        (run_id, p.rikishi_id, p.rank.division, p.rank.kind,
         p.rank.num, p.rank.side, p.confidence, p.basis)
        for p in preds
    ])
    conn.commit()
    log.info("prediction_run #%d 저장 완료 (target=%s)", run_id, target)

    for p in preds[:8]:
        moved = p.moved_maisu
        log.info("  %-22s conf=%.2f  %s%s",
                 p.rank.label(), p.confidence, p.basis,
                 f"  ({moved:+.1f}매)" if moved is not None else "")
    return 0


def cmd_evaluate(conn: Any, target: str) -> int:
    with conn.cursor() as cur:
        cur.execute(FETCH_RUN_SQL, {"target": target})
        rows = cur.fetchall()
    if not rows:
        log.error("target=%s 에 대한 예측 기록이 없습니다.", target)
        return 1

    run_id = rows[0][0]
    preds = [
        Prediction(
            rikishi_id=_int(r[1]),
            rank=Rank(division=r[2], kind=r[3], num=_int(r[4], 1) or 1, side=r[5]),
            confidence=float(r[6] or 0),
            basis=r[7] or "",
        )
        for r in rows
    ]

    with conn.cursor() as cur:
        cur.execute(FETCH_ACTUAL_SQL, {"basho": target})
        actual = {
            _int(r[0]): Rank(division=r[1], kind=r[2],
                             num=_int(r[3], 1) or 1, side=r[4])
            for r in cur.fetchall()
        }
    if not actual:
        log.error("%s 의 실제 반즈케가 아직 DB에 없습니다.", target)
        return 1

    acc = evaluate(preds, actual)
    db.executemany(conn, db.UPSERT_ACCURACY, [(
        run_id, acc.n_rikishi, acc.exact_rate,
        acc.within1_rate, acc.mae_ranks, acc.division_correct,
    )])
    conn.commit()

    log.info("=== %s 적중률 (run #%d, n=%d) ===", target, run_id, acc.n_rikishi)
    log.info("  완전 일치   : %.1f%%", acc.exact_rate * 100)
    log.info("  ±1매 이내   : %.1f%%   ← 주 지표", acc.within1_rate * 100)
    log.info("  평균 절대오차: %.2f 매", acc.mae_ranks)
    log.info("  디비전 일치 : %.1f%%", acc.division_correct * 100)
    return 0


def choose_backtest_pair(rows: list[tuple]) -> tuple[str, str] | None:
    """(근거 대회, 검증 대상 대회) 를 고른다.

    가장 최근 것부터 내려가며 '직전 대회에 성적이 실제로 들어 있는' 첫 짝을 쓴다.
    개막 전 대회는 반즈케만 있고 성적이 0이라 근거가 될 수 없다.
    """
    info = {
        str(r[0]): {"n": int(r[1] or 0), "played": int(r[2] or 0)}
        for r in rows
    }
    for target in sorted(info, reverse=True):
        if info[target]["n"] <= 0:
            continue
        source = prev_basho(target)
        src = info.get(source)
        if src and src["played"] > 0:
            return source, target
    return None


def cmd_backtest(conn: Any, target: str | None, params: PredictParams) -> int:
    """이미 발표된 반즈케로 예측 정확도를 측정한다.

    다음 대회를 기다릴 필요 없이 **지금** 엔진이 쓸 만한지 알 수 있다.
    """
    with conn.cursor() as cur:
        cur.execute(FETCH_BACKTEST_CANDIDATES_SQL)
        rows = cur.fetchall()

    if target:
        source = prev_basho(target)
    else:
        pair = choose_backtest_pair(rows)
        if not pair:
            log.error("검증에 쓸 대회 짝을 찾지 못했습니다. "
                      "성적이 들어 있는 대회가 연속 2개 이상 필요합니다.")
            return 1
        source, target = pair

    log.info("=== 과거 검증: %s 성적으로 %s 반즈케를 예측 ===", source, target)
    log.info("(실제 %s 반즈케는 이미 DB에 있으므로 바로 채점할 수 있습니다)", target)

    code = cmd_predict(conn, source, target, params)
    if code != 0:
        return code
    return cmd_evaluate(conn, target)


def all_backtest_pairs(rows: list[tuple]) -> list[tuple[str, str]]:
    """채점 가능한 (근거, 대상) 짝을 전부 모은다."""
    info = {
        str(r[0]): {"n": int(r[1] or 0), "played": int(r[2] or 0)}
        for r in rows
    }
    pairs = []
    for target in sorted(info, reverse=True):
        if info[target]["n"] <= 0:
            continue
        source = prev_basho(target)
        src = info.get(source)
        if src and src["played"] > 0:
            pairs.append((source, target))
    return pairs


def score_params(
    conn: Any, pairs: list[tuple[str, str]], params: PredictParams
) -> tuple[float, float, float, int]:
    """(±1매 비율, 완전일치 비율, 평균오차, 대상 인원) — DB에 쓰지 않는다."""
    tot_w = tot_e = tot_mae = 0.0
    tot_n = 0
    for source, target in pairs:
        with conn.cursor() as cur:
            cur.execute(FETCH_RESULTS_SQL, {
                "b0": source, "b1": prev_basho(source),
                "b2": prev_basho(source, 2)})
            rows = cur.fetchall()
            cur.execute(FETCH_ACTUAL_SQL, {"basho": target})
            actual = {
                _int(r[0]): Rank(division=r[1], kind=r[2],
                                 num=_int(r[3], 1) or 1, side=r[4])
                for r in cur.fetchall()
            }
        if not rows or not actual:
            continue
        preds = predict_banzuke(build_results(rows), params)
        acc = evaluate(preds, actual)
        if acc.n_rikishi == 0:
            continue
        tot_w += acc.within1_rate * acc.n_rikishi
        tot_e += acc.exact_rate * acc.n_rikishi
        tot_mae += acc.mae_ranks * acc.n_rikishi
        tot_n += acc.n_rikishi
    if not tot_n:
        return 0.0, 0.0, 0.0, 0
    return tot_w / tot_n, tot_e / tot_n, tot_mae / tot_n, tot_n


# 탐색 격자. 계수는 '일본식 목안(1.0)' 과 '회귀 실측(1.72)' 사이를 훑는다.
GRID_COEF = (0.6, 0.8, 1.0, 1.2, 1.4, 1.72)
GRID_BIGWIN = (0.5, 0.72, 1.0)
GRID_LOSS = (0.6, 0.78, 1.0)


def cmd_tune(conn: Any, save: bool, quick: bool) -> int:
    """과거 대회 전부로 계수를 훑어 가장 잘 맞는 값을 찾는다.

    반즈케 편성에는 성문 규칙이 거의 없으므로 계수는 '정해진 값' 이 아니라
    **측정해서 고르는 값** 이다. 데이터가 쌓일수록 다시 돌려야 한다.
    """
    with conn.cursor() as cur:
        cur.execute(FETCH_BACKTEST_CANDIDATES_SQL)
        rows = cur.fetchall()
    pairs = all_backtest_pairs(rows)
    if not pairs:
        log.error("채점할 대회 짝이 없습니다. 성적이 있는 대회가 연속 2개 이상 필요합니다.")
        return 1

    log.info("채점 대상 %d개 대회 짝: %s", len(pairs),
             ", ".join(t for _, t in pairs[:8]) + ("…" if len(pairs) > 8 else ""))

    base = PredictParams()
    cur_w, cur_e, cur_mae, n = score_params(conn, pairs, base)
    log.info("현재 설정 (계수 %.2f): ±1매 %.1f%% · 완전일치 %.1f%% · 평균오차 %.2f매 (n=%d)",
             base.coef_makuuchi, cur_w * 100, cur_e * 100, cur_mae, n)

    grid_bw = (base.big_win_damping,) if quick else GRID_BIGWIN
    grid_ls = (base.heavy_loss_damping,) if quick else GRID_LOSS

    results: list[tuple[float, float, float, PredictParams]] = []
    total = len(GRID_COEF) * len(grid_bw) * len(grid_ls)
    k = 0
    for coef in GRID_COEF:
        for bw in grid_bw:
            for ls in grid_ls:
                k += 1
                p = PredictParams(
                    model_version=f"v1.1-c{coef}-b{bw}-l{ls}",
                    coef_makuuchi=coef, coef_juryo=coef,
                    big_win_damping=bw, heavy_loss_damping=ls,
                )
                w, ex, mae, _ = score_params(conn, pairs, p)
                results.append((w, ex, mae, p))
                print(f"    [{k}/{total}] 계수 {coef:.2f} · 대승완충 {bw:.2f} · "
                      f"대패완충 {ls:.2f} → ±1매 {w:.1%} · 오차 {mae:.2f}매",
                      flush=True)

    results.sort(key=lambda r: (-r[0], r[2]))
    best_w, best_e, best_mae, best_p = results[0]

    if best_w <= 0:
        log.error("모든 설정이 0%% 로 나왔습니다 — 측정이 깨진 것입니다.")
        log.error("예측과 실제의 리키시가 하나도 겹치지 않았습니다. "
                  "데이터가 제대로 들어갔는지 '2_상태확인' 으로 확인해 보세요.")
        return 1

    log.info("")
    log.info("=== 가장 잘 맞는 설정 ===")
    log.info("  계수 %.2f · 대승완충 %.2f · 대패완충 %.2f",
             best_p.coef_makuuchi, best_p.big_win_damping, best_p.heavy_loss_damping)
    log.info("  ±1매 %.1f%%  (현재 %.1f%%)", best_w * 100, cur_w * 100)
    log.info("  완전일치 %.1f%%  (현재 %.1f%%)", best_e * 100, cur_e * 100)
    log.info("  평균오차 %.2f매  (현재 %.2f매)", best_mae, cur_mae)

    if not save:
        log.info("")
        log.info("저장하려면 --save 를 붙여 다시 실행하세요.")
        return 0

    from . import fieldmap  # app_setting 저장 헬퍼 재사용

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app_setting (key, value, note) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
            "note = EXCLUDED.note, updated_at = now()",
            ("predict_params", json.dumps(best_p.to_json(), ensure_ascii=False),
             f"tune 이 {len(pairs)}개 대회로 찾은 값 (±1매 {best_w:.1%})"),
        )
    conn.commit()
    log.info("")
    log.info("저장했습니다. 앞으로 예측은 이 설정을 씁니다.")
    return 0


def load_saved_params(conn: Any) -> PredictParams | None:
    """tune 이 저장해 둔 계수를 불러온다."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_setting WHERE key = 'predict_params'")
            row = cur.fetchone()
    except Exception:                                   # noqa: BLE001
        return None
    if not row or not row[0]:
        return None
    d = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    base = PredictParams()
    fields = {
        "model_version", "coef_makuuchi", "coef_juryo", "coef_makushita",
        "full_kyujo_penalty", "heavy_loss_threshold", "heavy_loss_damping",
        "big_win_threshold", "big_win_damping",
        "komusubi_to_sekiwake_wins", "ozeki_promo_wins_3basho",
        "ozeki_promo_wins_with_yusho", "ozeki_return_wins",
        "makushita_zensho_max_rank",
    }
    kwargs = {k: v for k, v in d.items() if k in fields}
    try:
        return PredictParams(**kwargs)
    except TypeError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="반즈케 예측 실행/평가")
    ap.add_argument("command",
                    choices=["predict", "evaluate", "backtest", "tune"])
    ap.add_argument("--source", help="근거 바쇼 (YYYYMM)")
    ap.add_argument("--target", help="예측 대상 바쇼 (YYYYMM)")
    ap.add_argument("--coef", type=float, default=None, help="勝ち越し点 1점당 이동 매수")
    ap.add_argument("--save", action="store_true", help="tune: 찾은 값을 저장")
    ap.add_argument("--quick", action="store_true", help="tune: 계수만 빠르게 훑기")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    with db.connect() as conn:
        saved = load_saved_params(conn)
        params = saved or PredictParams()
        if saved and args.command != "tune":
            log.info("저장된 계수를 사용합니다 (계수 %.2f). "
                     "다시 맞추려면 tune 을 실행하세요.", params.coef_makuuchi)
        if args.coef is not None:
            params = PredictParams(coef_makuuchi=args.coef, coef_juryo=args.coef)

        if args.command == "tune":
            return cmd_tune(conn, save=args.save, quick=args.quick)
        if args.command == "backtest":
            return cmd_backtest(conn, args.target, params)
        if args.command == "predict":
            if not args.source:
                ap.error("--source 가 필요합니다")
            target = args.target or next_basho(args.source)
            return cmd_predict(conn, args.source, target, params)
        if not args.target:
            ap.error("--target 이 필요합니다")
        return cmd_evaluate(conn, args.target)


if __name__ == "__main__":
    raise SystemExit(main())
