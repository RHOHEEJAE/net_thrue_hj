# 변수·트리거·태그 설정 상세 가이드

이 문서는 net_thrue_01에서 **변수(Variables)**, **트리거(Triggers)**, **태그(Tags)** 설정의 구조, 타입, 동작 방식을 자세히 설명합니다.

---

## 목차

1. [개요](#1-개요)
2. [변수 (Variables)](#2-변수-variables)
3. [변수 그룹 (Variable Groups)](#3-변수-그룹-variable-groups)
4. [트리거 (Triggers)](#4-트리거-triggers)
5. [태그 (Tags)](#5-태그-tags)
6. [설정 흐름 요약](#6-설정-흐름-요약)
7. [Admin UI — 추가·편집 시 설정 항목](#7-admin-ui--추가편집-시-설정-항목)

---

## 1. 개요

### 1.1 역할 구분

| 구분 | 역할 | 비유 |
|------|------|------|
| **변수** | 수집할 **값**을 정의 (예: 페이지 경로, 클릭한 텍스트, 상품코드) | “무엇을 보낼지” |
| **트리거** | **언제** 이벤트를 보낼지 정의 (예: 페이지 로드 시, 클릭 시, 스크롤 25% 도달 시) | “언제 보낼지” |
| **태그** | 트리거 발동 시 **어떤 로직으로** 데이터를 만들어 전송할지 정의 | “어떻게 보낼지” |

### 1.2 저장 위치

- **편집용(Admin)**  
  - `data/variables.json` — 변수 목록  
  - `data/variable_groups.json` — 변수 그룹  
  - `data/triggers.json` — 트리거 목록  
  - `data/tags.json` — 태그 목록  

- **배포된 설정(SDK/수집 API가 사용)**  
  - `settings/latest.json` — 현재 적용 설정  
  - `settings/versions/{YYYYMMDD_HHMMSS}.json` — 배포 버전 스냅샷  

Admin에서 “배포”를 하면 `data/` 내용이 가공되어 `settings/latest.json`에 반영되고, ntm.js는 `/settings/latest`로 이 설정만 읽습니다.

---

## 2. 변수 (Variables)

### 2.1 기본 필드

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `variable_code` | string | ○ | 고유 식별자. 설정·수집 페이로드의 키로 사용. |
| `variable_name` | string | - | 관리용 표시 이름. |
| `enabled` | boolean | - | true면 배포 시 “활성 변수 목록”에 포함. 기본 true. |
| `description` | string | - | 설명. |
| `type` | string | - | 변수 타입. 아래 참고. |
| `type_config` | object | - | 타입별 설정. |

배포 시 **enabled: true**인 변수만 `settings.variables` 배열(변수 코드 목록)에 들어가고, 수집 시 이 목록에 있는 변수만 context/payload로 서버에 전송됩니다.

### 2.2 변수 타입 (type)

#### 2.2.1 `url` — URL에서 값 추출 (스크립트 없음)

페이지 URL/문서 정보에서 일부만 가져옵니다. **스크립트 없이** SDK가 `type_config.part`만 보고 처리합니다.

| type_config.part | 설명 | 대응 값 |
|------------------|------|---------|
| `path` | 경로 | `location.pathname` |
| `host` / `hostname` | 호스트 | `location.host` |
| `href` | 전체 URL | `location.href` |
| `referrer` | 리퍼러 | `document.referrer` |
| `title` | 문서 제목 | `document.title` |
| `query` / `search` | 쿼리스트링 | `location.search` (앞에 ? 포함) |

**예 (standard_addon.json):**

```json
{
  "variable_code": "page_path",
  "variable_name": "페이지 경로(표준)",
  "enabled": true,
  "type": "url",
  "type_config": { "part": "path" }
}
```

#### 2.2.2 `element` — 클릭한 요소에서 값 추출 (스크립트 없음)

클릭 이벤트 시 **클릭한 DOM 요소**의 속성/텍스트를 가져옵니다. 페이지뷰 등 요소가 없을 때는 `type_config.fallback_document`가 있으면 문서 값(예: title) 사용.

| type_config.attribute | 설명 |
|-----------------------|------|
| `text` / `innertext` | `element.textContent` (앞뒤 공백 제거). `max_length`로 자르기 가능. |
| `href` | `element.href` |
| `id` | `element.id` |
| `class` / `classname` | `element.className` |
| `data-xxx` | `element.getAttribute("data-xxx")` |

- **max_length**: number. text 수집 시 이 길이로 자른다. 생략 시 기본 500.

**예:**

```json
{
  "variable_code": "click_text_std",
  "type": "element",
  "type_config": { "attribute": "text", "max_length": 200 }
}
```

#### 2.2.3 `string` — 고정 문자열

항상 같은 값을 넣을 때 사용합니다 (채널명, 태그명 등).

```json
"type_config": { "value": "Rround" }
```

#### 2.2.4 `script` — JavaScript로 값 계산

복잡한 로직(경로/클래스/페이지별 분기 등)이 필요할 때 사용합니다.

- **type_config.script**: 함수 본문 형태의 문자열.
- **컨텍스트 치환**: `{{변수명}}`이 같은 이름의 컨텍스트 값으로 치환된 뒤, `new Function(...)`으로 실행됩니다.
- **반환값**: 함수가 반환하는 값이 해당 변수의 값이 됩니다.

**사용 가능한 컨텍스트 예:**  
`clickElement`, `url`, `path`, `referrer`, `title`, `customData`, `paramDict`, `params`, `hash`, `host`, 그 외 설정에 정의된 다른 변수 코드(선행 스크립트 변수 결과가 컨텍스트에 누적됨).

**예 (variables.json):**

```json
{
  "variable_code": "class_name",
  "type": "script",
  "type_config": {
    "script": "function func() {\n  const el = {{clickElement}};\n  if (!el) return '';\n  const el_class = el.closest('[class]').classList[0];\n  return el_class ? el_class : '';\n}"
  }
}
```

스크립트 변수는 **다른 변수를 참조**할 수 있습니다. 예: `{{FC_nthReplace}}`, `{{customData}}`, `{{path}}` 등. 스크립트 변수끼리는 정의 순서/실행 순서에 따라 이전 변수 결과가 컨텍스트에 들어갑니다.

### 2.3 수집 시 변수 처리

- **SDK (ntm.js)**  
  활성 변수(`settings.variables`에 있는 코드)에 대해 표준/문자열/스크립트 순으로 값을 구한 뒤, 수집 페이로드에 넣습니다.  
  단, `COLLECT_EXCLUDE_VARS`에 들어 있는 변수(AL_impression, AL_popup, AL_swipe 등 대형 배열/설정용)는 페이로드에서 제외됩니다.

- **서버 (/collect)**  
  Body에서 “배포된 설정의 variables 목록에 있는 키”만 context로 추출하고, 나머지는 payload 등으로 넘깁니다.

---

## 3. 변수 그룹 (Variable Groups)

### 3.1 역할

변수를 **그룹으로 묶어 Admin UI에서 구분·표시**하기 위한 메타데이터입니다. 수집/트리거 동작에는 영향을 주지 않습니다.

### 3.2 구조 (variable_groups.json)

```json
{
  "group_id": "vg_1771829358246",
  "name": "기본 파라미터",
  "description": "",
  "items": [
    { "key": "nth_channel", "value": "channel" },
    { "key": "nth_menuId", "value": "page_id" },
    { "key": "nth_evType", "value": "act_type" }
  ]
}
```

- `group_id`: 그룹 고유 ID  
- `name` / `description`: 표시용  
- `items`: 그룹에 속한 항목. `value`는 변수 코드(variable_code)와 매핑되는 경우가 많음.

---

## 4. 트리거 (Triggers)

### 4.1 기본 필드

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `trigger_code` | string | ○ | 고유 식별자. 태그에서 “이 트리거일 때 실행” 참조에 사용. |
| `trigger_name` | string | - | 표시 이름. |
| `event_type` | string | - | 이벤트 종류. 아래 표 참고. |
| `event_config` | object | - | 이벤트별 옵션 (css_selector, event_name 등). |
| `conditions` | array | - | 발동 조건. 조건이 하나라도 false면 해당 트리거는 “발동하지 않은 것”으로 처리. |
| `enabled` | boolean | - | 사용 여부. |

### 4.2 event_type → 실제 동작

배포 시 `app.py`의 `_event_type_to_dom_event()`와 `_build_trigger_map()`이 아래처럼 변환합니다.

| event_type (설정) | DOM/동작 | 비고 |
|-------------------|----------|------|
| `dom_ready` / `DOMContentLoaded` | 페이지 로드 시 1회 실행 (immediate) | DOM_READY 전용. |
| `element_click` / `click` | document의 `click` 이벤트 | event_config.css_selector로 대상 제한. |
| `custom` | CustomEvent 이름으로 리스너 등록 | event_config.event_name 필수 (예: scroll, pv, pvDetail, swipe, popup). |
| `url_change` | history.pushState/replaceState, popstate | SPA URL 변경 시 페이지뷰용. |

그래서 **트리거 종류**는 사실상 다음과 같이 나뉩니다.

1. **DOM_READY**  
   - `event_type`: `dom_ready`  
   - DOM 준비 시 1회. 페이지뷰 1건 + DOM_READY에 연결된 태그 실행.

2. **클릭 트리거**  
   - `event_type`: `element_click` 또는 `click`  
   - `event_config.css_selector`: 예) `"a, button, li, ..."`  
   - 이 선택자에 맞는 요소를 클릭할 때만 발동 (비어 있으면 모든 클릭).

3. **커스텀 트리거**  
   - `event_type`: `custom`  
   - `event_config.event_name`: 예) `scroll`, `pv`, `pvDetail`, `swipe`, `popup`, `Scroll_Impression`, `impression`, `enter`, `click_touch`  
   - 해당 이름의 CustomEvent가 발생할 때 발동.  
   - 앱/태그에서 `Ntm00002.Event.fireUserDefined("scroll", { scroll_rate: 50 })` 처럼 이벤트를 발생시키면 트리거가 맞을 때 수집 1건이 나갑니다.

4. **URL 주소 변경**  
   - `event_type`: `url_change`  
   - SPA에서 주소만 바뀔 때 페이지뷰 1건 전송.

### 4.3 conditions (발동 조건)

트리거 단위로 “이 변수 값이 이 조건을 만족할 때만 발동”하게 할 수 있습니다.

**조건 객체:**

| 필드 | 설명 |
|------|------|
| `variable` | 변수 코드 (variable_code). |
| `operator` | 연산자. 아래 목록. |
| `value` | 비교 대상 값. |

**지원 연산자 (ntm.js 기준):**

- **같음** / **같지 않음**: 문자열·숫자·불리언 비교.  
- **유효함** / **유효하지 않음**: 값이 truthy/falsy인지.  
- **포함** / **포함하지 않음**: 문자열에 특정 문자열 포함 여부.  
- **다음으로 시작** / **다음으로 시작하지 않음**  
- **다음으로 끝남** / **다음으로 끝나지 않음**  
- **정규 표현식과 일치** / **정규 표현식과 일치 하지 않음**  
- **미만 / 이하 / 초과 / 이상**: 숫자 비교.  

**예 (triggers.json):**

```json
{
  "trigger_code": "CLICK_EVENT",
  "event_type": "element_click",
  "event_config": { "css_selector": "a, button, li, ..." },
  "conditions": [
    { "variable": "is_commerce_tab", "operator": "같음", "value": false },
    { "variable": "TO_has_search", "operator": "같음", "value": false }
  ]
}
```

조건이 여러 개면 **전부 만족**해야 트리거가 발동한 것으로 간주됩니다.

### 4.4 배포 후 trigger_map 구조 (settings/latest)

배포 시 트리거 배열이 **trigger_code를 키로 하는 맵**으로 바뀝니다.

- **DOM_READY**  
  `{ "type": "immediate", "conditions": [...], "event_config": {} }`

- **그 외**  
  `{ "type": "dom_event", "event": "click" 또는 event_name, "capture": true, "css_selector": "...", "conditions": [...], "event_config": {...} }`

SDK는 이 맵을 보고 어떤 DOM 이벤트에 어떤 트리거를 붙일지, 조건을 어떻게 검사할지 결정합니다.

---

## 5. 태그 (Tags)

### 5.1 기본 필드

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `tag_code` | string | ○ | 태그 고유 코드. 수집 시 전송되는 tag_code 값. |
| `tag_name` | string | - | 표시 이름. |
| `tag_type` | string | - | `nlogger` 또는 `script` (기본은 script로 처리). |
| `trigger_code` | string | - | 단일 트리거 연결 (레거시). |
| `triggers` | array | - | 연결할 트리거 코드 배열. 있으면 이걸 사용. |
| `exec_order` | number | - | 실행 순서. 작을수록 먼저. 기본 999. |
| `enabled` | boolean | - | 사용 여부. |
| `run_conditions` | array | - | 이 트리거들일 때만 실행. `[{ "trigger_code": "DOM_READY" }]` 형태. |
| `except_conditions` | array | - | 이 트리거일 때는 실행 제외. |
| `parameters` | array | - | nlogger 타입일 때 변수→전송 키 매핑. |
| `func_js` | string | - | script 타입일 때 실행할 코드. |

트리거 연결은 **`triggers` 배열이 있으면 그것을 쓰고**, 없으면 `trigger_code` 하나로 연결합니다.

### 5.2 태그 타입

#### 5.2.1 nlogger

- **역할**: “이 변수 값을 이 키 이름으로 보낸다”만 정의. 스크립트 없음.
- **parameters**: `{ "key": "전송할 키", "value": "변수 코드" }` 배열.  
  실행 시점에 변수 값을 구한 뒤, `key`로 수집 페이로드에 넣어 전송합니다.

**예 (standard_addon.json):**

```json
{
  "tag_code": "STANDARD_CLICK",
  "tag_type": "nlogger",
  "triggers": ["CLICK_STANDARD"],
  "parameters": [
    { "key": "click_text", "value": "click_text_std" },
    { "key": "class_name", "value": "click_class_std" },
    { "key": "page_id", "value": "page_path" },
    { "key": "channel", "value": "channel" }
  ]
}
```

클릭 시 `click_text_std`, `click_class_std` 등 변수 값이 각각 `click_text`, `class_name` 등으로 전송됩니다.

#### 5.2.2 script

- **역할**: 자유로운 JavaScript로 “언제 무엇을 보낼지” 구현.
- **func_js**:
  - **trackerFunc(send) 패턴**: `function trackerFunc(send) { return function () { ... }; }`  
    SDK가 `send` 함수를 주입하고, 트리거 발동 시 반환된 함수를 실행. `send(payload)` 호출 시 해당 payload가 1건으로 수집 전송됩니다.
  - **일반 함수**: `function func() { ... }` 형태면 반환된 함수가 있으면 실행.  
  `send`를 쓰려면 반드시 `trackerFunc(send)` 형태로 받아야 합니다.

**예 (tags.json):**

```json
{
  "tag_code": "COMMON_CLICK",
  "tag_type": "script",
  "trigger_code": "CLICK_EVENT",
  "func_js": "function trackerFunc(send) {\n  return function (e) {\n    const el = e.target.closest('a, button, ...');\n    if (!el) return;\n    send({ tag_code: 'COMMON_CLICK', event_type: 'click', click_text: el.innerText?.trim().slice(0, 30) || '', class_name: el.className || '' });\n  }\n}"
}
```

클릭 시 `send({...})`로 1건 전송됩니다.

**다른 예 — CustomEvent 발화만 하는 태그:**  
DOM_READY에서 URL/경로를 보고 `Ntm00002.Event.fireUserDefined("pv", { act_type: "pageview" })` 또는 `fireUserDefined("pvDetail", {...})`를 호출하면, 그 커스텀 이벤트에 연결된 트리거가 발동하고, 해당 트리거에 연결된 태그가 실행되며 수집 1건이 나갑니다.

### 5.3 실행 조건 (run_conditions / except_conditions)

- **run_conditions**: 배열에 있는 **트리거 중 하나라도** 현재 발동한 트리거와 같으면 이 태그를 실행.  
  비어 있으면 “트리거로 연결된 경우”만 실행(즉, `triggers`/`trigger_code`로 연결된 트리거일 때).
- **except_conditions**: 여기 있는 트리거일 때는 **이 태그를 실행하지 않음**.

정리하면, “이 태그는 A, B 트리거일 때만 실행하고, C 트리거일 때는 제외” 같은 제어가 가능합니다.

### 5.4 실행 순서

태그는 **exec_order** 오름차순으로 정렬된 뒤, 트리거 발동 시 “이 트리거에 연결된 태그”만 순서대로 실행됩니다.  
같은 트리거에 여러 태그가 걸려 있으면 exec_order로 실행 순서를 조정할 수 있습니다.

---

## 6. 설정 흐름 요약

1. **Admin에서 편집**  
   변수·트리거·태그를 `data/variables.json`, `data/triggers.json`, `data/tags.json`, `data/variable_groups.json`에 저장.

2. **배포**  
   - `data/`에서 enabled된 변수 코드 목록, 트리거 배열, 태그 배열을 읽음.  
   - 트리거는 `_build_trigger_map()`으로 맵 형태로 변환.  
   - `settings/latest.json`과 `settings/versions/{버전}.json`에 전체 설정(variables, variables_full, triggers, triggers_full, tags, tags_full, variable_groups_full 등) 저장.

3. **SDK (ntm.js)**  
   - `/settings/latest`로 설정 로드.  
   - 트리거 맵에 따라 DOM_READY 실행, click 리스너, CustomEvent 리스너 등록.  
   - 트리거 발동 시 조건(트리거 conditions + 태그 run/except)을 검사하고, 통과한 태그를 exec_order 순으로 실행.  
   - nlogger는 변수→parameters 매핑으로, script는 func_js의 `send(...)` 등으로 1건씩 `/collect`에 전송.

4. **서버 (/collect)**  
   - 수신 Body에서 배포된 설정의 variables에 있는 키만 context로 정리하고, 이벤트를 Kafka로 전달.

이렇게 **변수 = 무엇을**, **트리거 = 언제**, **태그 = 어떻게**가 결합되어, 코드 배포 없이 설정만으로 수집 동작을 바꿀 수 있습니다.

---

## 7. Admin UI — 추가·편집 시 설정 항목

Admin 페이지(`/static/admin.html`)에서 변수·트리거·태그를 **추가하거나 상세 수정**할 때 나타나는 **탭, 모달, 입력 필드**를 정리했습니다.

### 7.1 전체 레이아웃

- **사이드바(좌측)**  
  - **변수** — 변수·변수 그룹 관리  
  - **트리거** — 트리거 목록·추가  
  - **태그** — 태그 목록·추가  
  - **버전** — 배포 이력·롤백  

- **상단 버튼**  
  - **저장**: 현재 편집 내용을 `data/*.json`에 반영  
  - **게시**: 배포(이름·소속·코멘트 입력 모달 후 `settings/latest.json` 갱신)  
  - 행동 분석 대시보드, 계정 관리, Kafka UI 링크  

---

### 7.2 변수 패널

#### 7.2.1 변수 탭(서브 내비게이션)

변수 패널 상단에 **세 개 탭**이 있습니다.

| 탭 | 내용 |
|----|------|
| **기본 변수** | SDK에서 제공하는 읽기 전용 변수 목록(activeTag, clickElement, path, url, customData 등). 편집 불가, 참고용. |
| **변수** | 사용자 정의 변수 목록. 행별로 코드·이름·사용 체크·상세 수정·삭제. **+ 변수 추가**로 새 행 추가. |
| **변수 그룹** | 변수 그룹 목록. **+ 새 변수 그룹 추가**로 그룹 추가·수정. |

#### 7.2.2 변수 목록 행 (변수 탭)

각 행에 다음이 노출됩니다.

- **변수 코드** (입력)
- **변수명** (입력)
- **사용** (토글)
- **상세 수정** 버튼 → 변수 상세 모달
- **삭제** 버튼

#### 7.2.3 변수 상세 수정 모달 (필드 전체)

**공통 필드**

| 라벨 | 입력 | 저장 필드 | 비고 |
|------|------|-----------|------|
| 변수명 (코드) | 텍스트 | `variable_code` | 필수 |
| 이름 | 텍스트 | `variable_name` | 표시용 |
| 설명 | 텍스트 영역 | `description` | |
| 유형 | 드롭다운 | `type` | 선택에 따라 아래 “유형별 필드” 표시 |
| (유형별 필드) | — | `type_config` | 아래 표 참고 |
| 사용 | 체크박스 | `enabled` | |

**유형 선택 시 나타나는 필드 (유형별)**

| 유형 (Admin 표기) | type 값 | 추가 필드 | type_config 매핑 |
|-------------------|---------|------------|-------------------|
| **문자열** | string | 문자열값 입력 | `value` |
| **숫자** | number | 숫자값 입력 | `value` |
| **쿠키** | cookie | 쿠키 설정 입력, URL 디코딩 여부(체크) | `cookie_setting`, `url_decode` |
| **DOM요소** | dom | 검색 방법(드롭다운) + 유형별 추가 필드 | 아래 DOM 참고 |
| **URL(표준)** | url | URL 부분(드롭다운) | `part` |
| **요소(표준)** | element | 클릭 요소 속성, 최대 길이, 클릭 없을 때 | `attribute`, `max_length`, `fallback_document` |
| **스크립트** | script | 스크립트 입력(textarea) | `script` |
| **스크립트 전역 변수** | script_global | 변수 입력(전역 변수명) | `variable` |

**URL(표준) — URL 부분 옵션**

- path (경로)
- host
- href (전체 URL)
- referrer
- title (문서 제목)
- query (쿼리스트링)

**요소(표준) — 클릭 요소 속성 옵션**

- text (요소 텍스트)
- href
- id
- className
- data-id
- data-product-id  

그 외 **최대 길이**(숫자, 0=제한없음), **클릭 없을 때**: 없음 / document.title

**DOM요소 — 검색 방법 옵션**

- 문서전체에서 검색
- 클릭된요소기준 하위 방향으로 검색
- 클릭된요소기준 상위 방향으로 검색
- 클릭된 요소를 선택

검색 방법에 따라 추가 필드가 달라집니다.

- **document / child**: CSS선택자 입력, 속성값 입력, 클릭된 요소 속성값
- **parent**: 태그값 입력, 순서(숫자), 속성값 입력
- **clicked**: 속성값 입력

(저장 시 `type_config`에는 `search_method`, `css_selector`, `attribute_value`, `tag_value`, `order`, `clicked_attribute_value` 등이 들어갑니다.)

---

### 7.3 트리거 패널

#### 7.3.1 트리거 목록 행

각 행:

- **트리거 코드** (입력)
- **트리거명** (입력)
- **이벤트 타입** (입력)
- **사용** (토글)
- **상세 수정** 버튼
- **삭제** 버튼

**+ 트리거 추가**로 새 행 추가.

#### 7.3.2 트리거 상세 수정 모달 (필드 전체)

| 라벨 | 입력 | 저장 필드 | 비고 |
|------|------|-----------|------|
| 트리거 코드 | 텍스트 | `trigger_code` | 필수 |
| 트리거 이름 | 텍스트 | `trigger_name` | |
| 설명 | 텍스트 영역 | `description` | |
| 이벤트 유형 | 드롭다운 | `event_type` | 선택에 따라 “이벤트 유형별 필드” 표시 |
| (이벤트 유형별 필드) | — | `event_config` | 아래 표 참고 |
| 조건 | 조건 행 + **+ 추가** | `conditions` | 변수·연산자·값 |
| 사용 | 체크박스 | `enabled` | |

**이벤트 유형 옵션 (드롭다운)**

- 페이지 로드 (`page_load`)
- DOM 준비완료 (`dom_ready`)
- 윈도우 로드 (`window_load`)
- 페이지 표시 (`page_show`)
- 화면 노출 변화 (`visibility_change`)
- URL 주소 변경 (`url_change`)
- URL 해시 변경 (`hash_change`)
- 특정 요소 클릭 (`element_click`)
- 클릭 (`click`)
- 커스텀 (`custom`)

**이벤트 유형별 추가 필드 (event_config)**

| 이벤트 유형 | 추가 필드 | event_config 키 |
|-------------|-----------|------------------|
| 특정 요소 클릭 | CSS선택자 입력 | `css_selector` |
| 클릭 | 목적 태그명 입력 (A, BUTTON 등) | `target_tag` |
| 커스텀 | 이벤트명 입력 | `event_name` |
| 그 외 | 없음 | — |

**조건 (conditions)**

한 조건당 한 행. **+ 추가**로 행 추가, 행마다 ×로 삭제.

- **변수**: 드롭다운 (기본 변수 + 사용자 정의 변수 코드)
- **연산자**: 같음, 같지 않음, 포함, 포함하지 않음, 다음으로 시작, 다음으로 시작하지 않음, 다음으로 끝남, 다음으로 끝나지 않음, 정규 표현식과 일치, 정규 표현식과 일치 하지 않음, 미만, 이하, 초과, 이상, 유효함, 유효하지 않음
- **값**: 텍스트 (true / false / 숫자 / 문자열 입력 가능)

---

### 7.4 태그 패널

#### 7.4.1 태그 목록 행

각 행:

- **태그 코드** (입력)
- **태그명** (입력)
- **연결된 트리거** (표시만, 실행조건에서 유도)
- **실행 순서** (숫자)
- **사용** (토글)
- **상세 수정** 버튼
- **삭제** 버튼  
그 아래 **함수 코드** 텍스트 영역(스크립트 타입일 때).

**+ 태그 추가**로 새 태그 추가.

#### 7.4.2 태그 상세 수정 모달 (필드 전체)

**공통**

| 라벨 | 입력 | 저장 필드 | 비고 |
|------|------|-----------|------|
| 태그 코드 | 텍스트 | `tag_code` | 필수 |
| 태그명 | 텍스트 | `tag_name` | |
| 설명 | 텍스트 영역 | `description` | |
| 트리거 (실행조건) | 트리거 선택 목록 + **+ 추가** | `run_conditions` → `triggers` | 여기서 고른 트리거만 이 태그 실행 |
| 하나 이상 만족 시 실행 | 체크박스 | `run_condition_any` | |
| 예외 조건 | 트리거 선택 목록 + **+ 추가** | `except_conditions` | 선택한 트리거일 때 이 태그 미실행 |
| 유형 | 스크립트 / 헥토 로깅 모듈 | `tag_type` | script / nlogger |
| 사용 | 체크박스 | `enabled` | |

**유형 = 스크립트일 때**

| 라벨 | 입력 | 저장 필드 |
|------|------|-----------|
| 함수 코드 (수집·로그 로직) | textarea | `func_js` |

placeholder 예: `function trackerFunc(send) { return function(e) { ... send({ ... }); }; }`

**유형 = 헥토 로깅 모듈(nlogger)일 때**

| 라벨 | 입력 | 저장 필드 | 비고 |
|------|------|-----------|------|
| 전송방식 | 드롭다운 | `send_method` | 기본 / 지연 / 비콘API |
| 로그 유형 | 드롭다운 | `log_type` | 기본 / 사용자 정의 |
| 경로 | 텍스트 | `log_type_path` | 로그 유형이 “사용자 정의”일 때만 표시 |
| 파라미터 | 키·값(변수) 행들 + **+ 추가**, **변수 그룹 선택 + 그룹추가** | `parameters` | key = 전송 키, value = 변수 코드 |
| 쿠키 | 키·값(변수) 행들 + **+ 추가**, **변수 그룹 선택 + 그룹추가** | `cookies` | |

**전송방식 옵션**

- 기본 — 로그를 즉시 전송
- 지연 — 페이지 이동 후 전송
- 비콘API — 페이지 이동 중에도 전송 요청 유지

**실행조건·예외 조건**

- 실행조건: 트리거를 선택하면 “이 트리거일 때만 이 태그 실행”. 여러 개 선택 가능. 저장 시 `run_conditions`와 `triggers` 배열에 반영됨.
- 예외 조건: 선택한 트리거일 때는 이 태그를 실행하지 않음.

(저장 시 실행조건에서 선택된 트리거 코드들이 `triggers` 배열과 `trigger_code`(첫 번째)에 저장됩니다.)

---

### 7.5 변수 그룹 모달

**+ 새 변수 그룹 추가** 또는 기존 그룹 수정 시 열리는 모달.

| 라벨 | 입력 | 저장 필드 |
|------|------|-----------|
| 변수 그룹명 | 텍스트 | `name` |
| 설명 | 텍스트 영역 | `description` |
| 구성 | 키·값 행들 + **+ 추가** | `items` |

구성의 **키**는 전송 시 사용할 이름, **값**은 기본 변수명 또는 사용자 정의 변수 코드(variable_code)를 선택하는 드롭다운입니다. 검색 가능 드롭다운으로 표시됩니다.

---

### 7.6 요약 표 — “무엇을 어디서 설정하는지”

| 설정 | 목록에서 보이는 항목 | 상세 모달에서 추가로 설정하는 항목 |
|------|----------------------|-----------------------------------|
| **변수** | 코드, 이름, 사용 | 유형, 유형별 필드(문자열값/URL 부분/요소 속성/스크립트 등), 설명 |
| **트리거** | 코드, 이름, 이벤트 타입, 사용 | 설명, 이벤트 유형별 필드(CSS선택자/이벤트명 등), 조건(변수·연산자·값) |
| **태그** | 코드, 이름, 연결 트리거, 실행 순서, 사용, 함수 코드 | 설명, 실행조건·예외조건, 유형(스크립트/nlogger), nlogger 시 전송방식·로그유형·파라미터·쿠키 |
| **변수 그룹** | 그룹명, 구성 요약 | 그룹명, 설명, 구성(키·값 쌍 목록) |

---

## 참고 문서

- [FEATURE_DOCUMENTATION.md](FEATURE_DOCUMENTATION.md) — 전체 기능 개요  
- [STANDARD_TAGGING.md](STANDARD_TAGGING.md) — 표준 변수·트리거·태그로 다른 사이트 재사용  
- [data/standard_addon.json](../data/standard_addon.json) — 표준 설정 예시
