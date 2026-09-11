-- =====================================================================
--  PyxiSumo / 스모 반즈케 인사이트 — 코어 스키마
--  PostgreSQL 14+ (Supabase 호환)
--
--  설계 원칙
--   1) 리키시(rikishi)는 불변 식별자. 시코나는 이력 테이블로 분리한다.
--      → 개명(照ノ富士)과 동명이인(세대 계승)을 동시에 처리하기 위함.
--   2) 서열은 정렬 가능한 단일 정수(rank_value)로 인코딩한다.
--      → 예측 엔진의 재정렬이 ORDER BY 한 줄이 된다.
--   3) 뉴스는 메타데이터만 저장한다. 본문·리드문 컬럼을 두지 않는다.
--      → 일본 저작권법 리스크 회피(설계서 三장).
-- =====================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- 열거형
-- ---------------------------------------------------------------------
DO $$ BEGIN
  CREATE TYPE division_t AS ENUM (
    'Makuuchi','Juryo','Makushita','Sandanme','Jonidan','Jonokuchi','Banzukegai'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE rank_kind_t AS ENUM (
    'Yokozuna','Ozeki','Sekiwake','Komusubi','Maegashira','Numbered'
  );
  -- 'Numbered' = 쥬료 이하의 매수만 있는 지위 (Juryo 3, Makushita 15 ...)
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE side_t AS ENUM ('E','W');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- ---------------------------------------------------------------------
-- rank_value : 전 서열을 하나의 정수로 전순서화 (낮을수록 상위)
--   division_base + rank_kind_offset + (rank_num-1)*2 + (E:0 / W:1)
--
--   東 > 西 이므로 같은 매수면 東이 항상 앞선다.
--   張出(하리다시)는 1994년 7월 폐지 → 산야쿠 3인 이상도 같은 식으로 처리.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rank_value(
  p_division  division_t,
  p_kind      rank_kind_t,
  p_num       smallint,
  p_side      side_t
) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT
      CASE p_division
        WHEN 'Makuuchi'   THEN 0
        WHEN 'Juryo'      THEN 10000
        WHEN 'Makushita'  THEN 20000
        WHEN 'Sandanme'   THEN 40000
        WHEN 'Jonidan'    THEN 60000
        WHEN 'Jonokuchi'  THEN 80000
        WHEN 'Banzukegai' THEN 99000
      END
    + CASE p_kind
        WHEN 'Yokozuna'   THEN 0
        WHEN 'Ozeki'      THEN 100
        WHEN 'Sekiwake'   THEN 200
        WHEN 'Komusubi'   THEN 300
        WHEN 'Maegashira' THEN 400
        WHEN 'Numbered'   THEN 0
      END
    + (COALESCE(p_num, 1)::int - 1) * 2
    + CASE p_side WHEN 'E' THEN 0 ELSE 1 END
$$;


-- ---------------------------------------------------------------------
-- 헤야 (部屋)
-- ---------------------------------------------------------------------
CREATE TABLE heya (
  id                 BIGSERIAL PRIMARY KEY,
  slug               TEXT UNIQUE NOT NULL,          -- 'tatsunami'
  -- Sumo-API 는 헤야를 영문으로만 준다. 일본어 표기는 나중에 채워지므로
  -- 둘 중 하나만 있으면 되도록 한다 (아래 CHECK).
  name_ja            TEXT,                          -- 立浪
  name_kana          TEXT,                          -- たつなみ
  name_en            TEXT,                          -- Tatsunami
  name_ko            TEXT,                          -- 타츠나미   ← 시트 동기화
  ichimon            TEXT,                          -- 一門 (계파)
  youtube_channel_id TEXT,
  youtube_uploads_id TEXT,                          -- uploads 재생목록(캐시)
  x_handle           TEXT,
  instagram          TEXT,
  official_url       TEXT,
  closed_on          DATE,                          -- 폐쇄된 헤야
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT heya_has_a_name CHECK (name_ja IS NOT NULL OR name_en IS NOT NULL)
);


-- ---------------------------------------------------------------------
-- 리키시 (力士) — 불변 식별자. 시코나는 여기 없다.
-- ---------------------------------------------------------------------
CREATE TABLE rikishi (
  id             BIGSERIAL PRIMARY KEY,
  sumo_api_id    INTEGER UNIQUE,        -- 외부 소스 대조 키 (없을 수 있음)
  nsk_id         TEXT UNIQUE,           -- 협회 사이트 ID (있으면)
  birth_date     DATE,
  shusshin       TEXT,                  -- 出身地 원문
  shusshin_ko    TEXT,
  height_cm      NUMERIC(4,1),
  weight_kg      NUMERIC(4,1),
  heya_id        BIGINT REFERENCES heya(id) ON DELETE SET NULL,
  debut_basho    CHAR(6),               -- 'YYYYMM'
  retired_basho  CHAR(6),               -- NULL = 현역
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX rikishi_active_idx ON rikishi (heya_id) WHERE retired_basho IS NULL;


-- ---------------------------------------------------------------------
-- 시코나 (四股名) 이력
--   동명이인 = 서로 다른 rikishi_id 를 가진 같은 name_ja 행.
--   개명      = 같은 rikishi_id 의 여러 행.
-- ---------------------------------------------------------------------
CREATE TABLE shikona (
  id          BIGSERIAL PRIMARY KEY,
  rikishi_id  BIGINT NOT NULL REFERENCES rikishi(id) ON DELETE CASCADE,
  from_basho  CHAR(6) NOT NULL,
  to_basho    CHAR(6),                  -- NULL = 현재 사용 중
  -- 소스에 따라 일본어 표기가 없을 수 있다. 둘 중 하나만 있으면 된다.
  name_ja     TEXT,                     -- 大の里
  name_kana   TEXT,                     -- おおのさと
  name_en     TEXT,                     -- Onosato
  name_ko     TEXT,                     -- 오노사토   ← 시트 동기화
  UNIQUE (rikishi_id, from_basho),
  CONSTRAINT shikona_has_a_name CHECK (name_ja IS NOT NULL OR name_en IS NOT NULL)
);
CREATE INDEX shikona_current_idx ON shikona (rikishi_id) WHERE to_basho IS NULL;

-- 4개 표기 전부로 오타 허용 검색 (요건 F5: 통합 검색)
CREATE INDEX shikona_ja_trgm ON shikona USING gin (name_ja   gin_trgm_ops);
CREATE INDEX shikona_kana_trgm ON shikona USING gin (name_kana gin_trgm_ops);
CREATE INDEX shikona_en_trgm ON shikona USING gin (name_en   gin_trgm_ops);
CREATE INDEX shikona_ko_trgm ON shikona USING gin (name_ko   gin_trgm_ops);


-- ---------------------------------------------------------------------
-- 바쇼 (場所)
-- ---------------------------------------------------------------------
CREATE TABLE basho (
  id                  CHAR(6) PRIMARY KEY,   -- '202609'
  name_ja             TEXT,                  -- 秋場所
  name_ko             TEXT,                  -- 아키 바쇼
  venue               TEXT,                  -- 両国国技館
  city                TEXT,
  banzuke_released_on DATE,                  -- 반즈케 발표일
  start_date          DATE,                  -- 初日
  end_date            DATE,                  -- 千秋楽
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT basho_id_format CHECK (id ~ '^[0-9]{6}$')
);

-- 바쇼 상태는 저장하지 않고 날짜로 계산한다 (목업의 "실시간" 표기 오류 방지)
CREATE OR REPLACE FUNCTION basho_status(p_basho basho, p_now date DEFAULT CURRENT_DATE)
RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT CASE
    WHEN p_basho.start_date IS NULL                 THEN 'unknown'
    WHEN p_now <  p_basho.start_date                THEN 'upcoming'
    WHEN p_now <= COALESCE(p_basho.end_date, p_basho.start_date + 14) THEN 'ongoing'
    ELSE 'finished'
  END
$$;


-- ---------------------------------------------------------------------
-- 반즈케 1행 = 한 바쇼에서 한 리키시의 지위 + 그 바쇼 성적
-- ---------------------------------------------------------------------
CREATE TABLE banzuke_entry (
  basho_id    CHAR(6)     NOT NULL REFERENCES basho(id) ON DELETE CASCADE,
  rikishi_id  BIGINT      NOT NULL REFERENCES rikishi(id) ON DELETE CASCADE,
  division    division_t  NOT NULL,
  rank_kind   rank_kind_t NOT NULL,
  rank_num    SMALLINT,                   -- 마에가시라 3매목 → 3
  side        side_t      NOT NULL,
  rank_label  TEXT,                       -- 원본 문자열 보존 ('Maegashira 3 East')
  wins        SMALLINT NOT NULL DEFAULT 0,
  losses      SMALLINT NOT NULL DEFAULT 0,
  absences    SMALLINT NOT NULL DEFAULT 0,  -- 休場 일수
  rank_value  INTEGER GENERATED ALWAYS AS
              (rank_value(division, rank_kind, rank_num, side)) STORED,
  PRIMARY KEY (basho_id, rikishi_id),
  CONSTRAINT banzuke_num_chk CHECK (rank_num IS NULL OR rank_num BETWEEN 1 AND 200),
  CONSTRAINT banzuke_record_chk CHECK (wins >= 0 AND losses >= 0 AND absences >= 0),
  -- 마쿠우치만 지위명(요코즈나~마에가시라)을 쓰고, 그 이하는 전부 'Numbered'.
  -- 이 제약이 없으면 Makuuchi+Numbered 가 Yokozuna 와 같은 rank_value 로 충돌한다.
  CONSTRAINT banzuke_kind_chk CHECK (
    (division = 'Makuuchi' AND rank_kind <> 'Numbered')
    OR (division <> 'Makuuchi' AND rank_kind = 'Numbered')
  )
);
CREATE INDEX banzuke_order_idx ON banzuke_entry (basho_id, rank_value);
CREATE INDEX banzuke_rikishi_idx ON banzuke_entry (rikishi_id, basho_id DESC);

-- 같은 바쇼에 같은 슬롯이 둘일 수 없다 (수집 오류를 DB가 잡아준다)
CREATE UNIQUE INDEX banzuke_slot_uniq ON banzuke_entry (basho_id, rank_value);

-- 승/패/휴장 파생값
CREATE OR REPLACE FUNCTION net_score(w smallint, l smallint, a smallint)
RETURNS integer LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT w::int - (l::int + a::int)
$$;


-- ---------------------------------------------------------------------
-- 키마리테 (決まり手) — 82수 용어집. 아카이브/가이드의 기반.
-- ---------------------------------------------------------------------
CREATE TABLE kimarite (
  code        TEXT PRIMARY KEY,      -- 'oshidashi'
  name_ja     TEXT NOT NULL,         -- 押し出し
  name_en     TEXT,
  name_ko     TEXT,                  -- 오시다시   ← 시트 동기화
  category    TEXT,                  -- 基本技 / 投げ手 / 掛け手 ...
  desc_ja     TEXT,
  desc_en     TEXT,
  desc_ko     TEXT
);


-- ---------------------------------------------------------------------
-- 취조 (取組) — 대전 기록
--   winner_id IS NULL → 불전승(不戦勝) 또는 미확정
-- ---------------------------------------------------------------------
CREATE TABLE torikumi (
  basho_id   CHAR(6)    NOT NULL REFERENCES basho(id) ON DELETE CASCADE,
  day        SMALLINT   NOT NULL,
  division   division_t NOT NULL,
  match_no   SMALLINT   NOT NULL,
  east_id    BIGINT REFERENCES rikishi(id),
  west_id    BIGINT REFERENCES rikishi(id),
  winner_id  BIGINT REFERENCES rikishi(id),
  kimarite   TEXT REFERENCES kimarite(code),
  is_fusen   BOOLEAN NOT NULL DEFAULT false,   -- 不戦勝/不戦敗
  PRIMARY KEY (basho_id, day, division, match_no),
  CONSTRAINT torikumi_day_chk CHECK (day BETWEEN 1 AND 15),
  CONSTRAINT torikumi_winner_chk
    CHECK (winner_id IS NULL OR winner_id = east_id OR winner_id = west_id)
);
CREATE INDEX torikumi_east_idx ON torikumi (east_id, basho_id);
CREATE INDEX torikumi_west_idx ON torikumi (west_id, basho_id);
CREATE INDEX torikumi_kimarite_idx ON torikumi (kimarite);


-- ---------------------------------------------------------------------
-- 우승 / 삼상 (優勝・三賞) — 아카이브 요건 F3
-- ---------------------------------------------------------------------
CREATE TABLE basho_award (
  basho_id   CHAR(6) NOT NULL REFERENCES basho(id) ON DELETE CASCADE,
  rikishi_id BIGINT  NOT NULL REFERENCES rikishi(id) ON DELETE CASCADE,
  award      TEXT    NOT NULL,   -- 'yusho' | 'jun_yusho' | 'shukun' | 'kanto' | 'gino'
  division   division_t NOT NULL DEFAULT 'Makuuchi',
  PRIMARY KEY (basho_id, rikishi_id, award, division)
);


-- ---------------------------------------------------------------------
-- 반즈케 예측 — 실행 단위로 보존한다 (적중률 계산의 전제)
-- ---------------------------------------------------------------------
CREATE TABLE prediction_run (
  id              BIGSERIAL PRIMARY KEY,
  target_basho_id CHAR(6) NOT NULL,        -- 예측 대상 (아직 basho 행이 없을 수 있어 FK 없음)
  source_basho_id CHAR(6) NOT NULL REFERENCES basho(id),
  model_version   TEXT    NOT NULL,        -- 'v1.0-linear'
  params          JSONB   NOT NULL,        -- 계수·감쇠율 등 재현용
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (target_basho_id, model_version, created_at)
);

CREATE TABLE prediction_entry (
  run_id          BIGINT  NOT NULL REFERENCES prediction_run(id) ON DELETE CASCADE,
  rikishi_id      BIGINT  NOT NULL REFERENCES rikishi(id) ON DELETE CASCADE,
  division        division_t  NOT NULL,
  rank_kind       rank_kind_t NOT NULL,
  rank_num        SMALLINT,
  side            side_t NOT NULL,
  pred_rank_value INTEGER GENERATED ALWAYS AS
                  (rank_value(division, rank_kind, rank_num, side)) STORED,
  confidence      NUMERIC(3,2),
  basis           TEXT,   -- 'ozeki_art8' | 'yokozuna_lock' | 'linear' | 'makushita15_zensho'
  PRIMARY KEY (run_id, rikishi_id)
);
CREATE INDEX prediction_order_idx ON prediction_entry (run_id, pred_rank_value);

-- 적중률: 예측 vs 실제 반즈케
CREATE TABLE prediction_accuracy (
  run_id           BIGINT PRIMARY KEY REFERENCES prediction_run(id) ON DELETE CASCADE,
  evaluated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  n_rikishi        INTEGER NOT NULL,
  exact_rate       NUMERIC(5,4),   -- 지위·매수·동서까지 완전 일치
  within1_rate     NUMERIC(5,4),   -- ±1매 이내 (주 지표)
  mae_ranks        NUMERIC(6,3),   -- 평균 절대오차(매수)
  division_correct NUMERIC(5,4)    -- 소속 디비전만 맞힌 비율
);


-- ---------------------------------------------------------------------
-- 뉴스 — 메타데이터만. title_orig 는 개변하지 않는다.
-- ---------------------------------------------------------------------
CREATE TABLE news_source (
  id            BIGSERIAL PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  rss_url       TEXT,
  site_url      TEXT,
  lang          CHAR(2) NOT NULL DEFAULT 'ja',
  -- 이용조건 확인 결과를 DB에 남긴다. false 면 수집기가 건너뛴다.
  allowed       BOOLEAN NOT NULL DEFAULT false,
  license_note  TEXT,
  checked_on    DATE
);

CREATE TABLE news_item (
  id           BIGSERIAL PRIMARY KEY,
  source_id    BIGINT NOT NULL REFERENCES news_source(id) ON DELETE CASCADE,
  url          TEXT UNIQUE NOT NULL,
  title_orig   TEXT NOT NULL,          -- 원제. 번역·개변 금지
  lang         CHAR(2) NOT NULL,
  published_at TIMESTAMPTZ,
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  rikishi_id   BIGINT REFERENCES rikishi(id) ON DELETE SET NULL  -- 시코나 매칭 결과
);
CREATE INDEX news_recent_idx ON news_item (published_at DESC NULLS LAST);


-- ---------------------------------------------------------------------
-- 헤야 미디어 (YouTube)
-- ---------------------------------------------------------------------
CREATE TABLE heya_video (
  video_id     TEXT PRIMARY KEY,
  heya_id      BIGINT NOT NULL REFERENCES heya(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  published_at TIMESTAMPTZ,
  thumbnail_url TEXT,
  duration_s   INTEGER,
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX heya_video_recent_idx ON heya_video (heya_id, published_at DESC NULLS LAST);


-- ---------------------------------------------------------------------
-- 편의 뷰
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_banzuke AS
SELECT
  be.basho_id,
  be.rank_value,
  be.division,
  be.rank_kind,
  be.rank_num,
  be.side,
  be.rank_label,
  be.wins, be.losses, be.absences,
  net_score(be.wins, be.losses, be.absences) AS net,
  r.id   AS rikishi_id,
  s.name_ja, s.name_kana, s.name_en, s.name_ko,
  h.name_ja AS heya_ja, h.name_ko AS heya_ko, h.name_en AS heya_en
FROM banzuke_entry be
JOIN rikishi r ON r.id = be.rikishi_id
LEFT JOIN LATERAL (
  SELECT * FROM shikona sk
  WHERE sk.rikishi_id = r.id
    AND sk.from_basho <= be.basho_id
    AND (sk.to_basho IS NULL OR sk.to_basho >= be.basho_id)
  ORDER BY sk.from_basho DESC LIMIT 1
) s ON true
LEFT JOIN heya h ON h.id = r.heya_id;

COMMIT;
