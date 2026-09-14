# PyxiSUMO — Phase 0

스모 반즈케 인사이트의 데이터 기반. **PostgreSQL 스키마 + 수집 배치 + 반즈케 예측 엔진**.

상시 가동 백엔드가 없습니다. 수집·예측은 GitHub Actions cron 이 돌리고,
프론트(Next.js)는 Postgres 를 직접 읽습니다. 런타임 비용 0원에서 시작합니다.

```
db/001_schema.sql          코어 스키마 (rank_value 인코딩, 시코나 이력 분리)
db/002_seed_reference.sql  2026년 바쇼 일정, 헤야 YouTube, 뉴스 소스 정책
db/003_setup_state.sql     설정·체크포인트 상태

pyxisumo/setup.py          ★ 초기설정 자동화 (init / doctor / resume)
pyxisumo/migrate.py        마이그레이션 러너 (체크섬 기록, 재실행 안전)
pyxisumo/fieldmap.py       API 필드명 자동 학습
pyxisumo/checkpoint.py     적재 재개 지점 관리

pyxisumo/ranks.py          지위 파싱·인코딩  ← 순수 로직, DB 불필요
pyxisumo/predict.py        반즈케 예측 5단계 파이프라인  ← 순수 로직
pyxisumo/sumoapi.py        Sumo-API 클라이언트
pyxisumo/probe.py          실제 응답에서 필드 대응 학습
pyxisumo/db.py             upsert SQL 모음
pyxisumo/ingest.py         수집 배치
pyxisumo/run_predict.py    예측 실행 / 적중률 계산
pyxisumo/sync_sheets.py    스프레드시트 → 한국어 표기 동기화

.github/workflows/         초기설정 / 장중 갱신 / 일일 갱신 / 예측·평가 / CI
```

---

## 0-A. Windows — 클릭만으로

명령어를 쓰지 않으셔도 됩니다. `C:\pyxisumo` 에 압축을 풀고 번호 붙은 파일을 두 번 클릭하세요.

| 파일 | 하는 일 |
|---|---|
| `0_새버전적용하기.bat` | **새 압축본을 받았을 때 이것만** — 데이터는 그대로 두고 바뀐 것만 맞춘 뒤 웹페이지 재생성 |
| `1_설치하기.bat` | 파이썬 환경 구성 → 접속 주소 입력 → 스키마 → 필드맵 → 데이터 받기 |
| `2_상태확인.bat` | 지금 데이터가 얼마나 들어있고 이상은 없는지 |
| `3_이어받기.bat` | 받다 끊겼을 때. 받은 데까지는 건너뜀 |
| `4_예측하기.bat` | 다음 대회 순위표 예측 |
| `5_실패한것만다시받기.bat` | 일부 대회만 실패했을 때 그것만 재시도 |
| `6_예측정확도확인.bat` | 이미 끝난 대회로 예측 엔진 채점 (다음 대회를 안 기다려도 됨) |
| `7_웹페이지만들기.bat` | 이름 표기를 채우고 `docs` 폴더에 웹페이지 생성 후 브라우저로 열기 |
| `8_예측조정하기.bat` | 과거 대회로 계수를 맞춰 예측 정확도를 올림 |
| `9_이름다시채우기.bat` | 한국어·일본어 표기만 다시 채움 (헤야 한자를 추가한 뒤) |
| `A_깃허브에올리기.bat` | GitHub 저장소에 올림. 올리기 전에 **비밀번호가 새는지 먼저 검사** |
| `B_시크릿값복사하기.bat` | GitHub 에 넣을 접속 주소를 **클립보드에 담아** 줌 (손으로 복사하지 않게) |

### 새 버전을 받았을 때

> **압축은 `C:\pyxisumo` 에 풀어 덮어씁니다.** 그 안의 `pyxisumo` 폴더에 풀면
> 프로젝트 한 벌이 통째로 그 안에 들어가 옛 파일이 섞입니다. 실행에는 지장이
> 없어 눈치채기 어렵습니다 — `A_깃허브에올리기.bat` 이 이 상황을 찾아내
> `_중복파일_확인후삭제` 폴더로 옮겨 줍니다.

압축을 풀어 덮어쓴 뒤 **`0_새버전적용하기.bat` 하나만** 누르면 됩니다.

받아 둔 대회 데이터는 **건드리지 않습니다.** 스키마가 바뀌었으면 그것만 적용하고,
비어 있는 이름 표기를 채운 뒤, 웹페이지를 다시 만듭니다.

