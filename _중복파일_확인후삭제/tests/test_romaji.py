"""로마자 → 한글 음역 검증.

기대값은 사용자가 직접 만든 목업(index.html)의 표기를 기준으로 삼았다.
국립국어원 표기법이 아니라 **스모 팬·매체 표기**를 따른다는 뜻이다.
"""

from __future__ import annotations

import unittest

from pyxisumo.heya_names import japanese_for, normalize
from pyxisumo.romaji import to_hangul

# 목업에 실제로 등장한 이름들
MOCKUP = {
    "Hoshoryu": "호쇼류",
    "Onosato": "오노사토",
    "Kotozakura": "코토자쿠라",
    "Kirishima": "키리시마",
    "Daieisho": "다이에이쇼",
    "Wakamotoharu": "와카모토하루",
    "Abi": "아비",
    "Takayasu": "타카야스",
    "Kinbozan": "킨보잔",
    "Ura": "우라",
    "Tamawashi": "타마와시",
    "Hiradoumi": "히라도우미",
    "Shodai": "쇼다이",
    "Oho": "오호",
    "Atamifuji": "아타미후지",
    "Takerufuji": "타케루후지",
    "Churanoumi": "추라노우미",
    "Endo": "엔도",
    "Gonoyama": "고노야마",
    "Nishikigi": "니시키기",
    "Tobizaru": "토비자루",
    "Mitakeumi": "미타케우미",
    "Hokutofuji": "호쿠토후지",
    "Ryuden": "류덴",
    "Sadanoumi": "사다노우미",
    "Roga": "로가",
    "Shonannoumi": "쇼난노우미",
    "Tsurugisho": "츠루기쇼",
    "Kagayaki": "카가야키",
    "Myogiryu": "묘기류",
    "Chiyoshoma": "치요쇼마",
    "Nishikifuji": "니시키후지",
    "Bushozan": "부쇼잔",
    "Tokihayate": "토키하야테",
    "Kitanowaka": "키타노와카",
    "Asakoryu": "아사코류",
    "Shishi": "시시",
    "Aonishiki": "아오니시키",
}

HEYA = {
    "Tatsunami": "타츠나미",
    "Nishonoseki": "니쇼노세키",
    "Sadogatake": "사도가타케",
    "Michinoku": "미치노쿠",
    "Oitekaze": "오이테카제",
    "Takadagawa": "타카다가와",
    "Isegahama": "이세가하마",
    "Kokonoe": "코코노에",
    "Tokitsukaze": "토키츠카제",
    "Dewanoumi": "데와노우미",
    "Kasugano": "카스가노",
    "Arashio": "아라시오",
    "Hakkaku": "핫카쿠",
}


class TestRomaji(unittest.TestCase):
    def test_mockup_names(self):
        bad = {k: (v, to_hangul(k)) for k, v in MOCKUP.items()
               if to_hangul(k) != v}
        self.assertEqual(bad, {}, f"목업 표기와 어긋남: {bad}")

    def test_heya_names(self):
        bad = {k: (v, to_hangul(k)) for k, v in HEYA.items()
               if to_hangul(k) != v}
        self.assertEqual(bad, {}, f"헤야 표기와 어긋남: {bad}")

    def test_empty(self):
        for v in (None, "", "   "):
            self.assertEqual(to_hangul(v), "")

    def test_macron_and_apostrophe(self):
        # 장음 부호는 짧은 모음으로 눌러 적는다
        self.assertEqual(to_hangul("Hōshōryū"), "호쇼류")
        self.assertEqual(to_hangul("Hoshoryu"), to_hangul("Hōshōryū"))
        # 어퍼스트로피(ん 구분)는 표기에 영향을 주지 않는다
        self.assertEqual(to_hangul("Jun'ichi"), to_hangul("Junichi"))

    def test_sokuon(self):
        # 겹자음 = 촉음 → 앞 음절 ㅅ받침
        self.assertEqual(to_hangul("Hakkaku"), "핫카쿠")
        self.assertEqual(to_hangul("Nikki"), "닛키")

    def test_final_n(self):
        self.assertEqual(to_hangul("Kinbozan"), "킨보잔")
        self.assertEqual(to_hangul("Endo"), "엔도")
        # ん 뒤에 모음이 오면 な행이지 받침이 아니다
        self.assertEqual(to_hangul("Shonannoumi"), "쇼난노우미")

    def test_two_words(self):
        self.assertEqual(to_hangul("Onosato Daiki"), "오노사토 다이키")

    def test_terminates_on_garbage(self):
        """해석 못 하는 입력에도 무한 루프에 빠지지 않는다.

        빈 음절(발음 n)에서 인덱스를 전진시키지 않아 멈추지 않던 버그가 있었다.
        """
        for s in ("xyz", "n", "nn", "----", "Onosato (大の里)", "123"):
            with self.subTest(s=s):
                self.assertIsInstance(to_hangul(s), str)

    def test_idempotent_on_hangul(self):
        # 이미 한글인 값이 들어와도 글자를 잃지 않는다
        self.assertIn("오", to_hangul("오노사토") or "오")

    def test_no_latin_left_for_common_names(self):
        """정상적인 시코나를 넣으면 라틴 문자가 남지 않아야 한다."""
        for name in list(MOCKUP) + list(HEYA):
            with self.subTest(name=name):
                out = to_hangul(name)
                self.assertFalse(any("a" <= c.lower() <= "z" for c in out),
                                 f"{name} → {out} 에 로마자가 남음")


