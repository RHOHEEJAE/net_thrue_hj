# Cursor AI 프롬프트 — 표준 대시보드 + GTM/GA 스타일 하드코딩 최소화 + 의존성 보안

아래 블록 전체를 Cursor 채팅에 붙여 넣고, 프로젝트 루트(`net_thrue_01`)를 컨텍스트로 지정한 뒤 실행하면 된다.

---

## 프롬프트 (복사용)

```
이 프로젝트는 넷쓰루 와이즈콜렉터를 벤치마크한 행동 데이터 수집 서비스다. 아래 세 가지를 엔지니어링 관점에서 수정해 달라.

---

1. 대시보드 표준화 (Plausible / Google Analytics 스타일)

1.1. 개요(Overview) 탭을 첫 번째 탭으로 추가하고, 기본 진입 시 이 탭이 보이게 해라.
1.2. 개요 탭 구성:
     - 상단: KPI 카드 3개 (그리드). (1) 총 페이지뷰: 기간 내 act_type=pageview 합계, (2) 총 이벤트: 기간 내 전체 이벤트 합계, (3) 기간: 선택한 date_from ~ date_to 표시.
     - 중간: 일별 이벤트 추이 라인 차트. 기존 GET /api/dashboard/page_events?group_by=stat_date 응답으로 x=stat_date, y=total 사용.
     - 하단: 2열 레이아웃. 왼쪽 «인기 페이지 (페이지뷰)» 테이블: group_by=page_id, act_type=pageview, limit 15로 상위 15개 페이지 + 페이지뷰 건수. 오른쪽 «이벤트 유형별» 테이블: group_by=act_type으로 act_type별 건수.
1.3. 기간 필터에 7일/30일/90일 프리셋 버튼을 추가해, 클릭 시 date_from/date_to를 해당 구간으로 설정하고 데이터를 다시 로드하게 해라.
1.4. 탭 순서를 «개요 | 페이지 이벤트 | 퍼널 | 히트맵»으로 통일하고, 기존 페이지 이벤트/퍼널/히트맵 탭 패널은 유지해라.
1.5. 개요용 데이터는 새 API 없이 기존 page_events API만 사용하고, group_by·act_type 파라미터 조합으로 총 페이지뷰·총 이벤트·일별 추이·인기 페이지·유형별 건수를 계산해라. (필요 시 여러 번 호출해 Promise.all로 병렬 요청)
1.6. 반응형: 인기 페이지/이벤트 유형별 2열 그리드는 900px 이하에서 1열로 세로 쌓이게 해라.

---

2. 태그/트리거/변수 표준화 (GTM/GA 스타일, 하드코딩 최소화)

2.1. 변수 타입 확장 (ntm.js):
     - type "url": type_config.part 값(path | host | href | referrer | title | query)에 따라 getBuiltInContext의 path, host, url, referrer, title, params 등에서만 값을 채우고, 스크립트를 실행하지 않게 해라.
     - type "element": 클릭 시점의 clickElement가 있으면 type_config.attribute(text | href | id | className | data-xxx)와 type_config.max_length(선택)로 값을 채우고, 없으면 type_config.fallback_document(예: "title")가 있으면 document.title 등으로 채우고, 없으면 빈 문자열. 스크립트 실행 없이 처리해라.
     - 위 두 타입은 variablesFull에서 enabled 목록에 포함된 것만 필터링해 별도 배열(standardVariables)로 두고, getMergedVariableValues에서 builtIn 다음으로 이 배열 기준으로 값을 채운 뒤, 기존 script 변수 결과와 병합해라.
     - type "string" 변수도 스크립트 없이 type_config.value를 그대로 payload에 넣어 주어야 하므로, standardVariables와 동일한 병합 단계에서 string 타입을 처리해도 된다.

2.2. Admin UI (static/admin.html):
     - 변수 유형 선택 옵션에 «URL(표준)»(value="url"), «요소(표준)»(value="element")를 추가해라.
     - url 선택 시: type_config에 part만 넣으면 되므로, select로 path/host/href/referrer/title/query 중 하나 선택하는 폼을 보여 주고, 저장 시 type_config.part로 저장해라.
     - element 선택 시: type_config에 attribute, max_length, fallback_document가 들어가므로, attribute 선택( text, href, id, className, data-id, data-product-id 등), max_length 숫자 입력, fallback_document 선택(없음 | document.title) 폼을 보여 주고, 저장 시 해당 필드로 type_config를 채워라.
     - 변수 상세 모달에서 기존 변수 불러올 때 type이 url/element면 해당 폼 필드에 type_config 값을 채워 주어라.

2.3. 표준 설정 예시 및 문서:
     - data/standard_addon.json 파일을 만들어, 다른 웹사이트에서도 그대로 쓸 수 있는 변수·트리거·태그 예시를 넣어라. 변수: page_path(url, part=path), page_url(url, part=href), document_title(url, part=title), click_text_std(element, attribute=text, max_length=200), click_class_std(element, attribute=className). 트리거: CLICK_STANDARD(element_click, css_selector="a, button, [role=button], input[type=submit]"). 태그: STANDARD_CLICK(nlogger), parameters로 click_text_std→click_text, click_class_std→class_name, page_path→page_id, channel→channel 매핑.
     - docs/STANDARD_TAGGING.md 문서를 작성해, (1) url/element/string 표준 변수 타입 설명, (2) 새 사이트 적용 시 Admin에서 추가할 변수·트리거·태그 단계, (3) 사이트별 확장 시 data-* 속성 활용 등 하드코딩 대신 설정으로 처리하는 방법을 적어라.

2.4. 기존 data/variables.json, data/triggers.json, data/tags.json에는 사이트별 스크립트와 경로/클래스 하드코딩이 많다. 이 파일들을 삭제하거나 덮어쓰지 말고, «표준» 타입과 standard_addon.json 예시만 추가하고, 기존 설정은 그대로 두어라. 새 사이트나 공통 수집 시 표준 변수·트리거·태그를 참고해 추가하는 방식으로 문서에 안내해라.

---

3. 의존성 보안 업그레이드 (requirements.txt)

3.1. FastAPI: 0.100.0 포함 일부 버전에 CVE-2024-24762(ReDoS, 고위험) 취약점이 있다. Content-Type 헤더 파싱 과정에서 정규식 기반 ReDoS가 가능해, 폼 업로드를 쓰는 엔드포인트에서 서비스 거부(DoS) 위험이 있다. requirements.txt에서 fastapi 버전을 0.109.1 이상으로 지정해라. (예: fastapi>=0.109.1)

3.2. uvicorn: 알려진 CVE-2020-7694, 7695는 0.11.7 미만 구버전 이슈이며, 0.22.0은 해당 패치 이후다. 현재 공개 CVE 기준 추가 보안 이슈는 확인되지 않으나, 장기적으로 최신 안정 버전 유지가 좋으므로 uvicorn[standard]를 0.24.0 이상 등으로 올려라.

3.3. psycopg2-binary: 2.9.0에 대해 직접 보고된 CVE는 없고, 2.9.x 최신(예: 2.9.11)까지도 별도 취약점 리포트는 없으나, 버그·호환성 수정이 쌓여 있으므로 동일 메이저 내 최신으로 올려라. (예: psycopg2-binary>=2.9.11)

3.4. kafka-python: 2.0.2 자체에 대한 공개 CVE는 없으나, 2.0.3에서 CVE-2024-3219 관련 수정 등 보안·호환성 개선이 포함되어 있으므로 kafka-python>=2.0.3으로 지정해라.

3.5. 위 변경을 requirements.txt에 반영하고, 주석으로 각 패키지별 CVE·권장 사유를 한 줄씩 적어 두어라. (이미 반영된 프로젝트면 해당 항목은 스킵해도 된다.)
```

---

## 사용 방법

1. Cursor에서 `net_thrue_01` 프로젝트를 연다.
2. 새 채팅을 연다.
3. 위 «프롬프트 (복사용)» 블록 전체를 복사해 채팅에 붙여 넣는다.
4. 필요하면 `@.cursor/project-context.md` 또는 `@docs/STANDARD_TAGGING.md` 등을 @로 첨부해 맥락을 보강한다.
5. 실행 후 생성·수정된 파일(대시보드 HTML/JS, ntm.js, admin.html, standard_addon.json, STANDARD_TAGGING.md, requirements.txt 등)을 검토하고, 팀 브랜치에 반영한다.

---

## 참고: 이미 반영된 경우

이미 동일한 작업이 코드에 반영되어 있다면, 위 프롬프트는 «요구 사항 명세»로 활용하면 된다. 새 프로젝트나 포크에서 같은 규격으로 적용할 때 그대로 복사해 사용할 수 있다.
