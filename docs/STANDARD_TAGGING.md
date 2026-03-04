# 표준 수집 설정 (GTM/GA 스타일) — 하드코딩 최소화

다른 웹사이트에서도 **설정만으로** 행동 데이터를 수집하려면, 사이트별 스크립트 대신 **표준 변수·트리거·태그**를 사용하는 것을 권장합니다.

- **표준 추가용 JSON**: `data/standard_addon.json` — 여기 있는 변수·트리거·태그를 Admin에서 수동 추가하거나, 기존 `variables.json` / `triggers.json` / `tags.json`에 병합할 때 참고하세요.

---

## 1. 표준 변수 타입 (Admin에서 선택 가능)

| 유형 | 설명 | type_config 예시 |
|------|------|------------------|
| **URL(표준)** | 페이지 URL에서 일부만 추출. 스크립트 없음. | `{ "part": "path" }` — path, host, href, referrer, title, query 중 선택 |
| **요소(표준)** | 클릭한 요소의 텍스트/속성 추출. 스크립트 없음. | `{ "attribute": "text", "max_length": 500 }` — text, href, id, className, data-id 등 |
| **문자열** | 고정값 (채널명 등) | `{ "value": "Rround" }` |

- **path**: `location.pathname`
- **host**: `location.host`
- **href**: 전체 URL
- **referrer**: `document.referrer`
- **title**: `document.title`
- **query**: 쿼리스트링
- **요소 text**: `element.textContent` (max_length 자르기)
- **요소 href/id/className**: 해당 속성 값
- **요소 data-xxx**: `element.getAttribute("data-xxx")`

---

## 2. 새 사이트용 권장 설정 절차

1. **변수 추가** (Admin → 변수)
   - `page_path` — 유형: **URL(표준)**, URL 부분: **path**
   - `page_url` — 유형: **URL(표준)**, URL 부분: **href**
   - `document_title` — 유형: **URL(표준)**, URL 부분: **title**
   - `click_text_std` — 유형: **요소(표준)**, 클릭 요소 속성: **text**, 최대 길이: **200**
   - `click_class_std` — 유형: **요소(표준)**, 클릭 요소 속성: **className**
   - `channel` — 유형: **문자열**, 값: 사이트/채널명

2. **트리거 추가**
   - `CLICK_STANDARD` — 이벤트: **클릭**, CSS 선택자: `a, button, [role=button], input[type=submit]` (필요 시 확장)

3. **태그 추가**
   - **표준 페이지뷰**: 트리거 `DOM_READY`, 타입 **nlogger**, 매핑 — page_path → page_path, page_url → page_url, document_title → document_title, channel → channel.
   - **표준 클릭**: 트리거 `CLICK_STANDARD`, 타입 **nlogger**, 매핑 — click_text_std → click_text, click_class_std → class_name, page_path → page_id, channel → channel.

이렇게 하면 **어떤 사이트에 ntm.js만 붙여도** 페이지뷰·클릭이 최소한의 필드로 수집됩니다.

---

## 3. 사이트별 확장 (하드코딩 대신)

- **상품/카테고리 등**을 넘기고 싶으면: 해당 요소에 `data-product-id`, `data-category-id` 등을 붙이고, 변수는 **요소(표준)** 에서 속성 **data-product-id** 등으로 읽게 하면 됩니다.
- **특정 페이지만 제외**하고 싶으면: 트리거 조건에서 변수 `page_path` / `document_title` 사용, 연산자 "다음으로 시작하지 않음" 등으로 제외 경로 지정.
- **복잡한 로직**이 필요할 때만 **스크립트** 타입 변수/태그를 추가해 사용하면 됩니다.

---

## 4. 기존 와이즈콜렉터 벤치마크 설정과의 관계

- 현재 `data/tags.json`, `data/variables.json` 등에는 **특정 타겟 사이트**용 스크립트(경로/클래스 하드코딩)가 많이 들어 있습니다.
- **새 사이트**나 **공통 수집**이 목적이면 위 표준 변수·트리거·태그를 먼저 추가하고, 필요 시에만 스크립트/사이트 전용 설정을 추가하는 방식이 좋습니다.
- 표준 변수(`url`, `element`, `string`)는 **ntm.js**에서 스크립트 없이 해석하므로, 설정만 바꿔도 여러 도메인에서 재사용할 수 있습니다.
