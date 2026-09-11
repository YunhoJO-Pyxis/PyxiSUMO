-- =====================================================================
--  초기설정 자동화용 상태 테이블
--
--  두 가지를 DB에 둔다:
--   1) app_setting        — API 필드맵 등 런타임 설정.
--                           로컬 파일로 두면 GitHub Actions 러너가 공유하지
--                           못하므로 DB에 둔다.
--   2) ingest_checkpoint  — 초기 적재 진행 상황.
--                           1958년부터 받으면 수백 개 바쇼를 순회하므로
--                           중단 지점부터 재개할 수 있어야 한다.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS app_setting (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  note       TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest_checkpoint (
  task          TEXT NOT NULL,          -- 'banzuke' | 'torikumi' | 'rikishi' ...
  item          TEXT NOT NULL,          -- '202609' 같은 단위 키
  status        TEXT NOT NULL DEFAULT 'done',   -- 'done' | 'failed' | 'running'
  rows_affected INTEGER,
  error         TEXT,
  started_at    TIMESTAMPTZ,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (task, item),
  CONSTRAINT ingest_status_chk CHECK (status IN ('done','failed','running'))
);

CREATE INDEX IF NOT EXISTS ingest_checkpoint_status_idx
  ON ingest_checkpoint (task, status);

-- 셋업 상태를 한 눈에 — setup doctor 가 읽는다
CREATE OR REPLACE VIEW v_setup_status AS
SELECT
  (SELECT count(*) FROM rikishi)                                  AS rikishi_rows,
  (SELECT count(*) FROM heya)                                     AS heya_rows,
  (SELECT count(*) FROM shikona)                                  AS shikona_rows,
  (SELECT count(*) FROM basho)                                    AS basho_rows,
  (SELECT count(*) FROM banzuke_entry)                            AS banzuke_rows,
  (SELECT count(*) FROM torikumi)                                 AS torikumi_rows,
  (SELECT count(*) FROM kimarite)                                 AS kimarite_rows,
  (SELECT count(*) FROM prediction_run)                           AS prediction_runs,
  (SELECT count(*) FROM shikona WHERE name_ko IS NOT NULL)        AS shikona_ko_rows,
  (SELECT count(*) FROM ingest_checkpoint WHERE status = 'done')  AS ckpt_done,
  (SELECT count(*) FROM ingest_checkpoint WHERE status = 'failed') AS ckpt_failed,
  (SELECT max(basho_id) FROM banzuke_entry)                       AS latest_banzuke,
  (SELECT value FROM app_setting WHERE key = 'sumoapi_field_map') AS field_map,
  pg_database_size(current_database())                            AS db_bytes;

COMMIT;
