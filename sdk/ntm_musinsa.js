/**
 * NTM SDK — settings/latest(트리거·태그·변수) 기반 수집, 액션당 1건 전송 후 Kafka 적재
 * - DOM_READY: 태그 실행 후 페이지뷰 1건
 * - Click: 1회 클릭 = 1건 (NTMOBJ)
 * - Custom(scroll, pv, pvDetail, swipe, popup 등): 이벤트 1회 = 1건
 * 중복 로드 시 한 번만 초기화(싱글톤).
 */
(async function () {
  "use strict";
  if (typeof window !== "undefined") {
    if (window.__NTM_SDK_LOADED) return;
    window.__NTM_SDK_LOADED = true;
  }

  const SETTINGS_API = "https://net-thrue-hj-od6m.vercel.app/settings/latest";
  const COLLECT_URL = "https://net-thrue-hj-od6m.vercel.app/collect";
  const SETTINGS_REFRESH_MS = 5 * 60 * 1000;
  /** 수집 전송에서 제외할 설정용 변수(대형 배열 등) — settings.variables에는 있으나 payload에는 넣지 않음 */
  const COLLECT_EXCLUDE_VARS = new Set(["AL_impression", "AL_popup", "AL_swipe", "AL_modules", "AL_likeBtn_arr", "FC_nthReplace"]);

  const res = await fetch(SETTINGS_API);
  const settings = await res.json();
  console.log("[TRACKER SDK] init", settings.version);

  const enabledVarSet = new Set(settings.variables || []);
  const variablesFull = settings.variables_full || [];
  const scriptVariables = variablesFull.filter(
    (v) =>
      v.type === "script" &&
      v.type_config &&
      v.type_config.script &&
      enabledVarSet.has(v.variable_code)
  );
  /** 표준 변수: url / element / string — 스크립트 없이 설정만으로 해석 (다른 사이트에서도 재사용) */
  const standardVariables = variablesFull.filter(
    (v) => enabledVarSet.has(v.variable_code) && (v.type === "url" || v.type === "element")
  );
  const stringVariables = variablesFull.filter(
    (v) => enabledVarSet.has(v.variable_code) && v.type === "string"
  );

  const triggers = settings.triggers || {};
  const triggersFull = settings.triggers_full || [];
  const tags = (settings.tags || []).sort((a, b) => (a.exec_order || 999) - (b.exec_order || 999));

  let currentClickElement = null;
  let currentCustomData = null;
  let lastFiredTriggerCode = null;
  let scrollThresholdsSent = [];
  let lastScrollRateSent = -1;

  if (typeof window !== "undefined") {
    window.Ntm00002 = window.Ntm00002 || {};
    window.Ntm00002.Event = window.Ntm00002.Event || {};
    window.Ntm00002.Event.fireUserDefined = function (eventName, data) {
      document.dispatchEvent(new CustomEvent(eventName, { detail: data || {}, bubbles: true }));
    };
  }

  function parseQueryToObject(search) {
    const o = {};
    if (!search) return o;
    const s = search.indexOf("?") === 0 ? search.slice(1) : search;
    s.split("&").forEach((pair) => {
      const [k, v] = pair.split("=").map((x) => (x != null ? decodeURIComponent(x) : ""));
      if (k) o[k] = v;
    });
    return o;
  }

  function getBuiltInContext(clickEl, customData) {
    const loc = typeof location !== "undefined" ? location : { href: "", pathname: "", search: "", hash: "", host: "", hostname: "" };
    const doc = typeof document !== "undefined" ? document : { referrer: "", title: "" };
    const el = clickEl || null;
    const clickText = el ? String(el.textContent || "").trim().slice(0, 500) : "";
    const clickClass = el ? String(el.className || "").trim() : "";
    const ctx = {
      clickClass,
      clickElement: el,
      clickId: el ? String(el.id || "") : "",
      clickTag: el && el.tagName ? el.tagName.toLowerCase() : "",
      clickText,
      customData: customData != null ? customData : {},
      path: loc.pathname || "",
      referrer: doc.referrer || "",
      url: loc.href || "",
      title: doc.title || "",
      hash: loc.hash || "",
      host: loc.host || loc.hostname || "",
      paramDict: parseQueryToObject(loc.search),
      params: loc.search || ""
    };
    ctx.click_text = clickText;
    ctx.class_name = clickClass;
    return ctx;
  }

  function runScriptVariable(scriptSrc, payload, clickEl, context) {
    try {
      const ctx = context || getBuiltInContext(clickEl, payload && payload.customData);
      const names = [];
      const body = scriptSrc.replace(/\{\{(\w+)\}\}/g, (_, n) => {
        if (!names.includes(n)) names.push(n);
        return "__ctx_" + n + "__";
      });
      const uniq = [...new Set(names)];
      const args = uniq.map((n) => (ctx && n in ctx ? ctx[n] : undefined));
      const fn = new Function(
        ...uniq.map((n) => "__ctx_" + n + "__"),
        body + "; return typeof func === 'function' ? func() : undefined;"
      );
      return fn(...args);
    } catch (e) {
      console.warn("[TRACKER] script variable error", e);
      return undefined;
    }
  }

  /** 표준 변수(type: url, dom) 값 해석 — 하드코딩 없이 GTM/GA 스타일 공통 수집 */
  function getStandardVariableValues(payload, clickEl) {
    const ctx = getBuiltInContext(clickEl, payload && payload.customData);
    const out = {};
    standardVariables.forEach((v) => {
      const tc = v.type_config || {};
      let value;
      if (v.type === "url") {
        const part = (tc.part || "path").toLowerCase();
        if (part === "path") value = ctx.path || "";
        else if (part === "host" || part === "hostname") value = ctx.host || "";
        else if (part === "href") value = ctx.url || "";
        else if (part === "referrer") value = ctx.referrer || "";
        else if (part === "title") value = ctx.title || "";
        else if (part === "query" || part === "search") value = ctx.params ? (ctx.params[0] === "?" ? ctx.params : "?" + ctx.params) : "";
        else value = ctx[part] != null ? ctx[part] : "";
      } else if (v.type === "element" && clickEl) {
        const attr = (tc.attribute || "text").toLowerCase();
        const maxLen = typeof tc.max_length === "number" ? tc.max_length : 500;
        if (attr === "text" || attr === "innertext") {
          value = String(clickEl.textContent || "").trim();
          if (maxLen > 0 && value.length > maxLen) value = value.slice(0, maxLen);
        } else if (attr === "href") value = clickEl.href != null ? String(clickEl.href) : "";
        else if (attr === "id") value = clickEl.id != null ? String(clickEl.id) : "";
        else if (attr === "class" || attr === "classname") value = clickEl.className != null ? String(clickEl.className).trim() : "";
        else if (attr.indexOf("data-") === 0) value = clickEl.getAttribute ? (clickEl.getAttribute(attr) || "") : "";
        else if (attr.indexOf("data-") === -1 && attr.indexOf("data") !== 0) value = clickEl.getAttribute ? (clickEl.getAttribute("data-" + attr) || "") : "";
        else value = clickEl.getAttribute ? (clickEl.getAttribute(attr) || "") : "";
      } else if (v.type === "element" && !clickEl && tc.fallback_document) {
        const doc = typeof document !== "undefined" ? document : null;
        if (doc && tc.fallback_document === "title") value = doc.title || "";
        else value = "";
      } else if (v.type === "element") value = "";
      if (value !== undefined) out[v.variable_code] = value;
    });
    stringVariables.forEach((v) => {
      const val = (v.type_config && v.type_config.value) != null ? String(v.type_config.value) : "";
      out[v.variable_code] = val;
    });
    return out;
  }

  function getScriptVariableValues(payload, clickEl) {
    const out = {};
    let ctx = { ...getBuiltInContext(clickEl, payload && payload.customData) };
    scriptVariables.forEach((v) => {
      const value = runScriptVariable(v.type_config.script, payload || {}, clickEl, ctx);
      if (value !== undefined) {
        out[v.variable_code] = value;
        ctx[v.variable_code] = value;
      }
    });
    return out;
  }

  function getMergedVariableValues(payload, clickEl) {
    const builtIn = getBuiltInContext(clickEl, payload && payload.customData);
    const standardVals = getStandardVariableValues(payload || {}, clickEl);
    const scriptVals = getScriptVariableValues(payload || {}, clickEl);
    return { ...builtIn, ...standardVals, ...scriptVals };
  }

  function evaluateTriggerConditions(conditions, varValues) {
    if (!conditions || !conditions.length) return true;
    for (let i = 0; i < conditions.length; i++) {
      const c = conditions[i];
      const varVal = varValues[c.variable];
      const target = c.value;
      const op = c.operator || "같음";
      const strVar = varVal != null ? String(varVal) : "";
      const numVar = typeof varVal === "number" ? varVal : (typeof varVal === "string" && varVal.trim() !== "" ? Number(varVal) : NaN);
      const numTarget = typeof target === "number" ? target : (target !== "" && target != null ? Number(target) : NaN);
      const boolVar = !!varVal;
      const boolTarget = target === true || target === "true";
      if (op === "같음") {
        if (typeof target === "boolean" || target === "true" || target === "false") { if (boolVar !== boolTarget) return false; }
        else if (varVal !== target && strVar !== String(target)) return false;
      }
      if (op === "같지 않음") {
        if (typeof target === "boolean" || target === "true" || target === "false") { if (boolVar === boolTarget) return false; }
        else if (varVal === target || strVar === String(target)) return false;
      }
      if (op === "유효함" && !boolVar) return false;
      if (op === "유효하지 않음" && boolVar) return false;
      if (op === "포함") { if (strVar.indexOf(String(target)) === -1) return false; }
      if (op === "포함하지 않음") { if (strVar.indexOf(String(target)) !== -1) return false; }
      if (op === "다음으로 시작") { if (!strVar.startsWith(String(target))) return false; }
      if (op === "다음으로 시작하지 않음") { if (strVar.startsWith(String(target))) return false; }
      if (op === "다음으로 끝남") { if (!strVar.endsWith(String(target))) return false; }
      if (op === "다음으로 끝나지 않음") { if (strVar.endsWith(String(target))) return false; }
      if (op === "정규 표현식과 일치") {
        try { if (!new RegExp(target).test(strVar)) return false; } catch (_) { return false; }
      }
      if (op === "정규 표현식과 일치 하지 않음") {
        try { if (new RegExp(target).test(strVar)) return false; } catch (_) { return true; }
      }
      if (op === "미만") { if (!(!isNaN(numVar) && !isNaN(numTarget) && numVar < numTarget)) return false; }
      if (op === "이하") { if (!(!isNaN(numVar) && !isNaN(numTarget) && numVar <= numTarget)) return false; }
      if (op === "초과") { if (!(!isNaN(numVar) && !isNaN(numTarget) && numVar > numTarget)) return false; }
      if (op === "이상") { if (!(!isNaN(numVar) && !isNaN(numTarget) && numVar >= numTarget)) return false; }
    }
    return true;
  }

  function elementMatchesSelector(el, selectorStr) {
    if (!el || !selectorStr) return true;
    try {
      if (el.closest(selectorStr)) return true;
    } catch (_) {}
    const parts = selectorStr.split(",").map((s) => s.trim()).filter(Boolean);
    for (let i = 0; i < parts.length; i++) {
      try {
        if (el.matches(parts[i]) || el.closest(parts[i])) return true;
      } catch (_) {}
    }
    return false;
  }

  function sanitizeForSend(obj) {
    if (obj === null || obj === undefined) return obj;
    if (typeof obj === "function") return undefined;
    if (typeof window !== "undefined" && typeof Node !== "undefined" && obj instanceof Node) return "[Node]";
    if (typeof obj !== "object") return obj;
    if (Array.isArray(obj)) return obj.map(sanitizeForSend).filter((v) => v !== undefined);
    const out = {};
    for (const k of Object.keys(obj)) {
      try {
        const v = sanitizeForSend(obj[k]);
        if (v !== undefined) out[k] = v;
      } catch (_) {}
    }
    return out;
  }

  function produceEvent(payload) {
    const raw = typeof payload === "string" ? payload : JSON.stringify(sanitizeForSend(payload));
    function doSend() {
      if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        const ok = navigator.sendBeacon(COLLECT_URL, raw);
        return Promise.resolve(ok);
      }
      return fetch(COLLECT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: raw,
        keepalive: true
      }).then((r) => r.ok);
    }
    doSend()
      .then((ok) => {
        if (ok === false && typeof setTimeout !== "undefined") setTimeout(() => doSend().catch(() => {}), 500);
      })
      .catch((e) => {
        console.warn("[TRACKER] produce failed, retry...", e);
        if (typeof setTimeout !== "undefined") setTimeout(() => doSend().catch(() => {}), 500);
      });
    try {
      console.log("NTMOBJ ", JSON.parse(raw));
    } catch (_) {}
  }

  /** 수집 전송용 페이로드: 필수 필드 + 변수 중 전송 대상만 (설정용 대형 배열/함수 제외) */
  function buildCollectPayload(base, varValues, extra) {
    const loc = typeof location !== "undefined" ? location : { href: "" };
    const out = {
      page_url: loc.href || "",
      ts: Date.now(),
      event_trigger: base.event_trigger || lastFiredTriggerCode,
      ...base
    };
    if (varValues && typeof varValues === "object") {
      Object.keys(varValues).forEach((k) => {
        if (COLLECT_EXCLUDE_VARS.has(k)) return;
        const v = varValues[k];
        if (typeof v === "function") return;
        if (typeof window !== "undefined" && typeof Node !== "undefined" && v instanceof Node) return;
        out[k] = v;
      });
    }
    if (extra && typeof extra === "object") {
      Object.keys(extra).forEach((k) => {
        const v = extra[k];
        if (v !== undefined && typeof v !== "function") out[k] = v;
      });
    }
    return out;
  }

  function sendToCollect(payload, eventTrigger) {
    const loc = typeof location !== "undefined" ? location : { href: "" };
    const base = {
      ...payload,
      page_url: loc.href || "",
      ts: Date.now(),
      event_trigger: eventTrigger || lastFiredTriggerCode
    };
    if (base.referer_url === undefined && payload.referrer !== undefined) base.referer_url = payload.referrer;
    produceEvent(base);
  }

  function resolveEventName(triggerCode, triggerObj) {
    const ev = triggerObj.event || triggerObj.event_type || "";
    if (ev === "element_click" || ev === "click") return "click";
    if (ev === "dom_ready" || ev === "DOMContentLoaded") return "";
    if (ev === "custom") {
      if (triggerObj.event_config && triggerObj.event_config.event_name)
        return triggerObj.event_config.event_name;
      const full = triggersFull.find((t) => t.trigger_code === triggerCode);
      if (full && full.event_config && full.event_config.event_name) return full.event_config.event_name;
      const fallback = {
        "Scroll Event": "scroll",
        "Swipe Event": "swipe",
        "Popup Event": "popup",
        "pv_detail(Custom)": "pvDetail",
        "pv(Custom)": "pv",
        "Scroll Impression Event": "Scroll_Impression",
        "Banner Impression Event": "impression",
        "enter key press": "enter",
        "click touchend": "click_touch"
      };
      return fallback[triggerCode] || "";
    }
    return ev;
  }

  function shouldRunTag(tag, triggerCode, varValues) {
    const trigger = triggers[triggerCode];
    if (!trigger) return false;
    if (trigger.conditions && trigger.conditions.length > 0 && !evaluateTriggerConditions(trigger.conditions, varValues))
      return false;
    const runConds = tag.run_conditions || [];
    if (runConds.length > 0 && !runConds.some((c) => c.trigger_code === triggerCode)) return false;
    if ((tag.except_conditions || []).some((c) => c.trigger_code === triggerCode)) return false;
    return true;
  }

  const createSend = (triggerCodeForAsync) => (payload) => {
    const merged = { ...payload };
    Object.assign(merged, getMergedVariableValues(merged, currentClickElement));
    sendToCollect(merged, triggerCodeForAsync);
  };

  const tagHandlers = tags.map((tag) => {
    const tagType = tag.tag_type || "script";
    if (tagType === "nlogger") {
      return {
        tag,
        handler: function (e, triggerCode, mergedValues) {
          const payload = { tag_code: tag.tag_code };
          (tag.parameters || []).forEach(({ key, value }) => {
            if (key != null && key !== "" && mergedValues[value] !== undefined) payload[key] = mergedValues[value];
          });
          sendToCollect({ ...payload, page_url: (typeof location !== "undefined" && location.href) || "", ts: Date.now() }, triggerCode);
        },
        isNlogger: true
      };
    }
    try {
      const funcJs = tag.func_js || "function trackerFunc(send){ return function(){}; }";
      const hasTrackerFunc = /function\s+trackerFunc\s*\(\s*send\s*\)/.test(funcJs);
      const factory = new Function("send", `${funcJs}; return ${hasTrackerFunc ? "trackerFunc(send)" : "typeof func === 'function' ? func : function(){}"};`);
      const handler = hasTrackerFunc ? factory(createSend(null)) : (typeof factory() === "function" ? factory() : function () {});
      return { tag, handler, isNlogger: false };
    } catch (e) {
      console.error("[TRACKER ERROR]", tag.tag_code, e);
      return { tag, handler: null, isNlogger: false };
    }
  });

  const tagsByTrigger = {};
  tagHandlers.forEach(({ tag, handler, isNlogger }) => {
    if (!handler) return;
    const triggerCodes = (tag.triggers && tag.triggers.length) ? tag.triggers : (tag.trigger_code ? [tag.trigger_code] : []);
    triggerCodes.forEach((tc) => {
      if (!tc) return;
      if (!tagsByTrigger[tc]) tagsByTrigger[tc] = [];
      tagsByTrigger[tc].push({ tag, handler, isNlogger });
    });
  });

  function runDOMReady() {
    lastFiredTriggerCode = "DOM_READY";
    scrollThresholdsSent.length = 0;
    const list = tagsByTrigger["DOM_READY"] || [];
    const varValues = getMergedVariableValues({}, null);
    list.forEach(({ tag, handler, isNlogger }) => {
      if (tag.tag_code === "PV_DETAIL") return;
      if (!shouldRunTag(tag, "DOM_READY", varValues)) return;
      try {
        if (isNlogger) handler(null, "DOM_READY", varValues);
        else handler();
      } catch (e) {
        console.error("[TRACKER]", tag.tag_code, e);
      }
    });
    const pageviewPayload = buildCollectPayload(
      {
        channel: varValues.channel || "Musinsa",
        page_id: varValues.page_id || "",
        act_type: "pageview",
        referer_url: varValues.referrer || ""
      },
      varValues
    );
    sendToCollect(pageviewPayload, "DOM_READY");
  }

  function sendPageviewForUrl() {
    const loc = typeof location !== "undefined" ? location : { href: "", pathname: "" };
    const url = loc.href || "";
    const varValues = getMergedVariableValues({}, null);
    const payload = buildCollectPayload(
      {
        channel: varValues.channel || "Musinsa",
        page_id: varValues.page_id || "",
        act_type: "pageview",
        referer_url: varValues.referrer || ""
      },
      varValues
    );
    sendToCollect(payload, "URL 주소 변경");
  }

  let lastPageviewUrl = "";
  function maybeSendPageviewOnUrlChange() {
    const url = typeof location !== "undefined" ? location.href : "";
    if (url && url !== lastPageviewUrl) {
      lastPageviewUrl = url;
      scrollThresholdsSent.length = 0;
      sendPageviewForUrl();
    }
  }

  let domReadyFired = false;
  function runDOMReadyOnce() {
    if (domReadyFired) return;
    domReadyFired = true;
    runDOMReady();
    lastPageviewUrl = typeof location !== "undefined" ? location.href : "";
  }
  const doc = typeof document !== "undefined" ? document : null;
  if (doc) {
    if (doc.readyState === "complete" || doc.readyState === "interactive") {
      runDOMReadyOnce();
    } else {
      doc.addEventListener("DOMContentLoaded", runDOMReadyOnce);
    }
    if (typeof window !== "undefined") {
      window.addEventListener("load", runDOMReadyOnce);
      window.addEventListener("popstate", function () { setTimeout(maybeSendPageviewOnUrlChange, 0); });
      var _pushState = history.pushState;
      var _replaceState = history.replaceState;
      if (typeof _pushState === "function") {
        history.pushState = function () { _pushState.apply(this, arguments); maybeSendPageviewOnUrlChange(); };
      }
      if (typeof _replaceState === "function") {
        history.replaceState = function () { _replaceState.apply(this, arguments); maybeSendPageviewOnUrlChange(); };
      }
    }
  } else {
    runDOMReadyOnce();
  }

  const clickTriggerCodes = Object.keys(triggers).filter((tc) => {
    if (tc === "DOM_READY") return false;
    const t = triggers[tc];
    if (!t) return false;
    const ev = t.event || t.event_type;
    return ev === "click" || ev === "element_click";
  });

  if (clickTriggerCodes.length > 0 && typeof document !== "undefined") {
    document.addEventListener(
      "click",
      function (e) {
        const clickEl =
          e && e.target
            ? e.target.closest("a, button, li, div, span, svg, [role=button]") || e.target
            : null;
        currentClickElement = clickEl;
        lastFiredTriggerCode = clickTriggerCodes[0];
        let varValues = {};
        let matchedTriggerCode = null;
        try {
          varValues = getMergedVariableValues({}, clickEl);
          for (let i = 0; i < clickTriggerCodes.length; i++) {
            const tc = clickTriggerCodes[i];
            const t = triggers[tc];
            const sel = (t && t.css_selector) || "";
            const matches = !sel || !e.target || elementMatchesSelector(e.target, sel);
            if (!matches) continue;
            if (t.conditions && t.conditions.length > 0 && !evaluateTriggerConditions(t.conditions, varValues)) continue;
            matchedTriggerCode = tc;
            break;
          }
          const triggerCode = matchedTriggerCode || clickTriggerCodes[0];
          lastFiredTriggerCode = triggerCode;
          const payload = buildCollectPayload(
            {
              channel: varValues.channel || "Musinsa",
              page_id: varValues.page_id || "",
              act_type: "click",
              referer_url: varValues.referrer || "",
              click_text: varValues.clickText,
              class_name: varValues.clickClass,
              click_type: varValues.click_type,
              order: varValues.order != null ? varValues.order : varValues.el_order
            },
            varValues
          );
          sendToCollect(payload, triggerCode);
        } catch (err) {
          console.error("[TRACKER] click error", err);
          sendToCollect(
            {
              act_type: "click",
              page_url: typeof location !== "undefined" ? location.href : "",
              ts: Date.now()
            },
            clickTriggerCodes[0]
          );
        } finally {
          currentClickElement = null;
        }
      },
      true
    );
  }

  const customEventMap = {};
  Object.keys(triggers).forEach((tc) => {
    if (tc === "DOM_READY") return;
    const t = triggers[tc];
    if (!t) return;
    const ev = resolveEventName(tc, t);
    if (!ev || ev === "click") return;
    if (!customEventMap[ev]) customEventMap[ev] = [];
    customEventMap[ev].push(tc);
  });
  // settings/latest.json 의도: 모든 커스텀 이벤트가 수집되도록 ensure(설정에 없어도 리스너 등록)
  const CUSTOM_EVENT_FALLBACK = {
    scroll: "Scroll Event",
    pv: "pv(Custom)",
    pvDetail: "pv_detail(Custom)",
    swipe: "Swipe Event",
    popup: "Popup Event",
    impression: "Banner Impression Event",
    Scroll_Impression: "Scroll Impression Event",
    enter: "enter key press",
    click_touch: "click touchend",
    url_change: "URL 주소 변경"
  };
  Object.keys(CUSTOM_EVENT_FALLBACK).forEach((ev) => {
    if (!customEventMap[ev]) customEventMap[ev] = [CUSTOM_EVENT_FALLBACK[ev]];
  });

  if (typeof window !== "undefined") {
    const SCROLL_THRESHOLDS = [25, 50, 75, 99];
    let scrollTicking = false;
    function getWindowScrollRate() {
      const de = document.documentElement;
      const body = document.body;
      const scrollTop = typeof window.scrollY === "number" ? window.scrollY : (de && de.scrollTop) || (body && body.scrollTop) || 0;
      const winH = window.innerHeight || 0;
      const scrollHeight = Math.max((de && de.scrollHeight) || 0, (body && body.scrollHeight) || 0);
      const totalH = Math.max(scrollHeight - winH, 1);
      return Math.min(99, Math.round((scrollTop / totalH) * 100));
    }
    function sendNativeScroll() {
      const rate = getWindowScrollRate();
      SCROLL_THRESHOLDS.forEach(function (thresh) {
        if (rate >= thresh && scrollThresholdsSent.indexOf(thresh) === -1) {
          scrollThresholdsSent.push(thresh);
          const varValues = getMergedVariableValues({}, null);
          const payload = buildCollectPayload(
            {
              channel: varValues.channel || "Musinsa",
              page_id: varValues.page_id || "",
              act_type: "scroll",
              referer_url: varValues.referrer || "",
              scroll_rate: thresh
            },
            varValues,
            { scroll_rate: thresh }
          );
          sendToCollect(payload, "Scroll Event");
        }
      });
      scrollTicking = false;
    }
    window.addEventListener(
      "scroll",
      function () {
        if (!scrollTicking) {
          scrollTicking = true;
          if (typeof requestAnimationFrame !== "undefined") {
            requestAnimationFrame(sendNativeScroll);
          } else {
            setTimeout(sendNativeScroll, 100);
          }
        }
      },
      { passive: true }
    );
  }

  Object.keys(customEventMap).forEach((eventName) => {
    const triggerCodes = customEventMap[eventName];
    if (triggerCodes.length === 0 || typeof document === "undefined") return;
    document.addEventListener(
      eventName,
      function (e) {
        const customData = e.detail != null ? e.detail : null;
        currentCustomData = customData;
        currentClickElement =
          e && e.target
            ? e.target.closest("a, button, li, div, span, svg, [role=button]") || e.target
            : null;
        lastFiredTriggerCode = triggerCodes[0];
        let varValues = {};
        let matchedTriggerCode = null;
        try {
          varValues = getMergedVariableValues(customData ? { customData } : {}, currentClickElement);
          for (let i = 0; i < triggerCodes.length; i++) {
            const tc = triggerCodes[i];
            const t = triggers[tc];
            if (!t) continue;
            const sel = (t.css_selector) || "";
            const matches = !sel || !e.target || elementMatchesSelector(e.target, sel);
            if (!matches) continue;
            if (t.conditions && t.conditions.length > 0 && !evaluateTriggerConditions(t.conditions, varValues)) continue;
            matchedTriggerCode = tc;
            break;
          }
          const hasConditions = triggerCodes.some((tc) => (triggers[tc] && triggers[tc].conditions && triggers[tc].conditions.length));
          if (matchedTriggerCode == null && hasConditions) return;
          const triggerCode = matchedTriggerCode || triggerCodes[0];
          lastFiredTriggerCode = triggerCode;
          const actType =
            (customData && customData.act_type) ||
            (eventName === "scroll" ? "scroll" : eventName === "pv" || eventName === "pvDetail" || eventName === "url_change" ? "pageview" : eventName === "impression" || eventName === "Scroll_Impression" ? "impression" : eventName === "enter" || eventName === "click_touch" ? "click" : "custom");
          const payload = buildCollectPayload(
            {
              channel: varValues.channel || "Musinsa",
              page_id: varValues.page_id || "",
              act_type: actType,
              referer_url: varValues.referrer || ""
            },
            varValues,
            customData && typeof customData === "object" ? customData : undefined
          );
          sendToCollect(payload, triggerCode);
          if (eventName === "scroll" && customData && typeof customData.scroll_rate === "number") {
            lastScrollRateSent = customData.scroll_rate;
            if (scrollThresholdsSent.indexOf(customData.scroll_rate) === -1) scrollThresholdsSent.push(customData.scroll_rate);
          }
          if (eventName === "pv" || eventName === "pvDetail") scrollThresholdsSent.length = 0;
        } catch (err) {
          console.error("[TRACKER] custom event error", eventName, err);
          sendToCollect(
            {
              act_type: (e.detail && e.detail.act_type) || (eventName === "scroll" ? "scroll" : "custom"),
              page_url: typeof location !== "undefined" ? location.href : "",
              ts: Date.now(),
              ...(e.detail && typeof e.detail === "object" ? e.detail : {})
            },
            triggerCodes[0]
          );
        } finally {
          currentClickElement = null;
          currentCustomData = null;
        }
      },
      true
    );
  });

  if (SETTINGS_REFRESH_MS > 0 && typeof setInterval !== "undefined") {
    setInterval(async () => {
      try {
        const r = await fetch(SETTINGS_API);
        const next = await r.json();
        if (next.version != null && next.version !== settings.version) {
          console.log("[TRACKER SDK] new settings version", next.version, "reloading");
          if (typeof location !== "undefined") location.reload();
        }
      } catch (_) {}
    }, SETTINGS_REFRESH_MS);
  }

  console.log("[TRACKER SDK] ready", settings.version);
})();
