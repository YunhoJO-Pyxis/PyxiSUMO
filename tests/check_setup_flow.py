"""setup init 의 필드맵 단계를 실제 DB 위에서 검증한다.

2026-09-11 에 보고된 실패를 그대로 재현한다:
  - 202609 는 개막 전이라 torikumi 가 대회 정보 껍데기만 돌려준다
  - 그때 설치가 'east_id 미해결' 로 멈췄다

검증 항목
  1. 껍데기 응답이면 끝난 바쇼로 되짚어 학습한다
  2. 되짚어도 안 되면(진짜 모르는 키) 경고로만 남기고 설치는 계속된다
  3. 반즈케를 못 읽는 경우에는 확실히 멈춘다

    $ DATABASE_URL="postgresql://..." python tests/check_setup_flow.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_probe import FakeApi, TORIKUMI  # noqa: E402

from pyxisumo import fieldmap, probe, setup  # noqa: E402
from pyxisumo.sumoapi import FIELD_ALIASES  # noqa: E402


class ShellApi(FakeApi):
    """개막 전 바쇼는 껍데기만, 끝난 바쇼는 목록을 감싸서 준다 (실제 관찰된 모양)."""

    def torikumi(self, basho_id, division, day):
        self.torikumi_calls.append((basho_id, day))
        shell = {"date": basho_id, "startDate": "2026-09-13",
                 "endDate": "2026-09-27"}
        if basho_id not in self.started:
            return shell
        return {**shell, "torikumi": TORIKUMI}


class UnknownTorikumiApi(FakeApi):
    def torikumi(self, basho_id, division, day):
        self.torikumi_calls.append((basho_id, day))
        return [{"leftWrestler": 45, "rightWrestler": 12}]


class BrokenBanzukeApi(FakeApi):
    def banzuke(self, basho_id, division):
        self.banzuke_calls.append(basho_id)
        return [{"wrestlerNumber": 45, "position": "Y1e"}]


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 을 지정하세요.", file=sys.stderr)
        return 2

    failures: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        print(("  ✓ " if cond else "  ✗ ") + label + (f"  ({detail})" if detail else ""))
        if not cond:
            failures.append(label)

    backup = {k: list(v) for k, v in FIELD_ALIASES.items()}

    # ── 1. 보고된 실패 상황 ────────────────────────────────
    print("\n[1] 개막 전 바쇼 — 껍데기 응답")
    try:
        api = ShellApi(started={"202607"})
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)
        check("끝난 바쇼로 되짚었다", ("202607", 1) in api.torikumi_calls)
        check("east_id 를 학습했다", mapping.get("east_id") == "eastId",
              str(mapping.get("east_id")))
        check("west_id 를 학습했다", mapping.get("west_id") == "westId")
        check("미해결이 남지 않았다", unresolved == [], str(unresolved))
        check("핵심 항목도 그대로 학습했다",
              mapping.get("rikishi_id") == "id" and mapping.get("rank") == "rank")
    finally:
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(backup)

    # ── 2. 취조만 못 읽는 경우 → 진행되어야 한다 ───────────
    print("\n[2] 취조 키를 모르는 경우 — 경고로만")
    try:
        api = UnknownTorikumiApi(started={"202609"})
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)
        res = setup.Result()
        # learn_fieldmap 의 판정 로직만 떼어 확인 (네트워크 재호출 없이)
        blocking = set(report.get("_blocking_unresolved") or [])
        check("east_id 는 미해결로 잡힌다", "east_id" in unresolved)
        check("그러나 설치를 멈추지는 않는다", not blocking, str(blocking))
        check("반즈케·리키시는 정상 학습", mapping.get("rank") == "rank")
        res.warnings.append("fieldmap-partial")
        check("결과가 실패로 집계되지 않는다", not res.failed)
    finally:
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(backup)

    # ── 3. 반즈케를 못 읽으면 멈춰야 한다 ──────────────────
    print("\n[3] 반즈케 키를 모르는 경우 — 멈춤")
    try:
        api = BrokenBanzukeApi()
        _, unresolved, report = probe.run_probe(api, basho="202609", verbose=False)
        blocking = set(report.get("_blocking_unresolved") or [])
        check("rank 가 차단 사유로 잡힌다", "rank" in blocking, str(blocking))
    finally:
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(backup)

    # ── 4. 저장 경로 (실제 DB) ─────────────────────────────
    print("\n[4] 학습 결과 저장 — 실제 DB")
    try:
        from tests.check_checkpoint import Conn

        conn = Conn(dsn)
        sample = {"rikishi_id": "id", "rank": "rank", "east_id": "eastId"}
        fieldmap.save_db(conn, sample)
        back = fieldmap.load_db(conn)
        check("app_setting 에 저장되고 그대로 읽힌다", back == sample, str(back))

        fieldmap.install(back)
        from pyxisumo.sumoapi import pick

        check("저장된 대응이 실제로 적용된다",
              pick({"eastId": 7}, "east_id") == 7)
    finally:
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(backup)

    if failures:
        print(f"\nFAIL — {len(failures)}건: {failures}")
        return 1
    print("\nOK — 보고된 실패 상황이 해소되고, 차단 기준도 의도대로 동작합니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
