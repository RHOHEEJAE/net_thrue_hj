# net_thrue_01 프로젝트 재현용 프롬프트 (순서대로)

아래 프롬프트를 **빈 채팅창에 순서대로 하나씩** 붙여 넣어 실행하면, net_thrue_01(헥토 행동 데이터 트래커) 프로젝트가 처음부터 그대로 만들어질 수 있도록 구성했습니다.  
각 프롬프트는 이전 대화 없이도 실행 가능하도록 작성했습니다.

---

## 프롬프트 1 — 프로젝트 개요·폴더·의존성

```
다음 요구사항으로 프로젝트 루트를 만들어줘.

- 프로젝트명: net_thrue_01 (헥토 행동 데이터 트래커)
- 목적: 웹/앱 행동 이벤트(페이지뷰, 클릭, 스크롤 등)를 변수·트리거·태그 설정으로 수집하고, Kafka로 전달한 뒤 PostgreSQL에 저장·집계하여 대시보드로 분석하는 자체 트래킹 서비스

폴더 구조:
- app.py (FastAPI 진입점, 일단 빈 라우트만)
- requirements.txt: fastapi>=0.109.1, uvicorn[standard]>=0.24.0, psycopg2-binary>=2.9.11, kafka-python>=2.0.3
- docker-compose.yml (아직 서비스 정의 없어도 됨, 주석만 있어도 됨)
- db/ (DB 스크립트용)
- repo/ (Python 모듈용)
- static/ (HTML/정적 파일용)
- data/ (변수·트리거·태그 JSON 저장용)
- settings/ (배포된 설정 latest.json 및 versions용)
- kafka_client/ (Kafka 프로듀서·컨슈머용)

README.md에 "헥토 행동 데이터 트래커. Docker Compose로 실행. 자세한 내용은 docs 참고." 한 줄만 적어줘.
```

---

## 프롬프트 2 — DB 스키마 및 초기화

```
net_thrue_01 프로젝트에 PostgreSQL 스키마를 추가해줘.

1) create_user_table.sql (db/ 또는 루트)
- users 테이블: id SERIAL PRIMARY KEY, username VARCHAR UNIQUE NOT NULL, password_hash VARCHAR NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()

2) db/add_user_roles_and_approval.sql
- users에 role VARCHAR(20) DEFAULT 'user', status VARCHAR(20) DEFAULT 'pending', approved_at, approved_by 컬럼 추가 (ALTER TABLE)

3) db/create_analytics_tables.sql
- raw_events: id BIGSERIAL PRIMARY KEY, tag_code, act_type, event_trigger, channel, page_url, page_id, referer_url, context JSONB, payload JSONB, client_ts, server_ts TIMESTAMPTZ, ip, user_agent, created_at. 인덱스: server_ts, page_id, act_type, channel
- agg_page_events: stat_date, page_id, channel, act_type, event_trigger, event_count, updated_at. UNIQUE(stat_date, page_id, channel, act_type, event_trigger)
- funnel_definition: id, funnel_code UNIQUE, funnel_name, steps JSONB, enabled
- agg_funnel_daily: funnel_id FK, stat_date, step_order, step_name, users_entered, users_completed, users_dropped, drop_off_rate. UNIQUE(funnel_id, stat_date, step_order)
- agg_heatmap: stat_date, page_id, channel, heatmap_type, segment_key, event_count. UNIQUE(stat_date, page_id, channel, heatmap_type, segment_key)
- funnel_definition에 commerce_purchase 기본 퍼널 INSERT (ON CONFLICT DO NOTHING)

4) db/init_admin.sql
- username 'admin', password_hash는 bcrypt 또는 간단한 해시로 'admin' 암호화해서 INSERT (ON CONFLICT DO NOTHING)

5) db/connect.py
- 환경변수 POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD 사용해 psycopg2 연결 반환하는 get_db_conn()
```

---

## 프롬프트 3 — Docker Compose 및 Dockerfile

