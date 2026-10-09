import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../static/js/site-metrics.js", import.meta.url), "utf8");
const analyticsTemplate = readFileSync(new URL("../templates/_analytics.html", import.meta.url), "utf8");
const pageLocationFunction = analyticsTemplate.match(
  /function analyticsPageLocation\(\) \{[\s\S]*?^  \}/m,
)[0];

function privacySafePageLocation(href) {
  const context = { window: { location: new URL(href) }, URL, Set };
  vm.runInNewContext(`${pageLocationFunction}\nresult = analyticsPageLocation();`, context);
  return context.result;
}

function harness({ enabled = true, tagPresent = true, throwTag = false } = {}) {
  const sent = [];
  const listeners = {};
  let timer;
  let clock = 100000;
  const document = {
    documentElement: { dataset: {} },
    visibilityState: "visible",
    hasFocus: () => true,
    addEventListener() {},
  };
  const window = {
    fimoAnalytics: {
      enabled,
      measurementId: "G-TEST123",
      context: { page_type: "player_compare" },
      pageLocation: "https://fcbook.info/player_compare?utm_source=naver&utm_medium=organic",
    },
    location: { origin: "https://fcbook.info", pathname: "/player_compare", search: "?secret=excluded" },
    addEventListener(name, fn) { listeners[name] = fn; },
    setInterval(fn) { timer = fn; },
    fetch() { assert.fail("no server collection or fallback is allowed"); },
  };
  for (const key of ["localStorage", "sessionStorage", "crypto"]) {
    Object.defineProperty(window, key, { get() { assert.fail(`unexpected ${key} access`); } });
  }
  const tag = (...args) => {
    if (throwTag) throw new Error("tag blocked");
    assert.equal(args[0], "event", "identity lookup/config must not create another collection path");
    sent.push(JSON.parse(JSON.stringify(args)));
  };
  if (tagPresent) window.gtag = tag;
  vm.runInNewContext(source, { window, document, Date: { now: () => clock } });
  return {
    window, document, sent, tag,
    track: (...args) => window.fimoAnalytics.track(...args),
    interact() { listeners.keydown({ type: "keydown" }); },
    tick(seconds) { for (let i = 0; i < seconds; i++) { clock += 1000; timer(); } },
  };
}

test("custom events use the page_view destination through Google tag only", () => {
  const h = harness();
  assert.equal(h.track("comparison_complete", { result_count: 2 }), true);
  assert.deepEqual(h.sent, [["event", "comparison_complete", {
    page_type: "player_compare", measurement_version: "2026-09-06-2", result_count: 2,
    send_to: "G-TEST123",
    page_location: "https://fcbook.info/player_compare?utm_source=naver&utm_medium=organic",
  }]]);
  assert.equal(h.document.documentElement.dataset.siteMetricsTransport, "google-tag");
});

test("page location keeps acquisition parameters but drops private query data", () => {
  assert.equal(
    privacySafePageLocation(
      "https://fcbook.info/times?query=player-name&utm_source=naver&utm_medium=organic&gclid=abc123&token=private#results",
    ),
    "https://fcbook.info/times?utm_source=naver&utm_medium=organic&gclid=abc123",
  );
});

test("callers cannot override the destination or the tag's user/session identity", () => {
  const h = harness();
  h.track("player_select", { send_to: "G-WRONG", client_id: "legacy-uuid", session_id: 123,
    user_id: "another-user", page_location: "https://example.com/?secret=1" });
  const params = h.sent[0][2];
  assert.equal(params.send_to, "G-TEST123");
  assert.equal(params.page_location, "https://fcbook.info/player_compare?utm_source=naver&utm_medium=organic");
  for (const key of ["client_id", "session_id", "user_id"]) assert.equal(key in params, false);
});

test("queued events keep order while the async Google tag is loading", () => {
  const h = harness();
  h.track("site_interaction"); h.track("player_select"); h.track("comparison_complete");
  assert.deepEqual(h.sent.map(event => event[1]), ["site_interaction", "player_select", "comparison_complete"]);
});

test("missing or throwing tag never falls back to Measurement Protocol", () => {
  for (const options of [{ tagPresent: false }, { throwTag: true }]) {
    const h = harness(options);
    assert.equal(h.track("site_interaction"), false);
    assert.equal(h.sent.length, 0);
    assert.equal(h.document.documentElement.dataset.siteMetricsEventCount, undefined);
  }
});

test("once-only events are queued once and failed attempts do not consume the key", () => {
  const h = harness({ tagPresent: false });
  assert.equal(h.track("qualified_engagement", {}, { onceKey: "active10" }), false);
  h.window.gtag = h.tag;
  assert.equal(h.track("qualified_engagement", {}, { onceKey: "active10" }), true);
  assert.equal(h.track("qualified_engagement", {}, { onceKey: "active10" }), false);
  assert.equal(h.sent.length, 1);
});

test("invalid event names and unsafe parameters are excluded", () => {
  const h = harness();
  assert.equal(h.track("Bad event"), false);
  h.track("player_select", { "unsafe-key": "ignored", empty: "", long_value: "x".repeat(150) });
  assert.equal(h.sent.length, 1);
  assert.equal(h.sent[0][2]["unsafe-key"], undefined);
  assert.equal(h.sent[0][2].empty, undefined);
  assert.equal(h.sent[0][2].long_value.length, 100);
});

test("disabled analytics never installs or queues tracking", () => {
  const h = harness({ enabled: false });
  assert.equal(h.window.fimoAnalytics.track, undefined);
  assert.equal(h.sent.length, 0);
});

test("engagement counts visible active use and stops while idle or hidden", () => {
  const h = harness();
  h.tick(60); assert.equal(h.sent.length, 0);
  h.interact(); h.tick(10);
  assert.equal(h.sent.filter(e => e[1] === "qualified_engagement").length, 1);
  h.document.visibilityState = "hidden"; h.tick(20);
  assert.equal(h.sent.filter(e => e[1] === "active_time_milestone").length, 0);
  h.document.visibilityState = "visible"; h.tick(60);
  assert.equal(h.sent.length, 2);
  h.interact(); h.tick(20);
  assert.equal(h.sent.filter(e => e[1] === "site_interaction").length, 1);
  assert.equal(h.sent.filter(e => e[1] === "active_time_milestone").length, 1);
});
