-- =====================================================================
--  결정수(決まり手) 한국어·일본어 표기
--
--  Sumo-API 는 결정수를 로마자 코드로만 준다 ('yorikiri'). 첫 화면의
--  '오늘의 대전' 에 그대로 찍으면 한국어 페이지에 'yorikiri' 가 남는다.
--
--  자주 나오는 기술만 넣는다. 여기에 없는 코드는 로마자로 나오고,
--  나중에 이 표에 추가하면 채워진다 — **없는 한자를 지어내지 않는다**는
--  heya_names.py 와 같은 원칙이다.
--
--  이미 값이 있으면 덮어쓰지 않는다. 스프레드시트로 손수 고친 표기가
--  마이그레이션 재실행에 지워지면 안 된다.
-- =====================================================================

BEGIN;

INSERT INTO kimarite (code, name_ja, name_ko) VALUES
  -- 기본기 (基本技)
  ('tsukidashi',        '突き出し',     '츠키다시'),
  ('tsukitaoshi',       '突き倒し',     '츠키타오시'),
  ('oshidashi',         '押し出し',     '오시다시'),
  ('oshitaoshi',        '押し倒し',     '오시타오시'),
  ('yorikiri',          '寄り切り',     '요리키리'),
  ('yoritaoshi',        '寄り倒し',     '요리타오시'),
  ('abisetaoshi',       '浴びせ倒し',   '아비세타오시'),
  -- 던지기 (投げ手)
  ('uwatenage',         '上手投げ',     '우와테나게'),
  ('shitatenage',       '下手投げ',     '시타테나게'),
  ('kotenage',          '小手投げ',     '코테나게'),
  ('sukuinage',         '掬い投げ',     '스쿠이나게'),
  ('uwatedashinage',    '上手出し投げ', '우와테다시나게'),
  ('shitatedashinage',  '下手出し投げ', '시타테다시나게'),
  ('kubinage',          '首投げ',       '쿠비나게'),
  ('ipponzeoi',         '一本背負い',   '입폰제오이'),
  ('nichonage',         '二丁投げ',     '니초나게'),
  ('yaguranage',        '櫓投げ',       '야구라나게'),
  ('kakenage',          '掛け投げ',     '카케나게'),
  ('tsukaminage',       '掴み投げ',     '츠카미나게'),
  -- 걸기 (掛け手)
  ('uchigake',          '内掛け',       '우치가케'),
  ('sotogake',          '外掛け',       '소토가케'),
  ('chongake',          'ちょん掛け',   '촌가케'),
  ('kekaeshi',          '蹴返し',       '케카에시'),
  ('ketaguri',          '蹴手繰り',     '케타구리'),
  ('kawazugake',        '河津掛け',     '카와즈가케'),
  ('watashikomi',       '渡し込み',     '와타시코미'),
  ('nimaigeri',         '二枚蹴り',     '니마이게리'),
  ('susoharai',         '裾払い',       '스소하라이'),
  ('susotori',          '裾取り',       '스소토리'),
  ('ashitori',          '足取り',       '아시토리'),
  ('mitokorozeme',      '三所攻め',     '미토코로제메'),
  -- 젖히기·비틀기 (反り手・捻り手)
  ('izori',             '居反り',       '이조리'),
  ('shumokuzori',       '撞木反り',     '슈모쿠조리'),
  ('tasukizori',        '襷反り',       '타스키조리'),
  ('tsukiotoshi',       '突き落とし',   '츠키오토시'),
  ('makiotoshi',        '巻き落とし',   '마키오토시'),
  ('tottari',           'とったり',     '톳타리'),
  ('sakatottari',       '逆とったり',   '사카톳타리'),
  ('katasukashi',       '肩透かし',     '카타스카시'),
  ('sotomuso',          '外無双',       '소토무소'),
  ('uchimuso',          '内無双',       '우치무소'),
  ('zubuneri',          'ずぶねり',     '즈부네리'),
  ('uwatehineri',       '上手捻り',     '우와테히네리'),
  ('shitatehineri',     '下手捻り',     '시타테히네리'),
  ('kubihineri',        '首捻り',       '쿠비히네리'),
  ('amiuchi',           '網打ち',       '아미우치'),
  ('sabaori',           '鯖折り',       '사바오리'),
  ('harimanage',        '波離間投げ',   '하리마나게'),
  -- 특수기 (特殊技)
  ('hikiotoshi',        '引き落とし',   '히키오토시'),
  ('hikkake',           '引っ掛け',     '힛카케'),
  ('hatakikomi',        '叩き込み',     '하타키코미'),
  ('sokubiotoshi',      '素首落とし',   '소쿠비오토시'),
  ('tsuridashi',        '吊り出し',     '츠리다시'),
  ('tsuriotoshi',       '吊り落とし',   '츠리오토시'),
  ('okuridashi',        '送り出し',     '오쿠리다시'),
  ('okuritaoshi',       '送り倒し',     '오쿠리타오시'),
  ('okurinage',         '送り投げ',     '오쿠리나게'),
  ('okurihikiotoshi',   '送り引き落とし', '오쿠리히키오토시'),
  ('kimedashi',         '極め出し',     '키메다시'),
  ('kimetaoshi',        '極め倒し',     '키메타오시'),
  ('utchari',           'うっちゃり',   '웃차리'),
  ('waridashi',         '割り出し',     '와리다시'),
  ('ushiromotare',      '後ろもたれ',   '우시로모타레'),
  -- 기술이 아닌 결정 (非技) — 상대가 스스로 무너진 경우
  ('tsukite',           '突き手',       '츠키테 (손이 먼저 닿음)'),
  ('tsukihiza',         '突き膝',       '츠키히자 (무릎이 먼저 닿음)'),
  ('isamiashi',         '勇み足',       '이사미아시 (스스로 나감)'),
  ('fumidashi',         '踏み出し',     '후미다시 (스스로 나감)'),
  ('koshikudake',       '腰砕け',       '코시쿠다케 (스스로 무너짐)'),
  ('hansoku',           '反則',         '반칙패'),
  ('fusensho',          '不戦勝',       '부전승'),
  ('fusenpai',          '不戦敗',       '부전패')
ON CONFLICT (code) DO UPDATE SET
  name_ja = COALESCE(NULLIF(kimarite.name_ja, ''), EXCLUDED.name_ja),
  name_ko = COALESCE(NULLIF(kimarite.name_ko, ''), EXCLUDED.name_ko);

COMMIT;