> `1_설치하기.bat` 은 누르지 마세요. 설치는 처음 한 번만 하는 것이고,
> 데이터를 받는 단계까지 다시 들어갑니다.

무엇이 바뀌었든 이 하나로 충분하지만, 굳이 나누자면 이렇습니다.

| 바뀐 것 | 필요한 것 |
|---|---|
| 화면·디자인 (`pyxisumo/site/`) | `7_웹페이지만들기.bat` |
| 이름 표기 (`romaji.py`, `heya_names.py`) | `9_이름다시채우기.bat` → `7_웹페이지만들기.bat` |
| 예측 로직 (`predict.py`) | `4_예측하기.bat` → `7_웹페이지만들기.bat` |
| 스키마 (`db/` 에 새 파일) | `0_새버전적용하기.bat` |
| 모르겠을 때 | `0_새버전적용하기.bat` |

데이터를 더 받아야 할 때만 `3_이어받기.bat` 을 씁니다 (대회가 끝난 뒤 등).
`0_새버전적용하기.bat` 이 데이터를 건드리지 않는다는 것은 `tests/check_update.py`
가 매번 확인합니다 — 행 수가 하나라도 변하면 실패합니다.

---

배치 파일은 파이썬 가상환경(`.venv`)을 만들고 `tools/wizard.py` 를 부르는 것이 전부입니다.
안내 문구는 전부 파이썬 쪽에 있습니다 — 명령 프롬프트의 한글 인코딩 문제를 피하기 위해
`.bat` 내용은 ASCII 로만 씁니다.

마법사가 대신 처리하는 것:

- Supabase 연결 문자열에서 `[YOUR-PASSWORD]` 를 감지해 비밀번호를 따로 입력받고,
  `@ # / ?` 같은 기호를 **URL 인코딩**합니다. (인코딩을 빠뜨리면 주소가 깨지는데
  에러 메시지만 보고는 원인을 알 수 없습니다 — 초보자가 가장 많이 막히는 지점입니다.)
- `psql "postgresql://..."` 를 통째로 붙여넣어도 앞부분을 떼어냅니다.
- 메모장을 거치며 끼어든 줄바꿈·공백을 제거하고 `sslmode=require` 를 붙입니다.
- 적재 범위를 3년 / 10년 / 2000년~ / 전체 중에서 예상 소요시간과 함께 고르게 합니다.

---

## 0-B. 명령줄 — 한 명령

Supabase 프로젝트를 만들어 연결 문자열만 받아오면, 나머지는 자동입니다.

```bash
cp .env.example .env      # DATABASE_URL 채우기
export $(grep -v '^#' .env | xargs)
pip install -r requirements.txt

python -m pyxisumo.setup init
```

`init` 이 하는 일:

| 단계 | 내용 |
|---|---|
| 1 | **환경 점검** — 파이썬 버전, 드라이버, DSN 접속, sslmode 경고 |
| 2 | **마이그레이션** — `db/*.sql` 순서대로 적용하고 체크섬 기록 |
| 3 | **필드맵 학습** — Sumo-API 실제 응답에서 필드 대응을 추론해 DB에 저장 |
| 4 | **참조 데이터** — 바쇼 일정·헤야 채널·뉴스 소스 정책 (002에 포함) |
| 5 | **적재** — 체크포인트 기반. 중단되면 이어받기 |
| 6 | **검증** — 행 수·무결성·용량 점검 후 리포트 |

모든 단계가 **재실행해도 안전**합니다. 중간에 끊기면 같은 명령을 다시 치면 됩니다.

```bash
python -m pyxisumo.setup init --from 195801          # 1958년부터 전량
python -m pyxisumo.setup init --skip-ingest          # 스키마·필드맵까지만
python -m pyxisumo.setup doctor                      # 지금 상태만 점검
python -m pyxisumo.setup resume                      # 중단된 적재 이어받기
python -m pyxisumo.setup retry-failed                # 실패한 바쇼만 재시도
```

GitHub Actions 의 **초기설정 / 점검** 워크플로에서도 같은 명령을 고를 수 있습니다.
러너 6시간 제한에 걸려 죽어도 `resume` 으로 이어받습니다.

### init 이 해결해 주는 세 가지