class TestHeyaNames(unittest.TestCase):
    def test_known(self):
        self.assertEqual(japanese_for("Nishonoseki"), "二所ノ関")
        self.assertEqual(japanese_for("Isegahama"), "伊勢ヶ濱")

    def test_case_and_suffix(self):
        self.assertEqual(japanese_for("TATSUNAMI"), "立浪")
        self.assertEqual(japanese_for("Tatsunami-beya"), "立浪")
        self.assertEqual(japanese_for("tatsunami beya"), "立浪")

    def test_unknown_returns_none_not_guess(self):
        """모르는 헤야에 한자를 지어내면 안 된다.

        틀린 한자는 비어 있는 것보다 나쁘다 — 사이트가 사실을 주장하게 된다.
        """
        self.assertIsNone(japanese_for("Nonexistentbeya"))
        self.assertIsNone(japanese_for(""))
        self.assertIsNone(japanese_for(None))

    def test_no_beya_suffix_keys(self):
        """'otakebeya' 같은 키를 두면 한자→로마자 역방향에서 '오타케베야'가 된다.

        접미사는 japanese_for() 가 알아서 떼므로 표에는 본명만 둔다.
        """
        from pyxisumo.heya_names import HEYA_JA
        bad = [k for k in HEYA_JA if k.endswith("beya")]
        self.assertEqual(bad, [], f"접미사가 붙은 키: {bad}")

    def test_reverse_lookup(self):
        from pyxisumo.heya_names import romaji_for_ja
        self.assertEqual(romaji_for_ja("二所ノ関"), "nishonoseki")
        self.assertEqual(romaji_for_ja("大嶽"), "otake")
        self.assertIsNone(romaji_for_ja("存在しない"))
        self.assertIsNone(romaji_for_ja(None))

    def test_round_trip(self):
        """표에 있는 모든 헤야는 한자 → 로마자 → 한자 로 돌아와야 한다."""
        from pyxisumo.heya_names import HEYA_JA, japanese_for, romaji_for_ja
        for ja in set(HEYA_JA.values()):
            with self.subTest(ja=ja):
                en = romaji_for_ja(ja)
                self.assertIsNotNone(en)
                self.assertEqual(japanese_for(en), ja)

    def test_no_latin_in_table(self):
        from pyxisumo.heya_names import HEYA_JA
        for k, v in HEYA_JA.items():
            with self.subTest(k=k):
                self.assertEqual(k, normalize(k), "키는 정규화된 형태여야 한다")
                self.assertFalse(any("a" <= c.lower() <= "z" for c in v),
                                 f"{k} 의 값 {v} 에 로마자가 섞임")


if __name__ == "__main__":
    unittest.main()
