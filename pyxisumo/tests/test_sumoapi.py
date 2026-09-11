"""Sumo-API 클라이언트 테스트 (네트워크 없이).

이 API 는 문서가 없어서 엔드포인트마다 요구사항이 다르다.
실제로 확인된 것:
  - /api/kimarite 는 매개변수 없이 부르면 HTTP 400 (2026-09 확인)
  - /api/basho/{id}/torikumi/... 는 목록을 한 겹 감싸서 준다
  - 개막 전 바쇼의 취조는 대회 정보 껍데기만 온다
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.sumoapi import SumoApi, SumoApiError, rows_of  # noqa: E402


class RecordingApi(SumoApi):
    """get() 만 갈아끼워 네트워크 없이 동작을 본다."""

    def __init__(self, responses):
        super().__init__(min_interval=0)
        self.responses = responses      # callable(path, params) -> data | raise
        self.calls: list[tuple[str, dict]] = []

    def get(self, path, **params):
        self.calls.append((path, params))
        return self.responses(path, params)


class TestKimariteRetry(unittest.TestCase):
    DATA = [{"kimarite": "yorikiri", "nameEn": "Yorikiri"}]

    def test_retries_with_params_on_400(self):
        def responses(path, params):
            if not params:
                raise SumoApiError("HTTP 400 for /api/kimarite")
            return self.DATA

        api = RecordingApi(responses)
        self.assertEqual(api.kimarite(), self.DATA)
        self.assertTrue(api.calls[0][1], "첫 시도부터 매개변수를 붙인다")

    def test_first_success_wins(self):
        api = RecordingApi(lambda p, q: self.DATA)
        api.kimarite()
        self.assertEqual(len(api.calls), 1, "성공하면 더 시도하지 않는다")

    def test_tries_every_param_set_then_raises(self):
        def responses(path, params):
            raise SumoApiError("HTTP 400 for /api/kimarite")

        api = RecordingApi(responses)
        with self.assertRaises(SumoApiError):
            api.kimarite()
        self.assertEqual(len(api.calls), len(SumoApi.KIMARITE_PARAM_SETS))

    def test_non_400_error_is_not_retried(self):
        def responses(path, params):
            raise SumoApiError("HTTP 500 for /api/kimarite")

        api = RecordingApi(responses)
        with self.assertRaises(SumoApiError):
            api.kimarite()
        self.assertEqual(len(api.calls), 1,
                         "서버 오류는 매개변수 문제가 아니므로 조합을 바꿔봐야 소용없다")

    def test_none_response_moves_on(self):
        calls = {"n": 0}

        def responses(path, params):
            calls["n"] += 1
            return None if calls["n"] == 1 else self.DATA

        api = RecordingApi(responses)
        self.assertEqual(api.kimarite(), self.DATA)


class TestRowsOf(unittest.TestCase):
    ROW = {"eastId": 1, "westId": 2}

    def test_plain_list(self):
        self.assertEqual(rows_of([self.ROW]), [self.ROW])

    def test_named_envelope(self):
        self.assertEqual(rows_of({"records": [self.ROW]}), [self.ROW])

    def test_torikumi_envelope_with_metadata(self):
        # 실제 관찰된 모양
        data = {"date": "202607", "startDate": "x", "endDate": "y",
                "torikumi": [self.ROW]}
        self.assertEqual(rows_of(data), [self.ROW])

    def test_unknown_envelope_name(self):
        self.assertEqual(rows_of({"meta": 1, "whateverList": [self.ROW]}), [self.ROW])

    def test_ambiguous_envelope_is_refused(self):
        self.assertEqual(rows_of({"a": [self.ROW], "b": [self.ROW]}), [],
                         "목록이 둘이면 추측하지 않는다")

    def test_east_west_split_marks_side(self):
        rows = rows_of({"east": [{"id": 1}], "west": [{"id": 2}]})
        self.assertEqual([r["_side"] for r in rows], ["E", "W"])

    def test_shell_without_list_is_empty(self):
        self.assertEqual(rows_of({"date": "202609", "startDate": "x"}), [])

    def test_empty_list_inside_envelope(self):
        self.assertEqual(rows_of({"date": "202609", "torikumi": []}), [])

    def test_none_and_scalars(self):
        self.assertEqual(rows_of(None), [])
        self.assertEqual(rows_of("text"), [])
        self.assertEqual(rows_of(42), [])

    def test_list_of_non_dicts_is_filtered(self):
        self.assertEqual(rows_of([1, "x", self.ROW]), [self.ROW])


if __name__ == "__main__":
    unittest.main(verbosity=2)
