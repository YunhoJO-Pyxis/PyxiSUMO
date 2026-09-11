"""사이트 생성에 쓰는 조회문.

SQL 을 한곳에 모아두면 tests/check_site.py 가 전부 실제 DB에 던져
구문과 컬럼명을 검증할 수 있다.
"""

from __future__ import annotations

# 반즈케가 들어 있는 바쇼 목록 (최신순)
BASHO_LIST = """
SELECT b.id,
       COALESCE(b.name_ko, b.name_ja, b.id)       AS name,
       b.name_ja,
       b.venue,
       b.start_date::text,
       b.end_date::text,
       basho_status(b.*)                          AS status,
       COALESCE(c.n, 0)                           AS n_entries,
       COALESCE(c.played, 0)                      AS played
FROM basho b
LEFT JOIN (
  SELECT basho_id,
         count(*) AS n,
         sum(wins + losses + absences) AS played
  FROM banzuke_entry
  WHERE division IN ('Makuuchi','Juryo')
  GROUP BY basho_id
) c ON c.basho_id = b.id
WHERE COALESCE(c.n, 0) > 0
ORDER BY b.id DESC
"""

# 한 바쇼의 반즈케 전체
BANZUKE = """
SELECT rank_value, division::text, rank_kind::text, rank_num, side::text,
       rank_label, wins, losses, absences, net,
       rikishi_id,
       COALESCE(name_ko, name_ja, name_en, '?')   AS name,
       name_ja, name_en, name_kana,
       COALESCE(heya_ko, heya_ja, heya_en, '')    AS heya,
       heya_ja
FROM v_banzuke
WHERE basho_id = %s
ORDER BY rank_value
"""

# 최신 예측 실행
LATEST_PREDICTION = """
SELECT id, target_basho_id, source_basho_id, model_version,
       created_at::date::text
FROM prediction_run
ORDER BY id DESC
LIMIT 1
"""

PREDICTION_ENTRIES = """
SELECT pe.pred_rank_value, pe.division::text, pe.rank_kind::text,
       pe.rank_num, pe.side::text, pe.confidence, pe.basis,
       pe.rikishi_id,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       s.name_ja,
       COALESCE(h.name_ko, h.name_ja, h.name_en, '')  AS heya,
       h.name_ja                                      AS heya_ja,
       be.rank_label   AS prev_rank_label,
       be.wins, be.losses, be.absences,
       be.rank_kind::text AS prev_kind, be.rank_num AS prev_num,
       be.side::text AS prev_side, be.division::text AS prev_div,
       -- 실제로 발표된 반즈케 (아직 없으면 전부 NULL → '발표 전')
       ab.rank_kind::text AS act_kind, ab.rank_num AS act_num,
       ab.side::text AS act_side, ab.division::text AS act_div,
       ab.rank_label AS act_label
FROM prediction_entry pe
JOIN rikishi r ON r.id = pe.rikishi_id
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = r.id
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
LEFT JOIN heya h ON h.id = r.heya_id
LEFT JOIN prediction_run pr ON pr.id = pe.run_id
LEFT JOIN banzuke_entry be
       ON be.rikishi_id = pe.rikishi_id AND be.basho_id = pr.source_basho_id
LEFT JOIN banzuke_entry ab
       ON ab.rikishi_id = pe.rikishi_id AND ab.basho_id = pr.target_basho_id
WHERE pe.run_id = %s
ORDER BY pe.pred_rank_value
"""

ACCURACY_HISTORY = """
SELECT pr.target_basho_id, pr.model_version, pa.n_rikishi,
       pa.exact_rate, pa.within1_rate, pa.mae_ranks, pa.division_correct,
       pa.evaluated_at::date::text
FROM prediction_accuracy pa
JOIN prediction_run pr ON pr.id = pa.run_id
ORDER BY pr.target_basho_id DESC
"""

# 프로필 페이지를 만들 대상 — 실제로 반즈케에 오른 세키토리만
PROFILE_RIKISHI = """
SELECT r.id,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       s.name_ja, s.name_en, s.name_kana,
       COALESCE(h.name_ko, h.name_ja, h.name_en, '')  AS heya,
       h.name_ja                                       AS heya_ja,
       h.slug                                          AS heya_slug,
       r.shusshin,
       r.height_cm::text, r.weight_kg::text,
       r.birth_date::text,
       r.debut_basho, r.retired_basho,
       hi.n_basho, hi.best_rank_value, hi.best_rank_label,
       hi.best_kind, hi.best_num, hi.best_side, hi.best_div,
       hi.total_wins, hi.total_losses, hi.total_absences,
       hi.last_basho
FROM rikishi r
JOIN LATERAL (
  SELECT count(*) AS n_basho,
         min(rank_value) AS best_rank_value,
         (array_agg(rank_label ORDER BY rank_value))[1] AS best_rank_label,
         (array_agg(rank_kind::text ORDER BY rank_value))[1] AS best_kind,
         (array_agg(rank_num ORDER BY rank_value))[1] AS best_num,
         (array_agg(side::text ORDER BY rank_value))[1] AS best_side,
         (array_agg(division::text ORDER BY rank_value))[1] AS best_div,
         sum(wins) AS total_wins,
         sum(losses) AS total_losses,
         sum(absences) AS total_absences,
         max(basho_id) AS last_basho
  FROM banzuke_entry be
  WHERE be.rikishi_id = r.id AND be.division IN ('Makuuchi','Juryo')
) hi ON hi.n_basho > 0
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = r.id
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
LEFT JOIN heya h ON h.id = r.heya_id
ORDER BY hi.best_rank_value, r.id
"""