```
net_thrue_01에 Docker Compose와 앱 Dockerfile을 추가해줘.

docker-compose.yml:
- postgres: postgres:15, 포트 5432, 환경변수 POSTGRES_DB=testdb, POSTGRES_USER=testuser, POSTGRES_PASSWORD=testpass. healthcheck pg_isready. volumes postgres_data
- db-init: postgres:15, depends_on postgres healthy 후 다음 순서로 실행: create_user_table.sql, db/add_user_roles_and_approval.sql, db/create_analytics_tables.sql, db/init_admin.sql. volumes로 프로젝트 루트 마운트, 작업 디렉토리 /app
- zookeeper: zookeeper:3.7.1, 포트 2181
- kafka: confluentinc/cp-kafka:7.2.3, depends_on zookeeper, 포트 9092, KAFKA_ZOOKEEPER_CONNECT, KAFKA_LISTENERS 등 설정
- app-api: build ., depends_on db-init 성공·kafka 시작 후, 환경변수 POSTGRES_*, KAFKA_BOOTSTRAP_SERVERS=kafka:9092, KAFKA_TOPIC=test. 포트 8000. command uvicorn app:app --host 0.0.0.0 --port 8000
- app-consumer: 같은 이미지, command python -m kafka_client.consumer. 동일 DB·Kafka 환경변수
- app-funnel-agg: 같은 이미지, command 60초마다 run_funnel_agg.py 실행 (while loop). DB 환경변수만
- kafka-ui: provectuslabs/kafka-ui, 포트 18080, KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS kafka:9092

Dockerfile: Python 3.11 이상 베이스, WORKDIR /app, requirements.txt 복사 후 pip install, 프로젝트 전체 복사. CMD uvicorn app:app --host 0.0.0.0 --port 8000
.dockerignore: venv, __pycache__, .git, *.pyc
```

---

## 프롬프트 4 — 설정 저장소(file_repo) 및 변수·트리거·태그 데이터

```
net_thrue_01에 설정 파일 기반 저장소를 추가해줘.

repo/file_repo.py:
- DATA_DIR = "data", VARIABLES_FILE, TRIGGERS_FILE, TAGS_FILE, VARIABLE_GROUPS_FILE
- load_json_file(path, default=[]), save_json_file(path, data)
- get_variables() → 활성 변수 코드 목록, get_variables_full() → 전체 목록
- upsert_variables(list), replace_variables(list)
- get_variable_groups, upsert_variable_groups, replace_variable_groups
- get_triggers / get_triggers_full, upsert_triggers, replace_triggers
- get_tags / get_tags_full, upsert_tags, replace_tags

data/variables.json, data/triggers.json, data/tags.json, data/variable_groups.json 은 빈 배열 [] 로 초기 파일 생성해줘. data/standard_addon.json 은 표준용 예시로 variables에 type url (page_path, page_url), type element (click_text_std, click_class_std), triggers에 CLICK_STANDARD, tags에 nlogger 타입 STANDARD_CLICK 한 개씩 넣어줘.
```

---

## 프롬프트 5 — 사용자·인증 저장소 및 로그인/회원가입 API

```
net_thrue_01의 app.py에 다음을 구현해줘.

repo/user_repo.py:
- verify_user(username, password) → (ok, role, status). DB users에서 username 조회, password 해시 비교. status가 pending이면 ok=False, status 반환
- create_user(username, password) → 비밀번호 해시 후 INSERT, 중복 시 False
- list_all_users() → id, username, role, status, approved_at, approved_by 등 목록
- approve_user(username, role, approver) → status='approved', role 설정, approved_at=NOW(), approved_by
- get_user(username) → 단일 사용자 정보

app.py:
- FastAPI 앱, CORS allow_origins=["*"], static 파일 mount /static → static
- 세션: 메모리 dict, 쿠키 session_token (httponly, 24시간)
- get_session_token(request), get_session_user(request) → { username, role }
- require_login, require_admin 의존성
- POST /api/login: body username, password. verify_user 호출, 성공 시 세션 발급, role이 user면 redirectUrl /static/dashboard.html, 아니면 /static/admin.html. 쿠키 설정
- POST /api/logout: 세션 삭제, 쿠키 삭제
- GET /api/check-auth: { authenticated, role, username }
- POST /api/signup: username, password 검증 후 create_user. "가입 신청 완료, 관리자 승인 후 로그인 가능" 메시지
- GET /: RedirectResponse /static/login.html
```

