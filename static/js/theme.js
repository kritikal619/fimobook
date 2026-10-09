(function () {
  "use strict";

  var storageKey = "fimobook-theme";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function savedPreference() {
    try {
      var value = localStorage.getItem(storageKey);
      return value === "dark" || value === "light" ? value : "system";
    } catch (error) {
      return "system";
    }
  }

  function resolvedTheme(preference) {
    if (preference === "dark" || preference === "light") return preference;
    return media && media.matches ? "dark" : "light";
  }

  function updateThemeColor(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "theme-color";
      document.head.appendChild(meta);
    }
    meta.content = theme === "dark" ? "#0b1220" : "#132531";
  }

  function applyTheme(theme) {
    var next = theme === "dark" ? "dark" : "light";
    root.dataset.theme = next;
    root.style.colorScheme = next;
    updateThemeColor(next);
    window.dispatchEvent(new CustomEvent("fimobook:themechange", { detail: { theme: next } }));
  }

  function updateControls(preference) {
    document.querySelectorAll("[data-theme-select]").forEach(function (select) {
      select.value = preference;
    });
  }

  function applyPreference(preference, persist) {
    var nextPreference = preference === "dark" || preference === "light" ? preference : "system";
    if (persist) {
      try {
        if (nextPreference === "system") localStorage.removeItem(storageKey);
        else localStorage.setItem(storageKey, nextPreference);
      } catch (error) {
        // Storage can be unavailable in private or restricted browser modes.
      }
    }
    applyTheme(resolvedTheme(nextPreference));
    updateControls(nextPreference);
  }

  function bindControls() {
    document.querySelectorAll("[data-theme-select]").forEach(function (select) {
      if (select.dataset.themeBound === "true") return;
      select.dataset.themeBound = "true";
      select.addEventListener("change", function () {
        applyPreference(select.value, true);
      });
    });
  }

  function init() {
    var preference = savedPreference();
    bindControls();
    applyPreference(preference, false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  if (media) {
    var followSystem = function (event) {
      if (savedPreference() === "system") applyTheme(event.matches ? "dark" : "light");
    };
    if (media.addEventListener) media.addEventListener("change", followSystem);
    else if (media.addListener) media.addListener(followSystem);
  }

  window.addEventListener("storage", function (event) {
    if (event.key === storageKey) applyPreference(savedPreference(), false);
  });
})();
