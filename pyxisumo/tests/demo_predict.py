"""DB 없이 예측 엔진을 눈으로 확인하는 데모.

    $ python tests/demo_predict.py

합성 반즈케를 넣고 예측 결과 상위를 출력한다.
실제 데이터가 들어오기 전에 파이프라인 동작을 확인하는 용도.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyxisumo.predict import PredictParams, predict_banzuke  # noqa: E402
from pyxisumo.ranks import Rank  # noqa: E402
from tests.test_predict import build_prev_basho, replace_result  # noqa: E402


def main() -> int:
    prev = build_prev_basho()

    # 시나리오를 몇 개 심어 규칙이 실제로 발동하는지 본다
    prev = replace_result(prev, 1, wins=2, losses=13)                    # 요코즈나 대패
    prev = replace_result(prev, 3, wins=5, losses=10, ozeki_state="kadoban")  # 카도반 오제키 강등
    prev = replace_result(prev, 7, wins=11, losses=4)                    # 코무스비 11승
    prev = replace_result(prev, 9, wins=13, losses=2)                    # 東前頭筆頭 13승

    before = {r.rikishi_id: r for r in prev}
    preds = predict_banzuke(prev, PredictParams())

    print(f"입력 {len(prev)}명 → 예측 {len(preds)}명 "
          f"(마쿠우치 {sum(1 for p in preds if p.rank.division=='Makuuchi')}, "
          f"쥬료 {sum(1 for p in preds if p.rank.division=='Juryo')})\n")

    print(f"{'예측 지위':<24}{'직전 지위':<24}{'성적':<10}{'이동':>7}  {'확신':>5}  근거")
    print("-" * 100)
    for p in preds[:16]:
        b = before[p.rikishi_id]
        rec = f"{b.wins}-{b.losses}" + (f"-{b.absences}휴" if b.absences else "")
        moved = p.moved_maisu
        print(f"{p.rank.label():<24}{b.rank.label():<24}{rec:<10}"
              f"{moved:+6.1f}매  {p.confidence:5.2f}  {p.basis}")

    print("\n… 쥬료 경계 …")
    boundary = [p for p in preds if p.rank.value >= Rank('Makuuchi','Maegashira',16,'E').value][:6]
    for p in boundary:
        b = before[p.rikishi_id]
        print(f"{p.rank.label():<24}{b.rank.label():<24}"
              f"{b.wins}-{b.losses:<8}{(p.moved_maisu or 0):+6.1f}매  {p.confidence:5.2f}  {p.basis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
