/* One square card canvas for every surface. Existing growth/selection controls stay intact. */
window.FimoCardArt = (() => {
  'use strict';
  const cache = new Map(), pending = new Map(), configuredStyles = new WeakMap();
  let scheduled = false;
  const selector = '[data-fimo-player-card], [data-fimo-card-cid]';
  const safeColor = value => /^#[0-9a-f]{3,8}$/i.test(value || '') ? value : '#fff';
  const safeImage = value => typeof value === 'string' &&
    (value.startsWith('/static/') || value.startsWith('/media/player/') || value.startsWith('https://fco.vod.nexoncdn.co.kr/')) ? value : '';
  const offsets = ['utoty26_star_static', 'a5th_anniversary25h_star_static',
    'b_centurions24_star_static', 'b_rulebreaker_star_static', 'twg_bestvalue_static_c'];

  function node(tag, className, text) {
    const result = document.createElement(tag); result.className = className;
    if (text != null) result.textContent = text;
    return result;
  }
  function image(src, className, alt = '') {
    const result = node('img', className); result.src = safeImage(src); result.alt = alt;
    result.draggable = false; result.decoding = 'async';
    result.addEventListener('error', () => { result.remove(); }, {once: true});
    return result;
  }
  function clear(element) {
    element.classList.remove('fimo-card-art');
    element.querySelector('.fimo-card-symbols')?.remove();
    element.querySelector('.fimo-card-playstyles')?.remove();
    configuredStyles.delete(element);
    element.querySelectorAll('[data-fimo-generated]').forEach(child => child.remove());
    delete element.dataset.fimoCardCid; delete element.dataset.fimoLayout;
  }
  function render(element, player, options = {}) {
    if (!element || !player) { if (element) clear(element); return; }
    const meta = player.cardArt || player;
    element.classList.add('fimo-card-art');
    const cid = String(player.cid || meta.cid || '');
    if (element.dataset.fimoCardCid !== cid) element.dataset.fimoCardCid = cid;
    element.dataset.fimoLayout = meta.layout || (offsets.some(tag => (meta.cardProgram || '').includes(tag)) ? 'offset' : '');
    const background = element.querySelector(':scope > .card-background, :scope > .card-bg, :scope > .player-card-overlay');
    const face = element.querySelector(':scope > .player-image, :scope > .card-face, :scope > .player-card-player-img');
    if (background) background.classList.add('fimo-card-bg');
    if (face) face.classList.add('fimo-card-face');
    const layers = [...element.querySelectorAll(':scope > img:not(.card-enhance):not(.fimo-card-evolution)')];
    if (layers.length === 2 && !background && !face && !player.card) {
      layers[0].classList.add('fimo-card-bg'); layers[1].classList.add('fimo-card-face');
    } else layers.forEach(layer => layer.classList.add(layer.classList.contains('card-background') ? 'fimo-card-bg' : 'fimo-card-face'));
    if (player.card && !background && !element.querySelector('.fimo-card-bg')) element.prepend(image(player.card, 'card-background fimo-card-bg'));
    if (player.face && !face && !element.querySelector('.fimo-card-face')) element.append(image(player.face, 'card-face fimo-card-face'));
    const fields = [
      ['rating', '.card-rating, .ovr, .meta-ovr, .other-rating, .card-ovr, .player-card-ovr', options.ovr ?? player.ovr ?? meta.ovr, 'ovr'],
      ['position', '.card-position, .pos-text, .meta-pos, .other-position, .card-pos, .ovr-position-top > .position, .player-card-pos, .player-card-position', player.position ?? meta.position, 'pos'],
      ['name', '.pack-card-name, .player-name-bottom, .meta-name, .other-name, .player-card-name', player.playerKor ?? meta.playerKor, 'name'],
    ];
    fields.forEach(([kind, selectors, value, color]) => {
      let field = element.querySelector(`.fimo-card-${kind}, ${selectors}`);
      if (!field) { field = node('span', `fimo-card-${kind}`, value); field.dataset.fimoGenerated = ''; element.append(field); }
      else { field.classList.add(`fimo-card-${kind}`); if (options.ovr != null && kind === 'rating') field.textContent = options.ovr; }
      const ink = safeColor(meta.colors?.[color]);
      field.style.setProperty('color', ink, 'important');
      const hex = ink.slice(1);
      const rgb = hex.length <= 4 ? hex.slice(0, 3).split('').map(c => parseInt(c + c, 16)) :
        [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
      field.dataset.fimoInk = (rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722) < 140 ? 'dark' : 'light';
    });
    let symbols = element.querySelector('.fimo-card-symbols');
    if (!symbols) { symbols = node('span', 'fimo-card-symbols'); element.append(symbols); }
    const signature = JSON.stringify([meta.flag, meta.leagueBadge, meta.club]);
    if (symbols.dataset.signature !== signature) {
      symbols.replaceChildren(); symbols.dataset.signature = signature;
      [['flag', 'nation'], ['leagueBadge', 'league'], ['club', 'team']].forEach(([key, label]) => {
        if (safeImage(meta[key])) symbols.append(image(meta[key], '', meta[label] || ''));
      });
      symbols.dataset.count = symbols.childElementCount;
    }
    if (options.enhance != null) {
      element.querySelector('.fimo-card-evolution')?.remove();
      if (options.enhance > 0) element.append(image(`/static/squad/evolution/${options.enhance}.png`, 'fimo-card-evolution', `${options.enhance}진화`));
    }
    if (options.playstyleSlots) configuredStyles.set(element, options.playstyleSlots);
    const slots = configuredStyles.get(element) ?? player.playstyleSlots ?? meta.playstyleSlots ?? [];
    let styles = element.querySelector('.fimo-card-playstyles');
    if (!styles && slots.length) { styles = node('span', 'fimo-card-playstyles'); styles.setAttribute('aria-label', '플레이스타일'); element.append(styles); }
    if (styles && styles.dataset.signature !== JSON.stringify(slots)) {
      styles.dataset.signature = JSON.stringify(slots);
      styles.replaceChildren(...slots.map(slot => {
        const icon = image(slot.isEmpty ? '/static/playstyles/PLAYSTYLE_EMPTY_SLOT.png' : slot.imageUrl, '', slot.name || '빈 플레이스타일 슬롯');
        icon.title = slot.name || '빈 플레이스타일 슬롯';
        return icon;
      }));
    }
  }
  async function flush() {
    scheduled = false;
    const entries = [...pending.entries()]; pending.clear();
    for (let start = 0; start < entries.length; start += 40) {
      const batch = entries.slice(start, start + 40);
      try {
        const response = await fetch(`/api/player_card_art?cids=${batch.map(([cid]) => cid).join(',')}`);
        if (!response.ok) continue;
        const payload = await response.json();
        batch.forEach(([cid, elements]) => {
          const meta = payload.cards?.[cid]; if (!meta) return;
          cache.set(cid, meta);
          elements.forEach(element => { if (element.isConnected && element.dataset.fimoCardCid === cid) render(element, meta, {ovr: element.dataset.fimoCardOvr}); });
        });
      } catch (_) { /* Existing card text remains usable if metadata is unavailable. */ }
    }
  }
  function hydrate(element) {
    if (element.dataset.fimoPlayerCard) {
      try { const player = JSON.parse(element.dataset.fimoPlayerCard); if (player.cid) cache.set(String(player.cid), player); render(element, player); } catch (_) { /* Ignore invalid markup. */ }
      return;
    }
    const cid = element.dataset.fimoCardCid;
    if (!/^\d+$/.test(cid || '')) return;
    if (cache.has(cid)) { render(element, cache.get(cid), {ovr: element.dataset.fimoCardOvr}); return; }
    if (!pending.has(cid)) pending.set(cid, new Set()); pending.get(cid).add(element);
    if (!scheduled) { scheduled = true; queueMicrotask(flush); }
  }
  function scan(root) {
    if (root.nodeType !== 1 && root.nodeType !== 9) return;
    if (root.matches?.(selector)) hydrate(root);
    root.querySelectorAll(selector).forEach(hydrate);
  }
  const observer = new MutationObserver(records => records.forEach(record => {
    if (record.type === 'attributes') hydrate(record.target);
    else record.addedNodes.forEach(scan);
  }));
  function start() {
    scan(document);
    observer.observe(document.body, {subtree:true, childList:true, attributes:true,
      attributeFilter:['data-fimo-player-card', 'data-fimo-card-cid', 'data-fimo-card-ovr']});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true}); else start();
  return {render, clear};
})();
