(function () {
  "use strict";

  var sections = document.querySelectorAll("[data-price-history]");
  if (!sections.length) return;

  var formatNumber = new Intl.NumberFormat("ko-KR");

  function datePart(value) {
    return String(value || "").slice(0, 10);
  }

  function parseDate(value) {
    var text = String(value || "");
    if (text.includes("T")) return new Date(text);
    var parts = datePart(text).split("-").map(Number);
    return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
  }

  function shortDate(value) {
    var parts = datePart(value).split("-");
    return parts.length === 3 ? Number(parts[1]) + "/" + Number(parts[2]) : value;
  }

  function longDate(value) {
    var text = String(value || "");
    var parts = datePart(text).split("-");
    if (parts.length !== 3) return text;
    var label = parts[0] + "년 " + Number(parts[1]) + "월 " + Number(parts[2]) + "일";
    var timeMatch = text.match(/T(\d{2}):(\d{2})/);
    if (!timeMatch) return label;
    var hour = Number(timeMatch[1]);
    var minute = Number(timeMatch[2]);
    var period = hour < 12 ? "오전" : "오후";
    var displayHour = hour % 12 || 12;
    return label + " " + period + " " + displayHour + "시" + (minute ? " " + minute + "분" : "");
  }

  function init(section) {
    var payloadNode = section.querySelector("[data-price-history-data]");
    var history = [];
    try {
      history = JSON.parse(payloadNode ? payloadNode.textContent : "[]");
    } catch (error) {
      history = [];
    }

    var rangeButtons = Array.from(section.querySelectorAll("[data-price-range]"));
    var enhanceSelect = section.querySelector("[data-price-history-enhance]");
    var svg = section.querySelector("[data-price-history-chart]");
    var chartContent = section.querySelector("[data-price-history-chart-content]");
    var emptyState = section.querySelector("[data-price-history-empty]");
    var tooltip = section.querySelector("[data-price-history-tooltip]");
    var tooltipDate = section.querySelector("[data-price-history-tooltip-date]");
    var tooltipPrice = section.querySelector("[data-price-history-tooltip-price]");
    var selectedDate = section.querySelector("[data-price-history-selected-date]");
    var selectedPrice = section.querySelector("[data-price-history-selected-price]");
    var change = section.querySelector("[data-price-history-change]");
    var priceUnit = section.dataset.priceUnit || "MP";
    var rangeDays = 7;
    var points = [];
    var selectedIndex = -1;
    var pinned = false;
    var width = 720;
    var height = 300;
    var left = 24;
    var right = 24;
    var top = 34;
    var bottom = 42;
    var firstPointTime = 0;
    var lastPointTime = 0;

    function filteredPoints() {
      var enhanceLevel = Number(enhanceSelect ? enhanceSelect.value : 0);
      var latestValue = history.length
        ? (history[history.length - 1].timestamp || history[history.length - 1].date)
        : null;
      var latestDay = latestValue ? parseDate(datePart(latestValue)) : null;
      var cutoff = latestDay ? new Date(latestDay.getTime() - (rangeDays - 1) * 86400000) : null;
      return history.reduce(function (result, row) {
        var price = Array.isArray(row.prices) ? Number(row.prices[enhanceLevel]) : NaN;
        var timestamp = row.timestamp || row.date;
        var day = parseDate(datePart(timestamp));
        if (cutoff && day >= cutoff) {
          result.push({
            timestamp: timestamp,
            time: parseDate(timestamp).getTime(),
            price: Number.isFinite(price) && price > 0 ? price : null
          });
        }
        return result;
      }, []);
    }

    function xFor(index) {
      if (points.length <= 1 || firstPointTime === lastPointTime) return width / 2;
      return left + (points[index].time - firstPointTime) * (width - left - right) / (lastPointTime - firstPointTime);
    }

    function yFor(price, minValue, maxValue) {
      if (minValue === maxValue) return top + (height - top - bottom) / 2;
      return top + (maxValue - price) * (height - top - bottom) / (maxValue - minValue);
    }

    function clientToChartPoint(clientX, clientY) {
      var matrix = svg && svg.getScreenCTM ? svg.getScreenCTM() : null;
      if (matrix && svg.createSVGPoint) {
        try {
          var svgPoint = svg.createSVGPoint();
          svgPoint.x = clientX;
          svgPoint.y = clientY;
          return svgPoint.matrixTransform(matrix.inverse());
        } catch (error) {
          // Older embedded browsers can expose an incomplete SVG matrix API.
        }
      }

      var rect = svg.getBoundingClientRect();
      return {
        x: rect.width ? (clientX - rect.left) / rect.width * width : 0,
        y: rect.height ? (clientY - rect.top) / rect.height * height : 0
      };
    }

    function chartPointToTooltipPixels(x, y) {
      var parent = tooltip && tooltip.parentElement;
      var matrix = svg && svg.getScreenCTM ? svg.getScreenCTM() : null;
      if (parent && matrix && svg.createSVGPoint) {
        try {
          var svgPoint = svg.createSVGPoint();
          svgPoint.x = x;
          svgPoint.y = y;
          var screenPoint = svgPoint.matrixTransform(matrix);
          var parentRect = parent.getBoundingClientRect();
          return {
            x: screenPoint.x - parentRect.left,
            y: screenPoint.y - parentRect.top,
            width: parentRect.width
          };
        } catch (error) {
          // Fall through to the proportional fallback below.
        }
      }

      var fallbackWidth = parent ? parent.clientWidth : 0;
      return {
        x: x / width * fallbackWidth,
        y: y / height * (parent ? parent.clientHeight : 0),
        width: fallbackWidth
      };
    }

    function updateSelected(index, showTooltip) {
      if (!points.length) return;
      selectedIndex = Math.max(0, Math.min(index, points.length - 1));
      var point = points[selectedIndex];
      var markerLine = svg.querySelector("[data-price-marker-line]");
      var marker = svg.querySelector("[data-price-marker]");
      var pointNode = svg.querySelector('[data-price-point="' + selectedIndex + '"]');
      if (pointNode) {
        var x = Number(pointNode.getAttribute("cx"));
        var y = Number(pointNode.getAttribute("cy"));
        markerLine.setAttribute("x1", x);
        markerLine.setAttribute("x2", x);
        markerLine.removeAttribute("hidden");
        marker.setAttribute("cx", x);
        marker.setAttribute("cy", y);
        marker.removeAttribute("hidden");

        if (showTooltip && tooltip) {
          tooltip.hidden = false;
          var tooltipPoint = chartPointToTooltipPixels(x, y);
          var chartPixelWidth = tooltipPoint.width;
          var tooltipHalfWidth = tooltip.offsetWidth / 2 + 8;
          var tooltipPixelX = Math.max(
            tooltipHalfWidth,
            Math.min(chartPixelWidth - tooltipHalfWidth, tooltipPoint.x)
          );
          tooltip.style.left = tooltipPixelX + "px";
          tooltip.style.top = tooltipPoint.y + "px";
          tooltip.classList.toggle("is-flipped", tooltipPoint.y < tooltip.offsetHeight + 18);
          tooltipDate.textContent = longDate(point.timestamp);
          tooltipPrice.textContent = point.price === null
            ? "가격 정보 없음"
            : formatNumber.format(point.price) + " " + priceUnit;
        }
      }

      if (selectedDate) selectedDate.textContent = longDate(point.timestamp);
      if (selectedPrice) {
        selectedPrice.textContent = point.price === null
          ? "가격 정보 없음"
          : formatNumber.format(point.price) + " " + priceUnit;
      }
    }

    function render() {
      points = filteredPoints();
      pinned = false;
      selectedIndex = points.length - 1;
      if (tooltip) tooltip.hidden = true;
      if (emptyState) emptyState.hidden = points.length > 0;
      if (svg) svg.hidden = points.length === 0;

      if (!points.length) {
        chartContent.innerHTML = "";
        if (selectedDate) selectedDate.textContent = "선택한 기간";
        if (selectedPrice) selectedPrice.textContent = "가격 정보 없음";
        if (change) {
          change.textContent = "-";
          change.className = "price-history-change";
        }
        return;
      }

      var actualPrices = points
        .map(function (point) { return point.price; })
        .filter(function (price) { return price !== null; });
      var rawMin = actualPrices.length ? Math.min.apply(null, actualPrices) : 0;
      var rawMax = actualPrices.length ? Math.max.apply(null, actualPrices) : 1;
      var minValue = rawMin;
      var maxValue = rawMax;
      firstPointTime = points[0].time;
      lastPointTime = points[points.length - 1].time;
      var coordinates = points.map(function (point, index) {
        return [
          xFor(index),
          point.price === null ? height - bottom : yFor(point.price, minValue, maxValue)
        ];
      });
      var linePath = coordinates.map(function (pair, index) {
        return (index ? "L" : "M") + pair[0].toFixed(2) + " " + pair[1].toFixed(2);
      }).join(" ");
      var grid = [0, 1, 2, 3, 4].map(function (step) {
        var y = top + step * (height - top - bottom) / 4;
        return '<line class="price-history-grid-line" x1="' + left + '" y1="' + y + '" x2="' + (width - right) + '" y2="' + y + '"></line>';
      }).join("");
      var tickIndexes = Array.from(new Set([0, Math.round((points.length - 1) / 4), Math.round((points.length - 1) / 2), Math.round((points.length - 1) * 3 / 4), points.length - 1]));
      var ticks = tickIndexes.map(function (index) {
        var anchor = index === 0 ? "start" : (index === points.length - 1 ? "end" : "middle");
        return '<text class="price-history-axis-label" x="' + xFor(index) + '" y="286" text-anchor="' + anchor + '">' + shortDate(points[index].timestamp) + '</text>';
      }).join("");
      var pointNodes = coordinates.map(function (pair, index) {
        return '<circle data-price-point="' + index + '" cx="' + pair[0] + '" cy="' + pair[1] + '" r="8" fill="transparent"></circle>';
      }).join("");

      chartContent.innerHTML =
        grid +
        '<text class="price-history-value-label" x="' + (width - right) + '" y="25" text-anchor="end">' + (actualPrices.length ? formatNumber.format(rawMax) : '-') + '</text>' +
        '<text class="price-history-value-label" x="' + left + '" y="' + (height - bottom - 8) + '">' + (actualPrices.length ? formatNumber.format(rawMin) : '-') + '</text>' +
        '<path class="price-history-line" d="' + linePath + '"></path>' +
        '<line class="price-history-marker-line" data-price-marker-line y1="' + top + '" y2="' + (height - bottom) + '" hidden></line>' +
        '<circle class="price-history-marker" data-price-marker r="5" hidden></circle>' +
        pointNodes + ticks;

      var firstPrice = actualPrices.length ? actualPrices[0] : null;
      var lastPrice = actualPrices.length ? actualPrices[actualPrices.length - 1] : null;
      var difference = firstPrice !== null && lastPrice !== null ? lastPrice - firstPrice : 0;
      var percent = firstPrice ? difference / firstPrice * 100 : 0;
      if (change) {
        var sign = difference > 0 ? "+" : "";
        change.textContent = actualPrices.length > 1
          ? sign + percent.toFixed(1) + "% (기간 대비)"
          : (actualPrices.length ? "첫 수집일" : "-");
        change.className = "price-history-change" + (difference > 0 ? " is-up" : (difference < 0 ? " is-down" : ""));
      }
      updateSelected(points.length - 1, false);
    }

    function nearestIndex(event) {
      var viewX = clientToChartPoint(event.clientX, event.clientY).x;
      if (points.length <= 1) return 0;
      return points.reduce(function (nearest, point, index) {
        return Math.abs(xFor(index) - viewX) < Math.abs(xFor(nearest) - viewX) ? index : nearest;
      }, 0);
    }

    rangeButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        rangeDays = Number(button.dataset.priceRange || 7);
        rangeButtons.forEach(function (item) {
          var active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-pressed", active ? "true" : "false");
        });
        render();
      });
    });

    if (enhanceSelect) enhanceSelect.addEventListener("change", render);
    if (svg) {
      svg.addEventListener("pointermove", function (event) {
        if (!points.length || pinned) return;
        updateSelected(nearestIndex(event), true);
      });
      svg.addEventListener("pointerdown", function (event) {
        if (!points.length) return;
        pinned = true;
        updateSelected(nearestIndex(event), true);
      });
      svg.addEventListener("pointerleave", function () {
        if (!pinned && tooltip) tooltip.hidden = true;
      });
      svg.addEventListener("keydown", function (event) {
        if (!points.length || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
        event.preventDefault();
        pinned = true;
        updateSelected(selectedIndex + (event.key === "ArrowLeft" ? -1 : 1), true);
      });
    }

    document.addEventListener("pointerdown", function (event) {
      if (!pinned || !svg || svg.contains(event.target)) return;
      pinned = false;
      if (tooltip) tooltip.hidden = true;
      var markerLine = svg.querySelector("[data-price-marker-line]");
      var marker = svg.querySelector("[data-price-marker]");
      if (markerLine) markerLine.setAttribute("hidden", "");
      if (marker) marker.setAttribute("hidden", "");
    });

    render();
  }

  sections.forEach(init);
})();
