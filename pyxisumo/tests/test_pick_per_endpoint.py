"""엔드포인트마다 키 이름이 다를 때 pick 이 옳게 동작하는가.

2026-09-11 에 보고된 실제 실패:
  리키시 목록은 'id', 반즈케는 'rikishiID'(대문자 D) 를 쓴다.
  학습된 전역 대응이 'id' 로 굳는 바람에 반즈케 행에서 아무것도 못 찾았고,
  **반즈케 0행이 '완료' 로 기록된 채** 설치가 끝났다.
  에러도 경고도 없었다 — 가장 위험한 종류의 실패다.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import fieldmap  # noqa: E402
from pyxisumo.sumoapi import FIELD_ALIASES, normalize, pick  # noqa: E402

# 실제 응답 모양 (관찰된 것 + 그럴듯한 변형)
RIKISHI_ROW = {"id": 45, "shikonaEn": "Onosato", "heya": "Nishonoseki"}
BANZUKE_ROW = {"side": "East", "rikishiID": 45, "shikonaEn": "Onosato",
               "rank": "Yokozuna 1 East", "wins": 12, "losses": 3, "absences": 0}


class TestCrossEndpoint(unittest.TestCase):
    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}
        # probe 가 리키시 목록을 먼저 보므로 전역 대응은 'id' 로 굳는다
        fieldmap.install({"rikishi_id": "id"})

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_the_reported_failure(self):
        """이 한 줄이 반즈케 0행의 원인이었다."""
        self.assertEqual(pick(BANZUKE_ROW, "rikishi_id"), 45)

    def test_other_endpoint_still_works(self):
        self.assertEqual(pick(RIKISHI_ROW, "rikishi_id"), 45)

    def test_case_variants(self):
        for key in ("rikishiID", "rikishiId", "RikishiId", "RIKISHI_ID",
                    "rikishi-id", "rikishi id"):
            with self.subTest(key=key):
                self.assertEqual(pick({key: 45}, "rikishi_id"), 45)

    def test_specific_wins_even_across_match_kinds(self):
        # 'id' 는 정확 일치, 'rikishiID' 는 정규화 일치.
        # 둘을 나눠서 보면 'id' 가 먼저 잡혀 엉뚱한 값이 들어간다.
        row = {"id": 999, "rikishiID": 45}
        self.assertEqual(pick(row, "rikishi_id"), 45)

    def test_normalize_equivalence(self):
        for a, b in [("rikishiID", "rikishi_id"), ("eastId", "EAST-ID"),
                     ("shikonaEn", "shikona en")]:
            self.assertEqual(normalize(a), normalize(b), f"{a} ≡ {b}")

    def test_unrelated_keys_are_not_matched(self):
        self.assertIsNone(
            pick({"idx": 1, "identifier": 2}, "rikishi_id", required=False),
            "비슷해 보이는 이름을 아무거나 집으면 안 된다")

    def test_missing_required_raises_with_actual_keys(self):
        with self.assertRaises(KeyError) as ctx:
            pick({"foo": 1, "bar": 2}, "rikishi_id")
        msg = str(ctx.exception)
        self.assertIn("foo", msg, "실제 키를 알려줘야 고칠 수 있다")

    def test_rank_from_banzuke(self):
        self.assertEqual(pick(BANZUKE_ROW, "rank"), "Yokozuna 1 East")

    def test_record_fields_from_banzuke(self):
        self.assertEqual(pick(BANZUKE_ROW, "wins"), 12)
        self.assertEqual(pick(BANZUKE_ROW, "losses"), 3)
        self.assertEqual(pick(BANZUKE_ROW, "absences"), 0)


class TestPickDoesNotDependOnLearning(unittest.TestCase):
    """학습이 아예 없어도, 혹은 틀렸어도 동작해야 한다."""

    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_works_without_any_learning(self):
        self.assertEqual(pick(BANZUKE_ROW, "rikishi_id"), 45)

    def test_works_with_wrong_learning(self):
        fieldmap.install({"rikishi_id": "totallyWrongKey"})
        self.assertEqual(pick(BANZUKE_ROW, "rikishi_id"), 45,
                         "학습이 틀려도 응답의 실제 키로 찾아내야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