**① API 필드명을 손으로 맞출 필요가 없습니다.**
Sumo-API 는 응답 필드를 문서화하지 않습니다(webhooks 문서조차
"Execute tests to see the formats" 라고만 씁니다). 그래서 실제 응답을 보고
논리 필드 → 실제 키 대응을 **추론**합니다. `rikishiId`·`rikishi_id`·`Rikishi_ID`
같은 표기 차이는 정규화해서 잡고, `wins` 후보인 `w` 에 `"west"` 같은 문자열이
들어 있으면 타입이 안 맞으므로 채택하지 않습니다.

학습 결과는 **DB의 `app_setting`** 에 저장합니다. 로컬 파일에만 두면 Actions
러너가 공유하지 못하기 때문입니다.

```
✓ rikishi_id     → rikishiId
✓ rank           → rank
✓ wins           → w
✗ kimarite       미해결 — sumoapi.FIELD_ALIASES 에 실제 키를 추가하세요
```

미해결이 남는 필드가 있을 때만 `FIELD_ALIASES` 를 한 줄 고치면 됩니다.

**② 스키마가 조용히 갈라지지 않습니다.**
`schema_migrations` 에 파일명과 체크섬을 기록합니다. 이미 적용된 파일이 나중에
수정되면 경고합니다 — "내 DB에는 적용됐는데 남의 DB에는 안 된" 상태를 막습니다.

```
! 003_setup_state.sql — 적용 후 파일이 변경되었습니다
  (기록 efec326a ≠ 현재 b0638697). 새 마이그레이션 파일로 분리하세요.
```

**③ 적재가 끊겨도 처음부터 다시 받지 않습니다.**
1958년부터면 바쇼가 400개가 넘고, 무료 API 예의상 요청 간격이 0.6초라
몇 시간이 걸립니다. 바쇼 하나가 끝날 때마다 커밋하고 `ingest_checkpoint` 에
기록하므로, 네트워크가 끊기거나 러너가 죽어도 끝난 바쇼는 건너뜁니다.
실패는 조용히 삼키지 않고 `failed` 로 남겨 `retry-failed` 로 골라 재시도합니다.

```
[132/396] 199803  반즈케 5,412 · 취조 41,208 · 건너뜀 131  남은 예상 47분
```

### 검증 리포트

```
6. 검증
──────────────────────────────────────────────────────
    리키시     4,182    헤야         45
    시코나     5,903    바쇼        296
    반즈케    21,264    키마리테     82
    취조     198,410    예측          0
    최신 반즈케: 202609

  ✓ 같은 슬롯에 두 명이 배치된 바쇼: 없음
  ✓ 승패합이 16 이상인 성적: 없음
  ✓ 승자가 대전자가 아닌 취조: 없음
  ✓ 마쿠우치가 43명 이상인 바쇼: 없음
  ! 마쿠우치가 42명에 못 미치는 바쇼(적재 누락 가능): 2건
  ✓ DB 용량 178.4 MB — 무료 티어 500MB의 36%
```

무결성 점검은 **치명적**(데이터가 잘못 들어감)과 **비치명적**(적재가 덜 됨)을
구분합니다. 용량은 Supabase 무료 티어 500MB 기준으로 50% 경고, 80% 오류입니다.

---

## 1. 수동으로 돌리고 싶을 때

`setup init` 이 아래를 묶어 놓은 것뿐이라, 단계별로 따로 돌려도 됩니다.

```bash
python -m pyxisumo.migrate up                            # 스키마
python -m pyxisumo.probe                                 # 필드맵 학습
python -m pyxisumo.ingest kimarite                       # 키마리테 용어집
python -m pyxisumo.ingest rikishi                        # 리키시 마스터
python -m pyxisumo.ingest bootstrap --from 201801 --to 202609
```

용량은 이렇게 확인합니다.

```sql
SELECT pg_size_pretty(pg_database_size(current_database()));
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
```

---

## 3. 예측

```bash
# 아키 센슈라쿠(9/27) 다음날 → 큐슈(202611) 반즈케 예측
python -m pyxisumo.run_predict predict --source 202609 --target 202611

# 큐슈 반즈케 발표일(10/26) 직후 → 적중률
python -m pyxisumo.ingest basho --basho 202611
python -m pyxisumo.run_predict evaluate --target 202611
```

DB 없이 엔진 동작만 보려면:

```bash
python tests/demo_predict.py
```

### 엔진이 하는 일

