"""초기 적재 전 과정을 네트워크 없이 검증한다.

가짜 Sumo-API(FakeApi)가 **일부러 낯선 필드명**으로 응답을 내놓는다.
probe 의 학습 → fieldmap 설치 → ingest 파싱 → upsert → 체크포인트 →
중단 후 재개까지가 실제 Postgres 위에서 한 번에 돌아가는지 본다.

    $ DATABASE_URL="postgresql://..." python tests/check_bootstrap.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.check_checkpoint import Conn, Cursor  # noqa: E402

from pyxisumo import checkpoint, fieldmap, ingest  # noqa: E402
from pyxisumo.probe import EXPECTED  # noqa: E402
from pyxisumo.sumoapi import FIELD_ALIASES  # noqa: E402


# executemany 지원 추가 (db.executemany 가 쓴다)
def _executemany(self, sql, rows):
    for r in rows:
        self.execute(sql, r)


Cursor.executemany = _executemany  # type: ignore[attr-defined]


# ---------------------------------------------------------------------
#  가짜 API — 표준적이지 않은 키 이름을 일부러 쓴다
# ---------------------------------------------------------------------
RIKISHI = [
    {"Rikishi_ID": 1001, "shikona_en": "Hoshoryu", "shikona_jp": "豊昇龍",
     "stable": "Tatsunami", "birth_date": "1999-05-22",
     "height_cm": 187.0, "weight_kg": 151.0, "debut_basho": "201801"},
    {"Rikishi_ID": 1002, "shikona_en": "Onosato", "shikona_jp": "大の里",
     "stable": "Nishonoseki", "birth_date": "2000-06-07",
     "height_cm": 192.0, "weight_kg": 185.0, "debut_basho": "202305"},
    {"Rikishi_ID": 1003, "shikona_en": "Kotozakura", "shikona_jp": "琴櫻",
     "stable": "Sadogatake", "birth_date": "1997-11-19",
     "height_cm": 188.0, "weight_kg": 175.0, "debut_basho": "201511"},
    {"Rikishi_ID": 1004, "shikona_en": "Wakatakakage", "shikona_jp": "若隆景",
     "stable": "Arashio", "birth_date": "1994-12-06",
     "height_cm": 182.0, "weight_kg": 131.0, "debut_basho": "201703"},
]

BANZUKE = {
    "202607": [
        {"Rikishi_ID": 1001, "rankName": "Yokozuna 1 East", "w": 11, "l": 4, "kyujo": 0},
        {"Rikishi_ID": 1002, "rankName": "Yokozuna 1 West", "w": 13, "l": 2, "kyujo": 0},
        {"Rikishi_ID": 1003, "rankName": "Ozeki 1 East", "w": 6, "l": 9, "kyujo": 0},
        {"Rikishi_ID": 1004, "rankName": "Sekiwake 1 East", "w": 9, "l": 6, "kyujo": 0},
    ],
    "202609": [
        {"Rikishi_ID": 1001, "rankName": "Yokozuna 1 West", "w": 8, "l": 7, "kyujo": 0},
        {"Rikishi_ID": 1002, "rankName": "Yokozuna 1 East", "w": 12, "l": 3, "kyujo": 0},
        {"Rikishi_ID": 1003, "rankName": "Ozeki 1 East", "w": 5, "l": 10, "kyujo": 0},
        {"Rikishi_ID": 1004, "rankName": "Sekiwake 1 East", "w": 10, "l": 5, "kyujo": 0},
    ],
}

TORIKUMI = {
    ("202609", 1): [
        {"matchNumber": 1, "eastRikishiId": 1003, "westRikishiId": 1004,
         "winner_id": 1004, "winningTechnique": "Oshidashi"},
        {"matchNumber": 2, "eastRikishiId": 1001, "westRikishiId": 1002,
         "winner_id": 1002, "winningTechnique": "Yorikiri"},
    ],
}

KIMARITE = [
    {"kimarite": "oshidashi", "nameEn": "Oshidashi", "nameJp": "押し出し",
     "category": "基本技"},
    {"kimarite": "yorikiri", "nameEn": "Yorikiri", "nameJp": "寄り切り",
     "category": "基本技"},
]


class FakeApi:
    """호출 횟수를 세고, 지정한 시점에 한 번 터진다 (재개 검증용)."""

    def __init__(self, fail_on: str | None = None, kimarite_fails: bool = False):
        self.fail_on = fail_on
        self.kimarite_fails = kimarite_fails
        self.calls: list[str] = []

    def iter_rikishis(self, **kw):
        self.calls.append("rikishis")
        return iter(RIKISHI)

    def rikishis(self, **kw):
        self.calls.append("rikishis")
        return RIKISHI

    def kimarite(self):
        self.calls.append("kimarite")
        if self.kimarite_fails:
            raise RuntimeError("HTTP 400 for /api/kimarite")
        return KIMARITE

    def basho(self, basho_id):
        self.calls.append(f"basho:{basho_id}")
        return {"date": basho_id, "startDate": f"{basho_id[:4]}-{basho_id[4:]}-12",
                "endDate": f"{basho_id[:4]}-{basho_id[4:]}-26"}

    def banzuke(self, basho_id, division):
        self.calls.append(f"banzuke:{basho_id}:{division}")
        if self.fail_on == basho_id:
            raise ConnectionError("가짜 네트워크 오류")
        return BANZUKE.get(basho_id, []) if division == "Makuuchi" else []

    def torikumi(self, basho_id, division, day):
        self.calls.append(f"torikumi:{basho_id}:{division}:{day}")
        rows = [] if division != "Makuuchi" else TORIKUMI.get((basho_id, day), [])
        # 실제 API 처럼 한 겹 감싸서 돌려준다 (봉투 벗기기까지 검증)
        return {"bashoId": basho_id, "day": day, "division": division,
                "torikumi": rows}


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

    # 깨끗한 상태에서 시작
    for t in ("torikumi", "banzuke_entry", "shikona", "rikishi", "ingest_checkpoint"):
        conn.cursor().execute(f"DELETE FROM {t}")
    conn.cursor().execute("DELETE FROM heya WHERE slug NOT IN "
                          "('futagoyama','tatsunami','isegahama','tamanoi','kise',"
                          "'asakayama','isenoumi','musashigawa','nishonoseki')")

    backup = {k: list(v) for k, v in FIELD_ALIASES.items()}
    try:
        # ── 1. 낯선 필드명을 학습한다 ────────────────────────────
        print("\n[1] 필드 대응 학습")
        learned: dict[str, str] = {}
        learned.update(fieldmap.learn(RIKISHI, EXPECTED["rikishis"], FIELD_ALIASES))
        learned.update(fieldmap.learn(BANZUKE["202609"], EXPECTED["banzuke"],
                                      FIELD_ALIASES))
        from pyxisumo.sumoapi import rows_of
        wrapped = {"bashoId": "202609", "day": 1, "torikumi": TORIKUMI[("202609", 1)]}
        unwrapped = rows_of(wrapped)
        assert len(unwrapped) == 2, f"봉투를 못 벗겼다: {unwrapped}"
        learned.update(fieldmap.learn(unwrapped, EXPECTED["torikumi"], FIELD_ALIASES))
        fieldmap.install(learned)
        for logical, key in sorted(learned.items()):
            print(f"      {logical:<14} → {key}")
        check("rikishi_id 를 Rikishi_ID 로 학습", learned.get("rikishi_id") == "Rikishi_ID")
        check("rank 를 rankName 으로 학습", learned.get("rank") == "rankName")
        check("east_id 를 eastRikishiId 로 학습",
              learned.get("east_id") == "eastRikishiId")
        check("wins 를 w 로 학습 (숫자 타입 확인)", learned.get("wins") == "w")

        # ── 2. 중간에 터지는 적재 → 재개 ────────────────────────
        print("\n[2] 적재 중단 → 재개")
        api = FakeApi(fail_on="202609")
        crashed = False
        try:
            ingest.bootstrap(api, conn, "202607", "202609")
        except ConnectionError:
            crashed = True
        check("실패가 위로 전파된다", crashed)
        check("202607 은 done 으로 남는다",
              "202607" in checkpoint.completed(conn, "basho"))
        check("202609 는 failed 로 남는다",
              ("basho", "202609") in
              {(t, i) for t, i, _ in checkpoint.failed(conn, "basho")})
        rows_after_crash = int(scalar("SELECT count(*) FROM banzuke_entry") or 0)
        check("중단 시점까지의 데이터는 남아 있다", rows_after_crash == 4,
              f"{rows_after_crash}행")

        api2 = FakeApi()
        stats = ingest.bootstrap(api2, conn, "202607", "202609")
        check("재개 시 끝난 바쇼는 다시 받지 않는다", stats["skipped"] == 1,
              f"skipped={stats['skipped']}")
        check("재개 시 API 를 202607 에 대해 호출하지 않는다",
              not any("banzuke:202607" in c for c in api2.calls))
        check("남은 바쇼를 받았다", stats["basho"] == 1)
        check("실패 기록이 해소되었다", not checkpoint.failed(conn, "basho"))

        # ── 3. 적재 결과 ────────────────────────────────────────
        print("\n[3] 적재 결과")
        check("리키시 4명", scalar("SELECT count(*) FROM rikishi") == "4",
              str(scalar("SELECT count(*) FROM rikishi")))
        check("반즈케 8행", scalar("SELECT count(*) FROM banzuke_entry") == "8",
              str(scalar("SELECT count(*) FROM banzuke_entry")))
        check("취조 2행", scalar("SELECT count(*) FROM torikumi") == "2")
        # 행 수로 세지 않는다 — db/005 가 자주 쓰는 결정수를 미리 넣어 두므로
        # 표에는 용어집에서 온 것 말고도 행이 있다. 확인할 것은 '받아온 두 건이
        # 제대로 들어갔는가' 이지 '표가 비어 있었는가' 가 아니다.
        check("받아온 키마리테가 들어감",
              scalar("SELECT count(*) FROM kimarite "
                     "WHERE code IN ('oshidashi','yorikiri')") == "2")
        check("키마리테 일본어 이름이 채워짐",
              scalar("SELECT name_ja FROM kimarite WHERE code='yorikiri'") == "寄り切り",
              str(scalar("SELECT name_ja FROM kimarite WHERE code='yorikiri'")))

        # 지위 파싱과 rank_value 인코딩
        rv = scalar("""
            SELECT rank_value FROM banzuke_entry be
            JOIN rikishi r ON r.id = be.rikishi_id
            WHERE r.sumo_api_id = 1002 AND be.basho_id = '202609'
        """)
        check("東横綱의 rank_value = 0", rv == "0", f"rank_value={rv}")

        kind = scalar("""
            SELECT rank_kind::text FROM banzuke_entry be
            JOIN rikishi r ON r.id = be.rikishi_id
            WHERE r.sumo_api_id = 1003 AND be.basho_id = '202609'
        """)
        check("Ozeki 로 파싱된다", kind == "Ozeki", str(kind))

        wins = scalar("""
            SELECT wins FROM banzuke_entry be
            JOIN rikishi r ON r.id = be.rikishi_id
            WHERE r.sumo_api_id = 1004 AND be.basho_id = '202609'
        """)
        check("'w' 필드가 wins 로 들어갔다", wins == "10", str(wins))

        heya = scalar("""
            SELECT h.slug FROM rikishi r JOIN heya h ON h.id = r.heya_id
            WHERE r.sumo_api_id = 1001
        """)
        check("'stable' 이 heya 로 연결됐다", heya == "tatsunami", str(heya))

        kim = scalar("SELECT kimarite FROM torikumi WHERE match_no = 1")
        check("키마리테가 소문자로 정규화된다", kim == "oshidashi", str(kim))

        # ── 4. 용어집을 못 받아도 진행되는가 ────────────────────
        print("\n[4] 키마리테 용어집 실패 — 나머지는 진행되어야 한다")
        for t in ("torikumi", "banzuke_entry", "ingest_checkpoint"):
            conn.cursor().execute(f"DELETE FROM {t}")
        conn.cursor().execute("DELETE FROM kimarite")

        api3 = FakeApi(kimarite_fails=True)
        stats3 = ingest.bootstrap(api3, conn, "202607", "202609")
        check("용어집 실패가 전체를 멈추지 않는다", stats3["basho"] == 2,
              f"basho={stats3['basho']}")
        check("실패가 보고된다", bool(stats3["optional_failed"]),
              str(stats3["optional_failed"]))
        check("반즈케는 정상 적재된다",
              scalar("SELECT count(*) FROM banzuke_entry") == "8")
        check("대전 기록도 적재된다 (외래키 위반 없이)",
              scalar("SELECT count(*) FROM torikumi") == "2",
              str(scalar("SELECT count(*) FROM torikumi")))
        check("모르는 기술 코드가 자리만 만들어 등록된다",
              scalar("SELECT count(*) FROM kimarite") == "2",
              str(scalar("SELECT count(*) FROM kimarite")))
        check("나중에 용어집이 들어오면 덮어쓸 수 있다",
              scalar("SELECT name_ja FROM kimarite WHERE code='oshidashi'") is None)
        ingest.ingest_kimarite(FakeApi(), conn)
        conn.commit()
        check("용어집 재적재 시 일본어 이름이 채워진다",
              scalar("SELECT name_ja FROM kimarite WHERE code='oshidashi'") == "押し出し")

        # ── 5. 조용한 0행을 잡아내는가 ──────────────────────────
        print("\n[5] 반즈케 0행 — 조용히 완료로 기록되면 안 된다")
        for t in ("torikumi", "banzuke_entry", "ingest_checkpoint"):
            conn.cursor().execute(f"DELETE FROM {t}")

        class UnreadableBanzuke(FakeApi):
            """행은 오는데 키를 알아볼 수 없는 경우 (보고된 실패 상황)."""

            def banzuke(self, basho_id, division):
                self.calls.append(f"banzuke:{basho_id}:{division}")
                if division != "Makuuchi":
                    return []
                return [{"wrestlerNumber": 1001, "position": "Y1e"}]

        raised = False
        try:
            ingest.bootstrap(UnreadableBanzuke(), conn, "202609", "202609")
        except ingest.IngestError as e:
            raised = True
            check("실제 키를 오류에 담는다", "wrestlerNumber" in str(e), str(e)[:80])
        check("0행이면 예외를 올린다", raised)
        check("체크포인트가 완료로 남지 않는다",
              "202609" not in checkpoint.completed(conn, "basho"))
        check("실패로 기록된다",
              ("basho", "202609") in
              {(t, i) for t, i, _ in checkpoint.failed(conn, "basho")})

        # ── 6. 예전 버전이 남긴 '빈 완료' 기록 치유 ──────────────
        print("\n[6] 빈 채로 완료된 기록 치유")
        conn.cursor().execute("DELETE FROM ingest_checkpoint")
        conn.cursor().execute("DELETE FROM banzuke_entry")
        for bid in ("202607", "202609"):
            conn.cursor().execute(
                "INSERT INTO ingest_checkpoint (task, item, status, rows_affected) "
                "VALUES ('basho', %s, 'done', 0)", (bid,))
        from pyxisumo.setup import _heal_empty_banzuke_checkpoints

        n = _heal_empty_banzuke_checkpoints(conn)
        check("빈 완료 기록을 찾아 지운다", n == 2, f"{n}개")
        check("지운 뒤에는 다시 받는다",
              not checkpoint.completed(conn, "basho"))

        stats6 = ingest.bootstrap(FakeApi(), conn, "202607", "202609")
        check("재적재로 반즈케가 채워진다",
              scalar("SELECT count(*) FROM banzuke_entry") == "8",
              str(scalar("SELECT count(*) FROM banzuke_entry")))

        conn.cursor().execute(
            "INSERT INTO ingest_checkpoint (task, item, status, rows_affected) "
            "VALUES ('basho','202611','done',0)")
        n2 = _heal_empty_banzuke_checkpoints(conn)
        check("내용이 있는 바쇼의 기록은 건드리지 않는다", n2 == 1, f"{n2}개")
        check("정상 바쇼는 완료로 남는다",
              {"202607", "202609"} <= checkpoint.completed(conn, "basho"))

        # ── 7. 멱등성 ───────────────────────────────────────────
        print("\n[7] 멱등성")
        before = scalar("SELECT count(*) FROM banzuke_entry")
        ingest.bootstrap(FakeApi(), conn, "202607", "202609", force=True)
        after = scalar("SELECT count(*) FROM banzuke_entry")
        check("force 재적재해도 행이 늘지 않는다", before == after,
              f"{before} → {after}")

    finally:
        FIELD_ALIASES.clear()
        FIELD_ALIASES.update(backup)

    if failures:
        print(f"\nFAIL — {len(failures)}건: {failures}")
        return 1
    print("\nOK — 학습 → 적재 → 중단 → 재개 → 멱등성 전 과정 정상")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
