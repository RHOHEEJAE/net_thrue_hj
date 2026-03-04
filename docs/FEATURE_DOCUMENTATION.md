# net_thrue_01 — 기능별 상세 문서

헥토 행동 데이터 트래커(net_thrue_01)의 **기능별 상세 설명** 문서입니다.  
웹/앱 행동 이벤트 수집·저장·분석 파이프라인과 각 구성 요소의 역할을 정리했습니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [인증·계정 관리](#2-인증계정-관리)
3. [변수·트리거·태그 설정](#3-변수트리거태그-설정)
4. [배포 및 버전 관리](#4-배포-및-버전-관리)
5. [클라이언트 SDK (ntm.js)](#5-클라이언트-sdk-ntmjs)
6. [이벤트 수집 및 Kafka 파이프라인](#6-이벤트-수집-및-kafka-파이프라인)
7. [데이터 저장 및 집계](#7-데이터-저장-및-집계)
8. [행동 분석 대시보드](#8-행동-분석-대시보드)
9. [인프라 및 실행 환경](#9-인프라-및-실행-환경)

---

## 1. 프로젝트 개요

### 1.1 목적

- **웹/앱**에서 발생하는 행동 이벤트(페이지뷰, 클릭, 스크롤 등)를 **설정만으로** 수집하고,
- **Kafka**를 통해 실시간 전달한 뒤 **PostgreSQL**에 저장·집계하여,
- **대시보드**에서 기간·페이지·채널 등으로 필터링해 분석할 수 있는 **자체 트래킹 서비스**입니다.

### 1.2 전체 흐름

```
[관리자] Admin에서 변수·트리거·태그 편집 → 배포
    ↓
[웹 페이지] ntm.js 로드 → /settings/latest 로 설정 수신
    ↓
[사용자 행동] 페이지뷰·클릭·스크롤 등 → 트리거 발동 → 변수 값 계산
    ↓
[SDK] POST /collect → API 서버 → Kafka 토픽(test)
    ↓
[컨슈머] Kafka 구독 → raw_events INSERT + agg_page_events·agg_heatmap 갱신
    ↓
[퍼널 집계] run_funnel_agg.py → agg_funnel_daily 갱신
    ↓
[대시보드] 기간·필터로 페이지 이벤트·퍼널·히트맵 조회
```

### 1.3 사용자 역할

| 역할 | 접근 가능 기능 |
|------|----------------|
| **admin** | 변수·트리거·태그 편집, 배포, 배포 이력·롤백, 행동 분석 대시보드, 계정 관리 |
| **user** | 행동 분석 대시보드만 (설정·배포·계정 관리 불가) |

---

## 2. 인증·계정 관리

### 2.1 로그인

- **엔드포인트**: `POST /api/login`
- **요청**: `{ "username": "...", "password": "..." }`
- **동작**:
  - DB에서 사용자 검증 (`user_repo.verify_user`).
  - 승인 대기(`pending`) 사용자는 401 + "가입 승인 대기 중입니다" 반환.
  - 성공 시 세션 토큰 발급, 쿠키 `session_token` 설정(24시간), 역할에 따라 리다이렉트 URL 반환.
- **리다이렉트**:
  - `role === "user"` → `/static/dashboard.html`
  - 그 외(admin) → `/static/admin.html`

### 2.2 로그아웃

- **엔드포인트**: `POST /api/logout`
- 서버 메모리 세션 삭제 및 `session_token` 쿠키 제거.

### 2.3 인증 상태 확인

- **엔드포인트**: `GET /api/check-auth`
- **응답**: `{ "authenticated": true|false, "role": "admin"|"user"|null, "username": "..." }`

### 2.4 회원가입

- **엔드포인트**: `POST /api/signup`
- **요청**: `{ "username": "...", "password": "..." }`
- **규칙**: 아이디 3자 이상, 비밀번호 4자 이상. 중복 아이디 시 400.
- **동작**: 사용자 생성 시 기본적으로 **승인 대기(pending)**. 관리자 승인 후 로그인 가능.

### 2.5 계정 관리 (관리자 전용)

- **계정 목록**: `GET /api/admin/accounts`  
  - 전체 사용자 목록(승인 대기·승인됨, 권한 포함).
- **승인 및 권한 지정**: `POST /api/admin/accounts/approve`  
  - Body: `{ "username": "...", "role": "admin"|"user" }`  
  - 해당 사용자를 승인하고 권한 설정.
- **계정 직접 생성**: `POST /api/create-user`  
  - Body: `{ "username", "password", "role" }`  
  - 생성과 동시에 승인 처리(관리자가 직접 계정 만들 때 사용).

### 2.6 권한 체크

- **의존성**:
  - `require_login`: 로그인 필요(미로그인 시 401).
  - `require_admin`: 관리자만 접근(비관리자 시 403).

---

## 3. 변수·트리거·태그 설정

설정은 **편집용 파일**(`data/variables.json`, `data/triggers.json`, `data/tags.json`, `data/variable_groups.json`)과 **배포된 설정**(`settings/latest.json`)으로 구분됩니다.  
SDK와 수집 API는 **배포된 설정**만 사용합니다.

### 3.1 변수 (Variables)

- **역할**: 이벤트 수집 시 함께 보낼 **값**을 정의. (예: 페이지 경로, 클릭 텍스트, 채널명)
- **저장**: `data/variables.json`
- **타입** (Admin/표준 문서 기준):
  - **url**: URL 일부 추출. `type_config.part` → path, host, href, referrer, title, query 등.
  - **element**: 클릭 요소의 속성. `type_config.attribute` → text, href, id, className, data-* 등. `max_length`로 길이 제한 가능.
  - **string**: 고정 문자열. `type_config.value`.
  - **script**: JavaScript 스크립트로 값 계산. `type_config.script`에 `{{변수명}}` 형태로 컨텍스트 사용.
- **API**:
  - `GET /admin/config`: 전체 설정 중 `variables`(편집용 전체) 반환.
  - `POST /admin/config`: Body에 `variables` 포함해 저장(upsert).

### 3.2 변수 그룹 (Variable Groups)

- **역할**: 변수를 그룹으로 묶어 관리(UI/구성용).
- **저장**: `data/variable_groups.json`
- **API**: `GET/POST /admin/config` 에서 `variable_groups` 로 함께 조회·저장.

### 3.3 트리거 (Triggers)

- **역할**: **언제** 이벤트를 보낼지 정의. (예: DOM 로드 시, 클릭 시, 스크롤 25/50/75/99% 도달 시)
- **저장**: `data/triggers.json`
- **종류**:
  - **DOM_READY**: `DOMContentLoaded` 시점, 즉시 실행(페이지뷰 1건).
  - **클릭**: `event_type`: element_click/click, 선택적으로 `event_config.css_selector`로 대상 제한.
  - **커스텀**: `event_type`: custom, `event_config.event_name`에 CustomEvent 이름 지정(예: scroll, pv, pvDetail, swipe, popup).
- **조건**: `conditions` 배열로 변수 값에 대한 조건(같음, 포함, 정규식 등) 지정 가능. 조건 불일치 시 해당 트리거는 미발동.
- **API**: `GET/POST /admin/config` 에서 `triggers` 로 조회·저장.
- **배포 시**: `_build_trigger_map()`으로 DOM 이벤트명·선택자·조건이 포함된 맵으로 변환되어 `settings/latest.json`의 `triggers`에 들어갑니다.

### 3.4 태그 (Tags)

- **역할**: 트리거가 발동했을 때 **어떤 데이터를 어떻게** 보낼지 정의. (실제 전송 로직 또는 매핑)
- **저장**: `data/tags.json`
- **타입**:
  - **nlogger**: 변수→키 매핑만. `parameters` 배열로 `{ key, value }` (value는 변수 코드). 별도 스크립트 없이 변수 값을 지정 키로 전송.
  - **script**: `func_js`에 `function trackerFunc(send){ ... }` 형태의 코드. `send(payload)`로 수집 API에 전송.
- **실행 순서**: `exec_order`로 정렬하여 실행.
- **실행 조건**: `run_conditions`(실행할 트리거 목록), `except_conditions`(제외할 트리거)로 제한 가능.
- **API**: `GET/POST /admin/config` 에서 `tags` 로 조회·저장.

### 3.5 표준 설정 (다른 사이트 재사용)

- **문서**: `docs/STANDARD_TAGGING.md`
- **데이터**: `data/standard_addon.json` — URL(표준), 요소(표준), 문자열 변수와 표준 클릭 트리거·nlogger 태그 예시.
- **목적**: 사이트별 스크립트 없이, 설정만으로 페이지뷰·클릭을 수집할 수 있도록 GTM/GA 스타일의 공통 설정을 권장.

**변수·트리거·태그를 더 자세히 보려면** → [CONFIG_VARIABLES_TRIGGERS_TAGS.md](CONFIG_VARIABLES_TRIGGERS_TAGS.md) (필드 정의, 타입별 동작, 조건·실행 순서 등 상세 설명).

---

## 4. 배포 및 버전 관리

### 4.1 배포 (Deploy)

- **엔드포인트**: `POST /admin/deploy`
- **권한**: 관리자만.
- **Body(선택)**: `comment`, `name`, `affiliation` (배포 코멘트·배포자 정보).
- **동작**:
  1. 현재 `data/` 기준 변수·트리거·태그를 읽어, 배포용 설정 객체 생성(버전, 코멘트, 배포 시각, `variables`, `triggers`, `tags`, `variables_full`, `triggers_full`, `tags_full`, `variable_groups_full` 등).
  2. `settings/latest.json` 덮어쓰기 → **현재 적용 설정**.
  3. `settings/versions/{YYYYMMDD_HHMMSS}.json` 에 동일 내용 저장 → **버전 스냅샷**.
- **결과**: 웹/앱에 로드된 ntm.js는 `/settings/latest`로 이 설정을 받아 사용합니다.

### 4.2 배포 이력 조회

- **엔드포인트**: `GET /admin/deploy/versions`
- **응답**: `versions`(버전 목록, 각각 version, comment, deployed_at, deployed_by_name, deployed_by_affiliation), `current`(현재 적용 버전 정보).

### 4.3 롤백

- **엔드포인트**: `POST /admin/deploy/rollback`
- **Body**: `{ "version": "YYYYMMDD_HHMMSS" }`
- **동작**:
  1. 해당 버전 파일을 읽어 `settings/latest.json` 복원.
  2. `variables_full`, `triggers_full`, `tags_full`, `variable_groups_full`이 있으면 `data/` 쪽 파일도 복원 → Admin 화면에서도 해당 버전 내용이 보이도록 함.

### 4.4 버전 삭제

- **엔드포인트**: `DELETE /admin/deploy/versions/{version}`
- **동작**: `settings/versions/{version}.json` 파일만 삭제. `latest.json`은 변경하지 않음.

---

## 5. 클라이언트 SDK (ntm.js)

### 5.1 로드 및 초기화

- **설정 수신**: `GET http://localhost:8000/settings/latest` (상수 `SETTINGS_API`)로 배포된 설정 로드.
- **중복 로드 방지**: `window.__NTM_SDK_LOADED` 플래그로 한 번만 초기화(싱글톤).
- **설정 주기 갱신**: `SETTINGS_REFRESH_MS`(5분)마다 설정을 다시 받아 `version`이 바뀌면 `location.reload()`.

### 5.2 변수 값 계산

- **표준 변수**: `type === "url"` 또는 `type === "element"`인 변수는 스크립트 없이 `getStandardVariableValues()`에서 URL/요소 속성으로 해석.
- **스크립트 변수**: `type === "script"`인 변수는 `runScriptVariable()`에서 `{{변수명}}` 치환 후 Function 생성해 실행. 컨텍스트는 `getBuiltInContext(clickEl, customData)`(path, url, title, referrer, clickText, clickClass 등).
- **문자열 변수**: `type === "string"`은 `type_config.value`를 그대로 사용.
- **병합**: `getMergedVariableValues(payload, clickEl)`에서 built-in + 표준 + 스크립트 값을 합쳐 수집 페이로드에 사용.

### 5.3 트리거 조건 평가

- `evaluateTriggerConditions(conditions, varValues)`: 연산자(같음, 포함, 정규식, 미만/이하/초과/이상, 유효함 등)로 조건 검사. 하나라도 불일치하면 false.

### 5.4 이벤트 전송

- **수집 URL**: `POST http://localhost:8000/collect` (상수 `COLLECT_URL`).
- **전송 방식**: `navigator.sendBeacon` 우선, 실패 시 `fetch(..., keepalive: true)` 재시도.
- **페이로드**: `buildCollectPayload()`로 `page_url`, `ts`, `event_trigger`, 활성화된 변수 값 등 구성. 대형 배열 등은 `COLLECT_EXCLUDE_VARS`로 제외.

### 5.5 트리거별 동작

| 트리거/이벤트 | 동작 |
|---------------|------|
| **DOM_READY** | DOM 준비 시 태그 실행 후, 페이지뷰 1건 전송(act_type: pageview). |
| **클릭** | document click 캡처. 트리거 조건·CSS 선택자 매칭 시 1회 클릭당 1건 전송(act_type: click). |
| **스크롤** | scroll 이벤트에서 25/50/75/99% 구간별 1회만 전송(act_type: scroll, scroll_rate). |
| **커스텀** | CustomEvent 리스너. pv, pvDetail, swipe, popup, impression, Scroll_Impression, enter, click_touch, url_change 등. `Ntm00002.Event.fireUserDefined(eventName, data)`로 앱에서 발화 가능. |
| **URL 주소 변경** | history.pushState/replaceState, popstate 시 `sendPageviewForUrl()`로 페이지뷰 1건 전송. |

### 5.6 태그 실행

- **nlogger**: 매핑된 변수 값을 키에 넣어 `sendToCollect()` 호출.
- **script**: `func_js`로 만든 `trackerFunc(send)`의 `send`로 페이로드 전송. 조건은 `shouldRunTag(tag, triggerCode, varValues)`로 검사(트리거 조건, run_conditions, except_conditions).

---

## 6. 이벤트 수집 및 Kafka 파이프라인

### 6.1 수집 API

- **엔드포인트**: `POST /collect`
- **인증**: 없음(퍼블릭). 도메인 제한은 CORS 등으로 별도 구성 가능.
- **요청**: JSON Body. 필수/주요 필드: `page_url`, `ts`, `event_trigger`, `tag_code`, `event_type`/`act_type`, 그 외 변수·컨텍스트.
- **처리**:
  1. `load_settings()`로 배포된 설정 로드.
  2. Body에서 **설정에 포함된 변수**만 context로 추출(page_*, ts 제외).
  3. `page_id`는 Body 값 우선, 없으면 `page_url`에서 도메인 제거한 경로로 생성.
  4. `channel`, `referer_url` 등 정규화.
  5. 이벤트 객체를 **Kafka 메시지** 형태로 구성: tag_code, act_type, event_trigger, channel, page_url, page_id, referer_url, context, payload, client_ts, server_ts, ip, user_agent.
  6. `get_kafka_producer().send(KAFKA_TOPIC, value=event)` 후 flush.
- **응답**: 성공 `{ "ok": true }`, 실패 시 400/503 및 `error` 메시지.

### 6.2 Kafka

- **토픽**: 환경변수 `KAFKA_TOPIC`(기본 `test`).
- **프로듀서**: `kafka_client.connect.get_kafka_producer()` — 수집 API에서 1건씩 전송.
- **컨슈머**: `kafka_client.consumer` — 아래 데이터 저장·집계 담당.

---

## 7. 데이터 저장 및 집계

### 7.1 테이블 구조

- **raw_events**: 수집 이벤트 원시 데이터 1건 1행. (tag_code, act_type, event_trigger, channel, page_url, page_id, referer_url, context, payload, client_ts, server_ts, ip, user_agent 등.)
- **agg_page_events**: 일별·페이지·채널·act_type·event_trigger별 이벤트 건수. UNIQUE (stat_date, page_id, channel, act_type, event_trigger), ON CONFLICT 시 event_count 증가.
- **agg_heatmap**: 일별·페이지·채널·heatmap_type·segment_key별 건수. scroll은 segment_key 25|50|75|99, click은 text:... 또는 class:... 형태.
- **funnel_definition**: 퍼널 정의(funnel_code, funnel_name, steps JSON). steps는 step, name, page_id_pattern 배열.
- **agg_funnel_daily**: 퍼널별·일별·단계별 진입(users_entered), 완료(users_completed), 이탈(users_dropped), 이탈률(drop_off_rate).

### 7.2 Kafka 컨슈머

- **진입점**: `python -m kafka_client.consumer` (Docker에서는 `app-consumer` 서비스).
- **동작**:
  1. Kafka 토픽 구독.
  2. 메시지 수신 시 `insert_raw_event(event)` → raw_events INSERT.
  3. `server_ts`로 stat_date 결정.
  4. `process_event_aggregations(event, stat_date)` 호출:
     - `upsert_agg_page_events(stat_date, page_id, channel, act_type, event_trigger)`.
     - act_type이 scroll이면 scroll_rate 25/50/75/99에 대해 `upsert_agg_heatmap(..., "scroll", str(bucket))`.
     - act_type이 click이면 click_text, class_name에 대해 `upsert_agg_heatmap(..., "click", "text:..." | "class:...")`.

### 7.3 퍼널 일별 집계

- **스크립트**: `run_funnel_agg.py [YYYY-MM-DD]`. 인자 없으면 어제·오늘.
- **실행 주기**: Docker의 `app-funnel-agg` 서비스는 60초마다 `run_funnel_agg.py $(date +%Y-%m-%d)` 실행.
- **로직** (`analytics_repo.run_funnel_daily_aggregation(stat_date)`):
  - 활성 퍼널 정의 조회.
  - 해당 일자의 raw_events에서 (ip, stat_date) 단위로 방문 추적, page_id가 각 step의 page_id_pattern에 포함되는지로 최대 도달 단계 계산.
  - 단계별 users_entered, users_completed, users_dropped, drop_off_rate 계산 후 agg_funnel_daily UPSERT.

### 7.4 대시보드에서 퍼널 집계 실행

- **엔드포인트**: `POST /api/dashboard/funnel_agg`
- **Body(선택)**: `{ "date": "YYYY-MM-DD" }`. 없으면 어제·오늘에 대해 실행.
- **권한**: 로그인 필요.

---

## 8. 행동 분석 대시보드

모든 대시보드 API는 **로그인 필요** (`require_login`).

### 8.1 페이지별 이벤트 집계

- **엔드포인트**: `GET /api/dashboard/page_events`
- **쿼리**: `date_from`, `date_to`, `group_by`(stat_date|page_id|act_type|event_trigger|channel), `page_id`, `channel`, `act_type`, `limit`(기본 500).
- **응답**: group_by 기준으로 집계된 행 + meta(date_from, date_to, group_by).
- **용도**: 페이지·행동 유형·트리거·채널별 이벤트 건수 조회.

### 8.2 개요 지표 (KPI)

- **엔드포인트**: `GET /api/dashboard/overview_stats`
- **쿼리**: `date_from`, `date_to`, `page_id`, `channel`.
- **지표**: 방문자 수(visitors), 총 방문 수(visits), 총 페이지뷰(total_pageviews), 이탈률(bounce_rate), 방문당 페이지 수(pages_per_visit), 평균 방문 기간(avg_duration_ms).  
  방문 정의: (ip, stat_date) 1조합 = 1방문.

### 8.3 퍼널

- **정의 목록**: `GET /api/dashboard/funnels` → funnel_definition 목록.
- **일별 집계**: `GET /api/dashboard/funnel_daily`  
  - 쿼리: `date_from`, `date_to`, `funnel_id`(선택).  
  - 응답: 퍼널 단계별 users_entered, users_completed, users_dropped, drop_off_rate 등.

### 8.4 히트맵

- **엔드포인트**: `GET /api/dashboard/heatmap`
- **쿼리**: `date_from`, `date_to`, `page_id`, `heatmap_type`(scroll|click), `channel`, `limit`.
- **응답**: stat_date, page_id, heatmap_type, segment_key, event_count 등. 스크롤 구간·클릭 텍스트/클래스별 집계.

### 8.5 UI

- **대시보드 페이지**: `static/dashboard.html` — 기간·필터 선택 후 위 API 호출로 차트·테이블 표시.
- **관리자 페이지**: `static/admin.html` — 변수·트리거·태그 편집, 배포, 배포 이력·롤백, 대시보드 링크, 계정 관리 링크.
- **계정 관리**: `static/accounts.html` — 가입 대기 목록, 승인·권한 지정(관리자 전용).

---

## 9. 인프라 및 실행 환경

### 9.1 Docker Compose 서비스

| 서비스 | 역할 |
|--------|------|
| **postgres** | PostgreSQL 15. DB: testdb, 사용자: testuser. |
| **db-init** | postgres 기동 후 스키마·초기 관리자(admin/admin) 생성. create_user_table.sql, add_user_roles_and_approval.sql, create_analytics_tables.sql, init_admin.sql 순 실행. |
| **zookeeper** | Kafka 메타데이터. |
| **kafka** | 브로커, 토픽 test 사용. |
| **app-api** | FastAPI(uvicorn), 포트 8000. 설정·수집·로그인·배포·대시보드 API. |
| **app-consumer** | Kafka 컨슈머. raw_events + agg_page_events·agg_heatmap 갱신. |
| **app-funnel-agg** | 60초마다 퍼널 일별 집계 실행. |
| **kafka-ui** | Kafka UI, 포트 18080. 토픽·메시지 확인용. |

### 9.2 주요 URL

| 용도 | URL |
|------|-----|
| 로그인 | http://localhost:8000/static/login.html |
| 회원가입 | http://localhost:8000/static/signup.html |
| 컨테이너 관리(Admin) | http://localhost:8000/static/admin.html |
| 행동 분석 대시보드 | http://localhost:8000/static/dashboard.html |
| 계정 관리 | http://localhost:8000/static/accounts.html |
| 설정 API(SDK) | http://localhost:8000/settings/latest |
| 수집 API(SDK) | http://localhost:8000/collect |
| Kafka UI | http://localhost:18080 |

### 9.3 환경 변수 (API·컨슈머·퍼널)

- **DB**: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
- **Kafka**: KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC

### 9.4 스크립트

- **start.sh / stop.sh**: Compose 기동·중지.
- **run_funnel_agg_loop.sh**: 퍼널 집계 반복 실행용.
- **create_admin_user.py**: 수동으로 관리자 계정 생성 시 사용(선택).

---

## 관련 문서

- **실행·로그인·사용법**: [README.md](../README.md)
- **동작·기능 요약**: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- **표준 태깅(다른 사이트 재사용)**: [STANDARD_TAGGING.md](STANDARD_TAGGING.md)
- **대시보드·태깅 표준 프롬프트**: [CURSOR_PROMPT_STANDARD_DASHBOARD_AND_TAGGING.md](CURSOR_PROMPT_STANDARD_DASHBOARD_AND_TAGGING.md)