---

## 프롬프트 6 — 설정 API·배포·수집 API(Kafka 전송)

```
net_thrue_01의 app.py에 설정·배포·수집 API를 추가해줘.

- settings/latest.json 있으면 로드, 없으면 { variables: [], triggers: {}, tags: [] }. GET /settings/latest → JSON 반환 (인증 없음, SDK용)
- GET /admin/config (require_admin): file_repo에서 variables_full, variable_groups_full, triggers_full, tags_full 반환
- POST /admin/config (require_admin): body의 variables, variable_groups, triggers, tags를 file_repo upsert
- 트리거를 DOM 이벤트 맵으로 변환하는 함수: event_type dom_ready → immediate, element_click/click → dom_event+click+css_selector, custom → event_config.event_name. conditions 포함
- POST /admin/deploy (require_admin): 현재 data 기준으로 설정 객체 생성 (version YYYYMMDD_HHMMSS, comment, deployed_at, variables, triggers 맵, tags, variables_full, triggers_full, tags_full, variable_groups_full). settings/latest.json 덮어쓰기, settings/versions/{version}.json 저장
- GET /admin/deploy/versions: 버전 목록 및 current
- POST /admin/deploy/rollback: body version. 해당 버전 파일로 latest 복원 및 data 파일들 복원
- DELETE /admin/deploy/versions/{version}: 해당 버전 파일만 삭제
- kafka_client/connect.py: get_kafka_producer() → KafkaProducer(bootstrap_servers=env KAFKA_BOOTSTRAP_SERVERS, value_serializer=json.dumps)
- POST /collect (인증 없음): body JSON 수신. load_settings()로 활성 variables 목록 확인 후 context 추출. event 객체에 tag_code, act_type, event_trigger, channel, page_url, page_id, referer_url, context, payload, client_ts, server_ts, ip, user_agent. get_kafka_producer().send(KAFKA_TOPIC, value=event), flush. KAFKA_TOPIC은 환경변수 기본 "test". 응답 { ok: true } 또는 400/503
```

---

## 프롬프트 7 — 계정 관리 API 및 분석 저장소(analytics_repo)

```
net_thrue_01에 계정 관리 API와 집계 로직을 추가해줘.

app.py:
- GET /api/admin/accounts (require_admin): list_all_users() 반환
- POST /api/admin/accounts/approve (require_admin): body username, role. approve_user 호출
- POST /api/create-user (require_admin): body username, password, role. create_user 후 바로 approve_user

repo/analytics_repo.py:
- insert_raw_event(event): raw_events에 INSERT, RETURNING id
- upsert_agg_page_events(stat_date, page_id, channel, act_type, event_trigger): ON CONFLICT DO UPDATE SET event_count += 1
- upsert_agg_heatmap(stat_date, page_id, channel, heatmap_type, segment_key): 동일
- process_event_aggregations(event, stat_date): insert_raw_event 후, agg_page_events 1건 증가. act_type이 scroll이면 scroll_rate 25/50/75/99에 대해 agg_heatmap. act_type이 click이면 click_text, class_name으로 agg_heatmap
- run_funnel_daily_aggregation(stat_date): funnel_definition에서 enabled인 퍼널 조회, raw_events에서 (ip, stat_date)별 최대 도달 단계 계산 후 agg_funnel_daily UPSERT
- get_agg_page_events(date_from, date_to, group_by, page_id_filter, channel_filter, act_type_filter, limit): agg_page_events 집계 조회
- get_distinct_channels(date_from, date_to): DISTINCT channel 목록 정렬 반환
- get_overview_metrics(date_from, date_to, page_id_filter, channel_filter): raw_events 기반 방문자수, 방문수, 페이지뷰, 이탈률, 방문당 조회수, 평균 방문 기간
- get_funnel_definitions(), get_agg_funnel_daily(date_from, date_to, funnel_id), get_agg_heatmap(...)
```

