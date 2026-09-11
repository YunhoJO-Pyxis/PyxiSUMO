"""사이트 생성기의 표시 로직 테스트 (DB 불필요)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.site.build import (  # noqa: E402
    banzuke_table, basho_label, e, rank_ko, rec_txt, with_ja,
)


class TestEscape(unittest.TestCase):
    def test_html_is_escaped(self):
        self.assertEqual(e("<script>"), "&lt;script&gt;")
        self.assertEqual(e('a"b'), "a&quot;b")
        self.assertEqual(e("a&b"), "a&amp;b")

    def test_none_is_empty(self):
        self.assertEqual(e(None), "")

    def test_numbers(self):
        self.assertEqual(e(42), "42")


class TestRankKo(unittest.TestCase):
    def test_sanyaku(self):
        self.assertEqual(rank_ko("Yokozuna", 1, "E", "Makuuchi"), "동 요코즈나")
        self.assertEqual(rank_ko("Ozeki", 1, "W", "Makuuchi"), "서 오제키")

    def test_second_sanyaku_slot_shows_number(self):
        self.assertEqual(rank_ko("Sekiwake", 2, "E", "Makuuchi"), "동 세키와케 2")

    def test_maegashira_always_numbered(self):
        self.assertEqual(rank_ko("Maegashira", 1, "E", "Makuuchi"), "동 마에가시라 1")
        self.assertEqual(rank_ko("Maegashira", 17, "W", "Makuuchi"), "서 마에가시라 17")

    def test_juryo_uses_division_name(self):
        self.assertEqual(rank_ko("Numbered", 5, "W", "Juryo"), "서 쥬료 5")

    def test_no_english_leaks(self):
        for kind in ("Yokozuna", "Ozeki", "Sekiwake", "Komusubi", "Maegashira"):
            out = rank_ko(kind, 3, "E", "Makuuchi")
            self.assertNotIn(kind, out, f"{kind} 가 한국어 표기에 그대로 남았다")

    def test_empty_kind(self):
        self.assertEqual(rank_ko("", None, "E", "Makuuchi"), "")


class TestRecord(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(rec_txt(12, 3, 0), "12승 3패")

    def test_with_absences(self):
        self.assertEqual(rec_txt(5, 4, 6), "5승 4패 6휴")

    def test_no_record_is_blank(self):
        # 개막 전 대회 — 빈 줄이 표를 늘리지 않아야 한다
        self.assertEqual(rec_txt(0, 0, 0), "")

    def test_handles_strings(self):
        self.assertEqual(rec_txt("8", "7", "0"), "8승 7패")


class TestBashoLabel(unittest.TestCase):
    def test_format(self):
        self.assertEqual(basho_label("202609"), "2026년 9월")
        self.assertEqual(basho_label("202611"), "2026년 11월")

    def test_garbage_passes_through(self):
        self.assertEqual(basho_label(""), "")
        self.assertEqual(basho_label("abc"), "abc")


class TestBanzukeTable(unittest.TestCase):
    """rank_value 순서대로 東/西 를 한 줄에 묶는가."""

    def rows(self):
        # (rank_value, division, kind, num, side, label, w,l,a, net, id,
        #  name, ja, en, kana, heya, heya_ja)
        return [
            (0, "Makuuchi", "Yokozuna", 1, "E", "x", 12, 3, 0, 9, 1,
             "오노사토", "大の里", "Onosato", "", "니쇼노세키", "二所ノ関"),
            (1, "Makuuchi", "Yokozuna", 1, "W", "x", 11, 4, 0, 7, 2,
             "호쇼류", "豊昇龍", "Hoshoryu", "", "타츠나미", "立浪"),
            (400, "Makuuchi", "Maegashira", 1, "E", "x", 8, 7, 0, 1, 3,
             "우라", "宇良", "Ura", "", "키세", "木瀬"),
            (10000, "Juryo", "Numbered", 1, "E", "x", 9, 6, 0, 3, 4,
             "엔도", "遠藤", "Endo", "", "오이와토", None),
        ]

    def test_pairs_east_and_west(self):
        h = banzuke_table(self.rows())
        self.assertEqual(h.count('class="bz-row"'), 3,
                         "요코즈나 동·서는 한 줄로 묶여야 한다")

    def test_division_headers(self):
        h = banzuke_table(self.rows())
        self.assertIn("마쿠우치", h)
        self.assertIn("쥬료", h)

    def test_missing_side_is_marked_empty(self):
        h = banzuke_table(self.rows())
        self.assertIn("bz-side w empty", h.replace('"', ""))

    def test_names_are_escaped(self):
        rows = self.rows()
        rows[0] = rows[0][:11] + ("<script>x</script>",) + rows[0][12:]
        h = banzuke_table(rows)
        self.assertNotIn("<script>x", h)
        self.assertIn("&lt;script&gt;x", h)

    def test_links_use_depth(self):
        self.assertIn('href="rikishi/1.html"', banzuke_table(self.rows(), depth=0))
        self.assertIn('href="../rikishi/1.html"', banzuke_table(self.rows(), depth=1))

    def test_no_record_no_row(self):
        rows = [(0, "Makuuchi", "Yokozuna", 1, "E", "x", 0, 0, 0, 0, 1,
                 "오노사토", "大の里", "Onosato", "", "니쇼노세키", "二所ノ関")]
        h = banzuke_table(rows)
        self.assertNotIn("bz-rec", h, "성적이 없으면 성적 줄을 만들지 않는다")


    def test_heya_shows_japanese_alongside_korean(self):
        h = banzuke_table(self.rows())
        self.assertIn("니쇼노세키 (二所ノ関)", h)

    def test_heya_without_japanese_shows_korean_only(self):
        """한자를 모르는 헤야에 빈 괄호가 붙으면 안 된다."""
        h = banzuke_table(self.rows())
        self.assertIn("오이와토", h)
        self.assertNotIn("오이와토 (", h)


class TestWithJa(unittest.TestCase):
    def test_both(self):
        self.assertEqual(with_ja("니쇼노세키", "二所ノ関"), "니쇼노세키 (二所ノ関)")

    def test_missing_japanese(self):
        self.assertEqual(with_ja("니쇼노세키", None), "니쇼노세키")
        self.assertEqual(with_ja("니쇼노세키", ""), "니쇼노세키")
        self.assertEqual(with_ja("니쇼노세키", "   "), "니쇼노세키")

    def test_missing_korean(self):
        self.assertEqual(with_ja(None, "二所ノ関"), "二所ノ関")
        self.assertEqual(with_ja("", "二所ノ関"), "二所ノ関")

    def test_identical_is_not_doubled(self):
        """한국어 자리에 한자가 들어와 있을 때 '九重 (九重)' 이 되면 안 된다."""
        self.assertEqual(with_ja("九重", "九重"), "九重")

    def test_empty(self):
        self.assertEqual(with_ja(None, None), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