| 단계 | 내용 | 근거 |
|---|---|---|
| 1 | 요코즈나 고정, 오제키 상태머신, 마쿠시타 전승 최우선 | 番付編成要領 8조 등 **성문 규정** |
| 2 | `score = 직전위치 − 계수 × 勝ち越し点` + 전휴 가산 + 대패 완충 | 경험칙 |
| 3 | 산야쿠 확정 (최소 2명, 코무스비 11승 승격, 오제키 33승 신호) | 확정 + 경험칙 |
| 4 | 마쿠우치 42 / 쥬료 28 정원에 맞춰 **전원 재정렬** | 확정 |
| 5 | 매수마다 東 → 西 배치 | 관례 |

**반즈케에는 정확한 규칙이 거의 없습니다.** 성문 규정은 오제키 강등·복귀,
각 단 정원, 산야쿠 최소 정원, 마쿠시타 15매목 전승 정도이고 나머지는 전부 경험칙입니다.
그래서 이 엔진의 목표는 "정답 맞히기"가 아니라 **재현 가능한 예측과 정직한 적중률**입니다.

모든 경험칙 계수는 `PredictParams` 에 있고, 실행할 때마다
`prediction_run.params` 에 JSON 으로 저장됩니다. 바쇼가 끝날 때마다 적중률을 보고
계수를 조정한 뒤 어느 파라미터로 어떤 결과가 나왔는지 되짚을 수 있습니다.

```bash
python -m pyxisumo.run_predict predict --source 202609 --coef 1.0   # 일본식 목안
python -m pyxisumo.run_predict predict --source 202609 --coef 1.72  # 회귀 실측(기본)
```

### 적중률 지표 3종

| 지표 | 의미 |
|---|---|
| `exact_rate` | 지위·매수·동서까지 완전 일치. 가장 엄격 |
| `within1_rate` | ±1매 이내 — **주 지표.** 사용자가 체감하는 정확도 |
| `mae_ranks` | 평균 절대오차(매수). 모델 개선 판단용 |

---

## 3-A. 웹페이지 만들기

```bash
python -m pyxisumo.site.build --out docs
python tests/check_site.py --dir docs
```

`docs/` 에 정적 HTML 이 생깁니다. 서버가 필요 없고, `index.html` 을 더블클릭하면
그대로 열립니다 (검색 자료를 페이지에 직접 심어서 `file://` 로 열어도 검색이 됩니다).

만들어지는 화면:

| 경로 | 내용 |
|---|---|
| `index.html` | 최신 대회 반즈케 — 東西 대칭 서열표 |
| `banzuke/<바쇼>.html` | 대회별 반즈케 아카이브 |
| `yosou.html` | 차기 반즈케 예측. 실제 반즈케가 나오면 **실제 지위·차이**를 나란히 표시 (나오기 전에는 "발표 전") + 적중률 이력 |
| `rikishi/index.html` | 선수 검색 — 한/일/영/가나 어느 표기로든. 은퇴 선수는 `은퇴` 표시 |
| `rikishi/<id>.html` | 프로필 · 대회별 성적 · 상대 전적 |
| `heya/index.html` | 헤야 디렉토리 + 공식 YouTube·SNS |

지위는 **DB의 원본 문자열(`Maegashira 3 East`)을 그대로 쓰지 않고** 항상
`rank_ko()` 로 한국어를 만들어 씁니다. 그래야 한국어 페이지에 영어가 섞이지 않습니다.
`check_site.py` 가 영어 지위가 새어나오면 실패시킵니다.

### 웹페이지 공개하기 (GitHub Pages · 무료)

1. GitHub 에서 새 저장소(New repository)를 만듭니다.
2. **`A_깃허브에올리기.bat`** 을 실행합니다. 저장소 주소를 한 번만 물어보고
   그 뒤로는 기억합니다. 처음이면 브라우저가 열리며 GitHub 로그인을 묻습니다.
3. **`B_시크릿값복사하기.bat`** 을 실행합니다. 접속 주소를 클립보드에 담고
   넣을 화면을 열어 줍니다 — `Name` 에 `DATABASE_URL`, `Secret` 에 Ctrl+V.
   (손으로 드래그해 복사하면 끝부분이 겹쳐 들어가는 사고가 납니다)
4. **Settings → Pages** 에서 Source 를 **GitHub Actions** 로 바꿉니다.
5. **Actions → 웹페이지 공개 → Run workflow** 를 누릅니다.

