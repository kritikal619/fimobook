(function () {
  "use strict";

  var priceElements = Array.from(document.querySelectorAll("[data-live-price-cid]"));
  if (!priceElements.length) return;

  var elementsByCid = new Map();
  priceElements.forEach(function (element) {
    var cid = String(element.dataset.livePriceCid || "").trim();
    if (!/^\d+$/.test(cid)) return;
    if (!elementsByCid.has(cid)) elementsByCid.set(cid, []);
    elementsByCid.get(cid).push(element);
  });

  function formatPrice(value) {
    var numeric = Number(value);
    return Number.isFinite(numeric) && numeric > 0
      ? Math.trunc(numeric).toLocaleString("ko-KR")
      : "-";
  }

  function applyPrice(cid, payload) {
    var elements = elementsByCid.get(String(cid)) || [];
    elements.forEach(function (element) {
      var hasEnhance = element.hasAttribute("data-live-price-enhance");
      var level = element.dataset.livePriceEnhance || "0";
      var price = payload && Number(hasEnhance
        ? (payload.priceByEnhance || {})[level]
        : payload.price);
      var unit = element.dataset.livePriceUnit || "";
      element.textContent = formatPrice(price) + (unit ? " " + unit : "");
      element.dataset.livePriceValue = Number.isFinite(price) && price > 0 ? String(price) : "";
      element.dataset.livePriceSource = payload && payload.source === "live" ? "live" : "local";
      element.setAttribute("aria-busy", "false");

      var card = element.closest("[data-live-price-card]");
      if (card) card.dataset.livePriceValue = element.dataset.livePriceValue;
    });
  }

  // Small chunks keep each upstream lookup short; the server fetches names in parallel.
  var CHUNK_SIZE = 12;
  var MAX_IN_FLIGHT = 3;
  var RETRY_DELAYS = [2500, 6000];

  function fetchPriceChunk(cids) {
    cids.forEach(function (cid) {
      (elementsByCid.get(cid) || []).forEach(function (element) {
        element.setAttribute("aria-busy", "true");
      });
    });

    return fetch("/api/player_prices?cids=" + encodeURIComponent(cids.join(",")), {
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("live price request failed");
        return response.json();
      })
      .then(function (body) {
        var prices = body && body.prices ? body.prices : {};
        var pending = [];
        cids.forEach(function (cid) {
          if (!Object.prototype.hasOwnProperty.call(prices, cid)) return;
          applyPrice(cid, prices[cid]);
          if (prices[cid] && prices[cid].pending) pending.push(cid);
        });
        return pending;
      })
      .catch(function () {
        cids.forEach(function (cid) {
          (elementsByCid.get(cid) || []).forEach(function (element) {
            element.setAttribute("aria-busy", "false");
            element.dataset.livePriceSource = "local";
          });
        });
        return cids;
      });
  }

  function runChunks(cids) {
    var chunks = [];
    for (var index = 0; index < cids.length; index += CHUNK_SIZE) {
      chunks.push(cids.slice(index, index + CHUNK_SIZE));
    }
    var pending = [];
    var next = 0;
    function worker() {
      if (next >= chunks.length) return Promise.resolve();
      var chunk = chunks[next++];
      return fetchPriceChunk(chunk).then(function (missed) {
        pending = pending.concat(missed || []);
        return worker();
      });
    }
    var workers = [];
    for (var i = 0; i < Math.min(MAX_IN_FLIGHT, chunks.length); i++) workers.push(worker());
    return Promise.all(workers).then(function () { return pending; });
  }

  function fetchPrices(cids, attempt) {
    attempt = attempt || 0;
    return runChunks(Array.from(new Set(cids))).then(function (pending) {
      if (!pending.length || attempt >= RETRY_DELAYS.length) return;
      return new Promise(function (resolve) {
        window.setTimeout(resolve, RETRY_DELAYS[attempt]);
      }).then(function () { return fetchPrices(pending, attempt + 1); });
    });
  }

  function reorderByLivePrice(container) {
    var direction = container.dataset.livePriceSort;
    if (direction !== "price_asc" && direction !== "price_desc") return;
    var cards = Array.from(container.querySelectorAll("[data-live-price-card]"));
    cards.sort(function (left, right) {
      var leftPrice = Number(left.dataset.livePriceValue) || 0;
      var rightPrice = Number(right.dataset.livePriceValue) || 0;
      if (!leftPrice && rightPrice) return 1;
      if (leftPrice && !rightPrice) return -1;
      return direction === "price_asc" ? leftPrice - rightPrice : rightPrice - leftPrice;
    });
    cards.forEach(function (card) { container.appendChild(card); });
  }

  var sortContainer = document.querySelector("[data-live-price-sort]");
  if (sortContainer && /^price_(asc|desc)$/.test(sortContainer.dataset.livePriceSort || "")) {
    fetchPrices(Array.from(elementsByCid.keys())).then(function () {
      reorderByLivePrice(sortContainer);
    });
    return;
  }

  if (!("IntersectionObserver" in window)) {
    fetchPrices(Array.from(elementsByCid.keys()));
    return;
  }

  var queuedCids = new Set();
  var queueTimer = null;
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var cid = String(entry.target.dataset.livePriceCid || "").trim();
      observer.unobserve(entry.target);
      if (cid) queuedCids.add(cid);
    });
    if (!queuedCids.size || queueTimer) return;
    queueTimer = window.setTimeout(function () {
      var cids = Array.from(queuedCids);
      queuedCids.clear();
      queueTimer = null;
      fetchPrices(cids);
    }, 60);
  }, { rootMargin: "300px 0px" });

  priceElements.forEach(function (element) { observer.observe(element); });
})();