---

## 프롬프트 8 — Kafka 컨슈머 및 퍼널 집계 스크립트

```
net_thrue_01에 Kafka 컨슈머와 퍼널 집계 스크립트를 추가해줘.

kafka_client/consumer.py:
- KafkaConsumer(KAFKA_TOPIC, bootstrap_servers, group_id, value_deserializer=json.loads), auto_offset_reset=latest
- for message in consumer: event = message.value. insert_raw_event(event). server_ts로 stat_date 계산. process_event_aggregations(event, stat_date)
- __main__에서 run_consumer()

run_funnel_agg.py:
- 인자로 YYYY-MM-DD 받거나 없으면 어제·오늘. analytics_repo.run_funnel_daily_aggregation(d) 호출
```

---

## 프롬프트 9 — 대시보드 API 및 정적 페이지(로그인·회원가입)

```
net_thrue_01에 대시보드용 API와 로그인·회원가입 페이지를 추가해줘.

app.py:
- GET /api/dashboard/page_events (require_login): date_from, date_to, group_by, page_id, channel, act_type, limit. get_agg_page_events 호출
- GET /api/dashboard/overview_stats (require_login): date_from, date_to, page_id, channel. get_overview_metrics
- GET /api/dashboard/channels (require_login): date_from, date_to. get_distinct_channels
- GET /api/dashboard/funnels, GET /api/dashboard/funnel_daily, GET /api/dashboard/heatmap (require_login)
- POST /api/dashboard/funnel_agg (require_login): body date 선택. run_funnel_daily_aggregation
- date 파라미터 파싱: 없으면 기본 30일 전~오늘. _empty_to_none으로 "undefined"/빈 문자열 제거

static/login.html: 로그인 폼 (username, password), POST /api/login 호출 후 응답 redirectUrl로 이동 또는 메시지 표시
static/signup.html: 회원가입 폼 (username, password), POST /api/signup 호출 후 "가입 신청 완료" 메시지
```

---

## 프롬프트 10 — Admin 페이지(변수·트리거·태그·배포·버전·계정)

```
net_thrue_01에 관리자용 Admin 페이지를 추가해줘.

static/admin.html:
- 헤더: 제목, "행동 분석 대시보드" 링크, "계정 관리" 링크, "Kafka UI" 링크, [저장] [게시] [로그아웃]. 관리자는 /api/check-auth role이 admin일 때만 대시보드·계정 링크 표시
- 게시 모달: 이름, 소속, 게시 코멘트 입력 후 POST /admin/deploy
- 좌측 사이드바: 변수 | 트리거 | 태그 | 버전. 클릭 시 해당 패널만 표시
- 변수 패널: 탭 [기본 변수 | 변수 | 변수 그룹]. 기본 변수는 참고용 목록(clickElement, path, url 등). 변수 탭: 목록(코드, 이름, 사용 토글, 상세 수정, 삭제), + 변수 추가. 상세 모달: 변수 코드, 이름, 설명, 유형(문자열/숫자/쿠키/DOM요소/URL(표준)/요소(표준)/스크립트/스크립트 전역 변수), 유형별 필드, 사용 체크
- 트리거 패널: 목록(코드, 이름, 이벤트 타입, 사용, 상세, 삭제), + 트리거 추가. 상세 모달: 트리거 코드, 이름, 설명, 이벤트 유형(페이지 로드/DOM 준비완료/URL 주소 변경/특정 요소 클릭/클릭/커스텀 등), 이벤트별 필드(CSS 선택자/이벤트명 등), 조건(변수·연산자·값 행 추가), 사용
- 태그 패널: 목록(코드, 이름, 연결 트리거, 실행 순서, 사용, 상세, 삭제), + 태그 추가. 상세 모달: 태그 코드, 이름, 설명, 실행조건·예외조건(트리거 선택), 유형(스크립트 | 헥토 로깅 모듈). 스크립트면 함수 코드 textarea. nlogger면 전송방식, 로그 유형, 파라미터(키·값=변수), 쿠키, 사용
- 변수 그룹: 그룹명, 설명, 구성(키·값 쌍), + 추가
- 버전 패널: GET /admin/deploy/versions로 목록 표시. 롤백 버튼(POST rollback), 삭제 버튼(DELETE)
- 로드 시 GET /admin/config, 저장 시 POST /admin/config. 로그인 체크 /api/check-auth, 비로그인 시 /static/login.html로 이동, role user면 /static/dashboard.html로 리다이렉트
```