> **비밀번호는 올라가지 않습니다.** `.env` 는 `.gitignore` 에 있고, 그에 더해
> 올리기 직전에 모든 파일을 훑어 `.env` 의 값이나 접속 주소가 섞여 있으면
> **멈춥니다.** 저장소가 공개면 한 번 올라간 비밀번호는 되돌릴 수 없기 때문입니다.
> (이 안전장치가 실제로 동작하는지는 `tests/check_publish.py` 가 확인합니다)

이후로는 매일 아침(JST 06:30) 자동으로 다시 만들어 올립니다.
장중 성적 갱신이나 예측 실행이 끝나면 그 직후에도 다시 만듭니다.

주소는 `https://<사용자명>.github.io/<저장소명>/` 입니다.

---

## 4. 한국어 · 일본어 표기

### 자동 (기본)

Sumo-API 는 헤야를 **영문으로만** 줍니다. 그대로 두면 한국어 페이지에
`Nishonoseki` 가 나옵니다. 그래서 로마자를 한글로 음역해 비어 있는 칸을 채웁니다.

```bash
python -m pyxisumo.setup names
```

`7_웹페이지만들기.bat` 이 페이지를 만들기 전에 이 단계를 자동으로 돌리므로
평소에는 따로 실행할 일이 없습니다.

- **이미 값이 있는 칸은 절대 덮어쓰지 않습니다.** 손으로 고친 표기가 우선입니다.
- 표기는 국립국어원 외래어 표기법이 아니라 **스모 팬·매체 표기**를 따릅니다
  (코토자쿠라 / 타카야스, 고토자쿠라 / 다카야스 아님).
- 헤야 한자는 `pyxisumo/heya_names.py` 의 표에서 가져옵니다. **표에 없으면
  비워 둡니다 — 한자를 추측해서 넣지 않습니다.** 틀린 한자는 빈칸보다 나쁩니다.
  빠진 헤야가 보이면 그 파일에 한 줄 추가하고 `python -m pyxisumo.setup names`
  를 다시 돌리면 됩니다.

화면에는 `니쇼노세키 (二所ノ関)` 처럼 한국어 뒤에 일본어를 괄호로 붙입니다.
한자를 모르는 헤야는 한국어만 나오고 빈 괄호는 붙지 않습니다.

### 손으로 고치기 (스프레드시트)

음역은 기계가 하는 일이라 완벽하지 않습니다. 고치고 싶은 이름은 시트에서
덮어쓰면 되고, **그 값이 항상 이깁니다.**

시트를 `파일 → 공유 → 웹에 게시` 해두면 API 키 없이 CSV 로 읽습니다.

```
shikona  탭 :  name_ja , name_ko
heya     탭 :  slug    , name_ko
kimarite 탭 :  code    , name_ko , desc_ko
```

```bash
python -m pyxisumo.sync_sheets --sheet-id <SPREADSHEET_ID>
```

---

## 5. GitHub Actions

Secrets 에 `DATABASE_URL` (필요하면 `SHEET_ID`) 을 넣으면 됩니다.

| 워크플로 | 주기 | 하는 일 |
|---|---|---|
| `ingest-live` | JST 13:10~19:10, 20분 | 개최 중이면 성적·취조 갱신. 아니면 조용히 종료 |
| `ingest-daily` | JST 05:00 | 리키시 마스터, 키마리테, 시트 동기화 |
| `predict` | JST 07:00 | 센슈라쿠 다음날이면 예측, 반즈케 발표일이면 적중률 |
| `test` | push / PR | Postgres 서비스 컨테이너로 전체 테스트 |

GitHub cron 은 "홀수월의 15일간"을 표현할 수 없으므로, 스케줄은 넉넉히 걸고
**DB의 `basho` 테이블에 오늘이 무슨 날인지 물어보는 guard 스텝**이 판정합니다.
바쇼 상태를 컬럼으로 저장하지 않고 날짜로 계산하는 것도 같은 이유입니다
(`basho_status()` 함수) — 목업에서 7월 바쇼를 9월에 "실시간"이라고 표시한 것 같은
오류가 구조적으로 생기지 않게 합니다.

---

## 6. 테스트

