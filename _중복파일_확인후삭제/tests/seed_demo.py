"""사이트 확인용 데모 데이터 생성.

실제 규모(마쿠우치 42 + 쥬료 28, 여러 대회)를 흉내 내 레이아웃과
성능을 눈으로 확인하기 위한 것이다. 실제 성적이 아니다.

    $ DATABASE_URL="postgresql://..." python tests/seed_demo.py
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import asdict  # noqa: E402

from pyxisumo.predict import (  # noqa: E402
    PredictParams, RikishiResult, evaluate, predict_banzuke,
)
from pyxisumo.ranks import Rank, rank_value, slots_for  # noqa: E402
from pyxisumo.sqlrunner import Runner, quote_literal  # noqa: E402

# 실제 반즈케를 그대로 쓴다.
#
# 예전에는 시코나를 손으로 적고 순서를 무작위로 섞었다. 그랬더니 쇼다이가
# 요코즈나로 올라온 화면이 나왔고, **데이터가 망가진 것처럼 보였다.**
# 확인용 데이터라도 사실과 어긋나면 안 된다.
#
# 기준 파일: tests/fixtures/banzuke_202609.json
#   (일본상撲협회 공식 반즈케와 같은 내용 · Sumo-API 로 받아 고정해 둠)
TRUTH = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "banzuke_202609.json")
    .read_text(encoding="utf-8"))

# (한자, 로마자, 헤야 로마자) — 한국어는 일부러 넣지 않는다.
# 실제 API 도 한국어를 주지 않으므로, 음역 단계를 반드시 거치게 한다.
NAMES = [(e["name_ja"], e["name_en"], e["heya_en"]) for e in TRUTH["entries"]]

# 은퇴 선수 — 검색 결과에 '(은퇴)' 가 붙는지 확인하려면 실제로 은퇴한 사람이 있어야 한다.
# 이들도 지어낸 이름이 아니라 실제 은퇴자다 (은퇴일은 픽스처에 원본 그대로 들어 있다).
RETIRED = TRUTH.get("retired", [])
NAMES += [(r["name_ja"], r["name_en"], r["heya_en"]) for r in RETIRED]
FIRST_RETIRED_ID = len(TRUTH["entries"]) + 1

BASHO = [("202601", "初場所"), ("202603", "春場所"), ("202605", "夏場所"),
         ("202607", "名古屋場所"), ("202609", "秋場所")]

MAKUUCHI_SLOTS = [
    ("Yokozuna", 1), ("Yokozuna", 1),
    ("Ozeki", 1), ("Ozeki", 1),
    ("Sekiwake", 1), ("Sekiwake", 1),
    ("Komusubi", 1), ("Komusubi", 1),
]


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 을 지정하세요.", file=sys.stderr)
        return 2
    rn = Runner(dsn)
    rng = random.Random(20260911)

    sql: list[str] = ["BEGIN;"]
    for t in ("torikumi", "prediction_accuracy", "prediction_entry",
              "prediction_run", "banzuke_entry", "basho_award",
              "shikona", "rikishi"):
        sql.append(f"DELETE FROM {t};")

    # 헤야 — **실제 API 가 주는 모양대로** 영문만 넣는다.
    # 한자와 한국어를 미리 채워 두면 표기 채우기 단계를 검증할 수 없다.
    heya = sorted({n[2] for n in NAMES})
    for idx, h in enumerate(heya, start=1):
        slug = f"demo{idx}"
        sql.append(
            "INSERT INTO heya (slug, name_en, name_ja, name_ko) VALUES "
            f"({quote_literal(slug)}, {quote_literal(h)}, NULL, NULL) "
            "ON CONFLICT (slug) DO UPDATE SET name_en = EXCLUDED.name_en, "
            "name_ja = NULL, name_ko = NULL;")

    # 리키시 + 시코나
    for rid, (ja, en, h) in enumerate(NAMES, start=1):
        slug = f"demo{heya.index(h) + 1}"
        idx = rid - FIRST_RETIRED_ID
        retired = (quote_literal(RETIRED[idx]["retired_basho"])
                   if 0 <= idx < len(RETIRED) else "NULL")
        sql.append(
            "INSERT INTO rikishi (id, sumo_api_id, heya_id, debut_basho, "
            "retired_basho, height_cm, weight_kg, shusshin) VALUES "
            f"({rid}, {9000 + rid}, (SELECT id FROM heya WHERE slug={quote_literal(slug)}), "
            f"'201801', {retired}, {170 + rng.randint(0, 25)}, "
            f"{110 + rng.randint(0, 80)}, {quote_literal('東京都')});")
        # 한국어 표기는 일부러 비워 둔다 — 음역이 실제로 도는지 보기 위해서다.
        # (ko 는 기대값으로만 쓰인다: tests/check_site.py 가 결과를 검사한다)
        sql.append(
            "INSERT INTO shikona (rikishi_id, from_basho, name_ja, name_en, name_ko) "
            f"VALUES ({rid}, '201801', {quote_literal(ja)}, {quote_literal(en)}, "
            "NULL);")
    sql.append("SELECT setval(pg_get_serial_sequence('rikishi','id'), 500);")

    # 바쇼별 반즈케
    #
    # 두 가지를 지킨다.
    #
    # 1) 최신 대회(202609)는 **실제 반즈케 그대로** 넣는다. 순서를 섞으면 쇼다이가
    #    요코즈나로 올라오는 화면이 나와서 데이터가 망가진 것처럼 보인다.
    #
    # 2) 과거 대회는 **성적이 순위 변동을 설명하도록** 거꾸로 만든다.
    #    예전에는 순서와 성적을 각각 무작위로 뽑았는데, 그러면 성적과 다음 반즈케
    #    사이에 아무 관계가 없어서 yosou 페이지의 '차이' 칸이 20매씩 벌어졌다.
    #    엔진이 엉망인 것처럼 보이지만 사실은 **자료가 앞뒤가 안 맞았던 것**이다.
    #
    #    실제 스모에서는 그 관계가 반대 방향으로 성립한다 — 카치코시 점수만큼
    #    다음 반즈케에서 올라간다. 그래서 최신 대회에서 거슬러 올라가며,
    #    "이 사람이 그 자리로 가려면 직전에 어디서 몇 승을 했어야 하는가" 를
    #    역산해 과거 반즈케와 성적을 만든다.
    #
    #    ※ 그러므로 데모 데이터로 나오는 적중률은 **엔진의 실제 실력이 아니다.**
    #      실제 실력은 사용자의 진짜 데이터로 6_예측정확도확인 을 돌려야 나온다.
    ODD_NETS = (-11, -9, -7, -5, -3, -1, 1, 3, 5, 7, 9, 11)

    def delta_slots(net: int, division: str) -> float:
        """이 성적이면 엔진이 몇 슬롯을 올릴까 — **엔진과 같은 식을 쓴다.**

        대승·대패에는 완충이 걸리므로 2*net 을 그대로 쓰면 안 된다. 그러면
        역산이 어긋나서, 자료 탓인 오차를 엔진 탓으로 보게 된다.
        """
        pp = PredictParams()
        coef = pp.coef(division)
        if net <= pp.heavy_loss_threshold:
            over = net - pp.heavy_loss_threshold
            d = coef * (pp.heavy_loss_threshold + over * pp.heavy_loss_damping)
        elif net >= pp.big_win_threshold:
            over = net - pp.big_win_threshold
            d = coef * (pp.big_win_threshold + over * pp.big_win_damping)
        else:
            d = coef * net
        return d * 2.0

    # 최신 대회는 픽스처 순서 그대로 (= 실제 반즈케 순위 순)
    bid_last = BASHO[-1][0]
    for rid, ent in enumerate(TRUTH["entries"], start=1):
        sql.append(
            "INSERT INTO banzuke_entry (basho_id, rikishi_id, division, "
            "rank_kind, rank_num, side, rank_label, wins, losses, absences) "
            f"VALUES ({quote_literal(bid_last)}, {rid}, "
            f"{quote_literal(ent['division'])}, {quote_literal(ent['kind'])}, "
            f"{ent['num']}, {quote_literal(ent['side'])}, "
            f"{quote_literal(ent['rank'])}, 0, 0, 0);")

    # 픽스처는 東 전체 → 西 전체 순서로 저장돼 있다 (API 응답 모양 그대로).
    # 그대로 순위로 쓰면 서 요코즈나(호쇼류)가 22번째 선수가 되어 버린다.
    # 반드시 rank_value 로 다시 줄 세운다.
    order_next = [rid for rid, _ in sorted(
        ((rid, rank_value(e["division"], e["kind"], e["num"], e["side"]))
         for rid, e in enumerate(TRUTH["entries"], start=1)),
        key=lambda t: t[1])]
    n_slots = len(order_next)

    for b_i in range(len(BASHO) - 2, -1, -1):       # 최신 → 과거로 거슬러 간다
        bid = BASHO[b_i][0]

        # 그 대회에 아직 현역이던 은퇴 선수를 명단에 넣고, 같은 수만큼 아래를 덜어낸다
        still_active = [FIRST_RETIRED_ID + k for k, r in enumerate(RETIRED)
                        if bid <= r["retired_basho"]]
        pool = order_next[:n_slots - len(still_active)] + still_active

        pos_next = {rid: j for j, rid in enumerate(order_next)}
        net_of: dict[int, int] = {}
        desired: list[tuple[float, int]] = []
        for rid in pool:
            net = rng.choice(ODD_NETS)
            net_of[rid] = net
            # 다음 대회에 없는 사람(그 사이 은퇴)은 아래쪽에 둔다
            j = pos_next.get(rid, n_slots + 4)
            # 카치코시 점수만큼 올라갔다면, 직전에는 그만큼 아래에 있었다.
            div = "Juryo" if j >= 42 else "Makuuchi"
            desired.append((j + delta_slots(net, div) + rng.uniform(-1.2, 1.2), rid))
        order = [rid for _, rid in sorted(desired)]

        def record(rid: int) -> tuple[int, int]:
            net = net_of[rid]
            w = (15 + net) // 2
            return w, 15 - w

        pos = 0
        for kind, _ in MAKUUCHI_SLOTS:
            side = "E" if pos % 2 == 0 else "W"
            num = 1
            rid = order[pos]
            w, l = record(rid)
            side_en = "East" if side == "E" else "West"
            label = quote_literal(f"{kind} {num} {side_en}")
            sql.append(
                "INSERT INTO banzuke_entry (basho_id, rikishi_id, division, "
                "rank_kind, rank_num, side, rank_label, wins, losses, absences) VALUES "
                f"({quote_literal(bid)}, {rid}, 'Makuuchi', {quote_literal(kind)}, {num}, "
                f"{quote_literal(side)}, {label}, {w}, {l}, 0);")
            pos += 1

        for num, side in slots_for("Makuuchi", 42 - len(MAKUUCHI_SLOTS)):
            if pos >= len(order):
                break
            rid = order[pos]
            w, l = record(rid)
            side_en = "East" if side == "E" else "West"
            label = quote_literal(f"Maegashira {num} {side_en}")
            sql.append(
                "INSERT INTO banzuke_entry (basho_id, rikishi_id, division, "
                "rank_kind, rank_num, side, rank_label, wins, losses, absences) VALUES "
                f"({quote_literal(bid)}, {rid}, 'Makuuchi', 'Maegashira', {num}, "
                f"{quote_literal(side)}, {label}, {w}, {l}, 0);")
            pos += 1

        for num, side in slots_for("Juryo", 28):
            if pos >= len(order):
                break
            rid = order[pos]
            w, l = record(rid)
            side_en = "East" if side == "E" else "West"
            label = quote_literal(f"Juryo {num} {side_en}")
            sql.append(
                "INSERT INTO banzuke_entry (basho_id, rikishi_id, division, "
                "rank_kind, rank_num, side, rank_label, wins, losses, absences) VALUES "
                f"({quote_literal(bid)}, {rid}, 'Juryo', 'Numbered', {num}, "
                f"{quote_literal(side)}, {label}, {w}, {l}, 0);")
            pos += 1

        # 대전 기록 (첫 3일치만 — 상대전적 표 확인용)
        for day in (1, 2, 3):
            ids = order[:20]
            rng.shuffle(ids)
            # 상대 전적 표는 같은 상대와 2번 이상 붙은 경우만 보여 준다.
            for fixed in (1, 2):
                if fixed in ids:
                    ids.remove(fixed)
            ids = [1, 2] + ids
            for m in range(len(ids) // 2):
                ea, we = ids[m * 2], ids[m * 2 + 1]
                win = rng.choice([ea, we])
                sql.append(
                    "INSERT INTO torikumi (basho_id, day, division, match_no, "
                    "east_id, west_id, winner_id, kimarite) VALUES "
                    f"({quote_literal(bid)}, {day}, 'Makuuchi', {m + 1}, "
                    f"{ea}, {we}, {win}, NULL) ON CONFLICT DO NOTHING;")

        order_next = order

    sql.append("COMMIT;")
    rn.execute("\n".join(sql))
    sql = ["BEGIN;"]

    # 예측 — **진짜 예측 엔진에 태워서** 만든다.
    #
    # 예전에는 1번부터 순서대로 요코즈나·오제키… 를 붙인 가짜 예측을 넣었다.
    # 그러면 yosou 페이지의 '차이' 칸이 26매씩 벌어져서, 엔진이 엉망인 것처럼
    # 보인다. 화면 확인용 데이터라도 **성능을 왜곡해서는 안 된다.**
    #
    # 여기서 만든 예측은 이 데모의 직전 대회 성적을 실제 엔진에 넣은 결과다.
    # 따라서 '차이' 칸은 엔진의 진짜 실력을 보여 준다.
    src_basho, tgt_basho = BASHO[-2][0], BASHO[-1][0]
    prev = rn.query("""
        SELECT rikishi_id, division::text, rank_kind::text, rank_num, side::text,
               wins, losses, absences
        FROM banzuke_entry WHERE basho_id = %s
    """, (src_basho,))
    results = [
        RikishiResult(rikishi_id=int(r[0]),
                      rank=Rank(r[1], r[2], int(r[3] or 1), r[4]),
                      wins=int(r[5] or 0), losses=int(r[6] or 0),
                      absences=int(r[7] or 0))
        for r in prev
    ]
    params = PredictParams()
    preds = predict_banzuke(results, params)

    sql2: list[str] = ["BEGIN;"]
    sql2.append(
        "INSERT INTO prediction_run (id, target_basho_id, source_basho_id, "
        "model_version, params) VALUES "
        f"(1, {quote_literal(tgt_basho)}, {quote_literal(src_basho)}, "
        f"{quote_literal(params.model_version)}, "
        f"{quote_literal(json.dumps(asdict(params)))}::jsonb) "
        "ON CONFLICT (id) DO NOTHING;")
    for pr in preds:
        sql2.append(
            "INSERT INTO prediction_entry (run_id, rikishi_id, division, "
            "rank_kind, rank_num, side, confidence, basis) VALUES "
            f"(1, {pr.rikishi_id}, {quote_literal(pr.rank.division)}, "
            f"{quote_literal(pr.rank.kind)}, {pr.rank.num or 1}, "
            f"{quote_literal(pr.rank.side)}, {round(pr.confidence, 2)}, "
            f"{quote_literal(pr.basis)}) ON CONFLICT DO NOTHING;")

    # 적중률도 엔진이 직접 채점한 값을 넣는다 (손으로 적어 넣지 않는다)
    actual = {int(r[0]): Rank(r[1], r[2], int(r[3] or 1), r[4]) for r in rn.query("""
        SELECT rikishi_id, division::text, rank_kind::text, rank_num, side::text
        FROM banzuke_entry WHERE basho_id = %s
    """, (tgt_basho,))}
    acc = evaluate(preds, actual)
    sql2.append(
        "INSERT INTO prediction_accuracy (run_id, n_rikishi, exact_rate, "
        "within1_rate, mae_ranks, division_correct) VALUES "
        f"(1, {acc.n_rikishi}, {acc.exact_rate}, {acc.within1_rate}, "
        f"{acc.mae_ranks}, {acc.division_correct}) ON CONFLICT (run_id) DO NOTHING;")
    sql2.append("COMMIT;")
    rn.execute("\n".join(sql2))

    n = rn.scalar("SELECT count(*) FROM banzuke_entry")
    t = rn.scalar("SELECT count(*) FROM torikumi")
    print(f"데모 데이터 생성: 반즈케 {n}행 · 취조 {t}행 · 리키시 {len(NAMES)}명")
    print(f"  예측 {len(preds)}명 (실제 엔진) · ±1매 {acc.within1_rate:.1%} · "
          f"평균오차 {acc.mae_ranks:.2f}매")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
