(function () {
  "use strict";

  const analytics = window.fimoAnalytics || {};
  if (!analytics.enabled || typeof window.gtag !== "function") return;

  const baseContext = analytics.context || {};
  const sentOnce = new Set();
  const MAX_STRING_LENGTH = 100;
  const SAFE_EVENT_NAME = /^[a-z][a-z0-9_]{0,39}$/;

  function cleanValue(value) {
    if (value === undefined || value === null || value === "") return undefined;
    if (typeof value === "boolean" || typeof value === "number") return value;
    if (Array.isArray(value)) return value.slice(0, 10).map(cleanValue).filter(v => v !== undefined);
    return String(value).trim().slice(0, MAX_STRING_LENGTH) || undefined;
  }

  function cleanParams(params) {
    const cleaned = {};
    Object.entries(params || {}).forEach(([key, value]) => {
      if (!/^[a-z][a-z0-9_]{0,39}$/.test(key)) return;
      const safeValue = cleanValue(value);
      if (safeValue !== undefined) cleaned[key] = safeValue;
    });
    return cleaned;
  }

  function track(eventName, params, options) {
    if (!SAFE_EVENT_NAME.test(eventName)) return false;
    const onceKey = options && options.onceKey;
    if (onceKey && sentOnce.has(onceKey)) return false;
    if (onceKey) sentOnce.add(onceKey);

    window.gtag("event", eventName, cleanParams({
      page_type: baseContext.page_type,
      content_group: baseContext.content_group,
      login_state: baseContext.login_state,
      measurement_version: analytics.version,
      ...params,
    }));
    return true;
  }

  analytics.track = track;
  analytics.version = "2026-08-26";
  window.fimoAnalytics = analytics;

  function datasetParams(element) {
    const params = {};
    Object.entries(element.dataset || {}).forEach(([key, value]) => {
      if (!key.startsWith("gaParam")) return;
      const suffix = key.slice("gaParam".length);
      const paramName = suffix.replace(/^[A-Z]/, c => c.toLowerCase()).replace(/[A-Z]/g, c => `_${c.toLowerCase()}`);
      if (paramName) params[paramName] = value;
    });
    return params;
  }

  function countMeaningfulFormFields(form) {
    const data = new FormData(form);
    let count = 0;
    for (const [, rawValue] of data.entries()) {
      const value = String(rawValue || "").trim();
      if (value && value !== "0" && value !== "999") count += 1;
    }
    return count;
  }

  document.addEventListener("submit", event => {
    const form = event.target.closest("form[data-ga-event]");
    if (!form) return;
    const params = datasetParams(form);
    params.form_field_count = countMeaningfulFormFields(form);

    const searchSelector = form.dataset.gaSearchInput;
    if (searchSelector) {
      const input = form.querySelector(searchSelector) || document.querySelector(searchSelector);
      if (input) params.search_term = input.value;
    }
    track(form.dataset.gaEvent, params);
  }, true);

  document.addEventListener("click", event => {
    const target = event.target.closest("[data-ga-event]");
    if (!target || target.tagName === "FORM") return;
    track(target.dataset.gaEvent, datasetParams(target));
  }, true);

  document.addEventListener("fimobook:analytics", event => {
    const detail = event.detail || {};
    if (!detail.eventName) return;
    track(detail.eventName, detail.params || {}, detail.options || {});
  });

  // GA4's built-in engagement can include a focused tab left unattended.
  // These milestones count only visible, focused time after a real interaction,
  // and stop after 30 seconds without further input.
  let hasInteracted = false;
  let lastInteractionAt = 0;
  let activeSeconds = 0;
  const milestones = new Set([10, 30, 120, 300]);
  const markInteraction = () => {
    hasInteracted = true;
    lastInteractionAt = Date.now();
  };
  ["pointerdown", "keydown", "touchstart", "scroll"].forEach(eventName => {
    window.addEventListener(eventName, markInteraction, { passive: true, capture: true });
  });

  window.setInterval(() => {
    const isActivelyUsing = hasInteracted
      && document.visibilityState === "visible"
      && document.hasFocus()
      && Date.now() - lastInteractionAt <= 30000;
    if (!isActivelyUsing) return;
    activeSeconds += 1;
    if (!milestones.has(activeSeconds)) return;
    track(activeSeconds === 10 ? "qualified_engagement" : "active_time_milestone", {
      active_seconds: activeSeconds,
    }, { onceKey: `active_seconds_${activeSeconds}` });
  }, 1000);

})();
