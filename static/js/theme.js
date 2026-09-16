(function () {
  "use strict";

  var storageKey = "fimobook-theme";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function currentTheme() {
    return root.dataset.theme === "dark" ? "dark" : "light";
  }

  function savedTheme() {
    try {
      var value = localStorage.getItem(storageKey);
      return value === "dark" || value === "light" ? value : null;
    } catch (error) {
      return null;
    }
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

  function updateButtons(theme) {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var dark = theme === "dark";
      var icon = button.querySelector("[data-theme-icon]");
      var label = button.querySelector("[data-theme-label]");
      button.setAttribute("aria-pressed", dark ? "true" : "false");
      button.setAttribute("aria-label", dark ? "라이트 모드로 전환" : "다크 모드로 전환");
      button.title = dark ? "라이트 모드" : "다크 모드";
      if (icon) {
        if (icon.tagName === "I") {
          icon.className = dark ? "bi bi-sun" : "bi bi-moon-stars";
        } else {
          icon.textContent = dark ? "☀" : "☾";
        }
        icon.setAttribute("data-theme-icon", "");
      }
      if (label) label.textContent = dark ? "라이트 모드" : "다크 모드";
    });
  }

  function applyTheme(theme, persist) {
    var next = theme === "dark" ? "dark" : "light";
    root.dataset.theme = next;
    root.style.colorScheme = next;
    if (persist) {
      try {
        localStorage.setItem(storageKey, next);
      } catch (error) {
        // Storage can be unavailable in private or restricted browser modes.
      }
    }
    updateThemeColor(next);
    updateButtons(next);
    window.dispatchEvent(new CustomEvent("fimobook:themechange", { detail: { theme: next } }));
  }

  function createFallbackToggle() {
    if (document.querySelector("[data-theme-toggle]")) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "theme-toggle theme-toggle--floating";
    button.setAttribute("data-theme-toggle", "");
    button.innerHTML = '<span data-theme-icon aria-hidden="true">☾</span><span class="theme-toggle__sr" data-theme-label>다크 모드</span>';
    document.body.appendChild(button);
  }

  function bindButtons() {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      if (button.dataset.themeBound === "true") return;
      button.dataset.themeBound = "true";
      button.addEventListener("click", function () {
        applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
      });
    });
  }

  function init() {
    createFallbackToggle();
    bindButtons();
    applyTheme(currentTheme(), false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  window.addEventListener("storage", function (event) {
    if (event.key === storageKey && (event.newValue === "dark" || event.newValue === "light")) {
      applyTheme(event.newValue, false);
    }
  });

  if (media) {
    var followSystem = function (event) {
      if (!savedTheme()) applyTheme(event.matches ? "dark" : "light", false);
    };
    if (media.addEventListener) media.addEventListener("change", followSystem);
    else if (media.addListener) media.addListener(followSystem);
  }
})();
