"""반즈케 예측 엔진 v1.0.

설계서 五장의 5단계 파이프라인. DB에 의존하지 않는 순수 함수로 두어
tests/ 에서 합성 데이터로 검증할 수 있게 했다.

핵심 전제
---------
반즈케에는 정확한 규칙이 거의 없다. 성문 규정은 오제키 강등·복귀(番付編成要領 8조),
각 단 정원, 산야쿠 최소 정원, 마쿠시타 15매목 전승 정도이고 나머지는 전부 경험칙이다.
따라서 이 엔진의 목표는 "정답 맞히기"가 아니라 **재현 가능한 예측과 정직한 적중률**이다.
모든 경험칙 계수는 PredictParams 로 빼두었다 — 바쇼마다 재측정해 조정할 것.

좌표계
------
마쿠우치(42) + 쥬료(28) + 마쿠시타 상위를 직전 반즈케 순서로 일렬 인덱싱한다.
인덱스 1칸 = 슬롯 1개(東 또는 西), 즉 **1매 = 2칸**이다.
이렇게 두면 마쿠우치↔쥬료 승강이 별도 분기 없이 같은 축 위에서 처리된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Literal

from .ranks import (
    DIVISION_CAPACITY,
    SANYAKU_MIN_SLOTS,
    Rank,
    slots_for,
)

OzekiState = Literal["normal", "kadoban", "returning"]


# =====================================================================
#  입력
# =====================================================================
@dataclass(frozen=True, slots=True)
class RikishiResult:
    """직전 바쇼에서의 한 리키시의 지위와 성적."""

    rikishi_id: int
    rank: Rank
    wins: int = 0
    losses: int = 0
    absences: int = 0

    # --- 오제키 상태머신 입력 (番付編成要領 8조) --------------------
    # 'kadoban'   = 직전 바쇼를 마케코시로 마친 오제키 (이번에 또 지면 강등)
    # 'returning' = 직전 바쇼에 오제키에서 강등된 세키와케 (10승이면 특례 복귀)
    ozeki_state: OzekiState = "normal"

    # --- 오제키 승격 신호 (경험칙) ---------------------------------
    sanyaku_3basho_wins: int | None = None   # 직전 3바쇼 합계 승수
    sanyaku_3basho_all: bool = False         # 3바쇼 연속 산야쿠 재적 여부
    yusho: bool = False                      # 이번 바쇼 우승

    # --- 기타 ------------------------------------------------------
    retired: bool = False                    # 은퇴 → 반즈케에서 제거

    @property
    def net(self) -> int:
        """勝ち越し点. 휴장일은 패로 계산한다 (공상제도는 2004년 1월 폐지)."""
        return self.wins - (self.losses + self.absences)

    @property
    def full_kyujo(self) -> bool:
        return self.wins == 0 and self.absences >= 15

    @property
    def kachikoshi(self) -> bool:
        return self.net > 0


# =====================================================================
#  파라미터 — 전부 경험칙. prediction_run.params 에 그대로 저장된다.
# =====================================================================
@dataclass(frozen=True, slots=True)
class PredictParams:
    model_version: str = "v1.0-linear"

    # 勝ち越し点 1점당 이동 매수.
    #   1.00 = 일본식 목안("1점=1매")  ← 기본값
    #   1.72 = Ozeki Analytics OLS 회귀 실측
    #
    # 회귀값 1.72 를 그대로 쓰면 안 된다. 그 수치는 '실제 이동 매수' 를 맞춘
    # 것이고, 이 엔진은 점수를 매겨 **전원을 다시 줄 세우는** 방식이다.
    # 재정렬 모델에서 계수는 '현재 위치 대 성적' 의 교환비이므로 의미가 다르다.
    # 합성 검증(tests/check_tuning.py)에서 1.72 는 1.0 보다 크게 뒤졌다.
    # 실제 값은 tune 으로 측정해서 고를 것.
    coef_makuuchi: float = 1.0
    coef_juryo: float = 1.0
    coef_makushita: float = 4.0

    # 전휴는 전패보다 아래로 취급한다 (경험칙). 단위: 매수
    full_kyujo_penalty: float = 2.0

    # 대패 완충. 부상성 대패에 협회는 선형 예측보다 관대하다.
    heavy_loss_threshold: int = -5
    heavy_loss_damping: float = 0.78

    # 대승 완충. 변동은 선형이 아니라 **점수가 클수록 완만**해진다
    # (勝ち越し点 9점 이상이면 변동폭이 점수보다 작아진다는 관찰).
    # 이걸 빼면 13승 선수를 실제보다 훨씬 위로 올려버리고,
    # 그 여파로 아래 사람들이 전부 밀려 오차가 번진다.
    big_win_threshold: int = 5
    big_win_damping: float = 0.72

    # 산야쿠 (경험칙)
    komusubi_to_sekiwake_wins: int = 11      # 자리가 없어도 승격하는 승수
    ozeki_promo_wins_3basho: int = 33        # "3바쇼 33승" — 신호일 뿐 규칙 아님
    ozeki_promo_wins_with_yusho: int = 32    # 직전 우승이 있으면 완화
    ozeki_return_wins: int = 10              # 특례 복귀 [확정]

    # 마쿠시타 15매목 이내 7전 전승 → 쥬료 승격 최우선 [내규]
    makushita_zensho_max_rank: int = 15

    # 마쿠시타 → 쥬료 승격 목안 [경험칙]. (매수 상한, 최소 승수)
    #   筆頭 4승 / 3매목 5승 / 5매목 6승 이면 승격 유력.
    #   이 조건을 못 넘는 마쿠시타는 쥬료 밑으로 고정한다 — 없으면
    #   선형 점수만으로 하위 마쿠시타가 쥬료를 밀어내는 사고가 난다.
    makushita_promo_gates: tuple[tuple[int, int], ...] = ((1, 4), (3, 5), (5, 6))

    def coef(self, division: str) -> float:
        return {
            "Makuuchi": self.coef_makuuchi,
            "Juryo": self.coef_juryo,
        }.get(division, self.coef_makushita)

    def to_json(self) -> dict:
        return {
            "model_version": self.model_version,
            "coef_makuuchi": self.coef_makuuchi,
            "coef_juryo": self.coef_juryo,
            "coef_makushita": self.coef_makushita,
            "full_kyujo_penalty": self.full_kyujo_penalty,
            "heavy_loss_threshold": self.heavy_loss_threshold,
            "heavy_loss_damping": self.heavy_loss_damping,
            "big_win_threshold": self.big_win_threshold,
            "big_win_damping": self.big_win_damping,
            "komusubi_to_sekiwake_wins": self.komusubi_to_sekiwake_wins,
            "ozeki_promo_wins_3basho": self.ozeki_promo_wins_3basho,
            "ozeki_promo_wins_with_yusho": self.ozeki_promo_wins_with_yusho,
            "ozeki_return_wins": self.ozeki_return_wins,
            "makushita_zensho_max_rank": self.makushita_zensho_max_rank,
            "makushita_promo_gates": [list(g) for g in self.makushita_promo_gates],
        }


# =====================================================================
#  출력
# =====================================================================
@dataclass(slots=True)
class Prediction:
    rikishi_id: int
    rank: Rank
    confidence: float
    basis: str          # 'yokozuna_lock' | 'ozeki_art8' | 'linear' | ...
    prev_rank: Rank | None = None

    # 반즈케 전체를 일렬로 세웠을 때의 위치(슬롯 인덱스). 1매 = 2슬롯.
    # rank_value 는 지위·디비전 사이에 큰 오프셋이 있어 뺄셈으로 이동량을
    # 구할 수 없다 — 이동량은 반드시 이 인덱스로 계산한다.
    prev_index: int | None = None
    new_index: int | None = None

    @property
    def moved_maisu(self) -> float | None:
        """+면 상승. 지위·디비전을 넘나들어도 올바른 값이 나온다."""
        if self.prev_index is None or self.new_index is None:
            return None
        return (self.prev_index - self.new_index) / 2.0


# =====================================================================
#  PHASE 1 — 하드 제약
# =====================================================================
@dataclass(slots=True)
class _Cand:
    res: RikishiResult
    base_index: int = 0
    score: float = 0.0
    locked_kind: str | None = None    # 'Yokozuna' | 'Ozeki' | 'Sekiwake'
    basis: str = "linear"
    juryo_priority: bool = False


def _apply_hard_rules(cands: list[_Cand], p: PredictParams) -> None:
    for c in cands:
        r = c.res
        kind = r.rank.kind

        # [확정] 요코즈나는 마케코시·전휴여도 강등이 없다.
        #        1890년 이후 강등 사례 0건. 출구는 은퇴뿐.
        if kind == "Yokozuna":
            c.locked_kind = "Yokozuna"
            c.basis = "yokozuna_lock"
            continue

        # [확정] 番付編成要領 第八条 — 오제키 강등/복귀
        if kind == "Ozeki":
            if r.ozeki_state == "kadoban" and not r.kachikoshi:
                # 2바쇼 연속 마케코시 → 강등. 단 전휴여도 세키와케까지만.
                c.locked_kind = "Sekiwake"
                c.basis = "ozeki_art8_demotion"
            else:
                # 카도반이어도 카치코시면 해제, 정상이면 마케코시여도 유지
                c.locked_kind = "Ozeki"
                c.basis = "ozeki_art8_hold"
            continue

        # [확정] 오제키 강등 직후 세키와케에서 10승 이상 → 특례 복귀
        if r.ozeki_state == "returning":
            if r.wins >= p.ozeki_return_wins:
                c.locked_kind = "Ozeki"
                c.basis = "ozeki_art8_return"
            # 9승 이하면 특권 소멸 → 일반 세키와케로 선형 처리
            continue

        # [내규] 마쿠시타 15매목 이내 7전 전승 → 쥬료 승격 최우선.
        #        "ただし番付編成の都合による" 단서가 붙은 내규이므로
        #        하드 제약이 아니라 최우선 가중치로 구현한다.
        if (
            r.rank.division == "Makushita"
            and (r.rank.num or 99) <= p.makushita_zensho_max_rank
            and r.wins == 7
            and r.losses == 0
        ):
            c.juryo_priority = True
            c.basis = "makushita15_zensho"


# =====================================================================
#  PHASE 2 — 점수 산출
# =====================================================================
def _score(cands: list[_Cand], p: PredictParams) -> None:
    for c in cands:
        r = c.res
        net = r.net
        coef = p.coef(r.rank.division)

        delta_maisu = coef * net
        if net <= p.heavy_loss_threshold:
            # 임계점까지는 선형, 그 너머만 완만하게 — 임계점에서 값이 튀지 않게
            over = net - p.heavy_loss_threshold          # 음수
            delta_maisu = coef * (p.heavy_loss_threshold
                                  + over * p.heavy_loss_damping)
        elif net >= p.big_win_threshold:
            over = net - p.big_win_threshold             # 양수
            delta_maisu = coef * (p.big_win_threshold
                                  + over * p.big_win_damping)

        # 인덱스 1칸 = 슬롯 1개, 1매 = 2칸
        delta_index = delta_maisu * 2.0
        score = c.base_index - delta_index

        if r.full_kyujo:
            score += p.full_kyujo_penalty * 2.0

        # 전승 승격 대상은 쥬료 하한 근처로 강하게 끌어올린다
        if c.juryo_priority:
            score = min(score, _juryo_floor_index() - 1.5)
        elif r.rank.division == "Makushita" and not _makushita_promotable(r, p):
            # 승격 목안을 못 넘긴 마쿠시타는 쥬료 아래로 고정한다.
            score = max(score, _juryo_floor_index() + 1.0)

        c.score = score


def _makushita_promotable(r: RikishiResult, p: PredictParams) -> bool:
    """마쿠시타 → 쥬료 승격 목안 [경험칙].

    筆頭 4승 / 3매목 5승 / 5매목 6승. 15매목 이내 전승은 별도 최우선 경로.
    """
    n = r.rank.num or 99
    if n <= p.makushita_zensho_max_rank and r.wins == 7 and r.losses == 0:
        return True
    return any(n <= max_rank and r.wins >= min_wins
               for max_rank, min_wins in p.makushita_promo_gates)


def _juryo_floor_index() -> float:
    """마쿠우치 42 + 쥬료 28 = 70 → 쥬료 마지막 슬롯의 인덱스."""
    return float(DIVISION_CAPACITY["Makuuchi"] + DIVISION_CAPACITY["Juryo"] - 1)


# =====================================================================
#  PHASE 3 — 산야쿠 확정
# =====================================================================
def _assign_sanyaku(cands: list[_Cand], p: PredictParams) -> list[_Cand]:
    """산야쿠 구성원을 확정하고, 상위부터 정렬된 산야쿠 리스트를 돌려준다."""
    by_score = sorted(cands, key=lambda c: c.score)

    yokozuna = [c for c in by_score if c.locked_kind == "Yokozuna"]
    ozeki = [c for c in by_score if c.locked_kind == "Ozeki"]

    # --- 오제키 승격 심사 (경험칙) --------------------------------
    for c in by_score:
        if c.locked_kind or c in ozeki:
            continue
        r = c.res
        if r.rank.kind not in ("Sekiwake", "Komusubi"):
            continue
        if not r.sanyaku_3basho_all or r.sanyaku_3basho_wins is None:
            continue
        threshold = (
            p.ozeki_promo_wins_with_yusho if r.yusho else p.ozeki_promo_wins_3basho
        )
        if r.sanyaku_3basho_wins >= threshold and r.kachikoshi:
            c.locked_kind = "Ozeki"
            c.basis = "ozeki_promotion_signal"
            ozeki.append(c)

    # [관례] 오제키 최소 2명. 공석이면 요코즈나가 横綱大関으로 겸임한다
    #        — 지위 자체가 늘어나는 것이 아니므로 여기서는 채우지 않는다.

    locked_ids = {id(c) for c in yokozuna + ozeki}
    rest = [c for c in by_score if id(c) not in locked_ids]

    # --- 세키와케 -------------------------------------------------
    sekiwake: list[_Cand] = []
    # (a) 8조 강등으로 세키와케가 확정된 전 오제키
    for c in rest:
        if c.locked_kind == "Sekiwake":
            sekiwake.append(c)
    # (b) [경험칙] 코무스비 11승 이상은 자리가 없어도 승격
    for c in rest:
        if c in sekiwake:
            continue
        if c.res.rank.kind == "Komusubi" and c.res.wins >= p.komusubi_to_sekiwake_wins:
            c.basis = "komusubi_11win_promotion"
            sekiwake.append(c)
    # (c) [확정] 최소 2명이 될 때까지 상위 점수로 채운다
    for c in rest:
        if len(sekiwake) >= SANYAKU_MIN_SLOTS["Sekiwake"]:
            break
        if c in sekiwake:
            continue
        sekiwake.append(c)
        c.basis = c.basis if c.basis != "linear" else "sanyaku_fill"

    seki_ids = {id(c) for c in sekiwake}
    rest2 = [c for c in rest if id(c) not in seki_ids]

    # --- 코무스비 -------------------------------------------------
    komusubi: list[_Cand] = []
    # [경험칙] 東前頭筆頭의 카치코시는 코무스비 최우선
    for c in rest2:
        r = c.res
        if (
            r.rank.kind == "Maegashira"
            and (r.rank.num or 99) == 1
            and r.rank.side == "E"
            and r.kachikoshi
        ):
            c.basis = "east_m1_kachikoshi"
            komusubi.append(c)
            break
    for c in rest2:
        if len(komusubi) >= SANYAKU_MIN_SLOTS["Komusubi"]:
            break
        if c in komusubi:
            continue
        komusubi.append(c)
        c.basis = c.basis if c.basis != "linear" else "sanyaku_fill"

    for c in sekiwake:
        c.locked_kind = "Sekiwake"
    for c in komusubi:
        c.locked_kind = "Komusubi"

    # 각 지위 안에서는 점수순으로 東 → 西
    yokozuna.sort(key=lambda c: c.score)
    ozeki.sort(key=lambda c: c.score)
    sekiwake.sort(key=lambda c: c.score)
    komusubi.sort(key=lambda c: c.score)
    return yokozuna + ozeki + sekiwake + komusubi


# =====================================================================
#  PHASE 4·5 — 정원 제약 하 재정렬 + 동서 배치
# =====================================================================
def _confidence(c: "_Cand", moved_maisu: float) -> float:
    """휴리스틱. 실측 MAE≈1매를 전제로 이동폭이 클수록 낮춘다.

    주의: 이건 교정된 확률이 아니다. 바쇼마다 실제 적중률로 재교정할 것.
    """
    if c.basis.startswith(("yokozuna", "ozeki_art8")):
        return 0.98
    base = 0.90 if c.res.rank.division == "Makuuchi" else 0.85
    conf = base * math.exp(-abs(moved_maisu) / 12.0)
    if c.res.full_kyujo:
        conf *= 0.8
    if c.basis in ("ozeki_promotion_signal", "komusubi_11win_promotion"):
        conf = min(conf, 0.70)
    return round(max(0.25, min(0.99, conf)), 2)


def predict_banzuke(
    results: list[RikishiResult],
    params: PredictParams | None = None,
) -> list[Prediction]:
    """직전 바쇼 성적 → 차기 반즈케 예측 (마쿠우치 + 쥬료).

    입력에는 마쿠우치·쥬료 전원과, 쥬료 승격 후보가 될 수 있는
    마쿠시타 상위(대략 20매목 이내)를 넣어야 한다.
    """
    p = params or PredictParams()

    live = [r for r in results if not r.retired]
    if not live:
        return []

    # --- 직전 반즈케 순서로 일렬 인덱싱 (1칸 = 슬롯 1개) -----------
    ordered = sorted(live, key=lambda r: r.rank.value)
    cands = [_Cand(res=r, base_index=i) for i, r in enumerate(ordered)]

    _apply_hard_rules(cands, p)          # PHASE 1
    _score(cands, p)                     # PHASE 2
    sanyaku = _assign_sanyaku(cands, p)  # PHASE 3

    sanyaku_ids = {id(c) for c in sanyaku}
    others = sorted(
        (c for c in cands if id(c) not in sanyaku_ids), key=lambda c: c.score
    )

    # --- PHASE 4: 정원 배정 ---------------------------------------
    maku_cap = DIVISION_CAPACITY["Makuuchi"]
    juryo_cap = DIVISION_CAPACITY["Juryo"]

    n_maegashira = max(0, maku_cap - len(sanyaku))
    maegashira = others[:n_maegashira]
    juryo = others[n_maegashira : n_maegashira + juryo_cap]
    # 나머지는 마쿠시타 강등 — MVP 범위 밖이라 출력하지 않는다.

    placed: list[tuple[_Cand, Rank]] = []

    # --- PHASE 5: 동서 배치 ---------------------------------------
    def emit(group: list[_Cand], division: str, kind: str) -> None:
        for (num, side), c in zip(slots_for(division, len(group)), group):
            placed.append((c, Rank(division=division, kind=kind, num=num, side=side)))

    for kind in ("Yokozuna", "Ozeki", "Sekiwake", "Komusubi"):
        emit([c for c in sanyaku if c.locked_kind == kind], "Makuuchi", kind)
    emit(maegashira, "Makuuchi", "Maegashira")
    emit(juryo, "Juryo", "Numbered")

    placed.sort(key=lambda pair: pair[1].value)

    # 이동량은 슬롯 인덱스로 계산한다 (rank_value 뺄셈은 지위 오프셋 때문에 틀린다)
    out: list[Prediction] = []
    for new_index, (c, rank) in enumerate(placed):
        moved = (c.base_index - new_index) / 2.0
        out.append(
            Prediction(
                rikishi_id=c.res.rikishi_id,
                rank=rank,
                confidence=_confidence(c, moved),
                basis=c.basis,
                prev_rank=c.res.rank,
                prev_index=c.base_index,
                new_index=new_index,
            )
        )
    return out


# =====================================================================
#  적중률
# =====================================================================
@dataclass(slots=True)
class Accuracy:
    n_rikishi: int
    exact_rate: float
    within1_rate: float
    mae_ranks: float
    division_correct: float


_LADDER_ORDER = (
    ("Makuuchi", "Yokozuna"),
    ("Makuuchi", "Ozeki"),
    ("Makuuchi", "Sekiwake"),
    ("Makuuchi", "Komusubi"),
    ("Makuuchi", "Maegashira"),
    ("Juryo", "Numbered"),
    ("Makushita", "Numbered"),
    ("Sandanme", "Numbered"),
    ("Jonidan", "Numbered"),
    ("Jonokuchi", "Numbered"),
)


def _key(r: Rank) -> tuple[str, str, int, str]:
    return (r.division, r.kind, r.num or 1, r.side)


def _slot_ladder(ranks: list[Rank]) -> dict[tuple[str, str, int, str], int]:
    """등장하는 지위들로 '빈틈 없는 슬롯 사다리'를 만들어 각 지위에 서수를 준다.

    산야쿠 인원은 바쇼마다 달라지므로 고정 사다리를 쓸 수 없다.
    실제·예측에 나온 최대 매수까지 채워 만든 뒤 위에서부터 번호를 매긴다.
    슬롯 1칸 = 東 또는 西 하나, 즉 1매 = 2칸.
    """
    max_num: dict[tuple[str, str], int] = {}
    for r in ranks:
        k = (r.division, r.kind)
        max_num[k] = max(max_num.get(k, 0), r.num or 1)

    ladder: dict[tuple[str, str, int, str], int] = {}
    i = 0
    for div, kind in _LADDER_ORDER:
        top = max_num.get((div, kind))
        if not top:
            continue
        for num in range(1, top + 1):
            for side in ("E", "W"):
                ladder[(div, kind, num, side)] = i
                i += 1
    return ladder


def evaluate(
    predictions: list[Prediction],
    actual: dict[int, Rank],
) -> Accuracy:
    """예측 vs 실제 반즈케. 세 지표를 함께 낸다 (설계서 五장).

    exact       — 지위·매수·동서까지 완전 일치. 가장 엄격하다.
    within1     — ±1매 이내. 사용자가 체감하는 정확도 → 주 지표.
    mae_ranks   — 평균 절대오차(매수). 모델 개선 판단용.
    """
    matched = [pr for pr in predictions if pr.rikishi_id in actual]
    n = len(matched)
    if n == 0:
        return Accuracy(0, 0.0, 0.0, 0.0, 0.0)

    # 오차는 '몇 번째 슬롯인가'로 잰다. rank_value 를 그냥 빼면 지위·디비전
    # 오프셋(마에가시라 400, 쥬료 10000 …) 때문에 말도 안 되는 값이 나온다.
    ladder = _slot_ladder(
        [pr.rank for pr in predictions] + list(actual.values())
    )

    exact = within1 = div_ok = 0
    abs_err_sum = 0.0

    for pr in matched:
        act = actual[pr.rikishi_id]
        if act.division == pr.rank.division:
            div_ok += 1
        if (
            act.division == pr.rank.division
            and act.kind == pr.rank.kind
            and (act.num or 1) == (pr.rank.num or 1)
            and act.side == pr.rank.side
        ):
            exact += 1
        err_maisu = abs(ladder[_key(pr.rank)] - ladder[_key(act)]) / 2.0
        abs_err_sum += err_maisu
        if err_maisu <= 1.0:
            within1 += 1

    return Accuracy(
        n_rikishi=n,
        exact_rate=round(exact / n, 4),
        within1_rate=round(within1 / n, 4),
        mae_ranks=round(abs_err_sum / n, 3),
        division_correct=round(div_ok / n, 4),
    )
