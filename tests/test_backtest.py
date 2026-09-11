"""과거 검증(backtest) 대회 선택 로직 테스트.

개막 전 대회는 반즈케만 있고 성적이 0이라 근거가 될 수 없다.
2026-09-11 시점이 정확히 그 상황이다 — 202609 반즈케는 발표됐지만
9/13 개막이라 성적은 전부 0이다.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.run_predict import choose_backtest_pair, next_basho, prev_basho  # noqa: E402


def row(basho: str, n: int, played: int) -> tuple:
    return (basho, n, played)


class TestChoosePair(unittest.TestCase):
    def test_todays_situation(self):
        """202609 는 발표만 됐고 성적 0 — 근거가 될 수 없다."""
        rows = [
            row("202609", 70, 0),      # 개막 전
            row("202607", 70, 1050),   # 끝남
            row("202605", 70, 1050),
        ]
        self.assertEqual(choose_backtest_pair(rows), ("202607", "202609"),
                         "202607 성적으로 202609 반즈케를 맞춰보는 것이 맞다")

    def test_skips_target_whose_source_has_no_results(self):
        rows = [
            row("202611", 70, 0),      # 아직 발표도 성적도 없음
            row("202609", 70, 0),      # 개막 전 → 근거 불가
            row("202607", 70, 1050),
        ]
        # 202611 의 근거는 202609 인데 성적이 0 → 건너뛰고 202609/202607 짝
        self.assertEqual(choose_backtest_pair(rows), ("202607", "202609"))

    def test_picks_most_recent_valid_pair(self):
        rows = [
            row("202607", 70, 1050),
            row("202605", 70, 1050),
            row("202603", 70, 1050),
        ]
        self.assertEqual(choose_backtest_pair(rows), ("202605", "202607"))

    def test_none_when_no_results_at_all(self):
        rows = [row("202609", 70, 0), row("202607", 70, 0)]
        self.assertIsNone(choose_backtest_pair(rows))

    def test_none_when_gap_breaks_the_chain(self):
        # 202607 의 직전은 202605 인데 데이터가 없다
        rows = [row("202607", 70, 1050), row("202601", 70, 1050)]
        self.assertIsNone(choose_backtest_pair(rows))

    def test_empty_input(self):
        self.assertIsNone(choose_backtest_pair([]))

    def test_target_must_have_a_banzuke(self):
        rows = [row("202609", 0, 0), row("202607", 70, 1050),
                row("202605", 70, 1050)]
        self.assertEqual(choose_backtest_pair(rows), ("202605", "202607"),
                         "반즈케가 0행인 대회는 채점 대상이 될 수 없다")


class TestBashoArithmetic(unittest.TestCase):
    def test_round_trip(self):
        for b in ("202601", "202603", "202609", "202611"):
            self.assertEqual(prev_basho(next_basho(b)), b)

    def test_year_boundaries(self):
        self.assertEqual(next_basho("202611"), "202701")
        self.assertEqual(prev_basho("202701"), "202611")

    def test_only_odd_months(self):
        b = "202601"
        for _ in range(12):
            self.assertEqual(int(b[4:]) % 2, 1, b)
            b = next_basho(b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
