"""반즈케 예측 엔진 테스트.

합성 반즈케(마쿠우치 42 + 쥬료 28 + 마쿠시타 20)로 파이프라인의
확정 규칙과 정원 제약을 검증한다.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.predict import (  # noqa: E402
    PredictParams,
    Prediction,
    RikishiResult,
    evaluate,
    predict_banzuke,
)
from pyxisumo.ranks import Rank  # noqa: E402


# ---------------------------------------------------------------------
#  합성 반즈케 빌더
# ---------------------------------------------------------------------
def build_prev_basho() -> list[RikishiResult]:
    """전형적인 구성: 요코즈나 2, 오제키 2, 세키와케 2, 코무스비 2,
    마에가시라 34(17매 × 동서), 쥬료 28, 마쿠시타 20."""
    out: list[RikishiResult] = []
    rid = 1

    def add(rank: Rank, w: int, l: int, a: int = 0, **kw) -> int:
        nonlocal rid
        out.append(RikishiResult(rikishi_id=rid, rank=rank, wins=w, losses=l,
                                 absences=a, **kw))
        rid += 1
        return rid - 1

    for side in ("E", "W"):
        add(Rank("Makuuchi", "Yokozuna", 1, side), 12, 3)
    for side in ("E", "W"):
        add(Rank("Makuuchi", "Ozeki", 1 if side == "E" else 1, side), 9, 6)
    for side in ("E", "W"):
        add(Rank("Makuuchi", "Sekiwake", 1, side), 8, 7)
    for side in ("E", "W"):
        add(Rank("Makuuchi", "Komusubi", 1, side), 7, 8)
    for num in range(1, 18):
        for side in ("E", "W"):
            add(Rank("Makuuchi", "Maegashira", num, side), 8 if num % 2 else 7,
                7 if num % 2 else 8)
    for num in range(1, 15):
        for side in ("E", "W"):
            add(Rank("Juryo", "Numbered", num, side), 8 if num % 2 else 7,
                7 if num % 2 else 8)
    # 마쿠시타는 승격 목안(筆頭 4승 / 3매목 5승 / 5매목 6승)에 못 미치는
    # 평범한 성적으로 채운다 — 기본 상태에서는 쥬료를 밀어내면 안 된다.
    for num in range(1, 11):
        for side in ("E", "W"):
            add(Rank("Makushita", "Numbered", num, side), 3, 4)
    return out


def placement(preds: list[Prediction], rid: int) -> float:
    """반즈케에 없으면(마쿠시타 강등) 무한대로 취급한다."""
    p = by_id(preds, rid)
    return float(p.rank.value) if p else float("inf")


def by_id(preds: list[Prediction], rid: int) -> Prediction | None:
    return next((p for p in preds if p.rikishi_id == rid), None)


def replace_result(
    results: list[RikishiResult], rid: int, **changes
) -> list[RikishiResult]:
    out = []
    for r in results:
        if r.rikishi_id == rid:
            d = {
                "rikishi_id": r.rikishi_id, "rank": r.rank, "wins": r.wins,
                "losses": r.losses, "absences": r.absences,
                "ozeki_state": r.ozeki_state,
                "sanyaku_3basho_wins": r.sanyaku_3basho_wins,
                "sanyaku_3basho_all": r.sanyaku_3basho_all,
                "yusho": r.yusho, "retired": r.retired,
            }
            d.update(changes)
            out.append(RikishiResult(**d))
        else:
            out.append(r)
    return out


# ---------------------------------------------------------------------
class TestCapacity(unittest.TestCase):
    def setUp(self):
        self.prev = build_prev_basho()
        self.preds = predict_banzuke(self.prev)

    def test_makuuchi_is_42(self):
        n = sum(1 for p in self.preds if p.rank.division == "Makuuchi")
        self.assertEqual(n, 42, "마쿠우치 정원 42 (2004년 1월 장소 이후 확정)")

    def test_juryo_is_28(self):
        n = sum(1 for p in self.preds if p.rank.division == "Juryo")
        self.assertEqual(n, 28, "쥬료 정원 28")

    def test_no_duplicate_slots(self):
        vals = [p.rank.value for p in self.preds]
        self.assertEqual(len(set(vals)), len(vals), "같은 슬롯에 두 명이 배치됐다")

    def test_no_duplicate_rikishi(self):
        ids = [p.rikishi_id for p in self.preds]
        self.assertEqual(len(set(ids)), len(ids))

    def test_sorted_output(self):
        vals = [p.rank.value for p in self.preds]
        self.assertEqual(vals, sorted(vals))

    def test_sanyaku_minimums(self):
        for kind in ("Sekiwake", "Komusubi"):
            n = sum(1 for p in self.preds if p.rank.kind == kind)
            self.assertGreaterEqual(n, 2, f"{kind} 최소 2명 (동서 각 1)")

    def test_retired_excluded(self):
        prev = replace_result(self.prev, 1, retired=True)
        preds = predict_banzuke(prev)
        self.assertIsNone(by_id(preds, 1), "은퇴자는 반즈케에서 빠진다")
        self.assertEqual(sum(1 for p in preds if p.rank.division == "Makuuchi"), 42)


class TestYokozuna(unittest.TestCase):
    def test_makekoshi_stays_yokozuna(self):
        # [확정] 요코즈나는 강등이 없다. 1890년 이후 사례 0건.
        prev = replace_result(build_prev_basho(), 1, wins=3, losses=12)
        p = by_id(predict_banzuke(prev), 1)
        self.assertEqual(p.rank.kind, "Yokozuna")
        self.assertEqual(p.basis, "yokozuna_lock")

    def test_full_kyujo_stays_yokozuna(self):
        prev = replace_result(build_prev_basho(), 1, wins=0, losses=0, absences=15)
        p = by_id(predict_banzuke(prev), 1)
        self.assertEqual(p.rank.kind, "Yokozuna")


class TestOzekiArticle8(unittest.TestCase):
    """番付編成要領 第八条 — 유일하게 완전 성문화된 승강 규칙."""

    OZEKI_E = 3   # build_prev_basho 에서 동 오제키의 id

    def test_normal_makekoshi_stays_ozeki(self):
        # 카도반이 아니면 마케코시 1회로는 강등되지 않는다
        prev = replace_result(build_prev_basho(), self.OZEKI_E,
                              wins=6, losses=9, ozeki_state="normal")
        p = by_id(predict_banzuke(prev), self.OZEKI_E)
        self.assertEqual(p.rank.kind, "Ozeki")

    def test_kadoban_makekoshi_demoted_to_sekiwake(self):
        prev = replace_result(build_prev_basho(), self.OZEKI_E,
                              wins=6, losses=9, ozeki_state="kadoban")
        p = by_id(predict_banzuke(prev), self.OZEKI_E)
        self.assertEqual(p.rank.kind, "Sekiwake")
        self.assertEqual(p.basis, "ozeki_art8_demotion")

    def test_kadoban_full_kyujo_stops_at_sekiwake(self):
        # 「降下は全休を含めて関脇に止め」 — 전휴여도 세키와케까지만
        prev = replace_result(build_prev_basho(), self.OZEKI_E,
                              wins=0, losses=0, absences=15, ozeki_state="kadoban")
        p = by_id(predict_banzuke(prev), self.OZEKI_E)
        self.assertEqual(p.rank.kind, "Sekiwake")

    def test_kadoban_kachikoshi_cleared(self):
        prev = replace_result(build_prev_basho(), self.OZEKI_E,
                              wins=8, losses=7, ozeki_state="kadoban")
        p = by_id(predict_banzuke(prev), self.OZEKI_E)
        self.assertEqual(p.rank.kind, "Ozeki")

    def test_return_with_10_wins(self):
        # 강등 직후 세키와케에서 10승 → 특례 복귀
        prev = replace_result(build_prev_basho(), 5,
                              wins=10, losses=5, ozeki_state="returning")
        p = by_id(predict_banzuke(prev), 5)
        self.assertEqual(p.rank.kind, "Ozeki")
        self.assertEqual(p.basis, "ozeki_art8_return")

    def test_no_return_with_9_wins(self):
        prev = replace_result(build_prev_basho(), 5,
                              wins=9, losses=6, ozeki_state="returning")
        p = by_id(predict_banzuke(prev), 5)
        self.assertNotEqual(p.rank.kind, "Ozeki", "9승으로는 복귀하지 못한다")


class TestSanyakuHeuristics(unittest.TestCase):
    def test_komusubi_11_wins_promoted(self):
        # [경험칙] 세키와케에 자리가 없어도 11승이면 승격
        prev = build_prev_basho()
        prev = replace_result(prev, 7, wins=11, losses=4)   # 동 코무스비
        p = by_id(predict_banzuke(prev), 7)
        self.assertEqual(p.rank.kind, "Sekiwake")

    def test_ozeki_promotion_signal(self):
        prev = replace_result(build_prev_basho(), 5,
                              wins=12, losses=3,
                              sanyaku_3basho_wins=34, sanyaku_3basho_all=True)
        p = by_id(predict_banzuke(prev), 5)
        self.assertEqual(p.rank.kind, "Ozeki")
        self.assertEqual(p.basis, "ozeki_promotion_signal")

    def test_33_wins_without_sanyaku_streak_ignored(self):
        # 3바쇼 연속 산야쿠 재적이 아니면 신호가 켜지지 않는다
        prev = replace_result(build_prev_basho(), 5,
                              wins=12, losses=3,
                              sanyaku_3basho_wins=34, sanyaku_3basho_all=False)
        p = by_id(predict_banzuke(prev), 5)
        self.assertNotEqual(p.rank.kind, "Ozeki")

    def test_promotion_confidence_is_capped(self):
        prev = replace_result(build_prev_basho(), 5,
                              wins=12, losses=3,
                              sanyaku_3basho_wins=34, sanyaku_3basho_all=True)
        p = by_id(predict_banzuke(prev), 5)
        self.assertLessEqual(p.confidence, 0.70,
                             "경험칙 기반 승격은 확신도를 낮게 잡아야 한다")


class TestMovement(unittest.TestCase):
    def test_kachikoshi_moves_up(self):
        prev = replace_result(build_prev_basho(), 30, wins=13, losses=2)
        before = next(r for r in build_prev_basho() if r.rikishi_id == 30)
        p = by_id(predict_banzuke(prev), 30)
        self.assertLess(p.rank.value, before.rank.value, "13승인데 서열이 내려갔다")

    def test_makekoshi_moves_down(self):
        prev = replace_result(build_prev_basho(), 30, wins=2, losses=13)
        before = next(r for r in build_prev_basho() if r.rikishi_id == 30)
        p = by_id(predict_banzuke(prev), 30)
        self.assertGreater(p.rank.value, before.rank.value)

    def test_full_kyujo_falls_below_all_losses(self):
        base = build_prev_basho()
        target = 20   # 마에가시라 상위 — 전패·전휴 둘 다 쥬료 안에 남는 위치
        all_loss = predict_banzuke(replace_result(base, target, wins=0, losses=15))
        full_kyujo = predict_banzuke(
            replace_result(base, target, wins=0, losses=0, absences=15))
        self.assertGreater(
            placement(full_kyujo, target),
            placement(all_loss, target),
            "전휴는 전패보다 아래로 취급해야 한다",
        )

    def test_heavy_loss_damping(self):
        """대패 완충: 감쇠를 끄면 더 많이 떨어져야 한다."""
        base = replace_result(build_prev_basho(), 30, wins=2, losses=13)
        damped = predict_banzuke(base, PredictParams())
        undamped = predict_banzuke(base, PredictParams(heavy_loss_damping=1.0))
        self.assertLessEqual(placement(damped, 30), placement(undamped, 30))

    def test_juryo_promotion_on_strong_record(self):
        # 쥬료 1매목 동(id 79)이 14승이면 마쿠우치로 올라가야 한다
        prev = build_prev_basho()
        juryo1e = next(r for r in prev
                       if r.rank.division == "Juryo" and r.rank.num == 1
                       and r.rank.side == "E")
        prev = replace_result(prev, juryo1e.rikishi_id, wins=14, losses=1)
        p = by_id(predict_banzuke(prev), juryo1e.rikishi_id)
        self.assertEqual(p.rank.division, "Makuuchi")

    def test_makushita_zensho_reaches_juryo(self):
        # [내규] 마쿠시타 15매목 이내 7전 전승 → 쥬료 승격 최우선
        prev = build_prev_basho()
        m1e = next(r for r in prev
                   if r.rank.division == "Makushita" and r.rank.num == 3
                   and r.rank.side == "E")
        prev = replace_result(prev, m1e.rikishi_id, wins=7, losses=0)
        p = by_id(predict_banzuke(prev), m1e.rikishi_id)
        self.assertIsNotNone(p, "전승자가 반즈케에 들어오지 않았다")
        self.assertIn(p.rank.division, ("Juryo", "Makuuchi"))
        self.assertEqual(p.basis, "makushita15_zensho")

    def test_makushita_16_zensho_not_prioritized(self):
        prev = build_prev_basho()
        # 20매목은 15매목 이내가 아니므로 최우선 대상이 아니다
        extra = RikishiResult(
            rikishi_id=9999, rank=Rank("Makushita", "Numbered", 20, "E"),
            wins=7, losses=0)
        prev.append(extra)
        p = by_id(predict_banzuke(prev), 9999)
        if p is not None:
            self.assertNotEqual(p.basis, "makushita15_zensho")


class TestEvaluate(unittest.TestCase):
    def test_perfect_prediction(self):
        preds = predict_banzuke(build_prev_basho())
        actual = {p.rikishi_id: p.rank for p in preds}
        acc = evaluate(preds, actual)
        self.assertEqual(acc.exact_rate, 1.0)
        self.assertEqual(acc.within1_rate, 1.0)
        self.assertEqual(acc.mae_ranks, 0.0)

    def test_one_maisu_off_counts_as_within1(self):
        pred = Prediction(1, Rank("Makuuchi", "Maegashira", 5, "E"), 0.9, "linear")
        actual = {1: Rank("Makuuchi", "Maegashira", 6, "E")}
        acc = evaluate([pred], actual)
        self.assertEqual(acc.exact_rate, 0.0)
        self.assertEqual(acc.within1_rate, 1.0)
        self.assertEqual(acc.mae_ranks, 1.0)

    def test_east_west_swap_is_half_maisu(self):
        pred = Prediction(1, Rank("Makuuchi", "Maegashira", 5, "E"), 0.9, "linear")
        actual = {1: Rank("Makuuchi", "Maegashira", 5, "W")}
        acc = evaluate([pred], actual)
        self.assertEqual(acc.exact_rate, 0.0)
        self.assertEqual(acc.mae_ranks, 0.5)
        self.assertEqual(acc.within1_rate, 1.0)

    def test_division_metric(self):
        preds = [
            Prediction(1, Rank("Makuuchi", "Maegashira", 17, "W"), 0.5, "linear"),
            Prediction(2, Rank("Juryo", "Numbered", 1, "E"), 0.5, "linear"),
        ]
        actual = {
            1: Rank("Juryo", "Numbered", 1, "E"),
            2: Rank("Juryo", "Numbered", 1, "W"),
        }
        acc = evaluate(preds, actual)
        self.assertEqual(acc.division_correct, 0.5)

    def test_empty_is_safe(self):
        acc = evaluate([], {})
        self.assertEqual(acc.n_rikishi, 0)


class TestParamsSerialization(unittest.TestCase):
    def test_roundtrip(self):
        import json
        p = PredictParams(coef_makuuchi=1.5)
        blob = json.dumps(p.to_json())
        back = json.loads(blob)
        self.assertEqual(back["coef_makuuchi"], 1.5)
        self.assertIn("model_version", back)


if __name__ == "__main__":
    unittest.main(verbosity=2)