# 한 리키시의 바쇼별 성적
RIKISHI_HISTORY = """
SELECT be.basho_id,
       COALESCE(b.name_ko, b.name_ja, be.basho_id) AS basho_name,
       be.rank_label, be.rank_value, be.division::text,
       be.wins, be.losses, be.absences,
       be.rank_kind::text, be.rank_num, be.side::text
FROM banzuke_entry be
LEFT JOIN basho b ON b.id = be.basho_id
WHERE be.rikishi_id = %s AND be.division IN ('Makuuchi','Juryo')
ORDER BY be.basho_id DESC
"""

# 상대 전적 (많이 붙은 순)
RIKISHI_OPPONENTS = """
SELECT opp.id,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       count(*) AS bouts,
       count(*) FILTER (WHERE t.winner_id = %(me)s) AS wins,
       count(*) FILTER (WHERE t.winner_id = opp.id) AS losses
FROM torikumi t
JOIN rikishi opp
  ON opp.id = CASE WHEN t.east_id = %(me)s THEN t.west_id ELSE t.east_id END
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = opp.id
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
WHERE %(me)s IN (t.east_id, t.west_id)
GROUP BY opp.id, s.name_ko, s.name_en, s.name_ja
HAVING count(*) >= 2
ORDER BY count(*) DESC, opp.id
LIMIT 20
"""

# 헤야 디렉토리
HEYA_LIST = """
SELECT h.slug,
       COALESCE(h.name_ko, h.name_ja, h.name_en, h.slug) AS name,
       h.name_ja, h.name_en,
       h.youtube_channel_id, h.x_handle, h.instagram, h.official_url,
       COALESCE(m.n_active, 0)   AS n_active,
       COALESCE(m.n_sekitori, 0) AS n_sekitori
FROM heya h
LEFT JOIN (
  SELECT r.heya_id,
         count(*) AS n_active,
         count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM banzuke_entry be
           WHERE be.rikishi_id = r.id AND be.division IN ('Makuuchi','Juryo')
         )) AS n_sekitori
  FROM rikishi r
  WHERE r.retired_basho IS NULL
  GROUP BY r.heya_id
) m ON m.heya_id = h.id
ORDER BY m.n_sekitori DESC NULLS LAST, h.slug
"""

# 한 헤야 소속 세키토리
HEYA_MEMBERS = """
SELECT r.id,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       be.rank_label, be.rank_value, be.basho_id,
       be.rank_kind::text, be.rank_num, be.side::text, be.division::text
FROM rikishi r
JOIN heya h ON h.id = r.heya_id AND h.slug = %s
JOIN LATERAL (
  SELECT * FROM banzuke_entry b
  WHERE b.rikishi_id = r.id AND b.division IN ('Makuuchi','Juryo')
  ORDER BY b.basho_id DESC LIMIT 1
) be ON true
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = r.id
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
WHERE r.retired_basho IS NULL
ORDER BY be.rank_value
"""

# 사이트 전체 통계 (첫 화면)
SITE_STATS = """
SELECT (SELECT count(*) FROM rikishi)                               AS rikishi,
       (SELECT count(*) FROM banzuke_entry)                         AS banzuke,
       (SELECT count(*) FROM torikumi)                              AS torikumi,
       (SELECT count(DISTINCT basho_id) FROM banzuke_entry)          AS basho,
       (SELECT min(basho_id) FROM banzuke_entry)                     AS first_basho,
       (SELECT max(basho_id) FROM banzuke_entry)                     AS last_basho
"""

ALL_QUERIES = {
    "BASHO_LIST": (BASHO_LIST, 0),
    "BANZUKE": (BANZUKE, 1),
    "LATEST_PREDICTION": (LATEST_PREDICTION, 0),
    "PREDICTION_ENTRIES": (PREDICTION_ENTRIES, 1),
    "ACCURACY_HISTORY": (ACCURACY_HISTORY, 0),
    "PROFILE_RIKISHI": (PROFILE_RIKISHI, 0),
    "RIKISHI_HISTORY": (RIKISHI_HISTORY, 1),
    "RIKISHI_OPPONENTS": (RIKISHI_OPPONENTS, 1),
    "HEYA_LIST": (HEYA_LIST, 0),
    "HEYA_MEMBERS": (HEYA_MEMBERS, 1),
    "SITE_STATS": (SITE_STATS, 0),
}
