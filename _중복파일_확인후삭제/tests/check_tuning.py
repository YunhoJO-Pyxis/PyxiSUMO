"""예측 정확도 개선을 실제로 측정한다.

'고쳤다' 가 아니라 '얼마나 좋아졌다' 를 숫자로 확인하기 위한 것.

실제 반즈케 편성을 흉내 낸 합성 이력을 만든다 — 편성 규칙을 그대로 쓰면
엔진이 100% 맞히니 의미가 없으므로, **규칙 + 잡음 + 심판부의 재량**을 섞는다.
그 위에서 계수를 훑어 어느 설정이 가장 잘 맞는지 본다.

    $ DATABASE_URL="postgresql://..." python tests/check_tuning.py
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.predict import (  # noqa: E402
    PredictParams, RikishiResult, evaluate, predict_banzuke,
)
from pyxisumo.ranks import DIVISION_CAPACITY, Rank, slots_for  # noqa: E402

MAKUUCHI = DIVISION_CAPACITY["Makuuchi"]
JURYO = DIVISION_CAPACITY["Juryo"]
MAKUSHITA_POOL = 20


def build_banzuke(order: list[int]) -> dict[int, Rank]:
    """순서대로 마쿠우치 → 쥬료 → 마쿠시타 슬롯에 앉힌다."""
    out: dict[int, Rank] = {}
    i = 0
    sanyaku = [("Yokozuna", 2), ("Ozeki", 2), ("Sekiwake", 2), ("Komusubi", 2)]
    for kind, cnt in sanyaku:
        for n, side in list(slots_for("Makuuchi", cnt)):
            if i >= len(order):
                return out
            out[order[i]] = Rank("Makuuchi", kind, n, side)
            i += 1
    n_mae = MAKUUCHI - sum(c for _, c in sanyaku)
    for n, side in slots_for("Makuuchi", n_mae):
        if i >= len(order):
            return out
        out[order[i]] = Rank("Makuuchi", "Maegashira", n, side)
        i += 1
    for n, side in slots_for("Juryo", JURYO):
        if i >= len(order):
            return out
        out[order[i]] = Rank("Juryo", "Numbered", n, side)
        i += 1
    for n, side in slots_for("Makushita", MAKUSHITA_POOL):
        if i >= len(order):
            return out
        out[order[i]] = Rank("Makushita", "Numbered", n, side)
        i += 1
    return out


def simulate(n_basho: int, seed: int, true_coef: float, noise: float,
             makushita_coef: float = 4.0, damping: float = 0.7):
    """(바쇼별 (성적, 실제 다음 반즈케)) 를 만든다.

    실제 편성을 흉내 내는 규칙:
      · 성적에 따라 true_coef 만큼 이동하되 큰 점수는 완만하게 (sub-linear)
      · 심판부 재량을 noise 로 섞는다
      · 요코즈나는 강등하지 않는다
    """
    rng = random.Random(seed)
    pool = list(range(1, MAKUUCHI + JURYO + MAKUSHITA_POOL + 1))
    rng.shuffle(pool)
    order = pool[:]
    episodes = []

    for _ in range(n_basho):
        banzuke = build_banzuke(order)
        results: list[RikishiResult] = []
        score: dict[int, float] = {}

        for idx, rid in enumerate(order):
            rank = banzuke.get(rid)
            if rank is None:
                continue
            div = rank.division
            bouts = 15 if div != "Makushita" else 7
            w = rng.randint(0, bouts)
            l = bouts - w
            net = w - l
            results.append(RikishiResult(rikishi_id=rid, rank=rank,
                                         wins=w, losses=l))

            # '실제' 편성이 하는 일.
            # 마쿠시타 계수는 엔진과 같은 값을 쓴다 — 다르게 두면 이 테스트가
            # 엔진이 아니라 테스트 자신의 가정을 재게 된다.
            k = true_coef if div != "Makushita" else makushita_coef
            d = k * net
            if abs(net) > 5:                      # 큰 점수는 완만하게
                d = k * (5 + (abs(net) - 5) * damping) * (1 if net > 0 else -1)
            move = d * 2 + rng.gauss(0, noise)    # 슬롯 단위 + 재량
            if rank.kind == "Yokozuna":
                move = min(move, 0)               # 요코즈나는 내려가지 않는다
            score[rid] = idx - move

            # 마쿠시타 → 쥬료 승격 목안 (실제 규칙).
            # 筆頭 4승 / 3매목 5승 / 5매목 6승 / 15매목 전승 이 아니면 올라가지 못한다.
            # 시뮬레이터에도 넣어야 엔진과 같은 세계를 재는 것이 된다.
            if div == "Makushita":
                mn = rank.num or 99
                ok = ((mn <= 15 and w == bouts)
                      or (mn <= 1 and w >= 4)
                      or (mn <= 3 and w >= 5)
                      or (mn <= 5 and w >= 6))
                if not ok:
                    score[rid] = max(score[rid], MAKUUCHI + JURYO + 0.5)

        order = sorted(score, key=lambda r: score[r])
        actual = build_banzuke(order)
        actual_sekitori = {
            rid: rk for rid, rk in actual.items()
            if rk.division in ("Makuuchi", "Juryo")
        }
        episodes.append((results, actual_sekitori))
    return episodes


def score(episodes, params: PredictParams) -> tuple[float, float, float]:
    tw = te = tm = 0.0
    n = 0
    for results, actual in episodes:
        preds = predict_banzuke(results, params)
        acc = evaluate(preds, actual)
        if not acc.n_rikishi:
            continue
        tw += acc.within1_rate * acc.n_rikishi
        te += acc.exact_rate * acc.n_rikishi
        tm += acc.mae_ranks * acc.n_rikishi
        n += acc.n_rikishi
    return (tw / n, te / n, tm / n) if n else (0, 0, 0)


def main() -> int:
    failures: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        print(("  ✓ " if cond else "  ✗ ") + label + (f"  ({detail})" if detail else ""))
        if not cond:
            failures.append(label)

    print("\n[1] 마쿠시타 데이터가 있을 때 vs 없을 때")
    # 계수가 크게 어긋난 상태에서 재면 마쿠시타 효과가 잡음에 묻힌다.
    # 계수를 맞춘 상태에서 '마쿠시타 유무' 만 차이 나게 둔다.
    eps = simulate(12, seed=7, true_coef=1.0, noise=2.0)
    p = PredictParams(coef_makuuchi=1.0, coef_juryo=1.0)
    w_full, _, m_full = score(eps, p)

    # 마쿠시타를 빼고 같은 예측을 돌린다 (사용자의 첫 실행 상황)
    eps_nomk = [
        ([r for r in res if r.rank.division != "Makushita"], act)
        for res, act in eps
    ]
    w_no, _, m_no = score(eps_nomk, p)
    print(f"      마쿠시타 포함: ±1매 {w_full:.1%} · 오차 {m_full:.2f}매")
    print(f"      마쿠시타 없음: ±1매 {w_no:.1%} · 오차 {m_no:.2f}매")
    check("마쿠시타가 있으면 더 정확하다", w_full > w_no,
          f"{w_no:.1%} → {w_full:.1%}")

    print("\n[2] 대승 완충이 도움이 되는가")
    off = PredictParams(coef_makuuchi=1.0, coef_juryo=1.0, big_win_damping=1.0)
    w_off, _, m_off = score(eps, off)
    w_on, _, m_on = score(eps, p)
    print(f"      완충 없음: ±1매 {w_off:.1%} · 오차 {m_off:.2f}매")
    print(f"      완충 있음: ±1매 {w_on:.1%} · 오차 {m_on:.2f}매")
    check("대승 완충이 오차를 줄인다", m_on <= m_off, f"{m_off:.2f} → {m_on:.2f}매")

    print("\n[3] 계수 훑기 — 참값 1.0 을 찾아내는가")
    best = None
    for coef in (0.6, 0.8, 1.0, 1.2, 1.4, 1.72):
        w, e, m = score(eps, PredictParams(coef_makuuchi=coef, coef_juryo=coef))
        print(f"      계수 {coef:.2f} → ±1매 {w:.1%} · 오차 {m:.2f}매")
        if best is None or w > best[1]:
            best = (coef, w, m)
    check("훑기가 참값에 가까운 계수를 고른다", abs(best[0] - 1.0) <= 0.2,
          f"고른 값 {best[0]}")
    check("고른 계수가 기본값(1.72)보다 낫다",
          best[1] >= score(eps, PredictParams(coef_makuuchi=1.72,
                                              coef_juryo=1.72))[0],
          f"{best[1]:.1%}")

    print("\n[4] 참값이 다르면 다른 계수를 고르는가")
    eps2 = simulate(12, seed=11, true_coef=1.6, noise=2.0)
    best2 = None
    for coef in (0.6, 1.0, 1.4, 1.72):
        w, _, _ = score(eps2, PredictParams(coef_makuuchi=coef, coef_juryo=coef))
        if best2 is None or w > best2[1]:
            best2 = (coef, w)
    print(f"      참값 1.6 → 고른 값 {best2[0]} (±1매 {best2[1]:.1%})")
    check("참값이 크면 큰 계수를 고른다", best2[0] >= 1.4, str(best2[0]))

    print("\n[5] 재량(잡음)이 없고 계수가 같으면 거의 맞혀야 한다")
    print("      (엔진이 자기 모델을 제대로 재현하는지 — 배선 오류를 잡는 검사)")
    same = PredictParams(coef_makuuchi=1.0, coef_juryo=1.0, coef_makushita=4.0,
                         big_win_damping=0.7, heavy_loss_damping=0.7)
    clean = simulate(8, seed=3, true_coef=1.0, noise=0.0,
                     makushita_coef=4.0, damping=0.7)
    w_clean, e_clean, m_clean = score(clean, same)
    print(f"      ±1매 {w_clean:.1%} · 완전일치 {e_clean:.1%} · 오차 {m_clean:.2f}매")
    # 완벽히 일치하지는 않는다 — 시뮬레이터는 산야쿠 승격 경험칙
    # (코무스비 11승, 東前頭筆頭 카치코시, 오제키 33승)을 모사하지 않는다.
    # 그 부분만큼은 엔진이 '실제' 와 달라지는 것이 정상이다.
    check("규칙대로면 대부분 맞힌다", w_clean > 0.80, f"{w_clean:.1%}")
    check("평균 오차가 1.5매 미만", m_clean < 1.5, f"{m_clean:.2f}매")

    if failures:
        print(f"\nFAIL — {len(failures)}건: {failures}")
        return 1
    print("\nOK — 개선이 수치로 확인됩니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
