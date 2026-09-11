"""DB 접속과 upsert SQL.

드라이버는 psycopg 3 (`pip install "psycopg[binary]"`).
SQL 은 모듈 상수로 빼두었다 — tests/test_sql.py 가 실제 Postgres 에
PREPARE 로 던져 구문·컬럼명·타입을 검증한다.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Sequence


def dsn() -> str:
    """DATABASE_URL 을 쓴다. Supabase 는 커넥션 풀러(6543) 쪽을 권장."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL 이 없습니다. 예: "
            "postgresql://postgres:PW@db.xxxx.supabase.co:5432/postgres?sslmode=require"
        )
    return url


@contextmanager
def connect(autocommit: bool = False) -> Iterator[Any]:
    import psycopg  # 지연 임포트 — 순수 로직 테스트는 드라이버 없이 돈다

    with psycopg.connect(dsn(), autocommit=autocommit) as conn:
        yield conn


def executemany(conn: Any, sql: str, rows: Sequence[Sequence[Any]]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


# =====================================================================
#  UPSERT 문
#  전부 멱등(idempotent)하다 — 같은 배치를 두 번 돌려도 결과가 같다.
#  GitHub Actions cron 이 겹쳐 뜨거나 재실행돼도 안전하다.
# =====================================================================

UPSERT_HEYA = """
INSERT INTO heya (slug, name_ja, name_en, name_ko)
VALUES (%s, %s, %s, %s)
ON CONFLICT (slug) DO UPDATE SET
  name_ja = COALESCE(EXCLUDED.name_ja, heya.name_ja),
  name_en = COALESCE(EXCLUDED.name_en, heya.name_en),
  name_ko = COALESCE(EXCLUDED.name_ko, heya.name_ko),
  updated_at = now()
"""

UPSERT_RIKISHI = """
INSERT INTO rikishi (
  sumo_api_id, birth_date, shusshin, height_cm, weight_kg,
  heya_id, debut_basho, retired_basho
)
VALUES (
  %s, %s, %s, %s, %s,
  (SELECT id FROM heya WHERE slug = %s), %s, %s
)
ON CONFLICT (sumo_api_id) DO UPDATE SET
  birth_date    = COALESCE(EXCLUDED.birth_date,    rikishi.birth_date),
  shusshin      = COALESCE(EXCLUDED.shusshin,      rikishi.shusshin),
  height_cm     = COALESCE(EXCLUDED.height_cm,     rikishi.height_cm),
  weight_kg     = COALESCE(EXCLUDED.weight_kg,     rikishi.weight_kg),
  heya_id       = COALESCE(EXCLUDED.heya_id,       rikishi.heya_id),
  debut_basho   = COALESCE(EXCLUDED.debut_basho,   rikishi.debut_basho),
  retired_basho = EXCLUDED.retired_basho,
  updated_at    = now()
"""

# 시코나는 이력이다. 같은 (리키시, 시작 바쇼) 면 갱신, 아니면 새 행.
UPSERT_SHIKONA = """
INSERT INTO shikona (rikishi_id, from_basho, to_basho, name_ja, name_kana, name_en)
VALUES ((SELECT id FROM rikishi WHERE sumo_api_id = %s), %s, %s, %s, %s, %s)
ON CONFLICT (rikishi_id, from_basho) DO UPDATE SET
  to_basho  = EXCLUDED.to_basho,
  name_ja   = COALESCE(EXCLUDED.name_ja,   shikona.name_ja),
  name_kana = COALESCE(EXCLUDED.name_kana, shikona.name_kana),
  name_en   = COALESCE(EXCLUDED.name_en,   shikona.name_en)
"""

# 한국어 표기는 사람이 스프레드시트에서 채운다 (설계서 二장).
# 기계번역이 大の里를 "큰 마을"로 바꾸는 사고를 막기 위해 별도 경로로 둔다.
UPDATE_SHIKONA_KO = """
UPDATE shikona SET name_ko = %s
WHERE name_ja = %s AND (name_ko IS DISTINCT FROM %s)
"""

UPSERT_BASHO = """
INSERT INTO basho (id, name_ja, start_date, end_date)
VALUES (%s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
  name_ja    = COALESCE(EXCLUDED.name_ja,    basho.name_ja),
  start_date = COALESCE(EXCLUDED.start_date, basho.start_date),
  end_date   = COALESCE(EXCLUDED.end_date,   basho.end_date),
  updated_at = now()
"""

UPSERT_BANZUKE = """
INSERT INTO banzuke_entry (
  basho_id, rikishi_id, division, rank_kind, rank_num, side,
  rank_label, wins, losses, absences
)
VALUES (
  %s, (SELECT id FROM rikishi WHERE sumo_api_id = %s),
  %s::division_t, %s::rank_kind_t, %s, %s::side_t,
  %s, %s, %s, %s
)
ON CONFLICT (basho_id, rikishi_id) DO UPDATE SET
  division   = EXCLUDED.division,
  rank_kind  = EXCLUDED.rank_kind,
  rank_num   = EXCLUDED.rank_num,
  side       = EXCLUDED.side,
  rank_label = EXCLUDED.rank_label,
  wins       = EXCLUDED.wins,
  losses     = EXCLUDED.losses,
  absences   = EXCLUDED.absences
"""

UPSERT_KIMARITE = """
INSERT INTO kimarite (code, name_ja, name_en, category)
VALUES (%s, %s, %s, %s)
ON CONFLICT (code) DO UPDATE SET
  name_ja  = COALESCE(EXCLUDED.name_ja,  kimarite.name_ja),
  name_en  = COALESCE(EXCLUDED.name_en,  kimarite.name_en),
  category = COALESCE(EXCLUDED.category, kimarite.category)
"""

# torikumi.kimarite 가 kimarite(code) 를 참조하므로, 용어집이 비어 있으면
# 대전 기록 삽입이 전부 외래키 위반으로 실패한다. 처음 보는 기술 코드는
# 이름만 담은 자리를 먼저 만들어 둔다 — 나중에 용어집이 들어오면 채워진다.
UPSERT_KIMARITE_STUB = """
INSERT INTO kimarite (code, name_en) VALUES (%s, %s)
ON CONFLICT (code) DO NOTHING
"""

UPSERT_TORIKUMI = """
INSERT INTO torikumi (
  basho_id, day, division, match_no,
  east_id, west_id, winner_id, kimarite, is_fusen
)
VALUES (
  %s, %s, %s::division_t, %s,
  (SELECT id FROM rikishi WHERE sumo_api_id = %s),
  (SELECT id FROM rikishi WHERE sumo_api_id = %s),
  (SELECT id FROM rikishi WHERE sumo_api_id = %s),
  %s, %s
)
ON CONFLICT (basho_id, day, division, match_no) DO UPDATE SET
  east_id   = EXCLUDED.east_id,
  west_id   = EXCLUDED.west_id,
  winner_id = EXCLUDED.winner_id,
  kimarite  = EXCLUDED.kimarite,
  is_fusen  = EXCLUDED.is_fusen
"""

INSERT_PREDICTION_RUN = """
INSERT INTO prediction_run (target_basho_id, source_basho_id, model_version, params)
VALUES (%s, %s, %s, %s)
RETURNING id
"""

INSERT_PREDICTION_ENTRY = """
INSERT INTO prediction_entry (
  run_id, rikishi_id, division, rank_kind, rank_num, side, confidence, basis
)
VALUES (%s, %s, %s::division_t, %s::rank_kind_t, %s, %s::side_t, %s, %s)
ON CONFLICT (run_id, rikishi_id) DO UPDATE SET
  division  = EXCLUDED.division,
  rank_kind = EXCLUDED.rank_kind,
  rank_num  = EXCLUDED.rank_num,
  side      = EXCLUDED.side,
  confidence = EXCLUDED.confidence,
  basis     = EXCLUDED.basis
"""

UPSERT_ACCURACY = """
INSERT INTO prediction_accuracy (
  run_id, n_rikishi, exact_rate, within1_rate, mae_ranks, division_correct
)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (run_id) DO UPDATE SET
  evaluated_at     = now(),
  n_rikishi        = EXCLUDED.n_rikishi,
  exact_rate       = EXCLUDED.exact_rate,
  within1_rate     = EXCLUDED.within1_rate,
  mae_ranks        = EXCLUDED.mae_ranks,
  division_correct = EXCLUDED.division_correct
"""

UPSERT_NEWS_ITEM = """
INSERT INTO news_item (source_id, url, title_orig, lang, published_at)
VALUES ((SELECT id FROM news_source WHERE slug = %s), %s, %s, %s, %s)
ON CONFLICT (url) DO UPDATE SET
  title_orig   = EXCLUDED.title_orig,
  published_at = COALESCE(EXCLUDED.published_at, news_item.published_at)
"""

UPSERT_HEYA_VIDEO = """
INSERT INTO heya_video (video_id, heya_id, title, published_at, thumbnail_url, duration_s)
VALUES (%s, (SELECT id FROM heya WHERE slug = %s), %s, %s, %s, %s)
ON CONFLICT (video_id) DO UPDATE SET
  title         = EXCLUDED.title,
  published_at  = EXCLUDED.published_at,
  thumbnail_url = EXCLUDED.thumbnail_url,
  duration_s    = EXCLUDED.duration_s,
  fetched_at    = now()
"""

# 테스트가 순회할 대상
ALL_STATEMENTS: dict[str, str] = {
    "UPSERT_HEYA": UPSERT_HEYA,
    "UPSERT_RIKISHI": UPSERT_RIKISHI,
    "UPSERT_SHIKONA": UPSERT_SHIKONA,
    "UPDATE_SHIKONA_KO": UPDATE_SHIKONA_KO,
    "UPSERT_BASHO": UPSERT_BASHO,
    "UPSERT_BANZUKE": UPSERT_BANZUKE,
    "UPSERT_KIMARITE": UPSERT_KIMARITE,
    "UPSERT_KIMARITE_STUB": UPSERT_KIMARITE_STUB,
    "UPSERT_TORIKUMI": UPSERT_TORIKUMI,
    "INSERT_PREDICTION_RUN": INSERT_PREDICTION_RUN,
    "INSERT_PREDICTION_ENTRY": INSERT_PREDICTION_ENTRY,
    "UPSERT_ACCURACY": UPSERT_ACCURACY,
    "UPSERT_NEWS_ITEM": UPSERT_NEWS_ITEM,
    "UPSERT_HEYA_VIDEO": UPSERT_HEYA_VIDEO,
}
