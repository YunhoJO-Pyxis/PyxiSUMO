"""필드맵 자동 학습 테스트.

Sumo-API 의 실제 응답을 볼 수 없는 상태에서도 학습 로직이 맞는지 확인한다.
실제로 있을 법한 표기 변형(camelCase / snake_case / 축약)을 모두 넣었다.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import fieldmap  # noqa: E402
from pyxisumo.sumoapi import FIELD_ALIASES, pick  # noqa: E402


class TestNormalize(unittest.TestCase):
    def test_variants_collapse(self):
        for k in ("rikishiId", "rikishi_id", "RIKISHI-ID", "Rikishi Id"):
            self.assertEqual(fieldmap.normalize(k), "rikishiid")


class TestLearn(unittest.TestCase):
    def test_exact_alias(self):
        rows = [{"id": 45, "shikonaEn": "Onosato", "heya": "Nishonoseki"}]
        got = fieldmap.learn(rows, ["rikishi_id", "shikona_en", "heya"], FIELD_ALIASES)
        self.assertEqual(got["rikishi_id"], "id")
        self.assertEqual(got["shikona_en"], "shikonaEn")

    def test_case_and_separator_variants(self):
        rows = [{"Rikishi_ID": 45, "shikona_en": "Onosato", "Heya": "Nishonoseki"}]
        got = fieldmap.learn(rows, ["rikishi_id", "shikona_en", "heya"], FIELD_ALIASES)
        self.assertEqual(got["rikishi_id"], "Rikishi_ID")
        self.assertEqual(got["shikona_en"], "shikona_en")
        self.assertEqual(got["heya"], "Heya")

    def test_type_guard_rejects_wrong_kind(self):
        # 'wins' 후보 'w' 가 문자열이면 숫자 필드로 채택하지 않는다
        rows = [{"w": "west", "wins": 8, "losses": 7}]
        got = fieldmap.learn(rows, ["wins"], FIELD_ALIASES)
        self.assertEqual(got["wins"], "wins")

    def test_numeric_string_counts_as_int(self):
        rows = [{"wins": "8", "losses": "7"}]
        got = fieldmap.learn(rows, ["wins", "losses"], FIELD_ALIASES)
        self.assertEqual(got["wins"], "wins")

    def test_missing_field_is_omitted(self):
        rows = [{"id": 1}]
        got = fieldmap.learn(rows, ["rikishi_id", "kimarite"], FIELD_ALIASES)
        self.assertIn("rikishi_id", got)
        self.assertNotIn("kimarite", got, "없는 필드를 추측해서 채우면 안 된다")

    def test_uses_first_non_null_value_across_rows(self):
        # 첫 행의 값이 None 이어도 뒷 행을 보고 타입을 판정해야 한다
        rows = [{"eastId": None, "westId": None}, {"eastId": 12, "westId": 34}]
        got = fieldmap.learn(rows, ["east_id", "west_id"], FIELD_ALIASES)
        self.assertEqual(got["east_id"], "eastId")
        self.assertEqual(got["west_id"], "westId")

    def test_empty_rows_returns_empty(self):
        self.assertEqual(fieldmap.learn([], ["rikishi_id"], FIELD_ALIASES), {})


class TestInstall(unittest.TestCase):
    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_install_puts_learned_key_first(self):
        fieldmap.install({"rikishi_id": "wrestlerId"})
        self.assertEqual(FIELD_ALIASES["rikishi_id"][0], "wrestlerId")

    def test_pick_uses_installed_key(self):
        fieldmap.install({"rikishi_id": "wrestlerId"})
        self.assertEqual(pick({"wrestlerId": 7}, "rikishi_id"), 7)

    def test_install_is_idempotent(self):
        fieldmap.install({"rikishi_id": "wrestlerId"})
        before = len(FIELD_ALIASES["rikishi_id"])
        fieldmap.install({"rikishi_id": "wrestlerId"})
        self.assertEqual(len(FIELD_ALIASES["rikishi_id"]), before)

    def test_unknown_logical_field_is_added(self):
        fieldmap.install({"brand_new": "someKey"})
        self.assertEqual(FIELD_ALIASES["brand_new"], ["someKey"])


class TestPickSpecificity(unittest.TestCase):
    """한 응답에 후보가 여럿일 때 더 구체적인 이름을 택해야 한다.

    반즈케 행에 'id'(행 고유번호)와 'rikishiId'(리키시 번호)가 함께 있을 때
    'id' 를 집으면 조용히 엉뚱한 리키시가 들어간다 — 에러도 안 난다.
    """

    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_specific_wins_over_generic(self):
        row = {"id": 9999, "rikishiId": 45, "rank": "Yokozuna 1 East"}
        self.assertEqual(pick(row, "rikishi_id"), 45)

    def test_generic_used_when_alone(self):
        self.assertEqual(pick({"id": 45}, "rikishi_id"), 45)

    def test_learned_key_still_wins_among_equals(self):
        fieldmap.install({"rikishi_id": "wrestlerId"})
        row = {"wrestlerId": 7, "rikishiId": 45}
        self.assertEqual(pick(row, "rikishi_id"), 7,
                         "길이가 비슷하면 학습된 키가 우선")

    def test_missing_required_still_raises(self):
        with self.assertRaises(KeyError):
            pick({"somethingElse": 1}, "rikishi_id")

    def test_optional_missing_returns_none(self):
        self.assertIsNone(pick({"x": 1}, "kimarite", required=False))


class TestLocalCache(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "field_map.json")
            fieldmap.save_local({"rikishi_id": "id"}, path)
            self.assertEqual(fieldmap.load_local(path), {"rikishi_id": "id"})

    def test_missing_file_is_empty(self):
        self.assertEqual(fieldmap.load_local("/nonexistent/field_map.json"), {})


class TestEndToEndShape(unittest.TestCase):
    """실제로 올 법한 응답 3가지 변형에서 모두 필수 필드가 잡히는지."""

    VARIANTS = [
        # camelCase (가장 유력)
        {"id": 45, "sumoApiId": 45, "shikonaEn": "Onosato", "shikonaJp": "大の里",
         "heya": "Nishonoseki", "birthDate": "2000-06-07",
         "height": 192.0, "weight": 185.0, "debut": "202305"},
        # snake_case
        {"rikishi_id": 45, "shikona_en": "Onosato", "shikona_jp": "大の里",
         "stable": "Nishonoseki", "birth_date": "2000-06-07",
         "height_cm": 192.0, "weight_kg": 185.0, "debut_basho": "202305"},
        # 축약형
        {"id": 45, "shikonaEng": "Onosato", "nameJp": "大の里",
         "heyaEn": "Nishonoseki", "dob": "2000-06-07"},
    ]

    def test_required_fields_found(self):
        for i, row in enumerate(self.VARIANTS):
            with self.subTest(variant=i):
                got = fieldmap.learn([row], ["rikishi_id", "shikona_en", "heya"],
                                     FIELD_ALIASES)
                for f in ("rikishi_id", "shikona_en", "heya"):
                    self.assertIn(f, got, f"변형 {i} 에서 {f} 를 못 찾음")

    def test_learned_map_actually_resolves(self):
        backup = {k: list(v) for k, v in FIELD_ALIASES.items()}
        try:
            for row in self.VARIANTS:
                got = fieldmap.learn([row], ["rikishi_id", "shikona_en"], FIELD_ALIASES)
                fieldmap.install(got)
                self.assertEqual(pick(row, "rikishi_id"), 45)
                self.assertEqual(pick(row, "shikona_en"), "Onosato")
        finally:
            FIELD_ALIASES.clear()
            FIELD_ALIASES.update(backup)


if __name__ == "__main__":
    unittest.main(verbosity=2)
