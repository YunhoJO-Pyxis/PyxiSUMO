-- =====================================================================
--  외부 소스가 항상 일본어 이름을 주지는 않는다
--
--  kimarite.name_ja 가 NOT NULL 이라, 용어집을 아직 받지 못한 상태에서
--  대전 기록에 나온 기술 코드를 자리만 만들어 등록하려 하면 실패한다.
--  (그러면 외래키 때문에 대전 기록 전체가 들어가지 못한다)
--
--  heya·shikona 와 같은 방식으로 바꾼다: 둘 중 하나만 있으면 된다.
--
--  ※ 001 을 고치지 않고 새 파일로 분리한 이유 — 이미 적용된 마이그레이션을
--    수정하면 체크섬이 어긋나 "적용 후 파일이 변경됨" 경고가 뜬다.
-- =====================================================================

BEGIN;

ALTER TABLE kimarite ALTER COLUMN name_ja DROP NOT NULL;

DO $$ BEGIN
  ALTER TABLE kimarite
    ADD CONSTRAINT kimarite_has_a_name
    CHECK (name_ja IS NOT NULL OR name_en IS NOT NULL);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- heya_video.title 도 같은 이유로 비어 올 수 있다 (제목 없는 영상)
ALTER TABLE heya_video ALTER COLUMN title DROP NOT NULL;

COMMIT;
