"""지위 파싱·인코딩 테스트 (stdlib unittest)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.ranks import (  # noqa: E402
    Rank,
    RankParseError,
    parse_rank,
    rank_value,
    slots_for,
)


class TestParse(unittest.TestCase):
    def test_english_forms(self):
        cases = {
            "Yokozuna 1 East": Rank("Makuuchi", "Yokozuna", 1, "E"),
            "Ozeki 2 West": Rank("Makuuchi", "Ozeki", 2, "W"),
            "Sekiwake 1 East": Rank("Makuuchi", "Sekiwake", 1, "E"),
            "Komusubi 1 West": Rank("Makuuchi", "Komusubi", 1, "W"),
            "Maegashira 17 West": Rank("Makuuchi", "Maegashira", 17, "W"),
            "Juryo 3 East": Rank("Juryo", "Numbered", 3, "E"),
            "Makushita 15 West": Rank("Makushita", "Numbered", 15, "W"),
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_rank(raw), want)

    def test_japanese_forms(self):
        self.assertEqual(parse_rank("東前頭5枚目"), Rank("Makuuchi", "Maegashira", 5, "E"))
        self.assertEqual(parse_rank("西大関"), Rank("Makuuchi", "Ozeki", None, "W"))
        self.assertEqual(parse_rank("東十両3枚目"), Rank("Juryo", "Numbered", 3, "E"))

    def test_yokozuna_ozeki_is_yokozuna(self):
        # 横綱大関(오제키 공석 시 요코즈나 겸임)은 요코즈나로 취급
        self.assertEqual(parse_rank("Yokozuna-Ozeki 1 East").kind, "Yokozuna")

    def test_side_is_required(self):
        # 동/서가 없으면 조용히 East 로 넣지 않고 예외를 낸다
        with self.assertRaises(RankParseError):
            parse_rank("Maegashira 3")

    def test_garbage_raises(self):
        for bad in ("", "   ", "Sekitori-San 1 East", "???"):
            with self.subTest(bad=bad), self.assertRaises(RankParseError):
                parse_rank(bad)

    def test_division_hint(self):
        self.assertEqual(
            parse_rank("3 East", division_hint="Juryo"),
            Rank("Juryo", "Numbered", 3, "E"),
        )


class TestRankValue(unittest.TestCase):
    def test_east_beats_west(self):
        e = rank_value("Makuuchi", "Maegashira", 3, "E")
        w = rank_value("Makuuchi", "Maegashira", 3, "W")
        self.assertLess(e, w)

    def test_full_ordering(self):
        order = [
            Rank("Makuuchi", "Yokozuna", 1, "E"),
            Rank("Makuuchi", "Yokozuna", 1, "W"),
            Rank("Makuuchi", "Ozeki", 1, "E"),
            Rank("Makuuchi", "Sekiwake", 1, "E"),
            Rank("Makuuchi", "Sekiwake", 2, "E"),
            Rank("Makuuchi", "Komusubi", 1, "E"),
            Rank("Makuuchi", "Maegashira", 1, "E"),
            Rank("Makuuchi", "Maegashira", 17, "W"),
            Rank("Juryo", "Numbered", 1, "E"),
            Rank("Juryo", "Numbered", 14, "W"),
            Rank("Makushita", "Numbered", 1, "E"),
        ]
        values = [r.value for r in order]
        self.assertEqual(values, sorted(values), "서열이 단조증가하지 않는다")
        self.assertEqual(len(set(values)), len(values), "값이 중복된다")

    def test_sanyaku_third_slot_no_collision(self):
        # 張出는 1994년 폐지 → 3번째 세키와케도 같은 규칙으로 이어 붙는다
        vals = [Rank("Makuuchi", "Sekiwake", n, s).value
                for n in (1, 2, 3) for s in ("E", "W")]
        self.assertEqual(len(set(vals)), 6)
        self.assertLess(max(vals), Rank("Makuuchi", "Komusubi", 1, "E").value)

    def test_makuuchi_numbered_rejected(self):
        # Makuuchi + 'Numbered' 는 Yokozuna 와 값이 겹치므로 금지
        with self.assertRaises(RankParseError):
            rank_value("Makuuchi", "Numbered", 1, "E")

    def test_lower_division_kind_enforced(self):
        with self.assertRaises(RankParseError):
            rank_value("Juryo", "Maegashira", 1, "E")

    def test_no_cross_division_overlap(self):
        maku_max = max(
            Rank("Makuuchi", "Maegashira", n, s).value
            for n in range(1, 25) for s in ("E", "W")
        )
        juryo_min = Rank("Juryo", "Numbered", 1, "E").value
        self.assertLess(maku_max, juryo_min)


class TestSlots(unittest.TestCase):
    def test_slot_sequence(self):
        self.assertEqual(
            list(slots_for("Makuuchi", 5)),
            [(1, "E"), (1, "W"), (2, "E"), (2, "W"), (3, "E")],
        )

    def test_slot_count(self):
        self.assertEqual(len(list(slots_for("Juryo", 28))), 28)
        self.assertEqual(list(slots_for("Juryo", 28))[-1], (14, "W"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
