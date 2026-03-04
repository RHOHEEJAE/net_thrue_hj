# ntm.js SDK 상세 설명

ntm.js는 **헥토 행동 데이터 트래커**의 클라이언트 SDK입니다. 배포된 설정(트리거·태그·변수)을 받아, 페이지 로드·클릭·스크롤·커스텀 이벤트 시 **1건씩** `/collect`로 전송하고, 서버는 이를 Kafka로 보냅니다.

---

## 목차

1. [진입점과 초기화](#1-진입점과-초기화)
2. [설정 로드와 변수 분류](#2-설정-로드와-변수-분류)
3. [컨텍스트와 변수 값 계산](#3-컨텍스트와-변수-값-계산)
4. [트리거 조건 평가](#4-트리거-조건-평가)
5. [전송: 페이로드 구성과 전송](#5-전송-페이로드-구성과-전송)
6. [태그 핸들러와 실행](#6-태그-핸들러와-실행)
7. [DOM_READY와 페이지뷰](#7-dom_ready와-페이지뷰)
8. [URL 변경 감지](#8-url-변경-감지)
9. [클릭 이벤트](#9-클릭-이벤트)
10. [커스텀 이벤트](#10-커스텀-이벤트)
11. [네이티브 스크롤](#11-네이티브-스크롤)
12. [설정 갱신과 공개 API](#12-설정-갱신과-공개-api)

---

## 1. 진입점과 초기화

### 1.1 IIFE와 싱글톤

```javascript
(async function () {
  "use strict";
  if (typeof window !== "undefined") {
    if (window.__NTM_SDK_LOADED) return;
    window.__NTM_SDK_LOADED = true;
  }
  // ...
})();
```

- **비동기 IIFE**: 스크립트 로드 즉시 실행되는 비동기 함수.
- **중복 방지**: `window.__NTM_SDK_LOADED`가 이미 true면 아무 것도 하지 않고 종료(싱글톤).
- **서버/Node 등**: `window`가 없으면 플래그 체크를 건너뛰고 실행(SSR/테스트 환경 고려).

### 1.2 상수

| 상수 | 값 | 의미 |
|------|-----|------|
| `SETTINGS_API` | `http://localhost:8000/settings/latest` | 배포된 설정 JSON URL |
| `COLLECT_URL` | `http://localhost:8000/collect` | 이벤트 전송 API |
| `SETTINGS_REFRESH_MS` | `5 * 60 * 1000` (5분) | 설정 폴링 주기 |
| `COLLECT_EXCLUDE_VARS` | Set | 수집 페이로드에서 제외할 변수 코드 (AL_impression, AL_popup, AL_swipe 등) |

---

## 2. 설정 로드와 변수 분류

### 2.1 설정 fetch

```javascript
const res = await fetch(SETTINGS_API);
const settings = await res.json();
```

- 최초 1회 `GET /settings/latest`로 설정을 가져옵니다.
- 이후 동작은 모두 이 `settings` 객체 기준입니다.

### 2.2 변수 분류

설정에서 변수 목록을 **활성 여부**와 **타입**으로 나눕니다.

| 변수 | 조건 | 용도 |
|------|------|------|
| `enabledVarSet` | `settings.variables` (배포 시 활성 코드 목록) | 수집 시 “이 키만 전송” 여부 판단 |
| `scriptVariables` | `variables_full` 중 type=script이고 활성인 것 | `runScriptVariable()`로 값 계산 |
| `standardVariables` | 활성이고 type이 url 또는 element | 스크립트 없이 `getStandardVariableValues()`로 해석 |
| `stringVariables` | 활성이고 type=string | 고정값 `type_config.value` |

### 2.3 트리거·태그

- **triggers**: `settings.triggers` — trigger_code를 키로 하는 맵(배포 시 변환된 형태).
- **triggersFull**: `settings.triggers_full` — 조건·event_config 등 원본 배열.
- **tags**: `settings.tags`를 `exec_order` 오름차순으로 정렬한 배열.

### 2.4 런타임 상태(클로저 변수)

| 변수 | 용도 |
|------|------|
| `currentClickElement` | 현재 클릭/커스텀 이벤트의 대상 요소 (변수 계산·전송 시 사용) |
| `currentCustomData` | 커스텀 이벤트의 `e.detail` |
| `lastFiredTriggerCode` | 직전에 발동한 트리거 코드 (전송 시 event_trigger로 사용) |
| `scrollThresholdsSent` | 이미 전송한 스크롤 구간(25/50/75/99) — 구간당 1회만 전송 |
| `lastScrollRateSent` | 마지막으로 보낸 스크롤 비율 |

---

## 3. 컨텍스트와 변수 값 계산

### 3.1 getBuiltInContext(clickEl, customData)

클릭 요소와 커스텀 데이터를 받아 **SDK 기본 컨텍스트**를 만듭니다.

- **location**: path, href, search, hash, host
- **document**: referrer, title
- **클릭 요소(clickEl)**: clickText, clickClass, clickId, clickTag, clickElement
- **customData**: 커스텀 이벤트의 detail
- **paramDict**: `parseQueryToObject(loc.search)` — 쿼리스트링을 객체로
- **params**: `loc.search` 문자열
- **별칭**: click_text ↔ clickText, class_name ↔ clickClass

스크립트 변수의 `{{변수명}}`과 조건 평가 시 이 컨텍스트를 사용합니다.

### 3.2 runScriptVariable(scriptSrc, payload, clickEl, context)

**스크립트 타입 변수**의 값을 계산합니다.

1. `scriptSrc` 안의 `{{이름}}`을 정규식으로 찾아, 해당 이름을 인자 목록으로 모음.
2. `{{이름}}`을 `__ctx_이름__` 형태의 인자명으로 치환.
3. `new Function(인자명..., body + "; return typeof func === 'function' ? func() : undefined;")`로 함수 생성.
4. 인자값은 `context[이름]` 또는 `getBuiltInContext(...)`에서 채움.
5. 실행 후 반환값이 해당 변수의 값.
6. 에러 시 `console.warn` 후 `undefined` 반환.

스크립트는 `function func() { ... }` 형태를 가정하며, 이전에 계산된 스크립트 변수 값은 다음 스크립트 변수의 context에 누적됩니다.

### 3.3 getStandardVariableValues(payload, clickEl)

**표준 변수(url, element, string)**만 스크립트 없이 계산합니다.

- **url**: `type_config.part`에 따라 path, host, href, referrer, title, query 등 반환.
- **element**: clickEl이 있으면 해당 요소의 text, href, id, className, data-* 등. `max_length` 적용. clickEl이 없고 `fallback_document === "title"`이면 document.title.
- **string**: `type_config.value` 그대로.

결과는 `{ variable_code: value }` 형태의 객체입니다.

### 3.4 getScriptVariableValues(payload, clickEl)

`scriptVariables`를 순서대로 실행하고, 각 결과를 context에 넣어가며 다음 스크립트에서 사용할 수 있게 합니다. 반환도 `{ variable_code: value }`.

### 3.5 getMergedVariableValues(payload, clickEl)

- built-in 컨텍스트
- 표준 변수 값
- 스크립트 변수 값  

을 합친 객체를 반환합니다. 수집 페이로드와 조건 평가에 사용됩니다.

---

## 4. 트리거 조건 평가

### 4.1 evaluateTriggerConditions(conditions, varValues)

- `conditions`가 없거나 빈 배열이면 **true**(조건 없음 = 통과).
- 각 조건은 `{ variable, operator, value }`.
- **변수 값**은 `varValues[c.variable]`에서 가져옵니다.

지원 연산자:

- 같음 / 같지 않음 (문자·숫자·불리언)
- 유효함 / 유효하지 않음 (truthy/falsy)
- 포함 / 포함하지 않음 (문자열)
- 다음으로 시작 / 다음으로 시작하지 않음
- 다음으로 끝남 / 다음으로 끝나지 않음
- 정규 표현식과 일치 / 정규 표현식과 일치 하지 않음
- 미만 / 이하 / 초과 / 이상 (숫자)

하나라도 실패하면 false, 모두 통과하면 true.

### 4.2 elementMatchesSelector(el, selectorStr)

- selector가 없으면 true.
- `el.closest(selectorStr)` 시도.
- selectorStr을 쉼표로 나눈 각 부분에 대해 `el.matches(part)` 또는 `el.closest(part)` 시도.
- 하나라도 성공하면 true, 모두 실패하면 false. 예외 시 false.

---

## 5. 전송: 페이로드 구성과 전송

### 5.1 sanitizeForSend(obj)

전송 직렬화 전에 객체를 정리합니다.

- null/undefined → 그대로 반환.
- 함수 → undefined(제외).
- DOM Node → `"[Node]"` 문자열.
- 배열·객체는 재귀적으로 처리하고, undefined는 제거.

### 5.2 buildCollectPayload(base, varValues, extra)

수집 1건의 **페이로드 객체**를 만듭니다.

- **base**: page_url, ts, event_trigger, act_type, channel, page_id 등 이미 정해진 필드.
- **varValues**: 변수 값 객체. 키가 `COLLECT_EXCLUDE_VARS`에 있거나 값이 function/Node면 제외하고 나머지를 페이로드에 넣음.
- **extra**: 추가로 덮어쓸 키·값.

`event_trigger`는 base에 없으면 `lastFiredTriggerCode`를 사용합니다.

### 5.3 produceEvent(payload)

실제 HTTP 전송입니다.

1. payload를 `sanitizeForSend` 후 `JSON.stringify`.
2. **우선** `navigator.sendBeacon(COLLECT_URL, raw)` 사용.
3. 없으면 `fetch(COLLECT_URL, { method: "POST", body: raw, keepalive: true })`.
4. 실패 시 약 500ms 후 한 번 재시도.
5. 개발 시 `console.log("NTMOBJ ", ...)`로 페이로드 출력.

### 5.4 sendToCollect(payload, eventTrigger)

- payload에 page_url, ts, event_trigger(인자 또는 lastFiredTriggerCode)를 보강.
- referer_url이 없으면 payload.referrer를 referer_url로 사용.
- `produceEvent(base)`로 한 건 전송.

---

## 6. 태그 핸들러와 실행

### 6.1 createSend(triggerCodeForAsync)

태그의 스크립트에 주입되는 `send` 함수를 만듭니다.

- `send(payload)` 호출 시:
  - payload에 `getMergedVariableValues(merged, currentClickElement)`를 합침.
  - `sendToCollect(merged, triggerCodeForAsync)` 호출.

즉, 태그에서 `send({ ... })`를 호출하면 자동으로 변수 값이 붙고 한 건이 `/collect`로 나갑니다.

### 6.2 tagHandlers 배열

각 태그에 대해:

- **tag_type === "nlogger"**  
  - 핸들러: `tag.parameters`의 key·value를 보고, value는 변수 코드로 해석해 `mergedValues[value]`를 payload의 key로 넣고 `sendToCollect` 호출.
- **그 외(script)**  
  - `func_js` 문자열을 파싱.
  - `function trackerFunc(send)` 패턴이 있으면 `new Function("send", funcJs + "; return trackerFunc(send);")`로 factory 만들고, `createSend(null)`을 인자로 넣어 핸들러 생성.
  - 없으면 `func()` 반환값이 함수면 그걸 핸들러로 사용.

에러 나면 해당 태그의 handler는 null이 되고, 아래에서 스킵됩니다.

### 6.3 tagsByTrigger

- 각 태그의 `tag.triggers`(또는 `tag.trigger_code`)에 있는 트리거 코드마다, `tagsByTrigger[triggerCode]`에 해당 태그와 핸들러를 push.
- 트리거가 발동할 때 “이 트리거에 연결된 태그 목록”을 이 맵으로 조회합니다.

### 6.4 shouldRunTag(tag, triggerCode, varValues)

해당 트리거에서 이 태그를 **실행할지** 판단합니다.

1. 트리거가 없으면 false.
2. 트리거에 conditions가 있으면 `evaluateTriggerConditions` 실행. 실패하면 false.
3. 태그에 `run_conditions`가 있으면, 그 안에 현재 triggerCode가 있어야 함. 없으면 false.
4. `except_conditions`에 현재 triggerCode가 있으면 false.
5. 나머지는 true.

---

## 7. DOM_READY와 페이지뷰

### 7.1 runDOMReadyOnce

- `domReadyFired` 플래그로 **한 번만** 실행.
- 실행 시 `domReadyFired = true` 후 `runDOMReady()` 호출.
- `lastPageviewUrl`을 현재 location.href로 저장(URL 변경 감지용).

### 7.2 runDOMReady()

1. `lastFiredTriggerCode = "DOM_READY"`, `scrollThresholdsSent` 초기화.
2. `tagsByTrigger["DOM_READY"]`에 연결된 태그만 순서대로 실행.
   - 태그 코드가 "PV_DETAIL"이면 스킵(별도 pvDetail 로직에서 처리).
   - `shouldRunTag(tag, "DOM_READY", varValues)`가 true인 것만 실행.
   - nlogger면 handler(null, "DOM_READY", varValues), script면 handler().
3. 그 다음 **페이지뷰 1건** 전송: channel, page_id, act_type: "pageview", referer_url + varValues로 `buildCollectPayload` 후 `sendToCollect(..., "DOM_READY")`.

### 7.3 DOM/load 이벤트 연결

- `document.readyState`가 이미 "complete" 또는 "interactive"면 곧바로 `runDOMReadyOnce()`.
- 아니면 `document.addEventListener("DOMContentLoaded", runDOMReadyOnce)`.
- `window.addEventListener("load", runDOMReadyOnce)`도 등록(늦은 로드 대비).

---

## 8. URL 변경 감지

### 8.1 maybeSendPageviewOnUrlChange()

- 현재 `location.href`가 `lastPageviewUrl`과 다르면:
  - `lastPageviewUrl` 갱신.
  - `scrollThresholdsSent` 초기화.
  - `sendPageviewForUrl()` 호출 → channel, page_id, act_type: "pageview"로 1건 전송, event_trigger는 "URL 주소 변경".

### 8.2 sendPageviewForUrl()

- `getMergedVariableValues({}, null)`로 변수 값 계산.
- `buildCollectPayload`로 pageview 페이로드 만들고 `sendToCollect(payload, "URL 주소 변경")`.

### 8.3 history / popstate 후킹

- `window.addEventListener("popstate", () => setTimeout(maybeSendPageviewOnUrlChange, 0))`.
- `history.pushState` / `history.replaceState`를 래핑해서, 호출 후 `maybeSendPageviewOnUrlChange()` 실행.

SPA에서 주소만 바뀌는 경우에도 페이지뷰 1건이 나가도록 합니다.

---

## 9. 클릭 이벤트

### 9.1 clickTriggerCodes

- `triggers` 중 `event` 또는 `event_type`이 `"click"` 또는 `"element_click"`인 트리거 코드만 배열로 모음. DOM_READY 제외.

### 9.2 document click 리스너 (capture)

- 클릭 시 `e.target`에서 `closest("a, button, li, div, span, svg, [role=button]")`로 의미 있는 요소를 찾아 `currentClickElement`에 넣음.
- `getMergedVariableValues({}, clickEl)`로 변수 값 계산.
- clickTriggerCodes 순서대로:
  - `css_selector`가 있으면 `elementMatchesSelector(e.target, sel)`로 매칭.
  - 트리거에 conditions가 있으면 `evaluateTriggerConditions` 실행.
  - 처음 통과한 트리거를 `matchedTriggerCode`로 사용.
- 매칭된 트리거가 없으면 clickTriggerCodes[0]을 사용.
- `lastFiredTriggerCode = triggerCode` 설정.
- `buildCollectPayload`로 channel, page_id, act_type: "click", referer_url, click_text, class_name, click_type, order 등 + varValues 넣고 `sendToCollect(payload, triggerCode)`.
- finally에서 `currentClickElement = null`로 초기화.
- 예외 시 최소 페이로드(act_type: "click", page_url, ts)만 보내고, currentClickElement는 마찬가지로 null로.

클릭은 **SDK가 직접 1건 전송**하며, 같은 클릭에 대해 “태그”가 추가로 send를 호출하면 그때도 별도 건으로 나갈 수 있습니다(태그 쪽에서 중복 제어 가능).

---

## 10. 커스텀 이벤트

### 10.1 customEventMap 구성

- DOM_READY와 click 트리거를 제외한 트리거에 대해:
  - `resolveEventName(triggerCode, t)`로 이벤트 이름(문자열) 계산.
  - 빈 문자열이거나 "click"이면 제외.
  - `customEventMap[eventName]`에 해당 triggerCode를 push.

### 10.2 resolveEventName(triggerCode, triggerObj)

- trigger가 element_click/click이면 "click".
- dom_ready/DOMContentLoaded면 "".
- custom이면:
  - `event_config.event_name`이 있으면 사용.
  - 없으면 triggersFull에서 같은 trigger_code로 event_name 조회.
  - 없으면 trigger_code별 fallback 맵 사용(Scroll Event→scroll, pv(Custom)→pv, pv_detail(Custom)→pvDetail 등).

### 10.3 CUSTOM_EVENT_FALLBACK

설정에 해당 이벤트가 없어도 **리스너는 등록**되도록, 기본 트리거 코드를 채워 넣습니다.

- scroll → "Scroll Event"
- pv → "pv(Custom)"
- pvDetail → "pv_detail(Custom)"
- swipe, popup, impression, Scroll_Impression, enter, click_touch, url_change 등.

### 10.4 커스텀 이벤트 리스너

- `customEventMap`의 각 이벤트 이름에 대해 `document.addEventListener(eventName, handler, true)`.
- 핸들러 안에서:
  - `e.detail`을 customData로, target에서 의미 있는 요소를 찾아 currentClickElement로 설정.
  - 변수 값 계산 후, 트리거 조건·css_selector 매칭으로 matchedTriggerCode 결정.
  - 조건이 있는 트리거만 있는데 하나도 매칭 안 되면 return(전송 안 함).
  - act_type은 customData.act_type 또는 이벤트 이름에 따라 scroll/pageview/impression/click/custom 등으로 결정.
  - buildCollectPayload(기본 + varValues + customData) 후 sendToCollect.
  - scroll이고 customData.scroll_rate가 있으면 scrollThresholdsSent에 반영.
  - pv/pvDetail이면 scrollThresholdsSent 초기화.
  - finally에서 currentClickElement, currentCustomData 초기화.

앱/다른 태그에서 `Ntm00002.Event.fireUserDefined("scroll", { scroll_rate: 50 })`처럼 호출하면 이 리스너가 받아 1건 전송됩니다.

---

## 11. 네이티브 스크롤

### 11.1 SCROLL_THRESHOLDS

`[25, 50, 75, 99]` — 스크롤 진행률(%) 구간입니다. 각 구간에 **최초 1회만** 전송합니다.

### 11.2 getWindowScrollRate()

- scrollTop, window 높이, document 높이로 현재 스크롤 진행률(%) 계산.
- 최대 99로 제한한 정수로 반환.

### 11.3 scroll 이벤트 (passive)

- requestAnimationFrame(또는 setTimeout 100ms)으로 스로틀.
- `sendNativeScroll()`에서:
  - 현재 스크롤 비율 계산.
  - 25/50/75/99 중 아직 `scrollThresholdsSent`에 없는 구간이면:
    - 해당 구간을 sent에 추가.
    - channel, page_id, act_type: "scroll", scroll_rate 넣어 buildCollectPayload 후 sendToCollect(..., "Scroll Event").

즉, 스크롤은 **브라우저 scroll 이벤트**만으로도 25/50/75/99% 구간당 1건씩 자동 전송됩니다. 태그에서 별도로 fireUserDefined("scroll", ...)를 써도 동일 이벤트로 처리됩니다.

---

## 12. 설정 갱신과 공개 API

### 12.1 설정 주기 갱신

- `setInterval(SETTINGS_REFRESH_MS)`로 주기적으로 `GET /settings/latest` 호출.
- 응답의 `version`이 현재 `settings.version`과 다르면 `location.reload()`로 페이지 새로고침(새 설정으로 다시 로드).

### 12.2 Ntm00002.Event.fireUserDefined(eventName, data)

- `window.Ntm00002.Event.fireUserDefined = function (eventName, data) { document.dispatchEvent(new CustomEvent(eventName, { detail: data || {}, bubbles: true })); };`
- 앱 또는 태그 스크립트에서 `Ntm00002.Event.fireUserDefined("pvDetail", { act_type: "pageview", prd_code: "..." })`처럼 호출하면, 해당 커스텀 이벤트가 document에 발생하고, 위에서 등록한 커스텀 이벤트 리스너가 받아 1건 전송합니다.

---

## 요약 흐름도

```
[페이지 로드]
  → DOMContentLoaded / load
  → runDOMReadyOnce → runDOMReady
      → DOM_READY 연결 태그 실행 (PV_DETAIL 제외)
      → 페이지뷰 1건 전송 (event_trigger: DOM_READY)

[SPA URL 변경]
  → pushState/replaceState/popstate
  → maybeSendPageviewOnUrlChange → sendPageviewForUrl
      → 페이지뷰 1건 전송 (event_trigger: URL 주소 변경)

[클릭]
  → document click (capture)
  → currentClickElement 설정 → 변수 계산 → 트리거 매칭
  → 클릭 1건 전송 (act_type: click)

[스크롤 25/50/75/99%]
  → scroll 이벤트 (throttle)
  → sendNativeScroll → 구간당 1건 전송 (act_type: scroll)

[커스텀 이벤트]
  → Ntm00002.Event.fireUserDefined(name, data)
  → document CustomEvent
  → customEventMap 리스너 → 변수·트리거 매칭 → 1건 전송
```

모든 전송은 **buildCollectPayload → sendToCollect → produceEvent**를 거치며, 서버는 `/collect`에서 Kafka로 전달합니다.
