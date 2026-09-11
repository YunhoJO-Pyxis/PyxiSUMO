"""필드 학습 probe 의 되짚기(fallback) 동작 테스트.

아직 시작하지 않은 바쇼의 취조(대전 결과)를 물으면 빈 배열이 온다.
빈 응답에서는 배울 것이 없으므로 끝난 바쇼로 되짚어 내려가야 한다.
(2026-09-11 에 202609 로 probe 를 돌려 east_id/west_id 가 미해결로 남은 실제 사례)
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo import probe  # noqa: E402
from pyxisumo.sumoapi import FIELD_ALIASES  # noqa: E402

RIKISHI = [{"id": 45, "shikonaEn": "Onosato", "shikonaJp": "大の里",
            "heya": "Nishonoseki", "birthDate": "2000-06-07",
            "height": 192.0, "weight": 185.0, "debut": "202305"}]

BANZUKE = [{"rikishiId": 45, "rank": "Yokozuna 1 East", "wins": 12,
            "losses": 3, "absences": 0}]

TORIKUMI = [{"bashoId": "202607", "day": 1, "matchNo": 1,
             "eastId": 45, "eastShikona": "Onosato",
             "westId": 12, "westShikona": "Hoshoryu",
             "winnerId": 45, "kimarite": "yorikiri"}]


class FakeApi:
    """202609 는 아직 시작 전이라 취조가 비어 있는 상황을 재현한다."""

    def __init__(self, started: set[str] | None = None):
        self.started = started if started is not None else {"202607", "202605"}
        self.torikumi_calls: list[tuple[str, int]] = []
        self.banzuke_calls: list[str] = []

    def rikishis(self, **kw):
        return RIKISHI

    def rikishi(self, rid):
        return RIKISHI[0]

    def basho(self, basho_id):
        return {"date": basho_id, "startDate": "2026-09-13", "endDate": "2026-09-27"}

    def banzuke(self, basho_id, division):
        self.banzuke_calls.append(basho_id)
        return BANZUKE

    def torikumi(self, basho_id, division, day):
        self.torikumi_calls.append((basho_id, day))
        return TORIKUMI if basho_id in self.started else []

    def kimarite(self):
        return [{"kimarite": "yorikiri", "nameEn": "Yorikiri"}]


class TestFallback(unittest.TestCase):
    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_falls_back_to_finished_basho(self):
        api = FakeApi()
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)

        self.assertEqual(api.torikumi_calls[0], ("202609", 1),
                         "먼저 요청받은 바쇼를 시도해야 한다")
        self.assertIn(("202607", 1), api.torikumi_calls,
                      "비어 있으면 이전 바쇼로 되짚어야 한다")
        self.assertEqual(mapping.get("east_id"), "eastId")
        self.assertEqual(mapping.get("west_id"), "westId")
        self.assertEqual(unresolved, [],
                         f"미해결이 남으면 안 된다: {unresolved}")

    def test_stops_as_soon_as_rows_are_found(self):
        api = FakeApi()
        probe.run_probe(api, basho="202609", verbose=False)
        after_hit = api.torikumi_calls[api.torikumi_calls.index(("202607", 1)) + 1:]
        self.assertEqual(after_hit, [], "행을 찾으면 더 호출하지 않아야 한다")

    def test_empty_everywhere_is_warning_not_failure(self):
        # 모든 바쇼가 비어 있어도 '해석 실패' 로 막지는 않는다 —
        # 배울 응답 자체가 없는 것과, 키를 못 알아본 것은 다른 문제다.
        api = FakeApi(started=set())
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)
        self.assertTrue(report["torikumi"]["empty"])
        self.assertEqual(report["torikumi"]["missing_required"], [])
        self.assertNotIn("east_id", unresolved)
        # 다른 엔드포인트는 정상 학습되어야 한다
        self.assertEqual(mapping.get("rikishi_id"), "id")
        self.assertEqual(mapping.get("rank"), "rank")

    def test_unknown_keys_are_still_reported(self):
        """응답은 있는데 키를 못 알아본 경우는 확실히 실패로 잡아야 한다."""
        class OddApi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return [{"leftWrestler": 45, "rightWrestler": 12}]

        api = OddApi(started={"202609"})
        _, unresolved, report = probe.run_probe(api, basho="202609", verbose=False)
        self.assertIn("east_id", unresolved)
        self.assertFalse(report["torikumi"]["empty"])
        self.assertIn("leftWrestler", report["torikumi"]["keys"],
                      "실제 키 목록을 리포트에 남겨야 사용자가 알려줄 수 있다")

    def test_shikona_string_is_not_mistaken_for_id(self):
        # 'east' 를 후보에 넣었으므로, 문자열 시코나를 집지 않는지 확인
        class StrApi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return [{"east": "Onosato", "eastId": 45,
                         "west": "Hoshoryu", "westId": 12}]

        api = StrApi(started={"202609"})
        mapping, _, _ = probe.run_probe(api, basho="202609", verbose=False)
        self.assertEqual(mapping.get("east_id"), "eastId")
        self.assertEqual(mapping.get("west_id"), "westId")


class TestEnvelope(unittest.TestCase):
    """응답이 한 겹 감싸여 오는 경우.

    실제 사례: torikumi 가 {"bashoId":.., "torikumi":[...]} 로 온다.
    봉투를 못 벗기면 봉투 자체를 레코드로 착각해 '키를 못 알아봤다' 는
    엉뚱한 진단이 나온다.
    """

    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_named_envelope_is_unwrapped(self):
        class WrappedApi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return {"bashoId": basho_id, "day": day,
                        "division": division, "torikumi": TORIKUMI}

        api = WrappedApi(started={"202609"})
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)
        self.assertEqual(mapping.get("east_id"), "eastId")
        self.assertEqual(mapping.get("west_id"), "westId")
        self.assertEqual(unresolved, [])
        self.assertEqual(report["torikumi"]["n_rows"], 1)

    def test_unknown_envelope_name_is_unwrapped(self):
        # 봉투 이름을 모르더라도 dict 리스트가 하나뿐이면 내용물로 본다
        class OddApi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return {"meta": "x", "someBrandNewName": TORIKUMI}

        api = OddApi(started={"202609"})
        mapping, unresolved, _ = probe.run_probe(
            api, basho="202609", verbose=False)
        self.assertEqual(mapping.get("east_id"), "eastId")
        self.assertEqual(unresolved, [])

    def test_ambiguous_envelope_is_reported_not_guessed(self):
        # dict 리스트가 둘이면 추측하지 않고 문제로 보고한다
        class TwoListApi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return {"torikumiA": TORIKUMI, "torikumiB": TORIKUMI}

        api = TwoListApi(started={"202609"})
        _, unresolved, report = probe.run_probe(api, basho="202609", verbose=False)
        self.assertIn("east_id", unresolved)
        r = report["torikumi"]
        self.assertFalse(r["empty"], "데이터가 없는 것과 혼동하면 안 된다")
        self.assertEqual(sorted(r["envelope"]), ["torikumiA", "torikumiB"])

    def test_envelope_does_not_trigger_pointless_fallback(self):
        class TwoListApi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return {"a": TORIKUMI, "b": TORIKUMI}

        api = TwoListApi(started={"202609"})
        probe.run_probe(api, basho="202609", verbose=False)
        self.assertEqual(api.torikumi_calls, [("202609", 1)],
                         "봉투 문제는 이전 바쇼로 되짚어도 해결되지 않는다")

    def test_plain_record_still_works(self):
        # basho 엔드포인트처럼 단일 레코드를 주는 곳에서만 딕셔너리를 레코드로 본다
        rows = probe._sample_rows({"date": "202609", "startDate": "2026-09-13"},
                                  expect_list=False)
        self.assertEqual(len(rows), 1)
        self.assertIn("startDate", rows[0])

    def test_dict_is_not_a_record_where_a_list_is_expected(self):
        self.assertEqual(
            probe._sample_rows({"date": "202609", "startDate": "2026-09-13"},
                               expect_list=True),
            [])


class TestRealWorldEmptyTorikumi(unittest.TestCase):
    """실제로 보고된 사례를 그대로 재현한다 (2026-09-11).

    202609 는 9/13 개막이라 대전이 아직 없다. 그때 torikumi 엔드포인트는
    빈 목록이 아니라 **대회 정보 껍데기만** 돌려준다:

        {"date": "202609", "startDate": "...", "endDate": "..."}

    이걸 레코드로 착각하면 'east_id 를 못 알아봤다' 는 엉뚱한 진단이 나오고,
    끝난 바쇼로 되짚어 보지도 못한 채 설치가 멈춘다.
    """

    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    class ApiLikeReality(FakeApi):
        """개막 전 바쇼는 껍데기만, 끝난 바쇼는 목록을 감싸서 준다."""

        def torikumi(self, basho_id, division, day):
            self.torikumi_calls.append((basho_id, day))
            shell = {"date": basho_id,
                     "startDate": "2026-09-13", "endDate": "2026-09-27"}
            if basho_id not in self.started:
                return shell                       # ← 문제의 응답
            return {**shell, "torikumi": TORIKUMI}

    def test_shell_response_triggers_fallback(self):
        api = self.ApiLikeReality(started={"202607"})
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)

        self.assertEqual(api.torikumi_calls[0], ("202609", 1))
        self.assertIn(("202607", 1), api.torikumi_calls,
                      "껍데기만 왔으면 끝난 바쇼로 되짚어야 한다")
        self.assertEqual(unresolved, [],
                         f"미해결이 남으면 안 된다: {unresolved}")
        self.assertEqual(mapping.get("east_id"), "eastId")
        self.assertEqual(mapping.get("west_id"), "westId")
        self.assertEqual(report["torikumi"]["source"], ("202607", 1),
                         "어느 바쇼에서 배웠는지 기록해야 한다")

    def test_shell_is_not_mistaken_for_a_record(self):
        shell = {"date": "202609", "startDate": "x", "endDate": "y"}
        self.assertEqual(probe._sample_rows(shell, expect_list=True), [],
                         "목록이 와야 할 자리의 딕셔너리는 레코드가 아니다")

    def test_basho_endpoint_still_reads_single_record(self):
        # 같은 모양이어도 basho 엔드포인트에서는 이것이 진짜 레코드다
        shell = {"date": "202609", "startDate": "x", "endDate": "y"}
        rows = probe._sample_rows(shell, expect_list=False)
        self.assertEqual(len(rows), 1)
        self.assertIn("startDate", rows[0])

    def test_basho_meta_still_learned(self):
        api = self.ApiLikeReality(started={"202607"})
        mapping, _, _ = probe.run_probe(api, basho="202609", verbose=False)
        self.assertEqual(mapping.get("start_date"), "startDate")
        self.assertEqual(mapping.get("end_date"), "endDate")

    def test_all_basho_shells_ends_as_warning_not_wrong_diagnosis(self):
        api = self.ApiLikeReality(started=set())
        _, unresolved, report = probe.run_probe(api, basho="202609", verbose=False)
        self.assertTrue(report["torikumi"]["empty"],
                        "끝까지 껍데기면 '비어 있음' 으로 보고해야 한다")
        self.assertEqual(unresolved, [], "데이터가 없는 것은 해석 실패가 아니다")


class TestBlockingDistinction(unittest.TestCase):
    """무엇이 설치를 멈춰야 하고 무엇이 아닌지.

    리키시·반즈케는 핵심이라 못 읽으면 멈춰야 한다.
    취조(대전 기록)는 아카이브용이고 반즈케 예측에 쓰이지 않으므로,
    못 읽어도 나머지는 진행되어야 한다 — 그래야 예측은 돌릴 수 있다.
    """

    def setUp(self):
        self._backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    def tearDown(self):
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(self._backup)

    def test_torikumi_failure_is_not_blocking(self):
        class OddTorikumi(FakeApi):
            def torikumi(self, basho_id, division, day):
                self.torikumi_calls.append((basho_id, day))
                return [{"leftWrestler": 45, "rightWrestler": 12}]

        api = OddTorikumi(started={"202609"})
        _, unresolved, report = probe.run_probe(api, basho="202609", verbose=False)
        self.assertIn("east_id", unresolved)
        self.assertEqual(report["_blocking_unresolved"], [],
                         "취조 실패로 설치를 멈추면 안 된다")

    def test_banzuke_failure_is_blocking(self):
        class OddBanzuke(FakeApi):
            def banzuke(self, basho_id, division):
                self.banzuke_calls.append(basho_id)
                return [{"wrestlerNumber": 45, "position": "Y1e"}]

        api = OddBanzuke()
        _, unresolved, report = probe.run_probe(api, basho="202609", verbose=False)
        self.assertIn("rank", unresolved)
        self.assertIn("rank", report["_blocking_unresolved"],
                      "반즈케를 못 읽으면 멈춰야 한다")


class TestPrevBasho(unittest.TestCase):
    def test_steps_back_two_months(self):
        self.assertEqual(probe.prev_basho("202609"), "202607")
        self.assertEqual(probe.prev_basho("202609", 2), "202605")

    def test_wraps_year(self):
        self.assertEqual(probe.prev_basho("202601"), "202511")
        self.assertEqual(probe.prev_basho("202603", 2), "202511")


if __name__ == "__main__":
    unittest.main(verbosity=2)
