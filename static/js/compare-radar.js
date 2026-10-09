/* Read final stat values from the existing comparison table calculation. */
window.FimoCompareRadar = (() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const fieldOrder = ['ACC','SPD','POS','FIN','SHO','LSA','VOL','PEN','VIS','CRO','FRK','SPA','LPA','CUR','AGI','BAL','REA','BAC','DRI','AWR','HEA','STT','SLT','MRK','JMP','STR','AGG'];
  let fromZero = false, selected = null, activeGroup = '전체';
  let compactLayout = window.matchMedia('(max-width:760px)').matches, latest = null;
  const groupStyles = { '속도':'speed', '슈팅':'shoot', '패스':'pass', '드리블':'dribble', '수비':'defend', '피지컬':'physical', '골키퍼':'speed', '기본 능력':'physical' };
  function render(root, context) {
    latest = { root, context };
    const compact = window.matchMedia('(max-width:760px)').matches;
    compactLayout = compact;
    const { players, groups, order, value, numericCodes, isGk } = context;
    root.hidden = !players.every(Boolean);
    if (root.hidden) return;
    const entries = order.filter(group => group !== '기본').flatMap(group => Object.entries(groups[group])
      .filter(([code]) => numericCodes.has(code))
      .map(([code, label]) => ({ code, label, group, values: [value(0, code), value(1, code)] })));
    const axes = entries.filter(axis => axis.values.every(number => typeof number === 'number' && Number.isFinite(number)));
    if (!isGk) axes.sort((a, b) => order.indexOf(a.group) - order.indexOf(b.group) || fieldOrder.indexOf(a.code) - fieldOrder.indexOf(b.code));
    const activeGroups = order.filter(group => axes.some(axis => axis.group === group));
    if (!activeGroups.includes(activeGroup)) activeGroup = '전체';
    const format = number => Number(number.toFixed(1)).toString();
    const allValues = axes.flatMap(axis => axis.values);
    const lower = fromZero || !allValues.length ? 0 : Math.max(0, Math.floor((Math.min(...allValues) - 10) / 10) * 10);
    const upper = Math.max(lower + 30, Math.ceil((Math.max(0, ...allValues) + 10) / 10) * 10);
    root.innerHTML = `<div class="radar-header"><span>전체 능력치 <small>${lower}–${upper}</small></span><label><input type="checkbox" ${fromZero ? 'checked' : ''}>0부터 보기</label></div>
      <div class="radar-group-controls" role="group" aria-label="레이더 능력치 그룹">${['전체', ...activeGroups].map(group => `<button type="button" data-radar-group="${escape(group)}" class="radar-group-${groupStyles[group] || 'all'}" aria-pressed="${activeGroup === group}">${escape(group)}</button>`).join('')}</div>
      <div class="radar-body"><div class="radar-chart"><div class="radar-canvas"></div></div><div class="radar-advantages"></div></div>
      <div class="radar-legend">${players.map((player, side) => `<span class="radar-player radar-player-${side}"><i aria-hidden="true"></i><span><b>${escape(player.playerKor)}</b><small>${escape(player.className || '')}</small></span></span>`).join('')}</div>
      <div class="radar-stat-picker" role="group" aria-label="세부 능력치 선택"></div><div class="radar-inspect" aria-live="polite"></div>`;
    const chart = root.querySelector('.radar-chart');
    ['.radar-legend', '.radar-stat-picker', '.radar-inspect'].forEach(selector => chart.append(root.querySelector(selector)));
    root.querySelector('input').addEventListener('change', event => { fromZero = event.target.checked; render(root, context); root.querySelector('input').focus({ preventScroll: true }); });
    if (axes.length < 3) {
      root.querySelector('.radar-canvas').innerHTML = '<p>공통 능력치가 부족합니다.</p>';
      return;
    }
    const centerX = 300, centerY = 260, radius = 185;
    const point = (index, fraction) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / axes.length;
      return [centerX + Math.cos(angle) * radius * fraction, centerY + Math.sin(angle) * radius * fraction];
    };
    const coords = pair => pair.map(number => number.toFixed(2)).join(',');
    const rings = [.25, .5, .75, 1];
    let svg = `<svg viewBox="0 0 600 520" role="group" aria-label="전체 세부 능력치 비교, 모든 축 ${lower}부터 ${upper}"><title>${escape(players[0].playerKor)} · ${escape(players[1].playerKor)} 전체 능력치</title>`;
    rings.forEach(tick => {
      svg += `<polygon class="radar-grid" points="${axes.map((_, index) => coords(point(index, tick))).join(' ')}"/>`;
    });
    activeGroups.forEach(group => {
      const start = axes.findIndex(axis => axis.group === group) - .42;
      const end = axes.findLastIndex(axis => axis.group === group) + .42;
      const p1 = point(start, 1.055), p2 = point(end, 1.055);
      const large = end - start > axes.length / 2 ? 1 : 0;
      svg += `<path class="radar-group-arc radar-group-${groupStyles[group]}" data-sector="${escape(group)}" d="M ${coords(p1)} A ${radius * 1.055} ${radius * 1.055} 0 ${large} 1 ${coords(p2)}"/>`;
      const boundary = point(start - .08, 1);
      svg += `<line class="radar-group-boundary" x1="300" y1="260" x2="${boundary[0]}" y2="${boundary[1]}"/>`;
    });
    axes.forEach((axis, index) => { const p = point(index, 1); svg += `<line class="radar-spoke" x1="300" y1="260" x2="${p[0]}" y2="${p[1]}"/>`; });
    [0, 1].forEach(side => { svg += `<polygon class="radar-area radar-series-${side}" points="${axes.map((axis, index) => coords(point(index, (axis.values[side] - lower) / (upper - lower)))).join(' ')}"/>`; });
    const gapMax = Math.max(1, ...axes.map(axis => Math.abs(axis.values[0] - axis.values[1])));
    axes.forEach((axis, index) => {
      const labelPoint = point(index, 1.18), offset = labelPoint[0] - centerX;
      const anchor = Math.abs(offset) < 90 ? 'middle' : offset > 0 ? 'start' : 'end';
      const description = `${axis.label}: ${players[0].playerKor} ${format(axis.values[0])}, ${players[1].playerKor} ${format(axis.values[1])}`;
      svg += `<g class="radar-axis" data-axis-group="${escape(axis.group)}" tabindex="0" role="button" data-axis="${index}" aria-label="${escape(description)}"><title>${escape(description)}</title><text class="radar-axis-label radar-group-${groupStyles[axis.group]}" x="${labelPoint[0]}" y="${labelPoint[1]}" text-anchor="${anchor}" dominant-baseline="middle">${escape(axis.label.replaceAll(' ', ''))}</text>`;
      [0, 1].forEach(side => { const p = point(index, (axis.values[side] - lower) / (upper - lower)); svg += `<circle class="radar-dot radar-series-${side}" cx="${p[0]}" cy="${p[1]}" r="2.5"/>`; });
      svg += '</g>';
    });
    rings.forEach(tick => { svg += `<text class="radar-tick" x="307" y="${centerY - radius * tick - 4}">${format(lower + (upper - lower) * tick)}</text>`; });
    svg += `<text class="radar-tick" x="307" y="274">${lower}</text></svg>`;
    root.querySelector('.radar-canvas').innerHTML = svg;
    root.querySelector('.radar-advantages').innerHTML = [0, 1].map(side => {
      const higher = axes.filter(axis => axis.values[side] > axis.values[1 - side])
        .sort((a, b) => (b.values[side] - b.values[1 - side]) - (a.values[side] - a.values[1 - side]));
      return `<div class="radar-advantage radar-advantage-${side}"><div class="radar-advantage-heading"><b>${escape(players[side].playerKor)}</b><small>${higher.length}개 스탯 우위</small></div>${higher.slice(0, 4).map(axis => {
        const gap = axis.values[side] - axis.values[1 - side];
        return `<button type="button" class="radar-gap-row" data-stat="${escape(axis.code)}"><span>${escape(axis.label)}</span><b>+${format(gap)}</b><span class="radar-gap-track" aria-hidden="true"><i style="width:${gap / gapMax * 100}%"></i></span><small>${format(axis.values[side])} : ${format(axis.values[1 - side])}</small></button>`;
      }).join('') || '<p class="radar-no-advantage">더 높은 스탯 없음</p>'}</div>`;
    }).join('');
    function inspect(axis) {
      selected = axis.code;
      if (activeGroup !== '전체' && activeGroup !== axis.group) { activeGroup = axis.group; highlightGroup(); }
      const diff = axis.values[0] - axis.values[1];
      root.querySelector('.radar-inspect').innerHTML = `<div class="radar-inspect-stat"><small>${escape(axis.group)}</small><b>${escape(axis.label)}</b></div><div class="radar-inspect-player radar-value-0"><span>${escape(players[0].playerKor)}</span><b>${format(axis.values[0])}</b></div><div class="radar-inspect-player radar-value-1"><span>${escape(players[1].playerKor)}</span><b>${format(axis.values[1])}</b></div><small class="radar-inspect-diff">${diff === 0 ? '동일' : `${escape(players[diff > 0 ? 0 : 1].playerKor)} +${format(Math.abs(diff))}`}</small>`;
      root.querySelectorAll('[data-axis]').forEach(element => element.classList.toggle('is-selected', axes[Number(element.dataset.axis)].code === axis.code));
      updatePicker(axis.group);
    }
    function updatePicker(group) {
      const picker = root.querySelector('.radar-stat-picker');
      const shownGroup = activeGroup === '전체' ? group : activeGroup;
      picker.innerHTML = axes.filter(axis => axis.group === shownGroup).map(axis => `<button type="button" data-pick-stat="${escape(axis.code)}" aria-pressed="${axis.code === selected}">${escape(axis.label)}</button>`).join('');
      picker.querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
        inspect(axes.find(axis => axis.code === button.dataset.pickStat));
        picker.querySelector(`[data-pick-stat="${button.dataset.pickStat}"]`)?.focus({ preventScroll:true });
      }));
    }
    root.querySelectorAll('[data-axis]').forEach(element => {
      const show = () => inspect(axes[Number(element.dataset.axis)]);
      element.addEventListener('click', show);
      element.addEventListener('focus', show);
      element.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); show(); } });
    });
    function highlightGroup() {
      root.querySelectorAll('[data-axis-group]').forEach(element => element.classList.toggle('is-muted', activeGroup !== '전체' && element.dataset.axisGroup !== activeGroup));
      root.querySelectorAll('[data-sector]').forEach(element => element.classList.toggle('is-muted', activeGroup !== '전체' && element.dataset.sector !== activeGroup));
      root.querySelectorAll('[data-radar-group]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.radarGroup === activeGroup)));
    }
    root.querySelectorAll('[data-radar-group]').forEach(button => button.addEventListener('click', () => {
      activeGroup = button.dataset.radarGroup;
      highlightGroup();
      if (activeGroup !== '전체') inspect(axes.find(axis => axis.group === activeGroup));
    }));
    highlightGroup();
    root.querySelectorAll('[data-stat]').forEach(button => button.addEventListener('click', () => inspect(axes.find(axis => axis.code === button.dataset.stat))));
    inspect(axes.find(axis => axis.code === selected) || axes[0]);
    if (axes.length < entries.length) root.insertAdjacentHTML('beforeend', '<small class="radar-missing">미제공 항목 제외</small>');
  }
  window.matchMedia('(max-width:760px)').addEventListener('change', event => {
    if (latest && event.matches !== compactLayout) render(latest.root, latest.context);
  });
  return { render };
})();
