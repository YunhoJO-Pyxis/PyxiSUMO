-- =====================================================================
--  참조 데이터 시드 — 바쇼 일정, 헤야 미디어, 뉴스 소스 정책
--  (성적·반즈케 데이터는 ingest.py 가 API에서 가져온다)
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 2026년 본바쇼 일정
--   편성회의 = 千秋楽 3일 후(통상 수요일), 반즈케 발표 = 初日 13일 전 월요일
--   (春場所는 2/23 天皇誕生日 때문에 2/24 로 순연)
-- ---------------------------------------------------------------------
INSERT INTO basho (id, name_ja, name_ko, venue, city, banzuke_released_on, start_date, end_date) VALUES
  ('202601','初場所',   '하츠 바쇼',   '両国国技館',       '東京',   '2025-12-22','2026-01-11','2026-01-25'),
  ('202603','春場所',   '하루 바쇼',   'エディオンアリーナ大阪','大阪','2026-02-24','2026-03-08','2026-03-22'),
  ('202605','夏場所',   '나츠 바쇼',   '両国国技館',       '東京',   '2026-04-27','2026-05-10','2026-05-24'),
  ('202607','名古屋場所','나고야 바쇼', 'IGアリーナ',        '名古屋', '2026-06-29','2026-07-12','2026-07-26'),
  ('202609','秋場所',   '아키 바쇼',   '両国国技館',       '東京',   '2026-08-31','2026-09-13','2026-09-27'),
  ('202611','九州場所', '큐슈 바쇼',   '福岡国際センター', '福岡',   '2026-10-26','2026-11-08','2026-11-22')
ON CONFLICT (id) DO UPDATE SET
  name_ja = EXCLUDED.name_ja,
  name_ko = EXCLUDED.name_ko,
  venue   = EXCLUDED.venue,
  city    = EXCLUDED.city,
  banzuke_released_on = EXCLUDED.banzuke_released_on,
  start_date = EXCLUDED.start_date,
  end_date   = EXCLUDED.end_date;


-- ---------------------------------------------------------------------
-- 헤야 — YouTube 채널이 확인된 곳만 우선 시드.
-- 나머지 헤야(총 45개)는 ingest.py 가 API에서 채운다.
-- ---------------------------------------------------------------------
INSERT INTO heya (slug, name_ja, name_ko, name_en, youtube_channel_id, x_handle, official_url) VALUES
  ('futagoyama', '二子山',   '후타고야마',   'Futagoyama', 'UCq2bD4BLzP0hdtBw3c7BYEw', NULL, NULL),
  ('tatsunami',  '立浪',     '타츠나미',     'Tatsunami',  'UCUJrVwo3_mgUmOyZN81oLkg', NULL, 'https://www.tatsunami.jp/'),
  ('isegahama',  '伊勢ヶ濱', '이세가하마',   'Isegahama',  'UC1oS9raqjGaD7Ey2dUpLkdA', NULL, NULL),
  ('tamanoi',    '玉ノ井',   '타마노이',     'Tamanoi',    'UCskR-cLlm31Tw_6nqvUSATg', NULL, NULL),
  ('kise',       '木瀬',     '키세',         'Kise',       'UCI7RWhANvHeMxOyHsjgLwdg', NULL, NULL),
  ('asakayama',  '浅香山',   '아사카야마',   'Asakayama',  'UCD6xH6N6t1JpdC7u8WpVZWg', NULL, NULL),
  ('isenoumi',   '伊勢ノ海', '이세노우미',   'Isenoumi',   'UC5anti4g3SrK8IAP7Oe7DeA', NULL, NULL),
  ('musashigawa','武蔵川',   '무사시가와',   'Musashigawa','UCO52y9pO_RUO2GkzyXQfvlg', NULL, 'https://musashigawa.com/'),
  ('nishonoseki','二所ノ関', '니쇼노세키',   'Nishonoseki', NULL, 'nishonosekibeya', 'https://nishonosekibeya.com/')
ON CONFLICT (slug) DO UPDATE SET
  youtube_channel_id = COALESCE(EXCLUDED.youtube_channel_id, heya.youtube_channel_id),
  name_ko = EXCLUDED.name_ko,
  x_handle = COALESCE(EXCLUDED.x_handle, heya.x_handle),
  official_url = COALESCE(EXCLUDED.official_url, heya.official_url);


-- ---------------------------------------------------------------------
-- 뉴스 소스 — allowed=false 인 곳은 수집기가 건너뛴다.
-- 조사 결과를 DB에 남겨, 나중에 "이거 왜 안 긁지?" 를 방지한다.
-- ---------------------------------------------------------------------
INSERT INTO news_source (slug, name, rss_url, site_url, lang, allowed, license_note, checked_on) VALUES
  ('yahoo_news', 'Yahoo!ニュース', 'https://news.yahoo.co.jp/rss', 'https://news.yahoo.co.jp/', 'ja', false,
   '이용조건: RSS는 개인 이용 한정. RSS를 이용한 사이트/앱 공개 및 재배신 불허 → 서비스 사용 불가', '2026-09-11'),
  ('jiji', '時事通信', 'https://www.jiji.com/rss/', 'https://www.jiji.com/', 'ja', false,
   'robots.txt 로 /rss/ 크롤 금지', '2026-09-11'),
  ('google_news', 'Google News', NULL, 'https://news.google.com/', 'ja', false,
   'robots.txt 로 /rss/ 금지. 비공식·비지원 엔드포인트이며 ToS 위반 소지', '2026-09-11'),
  ('nikkansports', '日刊スポーツ', NULL, 'https://www.nikkansports.com/rss/', 'ja', false,
   'RSS 목록 페이지는 생존 확인(2026-09-09). 개별 피드 URL과 이용조건 미확인 → 확인 후 allowed=true 로 변경', '2026-09-11'),
  ('nhk', 'NHK NEWS WEB', NULL, 'https://www3.nhk.or.jp/news/', 'ja', false,
   'RSS는 존재하나 2025년 전후 엔드포인트 이동으로 불안정. 이용규약 직접 확인 필요', '2026-09-11'),
  ('jsa_official', '日本相撲協会 お知らせ', NULL, 'https://www.sumo.or.jp/IrohaKyokaiInformation/', 'ja', false,
   'RSS/API 없음. robots.txt 부재(=금지 미표명)이나 전재 허락은 별도 문의 필요', '2026-09-11')
ON CONFLICT (slug) DO UPDATE SET
  allowed = EXCLUDED.allowed,
  license_note = EXCLUDED.license_note,
  checked_on = EXCLUDED.checked_on;

COMMIT;
