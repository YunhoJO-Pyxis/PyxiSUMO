"""실제로 관찰된 Sumo-API 응답 모양 그대로 전 과정을 돌린다.

2026-09-11 에 사용자 환경에서 확인된 사실들을 전부 반영했다:

  · 리키시 목록   → 'id'
  · 반즈케        → 'rikishiID' (대문자 D), east/west 분리
  · 취조          → {date, startDate, endDate, torikumi:[...]} 로 감싸짐
  · 개막 전 바쇼  → 취조가 대회 정보 껍데기만 옴
  · /api/kimarite → 매개변수 없이 부르면 HTTP 400

이 조합에서 **반즈케가 실제로 채워지는지**가 핵심이다.
(직전 실행에서는 리키시 9,132명·취조 11,141행이 들어왔는데
 반즈케만 0행이었고, 그것이 '완료' 로 기록됐다.)

    $ DATABASE_URL="postgresql://..." python tests/check_realistic_api.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.check_checkpoint import Conn, Cursor  # noqa: E402

from pyxisumo import checkpoint, fieldmap, ingest, probe  # noqa: E402
from pyxisumo.sumoapi import FIELD_ALIASES, SumoApiError  # noqa: E402


def _executemany(self, sql, rows):
    for r in rows:
        self.execute(sql, r)


Cursor.executemany = _executemany  # type: ignore[attr-defined]


# ---------------------------------------------------------------------
#  관찰된 모양 그대로
# ---------------------------------------------------------------------
RIKISHI = [
    {"id": 1001, "sumoApiId": 1001, "shikonaEn": "Hoshoryu",
     "shikonaJp": "豊昇龍", "currentRank": "Yokozuna 1 East",
     "heya": "Tatsunami", "birthDate": "1999-05-22T00:00:00Z",
     "shusshin": "Mongolia", "height": 187, "weight": 151, "debut": "201801"},
    {"id": 1002, "sumoApiId": 1002, "shikonaEn": "Onosato",
     "shikonaJp": "大の里", "currentRank": "Yokozuna 1 West",
     "heya": "Nishonoseki", "birthDate": "2000-06-07T00:00:00Z",
     "shusshin": "Ishikawa", "height": 192, "weight": 185, "debut": "202305"},
    {"id": 1003, "sumoApiId": 1003, "shikonaEn": "Kotozakura",
     "shikonaJp": "琴櫻", "currentRank": "Ozeki 1 East",
     "heya": "Sadogatake", "birthDate": "1997-11-19T00:00:00Z",
     "shusshin": "Chiba", "height": 188, "weight": 175, "debut": "201511"},
    {"id": 1004, "sumoApiId": 1004, "shikonaEn": "Wakatakakage",
     "shikonaJp": "若隆景", "currentRank": "Sekiwake 1 East",
     "heya": "Arashio", "birthDate": "1994-12-06T00:00:00Z",
     "shusshin": "Fukushima", "height": 182, "weight": 131, "debut": "201703"},
]


def banzuke_payload(basho_id: str) -> dict:
    """east/west 를 나눠 주고, 리키시 번호는 'rikishiID' 로 준다."""
    return {
        "bashoId": basho_id,
        "division": "Makuuchi",
        "east": [
            {"side": "East", "rikishiID": 1001, "shikonaEn": "Hoshoryu",
             "rank": "Yokozuna 1 East", "wins": 11, "losses": 4, "absences": 0},
            {"side": "East", "rikishiID": 1003, "shikonaEn": "Kotozakura",
             "rank": "Ozeki 1 East", "wins": 6, "losses": 9, "absences": 0},
        ],
        "west": [
            {"side": "West", "rikishiID": 1002, "shikonaEn": "Onosato",
             "rank": "Yokozuna 1 West", "wins": 13, "losses": 2, "absences": 0},
            {"side": "West", "rikishiID": 1004, "shikonaEn": "Wakatakakage",
             "rank": "Sekiwake 1 West", "wins": 9, "losses": 6, "absences": 0},
        ],
    }


TORIKUMI_ROWS = [
    {"bashoId": "202607", "division": "Makuuchi", "day": 1, "matchNo": 1,
     "eastId": 1003, "eastShikona": "Kotozakura", "eastRank": "Ozeki 1 East",
     "westId": 1004, "westShikona": "Wakatakakage", "westRank": "Sekiwake 1 West",
     "kimarite": "Oshidashi", "winnerId": 1004, "winnerEn": "Wakatakakage"},
    {"bashoId": "202607", "division": "Makuuchi", "day": 1, "matchNo": 2,
     "eastId": 1001, "eastShikona": "Hoshoryu", "eastRank": "Yokozuna 1 East",
     "westId": 1002, "westShikona": "Onosato", "westRank": "Yokozuna 1 West",
     "kimarite": "Yorikiri", "winnerId": 1002, "winnerEn": "Onosato"},
]


class RealisticApi:
    STARTED = {"202607"}          # 202609 는 개막 전

    def __init__(self):
        self.calls: list[str] = []

    def iter_rikishis(self, **kw):
        self.calls.append("rikishis")
        return iter(RIKISHI)

    def rikishis(self, **kw):
        self.calls.append("rikishis")
        return RIKISHI

    def rikishi(self, rid):
        return next((r for r in RIKISHI if r["id"] == rid), None)

    def basho(self, basho_id):
        self.calls.append(f"basho:{basho_id}")
        return {"date": basho_id, "location": "Tokyo",
                "startDate": f"{basho_id[:4]}-{basho_id[4:]}-13T00:00:00Z",
                "endDate": f"{basho_id[:4]}-{basho_id[4:]}-27T00:00:00Z"}

    def banzuke(self, basho_id, division):
        self.calls.append(f"banzuke:{basho_id}:{division}")
        if division != "Makuuchi":
            return {"bashoId": basho_id, "division": division,
                    "east": [], "west": []}
        return banzuke_payload(basho_id)

    def torikumi(self, basho_id, division, day):
        self.calls.append(f"torikumi:{basho_id}:{division}:{day}")
        shell = {"date": basho_id,
                 "startDate": f"{basho_id[:4]}-{basho_id[4:]}-13T00:00:00Z",
                 "endDate": f"{basho_id[:4]}-{basho_id[4:]}-27T00:00:00Z"}
        if basho_id not in self.STARTED or division != "Makuuchi" or day != 1:
            return shell                       # 개막 전이면 껍데기만
        return {**shell, "torikumi": TORIKUMI_ROWS}

    def kimarite(self):
        # 매개변수 없이 부르면 400 — SumoApi.kimarite 가 조합을 바꿔 재시도한다
        self.calls.append("kimarite")
        raise SumoApiError("HTTP 400 for https://www.sumo-api.com/api/kimarite")


# ---------------------------------------------------------------------
def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 을 지정하세요.", file=sys.stderr)
        return 2

    conn = Conn(dsn)
    failures: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        print(("  ✓ " if cond else "  ✗ ") + label + (f"  ({detail})" if detail else ""))
        if not cond:
            failures.append(label)

    def scalar(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None

    for t in ("torikumi", "prediction_entry", "prediction_run", "banzuke_entry",
              "basho_award", "shikona", "rikishi", "ingest_checkpoint", "kimarite"):
        conn.cursor().execute(f"DELETE FROM {t}")

    backup = {k: list(v) for k, v in FIELD_ALIASES.items()}
    try:
        api = RealisticApi()

        # ── 1. 학습 ────────────────────────────────────────────
        print("\n[1] 필드 대응 학습 (실제 모양)")
        mapping, unresolved, report = probe.run_probe(
            api, basho="202609", verbose=False)
        for k in ("rikishi_id", "rank", "east_id", "west_id", "wins"):
            check(f"{k} 학습", k in mapping, str(mapping.get(k)))
        check("미해결 없음", unresolved == [], str(unresolved))
        check("취조는 끝난 바쇼에서 배웠다",
              report["torikumi"].get("source") == ("202607", 1),
              str(report["torikumi"].get("source")))
        fieldmap.install(mapping)

        # ── 2. 적재 ────────────────────────────────────────────
        print("\n[2] 적재 — 반즈케가 실제로 채워지는가")
        stats = ingest.bootstrap(api, conn, "202607", "202609")
        check("용어집 실패는 경고로만", bool(stats["optional_failed"]))
        check("바쇼 2개 처리", stats["basho"] == 2, str(stats["basho"]))
        check("반즈케가 0행이 아니다",
              int(scalar("SELECT count(*) FROM banzuke_entry") or 0) == 8,
              f"{scalar('SELECT count(*) FROM banzuke_entry')}행")
        check("리키시 4명", scalar("SELECT count(*) FROM rikishi") == "4")
        check("취조 2행", scalar("SELECT count(*) FROM torikumi") == "2")

        # ── 3. 내용이 맞는가 ───────────────────────────────────
        print("\n[3] 해석 결과 검증")
        check("東橫綱 rank_value = 0", scalar("""
            SELECT rank_value FROM banzuke_entry b JOIN rikishi r ON r.id=b.rikishi_id
            WHERE r.sumo_api_id=1001 AND b.basho_id='202609'""") == "0")
        check("西橫綱이 東橫綱 바로 뒤", scalar("""
            SELECT rank_value FROM banzuke_entry b JOIN rikishi r ON r.id=b.rikishi_id
            WHERE r.sumo_api_id=1002 AND b.basho_id='202609'""") == "1")
        check("Ozeki 로 파싱", scalar("""
            SELECT rank_kind::text FROM banzuke_entry b JOIN rikishi r ON r.id=b.rikishi_id
            WHERE r.sumo_api_id=1003 AND b.basho_id='202609'""") == "Ozeki")
        check("성적이 들어감 (13승)", scalar("""
            SELECT wins FROM banzuke_entry b JOIN rikishi r ON r.id=b.rikishi_id
            WHERE r.sumo_api_id=1002 AND b.basho_id='202609'""") == "13")
        check("휴장 0", scalar("""
            SELECT absences FROM banzuke_entry b JOIN rikishi r ON r.id=b.rikishi_id
            WHERE r.sumo_api_id=1002 AND b.basho_id='202609'""") == "0")
        check("동/서가 제대로 갈림", scalar("""
            SELECT side::text FROM banzuke_entry b JOIN rikishi r ON r.id=b.rikishi_id
            WHERE r.sumo_api_id=1004 AND b.basho_id='202609'""") == "W")
        check("생년월일 파싱 (ISO 시각 포함)",
              scalar("SELECT birth_date::text FROM rikishi WHERE sumo_api_id=1002")
              == "2000-06-07")
        check("신장 파싱", scalar(
            "SELECT height_cm::text FROM rikishi WHERE sumo_api_id=1002") == "192.0")
        check("헤야 연결", scalar("""
            SELECT h.slug FROM rikishi r JOIN heya h ON h.id=r.heya_id
            WHERE r.sumo_api_id=1002""") == "nishonoseki")
        check("기술 코드 소문자 정규화",
              scalar("SELECT kimarite FROM torikumi WHERE match_no=2") == "yorikiri")
        check("승자가 대전자 중 하나", scalar("""
            SELECT count(*) FROM torikumi WHERE winner_id IS NOT NULL
            AND winner_id NOT IN (east_id, west_id)""") == "0")

        # ── 4. 체크포인트가 정직한가 ───────────────────────────
        print("\n[4] 체크포인트")
        done = checkpoint.completed(conn, "basho")
        check("두 바쇼 모두 완료", {"202607", "202609"} <= done, str(sorted(done)))
        from pyxisumo.setup import _heal_empty_banzuke_checkpoints

        check("치유 대상이 없다 (내용이 실제로 있으므로)",
              _heal_empty_banzuke_checkpoints(conn) == 0)

        # ── 5. 예측이 돌아가는가 ───────────────────────────────
        print("\n[5] 예측 파이프라인")
        from pyxisumo.predict import PredictParams, predict_banzuke
        from pyxisumo.ranks import Rank

        cur = conn.cursor()
        cur.execute("""
            SELECT rikishi_id, division::text, rank_kind::text, rank_num, side::text,
                   wins, losses, absences
            FROM banzuke_entry WHERE basho_id='202609' ORDER BY rank_value""")
        from pyxisumo.predict import RikishiResult

        results = [
            RikishiResult(
                rikishi_id=int(r[0]),
                rank=Rank(r[1], r[2], int(r[3]) if r[3] else None, r[4]),
                wins=int(r[5]), losses=int(r[6]), absences=int(r[7]))
            for r in cur.fetchall()
        ]
        check("DB에서 예측 입력을 만들 수 있다", len(results) == 4, f"{len(results)}명")
        preds = predict_banzuke(results, PredictParams())
        check("예측이 나온다", len(preds) > 0, f"{len(preds)}명")
        check("요코즈나는 요코즈나로 남는다",
              all(p.rank.kind == "Yokozuna" for p in preds[:2]))

    finally:
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(backup)

    if failures:
        print(f"\nFAIL — {len(failures)}건: {failures}")
        return 1
    print("\nOK — 실제 응답 모양에서 반즈케가 정상 적재되고 예측까지 이어집니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
