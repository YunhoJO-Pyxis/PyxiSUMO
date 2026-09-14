"""사이트 생성기의 표시 로직 테스트 (DB 불필요)."""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import ichimon as I                     # noqa: E402
from pyxisumo.heya_names import HEYA_JA, normalize     # noqa: E402
from pyxisumo.ranks import DIVISION_CAPACITY          # noqa: E402
from pyxisumo.site import guide as G                  # noqa: E402
from pyxisumo.site.build import (  # noqa: E402
    analytics_parts, banzuke_table, basho_label, csp_value, division_jump, e,
    rank_ko, rec_txt, with_ja,
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


class TestDivisionJump(unittest.TestCase):
    """'마쿠우치 / 쥬료' 바로가기 단추."""

    ROWS = [
        (0, "Makuuchi", "Yokozuna", 1, "E", "x", 12, 3, 0, 9, 1,
         "오노사토", "大の里", "Onosato", "", "니쇼노세키", "二所ノ関"),
        (10000, "Juryo", "Numbered", 1, "E", "x", 9, 6, 0, 3, 4,
         "엔도", "遠藤", "Endo", "", "오이와토", None),
    ]

    def test_makes_a_button_per_division(self):
        h = division_jump(self.ROWS)
        self.assertIn('href="#makuuchi"', h)
        self.assertIn('href="#juryo"', h)
        self.assertIn("마쿠우치", h)
        self.assertIn("쥬료", h)

    def test_anchors_exist_in_the_table(self):
        """단추가 가리키는 자리가 표 안에 실제로 있어야 한다.

        여기가 어긋나면 눌러도 아무 일이 없어 고장으로 보인다.
        """
        table = banzuke_table(self.ROWS)
        for anchor in re.findall(r'href="#([a-z]+)"', division_jump(self.ROWS)):
            self.assertIn(f'id="{anchor}"', table, f"#{anchor} 자리가 없음")

    def test_no_button_for_a_division_that_is_absent(self):
        only_maku = [self.ROWS[0]]
        h = division_jump(only_maku, extra=[("torikumi", "오늘의 대전")])
        self.assertNotIn("juryo", h)
        self.assertIn("오늘의 대전", h)

    def test_single_target_makes_no_bar(self):
        """단추가 하나뿐이면 줄을 만들지 않는다 — 누를 곳이 없는 막대는 군더더기."""
        self.assertEqual(division_jump([self.ROWS[0]]), "")

    def test_extra_links_come_first(self):
        h = division_jump(self.ROWS, extra=[("torikumi", "오늘의 대전")])
        self.assertLess(h.index("오늘의 대전"), h.index("마쿠우치"))


class TestIchimon(unittest.TestCase):
    """일문 표 — 사실을 주장하므로 모양과 개수를 묶어 둔다.

    출처: ja.wikipedia.org/wiki/相撲部屋 '현존하는 헤야' 표 (45곳, 2026-09 확인).
    常盤山 은 2026년 1월에 湊川 으로 개칭돼 표에는 없지만, API 에 아직
    남아 있어 별칭으로 하나 더 넣는다 → 니쇼노세키만 17+1 = 18.
    """

    EXPECTED = {"dewanoumi": 14, "nishonoseki": 18, "tokitsukaze": 5,
                "takasago": 4, "isegahama": 5}

    def test_counts_match_the_source(self):
        from collections import Counter
        got = dict(Counter(I.HEYA_ICHIMON.values()))
        self.assertEqual(got, self.EXPECTED)

    def test_every_value_is_a_known_ichimon(self):
        for heya, code in I.HEYA_ICHIMON.items():
            self.assertIn(code, I.ICHIMON_NAMES, f"{heya} 의 일문 코드가 표에 없음")

    def test_order_covers_every_ichimon(self):
        self.assertEqual(sorted(I.ICHIMON_ORDER), sorted(I.ICHIMON_NAMES))

    def test_keys_are_normalized(self):
        for k in I.HEYA_ICHIMON:
            self.assertEqual(k, normalize(k), f"{k} 는 정규화된 형태가 아니다")

    def test_every_heya_here_has_a_known_kanji(self):
        """일문을 아는 헤야는 한자도 알아야 한다 — 화면에 반쪽만 나오면 이상하다."""
        missing = [k for k in I.HEYA_ICHIMON if k not in HEYA_JA]
        self.assertEqual(missing, [], f"heya_names.py 에 없는 헤야: {missing}")

    def test_lookup_handles_real_api_spellings(self):
        self.assertEqual(I.ichimon_for("Nishonoseki"), "nishonoseki")
        self.assertEqual(I.ichimon_for("NISHONOSEKI"), "nishonoseki")
        self.assertEqual(I.ichimon_for("Nishonoseki-beya"), "nishonoseki")
        self.assertEqual(I.ichimon_for("Futagoyama"), "dewanoumi")

    def test_unknown_is_none_not_a_guess(self):
        """모르는 헤야에 일문을 붙이면 사이트가 거짓을 말한다."""
        self.assertIsNone(I.ichimon_for("Nonexistentbeya"))
        self.assertIsNone(I.ichimon_for(""))
        self.assertIsNone(I.ichimon_for(None))

    def test_label(self):
        self.assertEqual(I.ichimon_label("dewanoumi"), ("데와노우미", "出羽海"))
        self.assertEqual(I.ichimon_label(None), ("", ""))
        self.assertEqual(I.ichimon_label("nope"), ("", ""))

    def test_closed_heya_are_not_assigned(self):
        """없어진 헤야에 지금의 일문을 붙이지 않는다 (지금의 일문이 없으므로)."""
        for gone in ("miyagino", "oguruma", "azumazeki", "chiganoura",
                     "irumagawa", "minezaki", "kagamiyama"):
            self.assertNotIn(gone, I.HEYA_ICHIMON, f"{gone} 은 현존 헤야가 아니다")


class TestGuideContent(unittest.TestCase):
    """설명 페이지는 사실을 주장한다 — 그래서 검사한다.

    사람이 쓴 글이라 테스트가 어색해 보이지만, 여기에 적힌 정원은 예측
    엔진이 쓰는 숫자와 같아야 한다. 둘이 어긋나면 사이트가 자기 자신과
    다른 말을 하게 된다.
    """

    def rows_as_dict(self):
        # [한국어, 일본어, 정원, 구분, 설명]
        return {r[1]: r[2] for r in G.DIVISION_ROWS}

    def test_capacity_matches_engine(self):
        cap = self.rows_as_dict()
        self.assertEqual(cap["幕内"], f"{DIVISION_CAPACITY['Makuuchi']}명")
        self.assertEqual(cap["十両"], f"{DIVISION_CAPACITY['Juryo']}명")
        self.assertEqual(cap["幕下"], f"{DIVISION_CAPACITY['Makushita']}명")

    def test_divisions_are_in_order(self):
        self.assertEqual([r[0] for r in G.DIVISION_ROWS],
                         ["마쿠우치", "쥬료", "마쿠시타", "산단메",
                          "조니단", "조노쿠치"])

    def test_sekitori_marked_only_on_top_two(self):
        marked = [r[0] for r in G.DIVISION_ROWS if r[3] == "세키토리"]
        self.assertEqual(marked, ["마쿠우치", "쥬료"])

    def test_six_basho(self):
        self.assertEqual(len(G.BASHO_ROWS), 6)
        self.assertEqual([r[0] for r in G.BASHO_ROWS],
                         ["1월", "3월", "5월", "7월", "9월", "11월"])

    def test_no_html_in_text(self):
        """guide.py 는 글만 담는다. 태그를 적으면 화면에 태그가 보인다."""
        def walk(v):
            if isinstance(v, str):
                self.assertNotIn("<", v, f"태그로 보이는 글자: {v[:40]}")
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    walk(x)
        walk(G.SECTIONS)

    def test_section_ids_are_unique_and_url_safe(self):
        ids = [s["id"] for s in G.SECTIONS]
        self.assertEqual(len(ids), len(set(ids)))
        for i_ in ids:
            self.assertRegex(i_, r"^[a-z0-9-]+$")

    def test_known_block_kinds(self):
        for s in G.SECTIONS:
            for kind, _ in s["blocks"]:
                self.assertIn(kind, ("p", "note", "table", "dl"))

    def test_tables_are_rectangular(self):
        for s in G.SECTIONS:
            for kind, data in s["blocks"]:
                if kind == "table":
                    n = len(data["head"])
                    for r in data["rows"]:
                        self.assertEqual(len(r), n, f"{s['id']}: 칸 수가 다름")

    def test_sources_are_https(self):
        self.assertTrue(G.SOURCES)
        for _, url in G.SOURCES:
            self.assertTrue(url.startswith("https://"), url)


class TestAnalytics(unittest.TestCase):
    """기본은 '추적 없음' 이어야 한다."""

    def test_off_by_default(self):
        self.assertEqual(analytics_parts(""), ("", [], []))
        self.assertEqual(analytics_parts("   "), ("", [], []))

    def test_unknown_provider_is_ignored(self):
        self.assertEqual(analytics_parts("google:UA-1")[0], "")
        self.assertEqual(analytics_parts("goatcounter:")[0], "")

    def test_goatcounter(self):
        tag, s, c = analytics_parts("goatcounter:pyxisumo")
        self.assertIn("https://pyxisumo.goatcounter.com/count", tag)
        self.assertIn("https://gc.zgo.at", s)
        self.assertIn("https://pyxisumo.goatcounter.com", c)

    def test_code_cannot_break_out_of_the_url(self):
        """코드 칸에 이상한 글자가 들어와도 URL 이 바뀌면 안 된다."""
        tag, _, _ = analytics_parts('goatcounter:ab"/><script>x</script>')
        self.assertNotIn("<script>x", tag)
        self.assertIn("https://abscriptxscript.goatcounter.com/count", tag)

    def test_cloudflare_token_is_alnum_only(self):
        tag, _, _ = analytics_parts("cloudflare:abc123\"/>")
        self.assertIn('"token": "abc123"', tag)


class TestCsp(unittest.TestCase):
    def test_locked_down_by_default(self):
        v = csp_value([], [])
        self.assertIn("default-src 'none'", v)
        self.assertIn("script-src 'self'", v)
        self.assertIn("connect-src 'self'", v)
        self.assertNotIn("unsafe-eval", v)
        # 인라인 <script> 는 쓰지 않는다 — 열어 두면 XSS 방어가 무너진다
        self.assertNotIn("script-src 'self' 'unsafe-inline'", v)

    def test_analytics_host_is_allowed_when_enabled(self):
        _, s, c = analytics_parts("goatcounter:pyxisumo")
        v = csp_value(s, c)
        self.assertIn("script-src 'self' https://gc.zgo.at", v)
        self.assertIn("https://pyxisumo.goatcounter.com", v)


if __name__ == "__main__":
    unittest.main(verbosity=2)
