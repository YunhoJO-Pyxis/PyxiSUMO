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
  -- 마쿠시타는 예측 재료로만 받는다 (쥬료 승격 후보를 알기 위해).
  -- 화면에 내보내면 프로필 페이지가 없는 선수로 링크가 걸려 깨지고,
  -- 머리글의 '총 70명' 과도 어긋난다.
  AND division IN ('Makuuchi','Juryo')
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

# --- 한 번에 다 가져오는 판 ---------------------------------------------
#
# 선수 한 명마다 따로 물어보면 원격 DB(Supabase)에서 감당이 안 된다.
# 왕복 한 번에 0.1초만 잡아도 선수 1,500명 × 2번 = 5분이 그냥 간다.
# 본바쇼 중에는 20분마다 갱신이 도는데 생성이 20분 걸리면 서로 취소돼
# **사이트가 영영 갱신되지 않는다.** 그래서 통째로 받아 파이썬에서 묶는다.

RIKISHI_HISTORY_ALL = """
SELECT be.rikishi_id,
       be.basho_id,
       COALESCE(b.name_ko, b.name_ja, be.basho_id) AS basho_name,
       be.rank_label, be.rank_value, be.division::text,
       be.wins, be.losses, be.absences,
       be.rank_kind::text, be.rank_num, be.side::text
FROM banzuke_entry be
LEFT JOIN basho b ON b.id = be.basho_id
WHERE be.division IN ('Makuuchi','Juryo')
ORDER BY be.rikishi_id, be.basho_id DESC
"""

# 대전 기록을 동/서 양방향으로 펼쳐 한 번에 집계한다.
RIKISHI_OPPONENTS_ALL = """
WITH pair AS (
  SELECT east_id AS me, west_id AS opp, winner_id FROM torikumi
  UNION ALL
  SELECT west_id AS me, east_id AS opp, winner_id FROM torikumi
)
SELECT p.me, p.opp,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       count(*) AS bouts,
       count(*) FILTER (WHERE p.winner_id = p.me)  AS wins,
       count(*) FILTER (WHERE p.winner_id = p.opp) AS losses
FROM pair p
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = p.opp
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
GROUP BY p.me, p.opp, s.name_ko, s.name_ja, s.name_en
HAVING count(*) >= 2
ORDER BY p.me, count(*) DESC, p.opp
"""

# 헤야 소속 세키토리도 헤야마다 묻지 않고 한 번에. (기준은 HEYA_MEMBERS 와 같다)
HEYA_MEMBERS_ALL = """
SELECT h.slug, r.id,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       be.rank_label, be.rank_value, be.basho_id,
       be.rank_kind::text, be.rank_num, be.side::text, be.division::text
FROM rikishi r
JOIN heya h ON h.id = r.heya_id
JOIN banzuke_entry be
  ON be.rikishi_id = r.id
 AND be.basho_id = (SELECT max(basho_id) FROM banzuke_entry)
 AND be.division IN ('Makuuchi','Juryo')
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk WHERE sk.rikishi_id = r.id
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
WHERE r.retired_basho IS NULL
ORDER BY h.slug, be.rank_value
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
# '세키토리' 는 **지금** 마쿠우치·쥬료에 있는 사람이다.
#
#   예전 판은 "마쿠우치·쥬료 기록이 한 번이라도 있는가" 로 셌다. 그래서
#   쥬료에 있다가 마쿠시타로 떨어진 선수(예: 후타고야마의 三田 — 2025년
#   11월 쥬료 3매, 2026년 9월 현재 마쿠시타 15매)가 계속 세키토리로
#   잡혔다. 한 번 관취가 된 사람은 영원히 관취로 남는 셈이었다.
#
#   기준은 최신 반즈케다. 그 반즈케에 이름이 없으면(휴장·번付외) 세키토리가
#   아니다 — 실제 대우도 그렇다.
HEYA_LIST = """
WITH cur AS (SELECT max(basho_id) AS bid FROM banzuke_entry)
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
           WHERE be.rikishi_id = r.id
             AND be.basho_id = (SELECT bid FROM cur)
             AND be.division IN ('Makuuchi','Juryo')
         )) AS n_sekitori
  FROM rikishi r
  WHERE r.retired_basho IS NULL
  GROUP BY r.heya_id
) m ON m.heya_id = h.id
ORDER BY m.n_sekitori DESC NULLS LAST, h.slug
"""

# 한 헤야 소속 세키토리 — **최신 반즈케 기준** (위 HEYA_LIST 주석 참고).
#   예전에는 '마지막으로 세키토리였던 대회'의 지위를 가져왔다. 그래서 지금은
#   마쿠시타인 선수가 옛 쥬료 지위를 단 채 현역 세키토리처럼 보였다.
HEYA_MEMBERS = """
SELECT r.id,
       COALESCE(s.name_ko, s.name_ja, s.name_en, '?') AS name,
       be.rank_label, be.rank_value, be.basho_id,
       be.rank_kind::text, be.rank_num, be.side::text, be.division::text
FROM rikishi r
JOIN heya h ON h.id = r.heya_id AND h.slug = %s
JOIN banzuke_entry be
  ON be.rikishi_id = r.id
 AND be.basho_id = (SELECT max(basho_id) FROM banzuke_entry)
 AND be.division IN ('Makuuchi','Juryo')
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