```bash
# 순수 로직 62건 (DB 불필요)
python -m unittest discover -s tests -p "test_*.py" -v

# 아래는 Postgres 가 필요합니다
export DATABASE_URL='postgresql://...'
export PSQL="psql \"$DATABASE_URL\""
python tests/test_rank_value_parity.py   # Python/Postgres rank_value 일치
python tests/check_sql.py                # 모든 upsert SQL PREPARE
python tests/check_predict_sql.py        # 카도반/특례복귀 판정 SQL
python tests/check_checkpoint.py         # 적재 중단 → 재개 상태 전이
python tests/check_bootstrap.py          # 학습 → 적재 → 중단 → 재개 → 멱등성
```

`check_bootstrap.py` 는 **네트워크 없이** 전 과정을 돌립니다. 가짜 API가
일부러 낯선 필드명(`Rikishi_ID`, `rankName`, `w`, `stable`)으로 응답하고,
중간에 한 번 터집니다. 학습이 그 이름들을 잡아내는지, 중단 지점까지의 데이터가
남는지, 재개할 때 끝난 바쇼를 다시 받지 않는지를 실제 Postgres 위에서 확인합니다.

`test_rank_value_parity.py` 가 중요합니다. 서열 인코딩이 Python 과 Postgres에
이중으로 구현되어 있어서, 둘이 갈라지면 **예측 결과와 DB 정렬이 조용히 어긋납니다.**
232개 지위 조합에서 두 구현이 같은 값을 내고 값이 중복되지 않는지 매번 확인합니다.

---

## 설계 메모

**시코나를 리키시에서 분리한 이유.** 리키시는 경력 중 시코나를 바꾸고
(`若三勝 → 照ノ富士`), 같은 시코나를 다른 세대가 물려받기도 합니다.
시코나를 리키시의 속성으로 두면 이 둘을 동시에 처리할 수 없습니다.
`shikona` 테이블이 `(rikishi_id, from_basho, to_basho)` 로 이력을 갖고,
동명이인은 **서로 다른 `rikishi_id` 를 가진 같은 `name_ja` 행**이 됩니다.

**서열을 정수 하나로 인코딩한 이유.** "동 마에가시라 3매목"과 "서 코무스비" 중
누가 위인지 매번 분기문으로 따지는 대신 정렬 가능한 단일 정수로 만들면
예측 엔진의 재정렬이 `ORDER BY` 한 줄이 됩니다.
`(basho_id, rank_value)` 유니크 인덱스가 같은 슬롯에 두 명이 들어가는
수집 오류도 DB 차원에서 잡아줍니다.

**이동량을 rank_value 로 빼면 안 되는 이유.** 지위·디비전 사이에 큰 오프셋
(마에가시라 +400, 쥬료 +10000)이 있어서 뺄셈하면 "+4783매 상승" 같은 값이 나옵니다.
이동량과 적중률 오차는 반드시 **슬롯 인덱스**로 계산합니다 (1매 = 2슬롯).

**뉴스 본문 컬럼이 없는 이유.** 일본 저작권법 27조상 번역만 해도 침해이고,
제목만 모아도 요미우리 온라인 판결(지재고재 2005-10-06)이 불법행위 배상을
인정했습니다. `news_item` 은 원제·URL·매체·게재일만 갖습니다.
본문을 빼면 DB 용량도 100MB대에서 멈춰 무료 티어에 여유가 생깁니다.

**API 의존도.** Sumo-API 는 개인이 운영하는 무료 서비스입니다. 멈추면 사이트도 멈춥니다.
초기 적재 후에는 **자체 Postgres 를 정본으로 두고** API 는 증분 갱신용으로만 쓰세요.
`dai/o-sumo`(MIT, 정적 JSON, 장중 10분 갱신)를 2차 소스로 병행하면 이중화가 됩니다.

---

**헤야·시코나의 일본어 표기가 NOT NULL 이 아닌 이유.** Sumo-API 는 헤야를
영문으로만 줍니다. `name_ja NOT NULL` 로 두면 첫 적재부터 막힙니다.
대신 `CHECK (name_ja IS NOT NULL OR name_en IS NOT NULL)` 로 "이름이 하나는 있어야
한다"만 강제합니다. 일본어 표기는 나중에 시트로 채웁니다.

---

## 다음 (Phase 1)

- [ ] `python -m pyxisumo.setup init` 실행 + 용량 실측
- [ ] Next.js 반즈케 표 (목업 레이아웃 이식, 640px 이하 카드 전환)
- [ ] **9/28 큐슈 반즈케 예측 게시 → 10/26 발표 직후 적중률 자동 계산**
- [ ] 시코나 4표기(`大の里 / おおのさと / Onosato / 오노사토`) 통합 검색