---

## 프롬프트 11 — 계정 관리 페이지 및 대시보드(개요·페이지 이벤트·퍼널·히트맵)

```
net_thrue_01에 계정 관리 페이지와 행동 분석 대시보드를 추가해줘.

static/accounts.html (관리자 전용):
- GET /api/admin/accounts로 사용자 목록. 테이블: username, role, status, approved_at. status가 pending인 행에 [승인] 버튼. 승인 시 POST /api/admin/accounts/approve { username, role: "admin"|"user" }. 로그인·관리자 체크

static/dashboard.html:
- 헤더: 제목, (관리자면 Admin·계정 관리 링크), Kafka UI 링크, [새로고침] [로그아웃], 60초 자동 새로고침 체크박스
- 필터: 기간(date_from, date_to), 7일/30일/90일 프리셋, 집계 기준(group_by: page_id/stat_date/act_type/event_trigger/channel), 필터 page_id(텍스트), 필터 channel(드롭다운), 필터 act_type(텍스트), [적용]
- 채널 드롭다운: GET /api/dashboard/channels?date_from=&date_to= 로 기간 내 존재하는 channel 목록 조회 후 <select> 옵션으로 채움. 옵션 value=""는 "전체". 적용·새로고침·프리셋 클릭 시 loadChannelOptions() 후 데이터 로드
- 탭: 개요 | 페이지 이벤트 | 퍼널 | 히트맵
- 개요: GET /api/dashboard/overview_stats, GET /api/dashboard/page_events (group_by stat_date, page_id, act_type). KPI 카드(총 페이지뷰, 총 이벤트, 방문자수, 방문 횟수, 방문당 조회수, 이탈률, 평균 방문 기간), 이벤트 추이 차트, 인기 페이지·이벤트 유형별 테이블
- 페이지 이벤트: GET /api/dashboard/page_events. 차트·테이블, group_by 변경 가능
- 퍼널: GET /api/dashboard/funnels로 퍼널 선택, GET /api/dashboard/funnel_daily. 퍼널 집계 실행 버튼 POST /api/dashboard/funnel_agg
- 히트맵: GET /api/dashboard/heatmap. heatmap_type 스크롤/클릭 선택, 테이블
- 모든 API 호출 시 credentials: "include". 401 시 로그인 페이지로
```

---

## 프롬프트 12 — 클라이언트 SDK(ntm.js)