# ---------------------------------------------------------------------
#  그날의 대전 (取組) — 첫 화면의 '오늘의 대전'
# ---------------------------------------------------------------------
# 대전이 들어 있는 가장 마지막 날. 아직 결과가 없는 날(편성만 된 날)도
# 포함한다 — 그날이 바로 '오늘의 대전표'이기 때문이다.
TORIKUMI_LATEST_DAY = """
SELECT max(day) FROM torikumi WHERE basho_id = %s
"""

# 역대 상대 전적을 **한 번에** 계산한다.
#   대전마다 따로 물으면 하루 40경기 × 1회 = 40왕복이 된다. Supabase 처럼
#   인터넷 너머에 있는 DB 에서는 이것만으로 20초가 날아간다 (fill_names 에서
#   같은 실수를 한 적이 있다).
#
#   쌍은 (작은 id, 큰 id) 로 정규화한다. 그래야 東西가 바뀌어도 같은 쌍으로
#   묶인다 — 실제로 대전마다 東西는 바뀐다.
TORIKUMI_DAY = """
WITH h2h AS (
  SELECT least(east_id, west_id)  AS lo,
         greatest(east_id, west_id) AS hi,
         count(*) FILTER (WHERE winner_id IS NOT NULL) AS bouts,
         count(*) FILTER (WHERE winner_id = least(east_id, west_id))    AS lo_wins,
         count(*) FILTER (WHERE winner_id = greatest(east_id, west_id)) AS hi_wins
  FROM torikumi
  WHERE east_id IS NOT NULL AND west_id IS NOT NULL
  GROUP BY 1, 2
)
SELECT t.division::text, t.match_no,
       t.east_id, es.name, es.ja,
       eb.division::text, eb.rank_kind::text, eb.rank_num, eb.side::text,
       t.west_id, ws.name, ws.ja,
       wb.division::text, wb.rank_kind::text, wb.rank_num, wb.side::text,
       t.winner_id,
       COALESCE(NULLIF(k.name_ko, ''), NULLIF(k.name_ja, ''),
                NULLIF(k.name_en, ''), t.kimarite) AS kimarite,
       t.is_fusen,
       COALESCE(h.bouts, 0) AS bouts,
       CASE WHEN t.east_id < t.west_id
            THEN COALESCE(h.lo_wins, 0) ELSE COALESCE(h.hi_wins, 0) END AS east_wins,
       CASE WHEN t.east_id < t.west_id
            THEN COALESCE(h.hi_wins, 0) ELSE COALESCE(h.lo_wins, 0) END AS west_wins
FROM torikumi t
LEFT JOIN LATERAL (
  SELECT COALESCE(sk.name_ko, sk.name_ja, sk.name_en, '?') AS name, sk.name_ja AS ja
  FROM shikona sk WHERE sk.rikishi_id = t.east_id
  ORDER BY sk.from_basho DESC LIMIT 1
) es ON true
LEFT JOIN LATERAL (
  SELECT COALESCE(sk.name_ko, sk.name_ja, sk.name_en, '?') AS name, sk.name_ja AS ja
  FROM shikona sk WHERE sk.rikishi_id = t.west_id
  ORDER BY sk.from_basho DESC LIMIT 1
) ws ON true
LEFT JOIN banzuke_entry eb
       ON eb.basho_id = t.basho_id AND eb.rikishi_id = t.east_id
LEFT JOIN banzuke_entry wb
       ON wb.basho_id = t.basho_id AND wb.rikishi_id = t.west_id
LEFT JOIN kimarite k ON k.code = t.kimarite
LEFT JOIN h2h h ON h.lo = least(t.east_id, t.west_id)
               AND h.hi = greatest(t.east_id, t.west_id)
WHERE t.basho_id = %s AND t.day = %s
  AND t.division IN ('Makuuchi', 'Juryo')
-- 지위가 높은 대전을 위에 놓는다. 실제 진행 순서(아래 지위부터)와는 반대지만,
-- 화면에서는 요코즈나 대전을 맨 밑에서 찾게 만들지 않는 편이 낫다.
ORDER BY least(COALESCE(eb.rank_value, 999999),
               COALESCE(wb.rank_value, 999999)), t.match_no
"""

ALL_QUERIES = {
    "BASHO_LIST": (BASHO_LIST, 0),
    "TORIKUMI_LATEST_DAY": (TORIKUMI_LATEST_DAY, 1),
    "TORIKUMI_DAY": (TORIKUMI_DAY, 2),
    "BANZUKE": (BANZUKE, 1),
    "LATEST_PREDICTION": (LATEST_PREDICTION, 0),
    "PREDICTION_ENTRIES": (PREDICTION_ENTRIES, 1),
    "ACCURACY_HISTORY": (ACCURACY_HISTORY, 0),
    "PROFILE_RIKISHI": (PROFILE_RIKISHI, 0),
    "RIKISHI_HISTORY": (RIKISHI_HISTORY, 1),
    "RIKISHI_OPPONENTS": (RIKISHI_OPPONENTS, 1),
    "RIKISHI_HISTORY_ALL": (RIKISHI_HISTORY_ALL, 0),
    "RIKISHI_OPPONENTS_ALL": (RIKISHI_OPPONENTS_ALL, 0),
    "HEYA_MEMBERS_ALL": (HEYA_MEMBERS_ALL, 0),
    "HEYA_LIST": (HEYA_LIST, 0),
    "HEYA_MEMBERS": (HEYA_MEMBERS, 1),
    "SITE_STATS": (SITE_STATS, 0),
}
