(function () {
  "use strict";
  var panel = document.querySelector("[data-evolution-materials]");
  if (!panel) return;
  var dataNode = panel.querySelector("[data-evolution-data]");
  if (!dataNode) return;
  var payload;
  try { payload = JSON.parse(dataNode.textContent); } catch (_) { return; }
  var selectedOvr = payload.targets[0].ovr;
  var seriesSelect = panel.querySelector("[data-evolution-series]");
  var targets = new Map(payload.targets.map(function (target) { return [target.ovr, target]; }));
  var loaded = new Set([selectedOvr]);
  var unit = panel.dataset.priceUnit || "MP";
  var number = new Intl.NumberFormat("ko-KR");
  var dateFormat = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false
  });
  var requestId = 0;

  function get(name) { return panel.querySelector("[data-evolution-" + name + "]"); }
  function dateLabel(value) {
    if (!value) return "";
    // Old daily snapshots represent a calendar date, not an intraday time.
    if (!value.includes("T")) return value;
    var moment = new Date(value);
    return Number.isNaN(moment.getTime()) ? value : dateFormat.format(moment);
  }
  function priceLabel(value) { return value == null ? "—" : number.format(value); }
  function comboLabel(item) { return item ? item.ovr + " OVR · " + item.level + "진" : "—"; }
  function changeLabel(value) { return value == null ? "—" : (value > 0 ? "+" : "") + value.toFixed(1) + "%"; }
  function colorChange(element, value) {
    element.classList.toggle("is-up", value > 0);
    element.classList.toggle("is-down", value < 0);
  }
  function cell(row, tag, value) {
    var element = document.createElement(tag);
    element.textContent = value;
    row.appendChild(element);
    return element;
  }
  function renderSummary(target) {
    get("detail-title").textContent = target.ovr + " 진재 조합";
    var overview = panel.querySelector('[data-evolution-entry="' + target.ovr + '"]');
    if (overview) {
      overview.querySelector("[data-overview-combo]").textContent = target.best ? target.best.ovr + " · " + target.best.level + "진" : "—";
      overview.querySelector("[data-overview-price]").textContent = target.best ? priceLabel(target.best.price) : "산정 불가";
    }
    var rows = get("rows");
    rows.replaceChildren();
    var maximum = Math.max.apply(null, target.combinations.map(function (item) { return item.price || 0; }));
    target.combinations.forEach(function (item) {
      var row = document.createElement("li");
      row.className = "evolution-comparison" + (item.best ? " evolution-best-row" : "");
      var heading = cell(row, "strong", item.ovr + " ");
      heading.className = "evolution-combo-name";
      cell(heading, "span", "· " + item.level + "진");
      var track = cell(row, "div", "");
      track.className = "evolution-bar-track";
      track.setAttribute("aria-hidden", "true");
      var bar = cell(track, "span", "");
      bar.className = "evolution-bar";
      bar.style.width = (maximum && item.price ? item.price / maximum * 100 : 0) + "%";
      var price = cell(row, "div", "");
      price.className = "evolution-combo-price";
      cell(price, "strong", item.price == null ? (item.count ? "표본 부족" : "가격 없음") : priceLabel(item.price));
      var difference = cell(price, "span", item.best ? "최저가" : (target.best && item.price != null ? "+" + priceLabel(item.price - target.best.price) : ""));
      difference.className = "evolution-difference";
      if (!item.best && item.price != null && target.best) difference.setAttribute("aria-label", "최저가보다 " + priceLabel(item.price - target.best.price) + " " + unit + " 비쌈");
      rows.appendChild(row);
    });
    var selectedSeries = seriesSelect.value;
    seriesSelect.replaceChildren(new Option("가장 싼 조합", "best"));
    target.combinations.forEach(function (item) {
      seriesSelect.add(new Option(comboLabel(item), item.ovr + ":" + item.level));
    });
    if (Array.from(seriesSelect.options).some(function (option) { return option.value === selectedSeries; })) {
      seriesSelect.value = selectedSeries;
    }
    get("updated").textContent = payload.source === "snapshot"
      ? "업데이트 " + dateLabel(payload.updated_at) + " (한국시간)"
      : "현재 선수 데이터 기준";
    if (payload.error) get("status").textContent = "가격 이력을 불러오지 못했습니다.";
  }
  function svgElement(tag, attributes, text) {
    var element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attributes || {}).forEach(function (key) { element.setAttribute(key, attributes[key]); });
    if (text != null) element.textContent = text;
    return element;
  }
  function renderChart(target) {
    var series = seriesSelect.value;
    seriesSelect.closest("label").hidden = target.history.length < 2;
    var points = target.history.map(function (snapshot) {
      var item = series === "best" ? snapshot.best : snapshot.combinations.find(function (combo) {
        return combo.ovr + ":" + combo.level === series;
      });
      return {date: snapshot.date, price: item ? item.price : null, item: item};
    });
    get("history-details").hidden = points.length === 0;
    var historyRows = get("history-rows");
    historyRows.replaceChildren();
    points.slice().reverse().forEach(function (point) {
      var row = document.createElement("tr");
      cell(row, "td", dateLabel(point.date));
      cell(row, "td", comboLabel(point.item));
      cell(row, "td", point.price == null ? "산정 불가" : priceLabel(point.price));
      historyRows.appendChild(row);
    });
    var valid = points.filter(function (point) { return point.price != null; });
    var drawable = valid.length >= 2;
    get("chart").hidden = !drawable;
    get("empty").hidden = drawable;
    get("empty-message").textContent = points.length >= 2 && !drawable
      ? "이 조합의 가격 이력이 부족합니다"
      : "가격 추세 준비 중";
    if (!drawable) return;
    var svg = get("svg");
    svg.replaceChildren(svgElement("title", {id: "evolution-chart-title"}, target.ovr + " 대상 · " + seriesSelect.selectedOptions[0].text + " 가격 추세"));
    var min = Math.min.apply(null, valid.map(function (point) { return point.price; }));
    var max = Math.max.apply(null, valid.map(function (point) { return point.price; }));
    var padding = Math.max((max - min) * 0.15, max * 0.02, 1);
    min = Math.max(0, min - padding); max += padding;
    var first = new Date(points[0].date).getTime();
    var last = new Date(points[points.length - 1].date).getTime();
    var x = function (point, index) { return 78 + (last > first ? (new Date(point.date).getTime() - first) / (last - first) : index / (points.length - 1)) * 582; };
    var y = function (price) { return 18 + (max - price) / (max - min) * 166; };
    for (var i = 0; i < 3; i++) {
      var axisValue = min + (max - min) * i / 2;
      var axisY = y(axisValue);
      svg.appendChild(svgElement("line", {x1: 78, y1: axisY, x2: 660, y2: axisY, class: "evolution-grid"}));
      var compact = axisValue >= 100000000 ? (axisValue / 100000000).toFixed(2) + "억" : (axisValue / 10000).toFixed(1) + "만";
      svg.appendChild(svgElement("text", {x: 70, y: axisY + 4, "text-anchor": "end"}, compact));
    }
    var path = "";
    var connected = false;
    points.forEach(function (point, index) {
      if (point.price == null) { connected = false; return; }
      path += (connected ? " L " : " M ") + x(point, index) + " " + y(point.price);
      connected = true;
    });
    svg.appendChild(svgElement("path", {d: path, class: "evolution-line"}));
    points.forEach(function (point, index) {
      if (point.price == null) return;
      var dot = svgElement("circle", {cx: x(point, index), cy: y(point.price), r: 3});
      dot.appendChild(svgElement("title", {}, dateLabel(point.date) + " · " + comboLabel(point.item) + " · " + priceLabel(point.price) + " " + unit));
      svg.appendChild(dot);
    });
    get("range").replaceChildren();
    [points[0], points[points.length - 1]].forEach(function (point) {
      var label = document.createElement("span"); label.textContent = dateLabel(point.date); get("range").appendChild(label);
    });
  }
  async function selectTarget() {
    var id = ++requestId;
    var ovr = selectedOvr;
    var target = targets.get(ovr);
    if (!target) return;
    seriesSelect.value = "best";
    get("status").textContent = "";
    renderSummary(target);
    renderChart(target);
    if (payload.source !== "snapshot" || loaded.has(ovr)) return;
    get("status").textContent = "불러오는 중…";
    try {
      var response = await fetch(panel.dataset.endpoint + "?ovr=" + ovr, {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error("history unavailable");
      var result = await response.json();
      if (id !== requestId) return;
      targets.set(ovr, result.target);
      loaded.add(ovr);
      payload.source = result.source; payload.updated_at = result.updated_at; payload.error = result.error;
      get("status").textContent = "";
      renderSummary(result.target); renderChart(result.target);
    } catch (_) {
      if (id === requestId) get("status").textContent = "가격 이력을 불러오지 못했습니다.";
    }
  }
  var openedButton = null;
  panel.querySelectorAll("[data-evolution-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      var closing = button === openedButton;
      if (openedButton) {
        openedButton.setAttribute("aria-expanded", "false");
        openedButton.querySelector("[data-evolution-open-label]").textContent = "자세히";
      }
      get("detail").hidden = closing;
      if (closing) { openedButton = null; ++requestId; return; }
      openedButton = button;
      selectedOvr = Number(button.dataset.evolutionOpen);
      button.setAttribute("aria-expanded", "true");
      button.querySelector("[data-evolution-open-label]").textContent = "접기";
      button.closest("[data-evolution-entry]").appendChild(get("detail"));
      selectTarget();
    });
  });
  var more = get("more");
  if (more) more.addEventListener("click", function () {
    var expanded = more.getAttribute("aria-expanded") !== "true";
    more.setAttribute("aria-expanded", String(expanded));
    more.textContent = expanded ? "접기 ⌃" : "다른 OVR 보기 ⌄";
    panel.querySelectorAll("[data-evolution-extra]").forEach(function (entry) { entry.hidden = !expanded; });
    if (!expanded && openedButton && openedButton.closest("[data-evolution-extra]")) {
      openedButton.setAttribute("aria-expanded", "false");
      openedButton.querySelector("[data-evolution-open-label]").textContent = "자세히";
      get("detail").hidden = true; openedButton = null; ++requestId;
    }
  });
  seriesSelect.addEventListener("change", function () { renderChart(targets.get(selectedOvr)); });
  renderSummary(targets.get(selectedOvr));
  renderChart(targets.get(selectedOvr));
})();