```
net_thrue_01 루트에 클라이언트 SDK ntm.js를 추가해줘.

동작 요약:
- 비동기 IIFE, 중복 로드 방지(window.__NTM_SDK_LOADED)
- GET /settings/latest 로 설정 로드. settings.variables(활성 변수 코드), variables_full, triggers(맵), tags(exec_order 정렬)
- 변수: type url/element/string은 스크립트 없이 해석, type script는 {{변수명}} 치환 후 Function 실행. getBuiltInContext(clickEl, customData)로 path, url, clickText 등 제공. getMergedVariableValues(payload, clickEl)로 수집 시 사용
- 트리거 조건: evaluateTriggerConditions(conditions, varValues). 연산자 같음/포함/정규식/미만·이상 등
- 전송: buildCollectPayload(base, varValues, extra)로 페이로드 구성. COLLECT_EXCLUDE_VARS에 있는 변수는 제외. sendToCollect(payload, eventTrigger) → produceEvent (sendBeacon 우선, 실패 시 fetch 재시도)
- DOM_READY: DOM/load 시 runDOMReadyOnce → runDOMReady. DOM_READY 연결 태그 실행(PV_DETAIL 제외), 페이지뷰 1건 전송(channel, page_id, act_type pageview). channel은 varValues.channel || "Rround"
- URL 변경: history.pushState/replaceState, popstate 후 maybeSendPageviewOnUrlChange → sendPageviewForUrl
- 클릭: document click capture. clickTriggerCodes(triggers 중 event click/element_click). 요소·조건 매칭 후 buildCollectPayload(act_type click, channel, page_id, click_text, class_name 등) → sendToCollect
- 스크롤: scroll 이벤트 스로틀, 25/50/75/99% 구간별 1회만 전송(scrollThresholdsSent). act_type scroll, scroll_rate
- 커스텀: customEventMap으로 event_name별 트리거 등록. Ntm00002.Event.fireUserDefined(eventName, data) → document.dispatchEvent(CustomEvent). 리스너에서 varValues·매칭 후 buildCollectPayload + customData → sendToCollect
- 태그: nlogger는 parameters(key→변수값)로 payload 구성 후 sendToCollect. script는 func_js에서 trackerFunc(send) 패턴으로 send 주입, send(payload) 시 변수 병합 후 sendToCollect
- 5분마다 설정 재조회, version 바뀌면 location.reload()
- SETTINGS_API, COLLECT_URL은 http://localhost:8000 기준
```

---

## 프롬프트 13 — README 정리 및 (선택) 사이트별 SDK·문서

```
net_thrue_01의 README.md를 다음 내용으로 정리해줘.

- 제목: 헥토 행동 데이터 트래커 (net_thrue_01)
- 요약: 웹/앱 행동 이벤트를 변수·트리거·태그 설정으로 수집하고 Kafka를 통해 저장·분석하는 자체 인프라 기반 트래킹 서비스
- 실행: Docker, Docker Compose v2. docker compose up -d. PostgreSQL, Zookeeper, Kafka, API, 컨슈머, 퍼널 집계, Kafka UI 기동. 최초 실행 시 DB 테이블·초기 관리자(admin/admin) 생성
- 로그인: http://localhost:8000/static/login.html. 회원가입 /static/signup.html. 관리자 승인 후 로그인
- 관리자: 컨테이너 관리(변수·트리거·태그 편집, 배포, 배포 이력·롤백), 행동 분석 대시보드, 계정 관리
- 일반 사용자: 행동 분석 대시보드만
- 주요 URL 표: 로그인, 회원가입, Admin, 대시보드, 계정 관리, Kafka UI 18080, /settings/latest, /collect
- 트래커 붙이기: 수집 대상 페이지에 ntm.js 로드. 배포된 설정으로 페이지뷰·클릭·스크롤·커스텀 이벤트 수집
- 문제 해결: 로그인 실패 시 admin/admin 확인, 데이터 없을 때 Kafka·컨슈머·트래커 확인

(선택) sdk/ntm_29cm.js: ntm.js와 동일 로직이되 상수 CHANNEL = "twenty_nine_cm" 정의. buildCollectPayload 마지막에 out.channel = CHANNEL, sendToCollect에서 base.channel = CHANNEL. 이 SDK 사용 시 설정의 channel 변수와 무관하게 항상 twenty_nine_cm로 전송되도록 해줘.
```

---

## 사용 방법

1. **새 채팅**을 연다.
2. **프롬프트 1**을 복사해 붙여 넣고 실행한다.
3. 생성·수정된 파일을 확인한 뒤, **프롬프트 2**를 붙여 넣고 실행한다.
4. 같은 방식으로 **프롬프트 3 → 4 → … → 13**까지 순서대로 실행한다.
5. 13까지 반영한 뒤 `docker compose up -d`로 기동하고, 로그인·배포·대시보드·수집 동작을 확인한다.

필요하면 특정 프롬프트만 골라 실행하거나, "프롬프트 5에서 비밀번호는 bcrypt로 해싱해줘"처럼 세부 요구만 추가해서 사용하면 된다.
