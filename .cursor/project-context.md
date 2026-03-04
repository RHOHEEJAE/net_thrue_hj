# net_thrue_01 — 새 채팅용 맥락(압축)

> 새 채팅에서 `@.cursor/project-context.md` 첨부 후 작업 지시하면 맥락 복원용.

## 프로젝트
| 항목 | 내용 |
|------|------|
| 이름 | net_thrue_01 (넷쓰루 트래커 / 헥토 행동 데이터 수집) |
| 역할 | 웹/앱 행동 이벤트 수집(변수·트리거·태그) → Kafka → PostgreSQL 적재·집계 → 대시보드. GTM 유사 설정 기반 파이프라인. |

## 스택
| 구분 | 기술 |
|------|------|
| 백엔드 | FastAPI, uvicorn |
| DB | PostgreSQL. db/connect.py, env: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD |
| 메시징 | Kafka. kafka_client/. env: KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC |
| 클라이언트 | ntm.js. GET /settings/latest, POST /collect. 설정: data/*.json → 배포 시 settings/latest.json |
| 실행 | Docker: postgres, zookeeper, kafka, db-init, app-api, app-consumer, app-funnel-agg, kafka-ui. 로컬: start.sh / stop.sh (uvicorn, consumer, run_funnel_agg_loop.sh) |

## 경로·역할
| 경로 | 역할 |
|------|------|
| app.py | API, 세션 인증, /admin/*(require_admin), /api/dashboard/*(require_login), /collect→Kafka |
| repo/file_repo.py | data/*.json 읽기·쓰기 |
| repo/user_repo.py | 계정 생성·승인·역할(approve_user, list_all_users) |
| repo/analytics_repo.py | raw_events·집계 테이블·대시보드 쿼리, run_funnel_daily_aggregation |
| db/connect.py | env 기반 PostgreSQL 연결 |
| db/*.sql | create_user_table.sql, add_user_roles_and_approval.sql, create_analytics_tables.sql, init_admin.sql |
| kafka_client/consumer.py | test 토픽 구독 → insert_raw_event, process_event_aggregations(agg_page_events, agg_heatmap) |
| run_funnel_agg.py | run_funnel_daily_aggregation(날짜). run_funnel_agg_loop.sh: 오늘 날짜 60초마다 |
| static/admin.html | 변수·트리거·태그 편집, 배포, 계정 관리 링크 |
| static/dashboard.html | 행동 분석(페이지 이벤트, 퍼널, 히트맵). 필터 qs()에서 undefined/null/"" 제거 |
| static/accounts.html | 관리자 전용: 가입 승인·역할 지정 |

## 표준 수집 (하드코딩 최소화)
- **변수 타입**: url(part: path/host/href/referrer/title/query), element(attribute: text/href/id/className/data-xxx, max_length). 스크립트 없이 설정만으로 해석.
- **문서**: docs/STANDARD_TAGGING.md, data/standard_addon.json (표준 변수·트리거·태그 예시).

## 규칙·결정
- **응답**: 항상 한국어.
- **계정**: role=admin|user. 가입 시 status=pending → 관리자 승인 후 로그인 가능. admin만 Admin·계정관리 접근.
- **Docker db-init 순서**: create_user_table.sql → add_user_roles_and_approval.sql → create_analytics_tables.sql → init_admin.sql. 초기 계정 admin/admin.
- **대시보드 API**: 쿼리 파라미터 빈 값 처리. 프론트 qs()로 undefined/null/"" 제외, 백엔드 _empty_to_none.
- **Kafka UI 버튼**: admin/dashboard 헤더. href = 현재 host + :18080/ui/clusters/local/topics/test (스크립트로 설정).
- **ntm.js**: SETTINGS_API, COLLECT_URL 하드코드(localhost:8000). 외부 도메인 테스트 시 환경별로 수정 또는 env 필요.

## 의존성(보안 반영)
- fastapi>=0.109.1, uvicorn[standard]>=0.24.0, psycopg2-binary>=2.9.11, kafka-python>=2.0.3

## 새 채팅용 한 줄 프롬프트 예시
`@.cursor/project-context.md 읽고, [질문 또는 작업 내용] 해줘.`
