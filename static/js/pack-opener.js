(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const stage = $('opening-stage');
  const cinematic = $('cinematic-video') || $('tunnel-video'); // Cached pre-deployment HTML.
  const state = {catalog: null, selected: null, filter: 'all', categoryFilter: 'all', busy: false, result: null,
    run: 0, timers: new Set(), oddsPath: [], oddsPage: 1, oddsPages: 1, oddsRun: 0, sound: false,
    flowRewards: [], flowIndex: 0};
  const mobilePlayback = matchMedia('(max-width:740px)').matches || /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
  const syncEffects = () => { stage.dataset.effects = motionPreference.matches ? 'gentle' : 'full'; };
  syncEffects();
  if (motionPreference.addEventListener) motionPreference.addEventListener('change', syncEffects);
  else motionPreference.addListener?.(syncEffects);
  let particleFrame = 0, particleContext = null;
  const scoreboardStart = 7; // Encoded keyframe in cinematic-v1, shared by every season.
  stage.classList.toggle('mobile-playback', mobilePlayback);
  function releaseVideo(video) {
    video.pause();
  }
  const storageKey = 'fimobook.pack-opener.v1';
  const moonWon = 25000 / 500;
  // User-defined display scale: 500m MP / 50,000 KRW is displayed as 100,000x.
  const eventMultiplierScale = 10;
  const emptyTotals = () => ({opened:0, fv:0, mp:0, players:0, unknownFV:0, unknownPlayers:0,
    eventMP:0, eventPlayers:0, moonSpent:0, eventUnknownCost:0});
  const emptyHistory = () => ({opened:0, rewards:[], totals:emptyTotals(), priceTotalsVersion:1});
  let history = emptyHistory(), historyBackup = null, historyRenderPending = false;
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved && Number.isSafeInteger(saved.opened) && saved.opened >= 0 && Array.isArray(saved.rewards)) {
      history = {priceTotalsVersion:saved.priceTotalsVersion, totals: {...emptyTotals(), ...(saved.totals || {})}, opened: saved.opened, rewards: saved.rewards.filter(r => r && ['player', 'item'].includes(r.kind) && typeof r.name === 'string').slice(0, 100)};
    }
    historyBackup = JSON.parse(localStorage.getItem(storageKey + '.backup'));
  } catch (_) { /* Storage may be unavailable in private browsing. */ }
  function reconcileHistoryPrices(record) {
    if (!record?.rewards || !record.totals) return;
    const players = record.rewards.filter(reward => reward.kind === 'player');
    // A non-full retained list still contains every reward, so legacy totals can
    // be repaired exactly without dropping value from older, truncated records.
    if (!record.priceTotalsVersion && record.rewards.length < 100) {
      record.totals.players = players.reduce((sum, reward) => sum + (Number(reward.price) || 0) * (Number(reward.count) || 1), 0);
      record.totals.unknownPlayers = players.reduce((sum, reward) => sum + (Number(reward.price) > 0 ? 0 : Number(reward.count) || 1), 0);
    }
    players.forEach(reward => { reward.accountedPrice ??= Number(reward.price) > 0 ? Number(reward.price) : null; });
    record.priceTotalsVersion = 1;
  }
  reconcileHistoryPrices(history);
  if (historyBackup?.totals) historyBackup.totals = {...emptyTotals(), ...historyBackup.totals};
  reconcileHistoryPrices(historyBackup);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const image = (src, className, alt = '') => {
    const node = el('img', className); node.src = src; node.alt = alt; node.draggable = false;
    node.addEventListener('error', () => { node.hidden = true; }, {once: true});
    return node;
  };
  const number = n => Number(n).toLocaleString('ko-KR');
  function error(message) { $('pack-error').textContent = message; $('pack-error').hidden = !message; }
  async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || '자료를 불러오지 못했어요. 잠시 후 다시 시도해주세요.');
      }
      return await response.json();
    } catch (err) {
      if (err.name === 'AbortError') throw new Error('응답이 지연되고 있어요. 잠시 후 다시 시도해주세요.');
      throw err;
    } finally { clearTimeout(timeout); }
  }
  function wait(ms, run) {
    return new Promise(resolve => {
      const timer = setTimeout(() => { state.timers.delete(timer); resolve(run === state.run); }, ms);
      state.timers.add(timer);
    });
  }
  function stopRun() {
    state.run += 1;
    stopParticles();
    // Let short pending waits settle naturally so canceled runs can exit cleanly.
    releaseVideo(cinematic);
    cinematic.onended = null;
    $('resume-opening').hidden = true; $('resume-opening').onclick = null;
    $('opening-flash').classList.remove('tunnel-flashed', 'flash');
    $('reveal-hint').replaceChildren();
    return state.run;
  }
  const loadingDialog = $('pack-loading');
  function setLoading(value) {
    // APNG preserves the supplied rotating logo, with no video autoplay policy
    // or extra video decoder competing with the cinematic scene.
    loadingDialog.hidden = !value;
  }
  loadingDialog.addEventListener('click', event => event.stopPropagation());
  function phase(value) { stage.dataset.phase = value; setLoading(value === 'loading'); }
  function setBusy(value) {
    state.busy = value;
    if (!value && historyRenderPending) renderHistory();
    $('history-pending').hidden = !value || Boolean(state.result?.historyRecorded);
    $('open-pack').disabled = value || !state.selected;
    $('open-again').disabled = value;
    $('pack-quantity').disabled = value;
    $('choose-pack').disabled = value;
    $('choose-bat-pack').disabled = value;
    $('history-reset').disabled = value;
    $('history-undo').disabled = value;
    document.querySelectorAll('.pack-option').forEach(button => { button.disabled = value; });
  }
  function flash() {
    const node = $('opening-flash');
    node.classList.remove('flash'); void node.offsetWidth; node.classList.add('flash');
  }
  let audio;
  function sound(type) {
    if (!state.sound) return;
    try {
      audio ||= new (window.AudioContext || window.webkitAudioContext)();
      audio.resume().catch(() => {});
      const now = audio.currentTime;
      if (type === 'reveal') {
        [261.63, 329.63, 392, 523.25].forEach((frequency, index) => {
          const osc = audio.createOscillator(), gain = audio.createGain();
          osc.type = 'triangle'; osc.frequency.value = frequency;
          gain.gain.setValueAtTime(0, now + index * .08);
          gain.gain.linearRampToValueAtTime(.06, now + index * .08 + .04);
          gain.gain.exponentialRampToValueAtTime(.001, now + 1.3);
          osc.connect(gain); gain.connect(audio.destination); osc.start(now + index * .08); osc.stop(now + 1.4);
        });
      } else {
        const length = audio.sampleRate * .8, buffer = audio.createBuffer(1, length, audio.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 3);
        const source = audio.createBufferSource(), gain = audio.createGain(), filter = audio.createBiquadFilter();
        source.buffer = buffer; filter.type = 'lowpass'; filter.frequency.setValueAtTime(4000, now);
        filter.frequency.exponentialRampToValueAtTime(200, now + .7); gain.gain.value = .14;
        source.connect(filter); filter.connect(gain); gain.connect(audio.destination); source.start();
      }
    } catch (_) { /* Sound is optional. */ }
  }
  function stopParticles() {
    if (particleFrame) cancelAnimationFrame(particleFrame);
    particleFrame = 0;
    if (particleContext) particleContext.clearRect(0, 0, particleContext.canvas.width, particleContext.canvas.height);
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopParticles(); });
  function particles() {
    stopParticles();
    const canvas = $('opening-particles'), ctx = canvas.getContext('2d');
    if (!ctx) return;
    particleContext = ctx;
    const gentle = motionPreference.matches;
    const run = state.run, bounds = stage.getBoundingClientRect(), dpr = mobilePlayback ? 1 : Math.min(devicePixelRatio, 2);
    if (!bounds.width || !bounds.height) return;
    // Bound the canvas even in fullscreen and keep a single short-lived animation.
    canvas.width = Math.max(1, Math.round(Math.min(bounds.width * dpr, mobilePlayback ? 960 : 1536)));
    canvas.height = Math.max(1, Math.round(canvas.width * bounds.height / bounds.width));
    const w = canvas.width, h = canvas.height, start = performance.now();
    const duration = gentle ? 1.1 : 1.5, frameInterval = 1000 / (mobilePlayback ? 24 : 30);
    const scale = w / Math.max(bounds.width, 1);
    let lastPaint = -Infinity;
    const dots = Array.from({length: gentle ? 18 : mobilePlayback ? 28 : 80}, () => ({
      x: w * (.5 + (gentle ? (Math.random() - .5) * .3 : 0)),
      y: h * (.47 + (gentle ? (Math.random() - .5) * .4 : 0)), angle: Math.random() * Math.PI * 2,
      speed: (gentle ? 8 + Math.random() * 14 : 70 + Math.random() * 200) * scale,
      size: (1.3 + Math.random() * 1.5) * scale, color: Math.random() > .4 ? '#eaffb2' : '#9effdc'}));
    function frame(now) {
      particleFrame = 0;
      const elapsed = (now - start) / 1000;
      if (run !== state.run || document.hidden || elapsed >= duration) { ctx.clearRect(0, 0, w, h); return; }
      if (now - lastPaint >= frameInterval) {
        lastPaint = now; ctx.clearRect(0, 0, w, h);
        ctx.globalAlpha = gentle ? Math.sin(Math.PI * elapsed / duration) * .8 : 1 - elapsed / duration;
        dots.forEach(dot => { ctx.fillStyle = dot.color;
          const x = dot.x + Math.cos(dot.angle) * dot.speed * elapsed;
          const y = dot.y + Math.sin(dot.angle) * dot.speed * elapsed + (gentle ? 0 : 35 * elapsed ** 2);
          ctx.fillRect(x, y, dot.size, dot.size * 2);
        });
      }
      particleFrame = requestAnimationFrame(frame);
    }
    particleFrame = requestAnimationFrame(frame);
  }
  function playerCard(reward) {
    const card = el('div', 'player-card');
    card.setAttribute('aria-label', `${reward.season} ${reward.playerKor} ${reward.ovr} ${reward.position || ''} ${reward.enhance}진화`);
    FimoCardArt.render(card, reward, {ovr: reward.ovr, enhance: reward.enhance});
    return card;
  }
  function itemCard(reward) {
    const card = el('div', 'item-reward');
    if (reward.name.startsWith('MP')) card.classList.add('mp-reward');
    card.append(reward.name.startsWith('MP')
      ? image('/static/pack-opener/images/mp-reward-transparent.png', 'item-icon mp-icon', 'MP')
      : tokenImage(reward.name, 'item-icon') || el('span', 'item-icon', 'FC'));
    card.append(el('strong', '', reward.name));
    if (reward.count > 1) card.append(el('small', '', `× ${number(reward.count)}`));
    return card;
  }
  const rewardCard = reward => reward.kind === 'player' ? playerCard(reward) : itemCard(reward);
  function updatePriceCaption(caption, reward) {
    const value = Number(reward.price);
    caption.querySelector('.reward-price-amount').textContent = Number.isFinite(value) && value > 0
      ? `${number(value)} MP` : '가격 정보 없음';
    caption.title = `${reward.priceSource === 'live' ? '최근 조회 시세' : '저장된 시세'} · ${reward.enhance}진화`;
    caption.dataset.priceSource = reward.priceSource || 'local';
  }
  function priceCaption(reward, className) {
    const caption = el('div', `${className} reward-price`);
    caption.dataset.cid = String(reward.cid || ''); caption.dataset.enhance = String(reward.enhance);
    caption.append(el('small', 'reward-price-heading', '현재 가치'));
    const amount = el('span', 'reward-price-line');
    amount.append(image('/static/pack-opener/images/mp-token-transparent.png', 'reward-price-coin', ''),
      el('span', 'reward-price-amount'));
    caption.append(amount); updatePriceCaption(caption, reward);
    return caption;
  }
  async function refreshRewardPrices(result) {
    const players = result.rewards.filter(reward => reward.kind === 'player' && reward.cid);
    const cids = [...new Set(players.map(reward => reward.cid))];
    try {
      for (let start = 0; start < cids.length; start += 40) {
        const payload = await request(`/api/player_prices?cids=${encodeURIComponent(cids.slice(start, start + 40).join(','))}`);
        if (state.result !== result) return;
        players.forEach(reward => {
          const price = payload.prices?.[String(reward.cid)];
          if (!price) return;
          const value = Number(price.priceByEnhance?.[String(reward.enhance)]);
          reward.price = Number.isFinite(value) && value > 0 ? value : null;
          reward.priceSource = price.source || 'local';
          document.querySelectorAll('.reward-price').forEach(caption => {
            if (caption.dataset.cid === String(reward.cid) && caption.dataset.enhance === String(reward.enhance)) {
              updatePriceCaption(caption, reward);
            }
          });
        });
      }
    } catch (_) { /* Keep the exact-level stored price when the quote service is unavailable. */ }
  }
  async function refreshHistoryPrices() {
    const record = history;
    const players = record.rewards.filter(reward => reward.kind === 'player' && reward.cid);
    const cids = [...new Set(players.map(reward => reward.cid))];
    if (!cids.length) return;
    try {
      for (let start = 0; start < cids.length; start += 40) {
        const payload = await request(`/api/player_prices?cids=${encodeURIComponent(cids.slice(start, start + 40).join(','))}`);
        if (history !== record) return;
        players.forEach(reward => {
          if (!record.rewards.includes(reward)) return;
          const price = payload.prices?.[String(reward.cid)];
          if (!price) return;
          const value = Number(price.priceByEnhance?.[String(reward.enhance)]);
          const nextPrice = Number.isFinite(value) && value > 0 ? value : null;
          const count = Number(reward.count) || 1;
          const previousPrice = Number(reward.accountedPrice) || 0;
          record.totals.players += ((nextPrice || 0) - previousPrice) * count;
          if (reward.categoryId === 'KKAEBI_BAT') record.totals.eventPlayers += ((nextPrice || 0) - previousPrice) * count;
          record.totals.unknownPlayers += ((nextPrice ? 0 : 1) - (previousPrice ? 0 : 1)) * count;
          reward.price = nextPrice;
          reward.accountedPrice = nextPrice;
          reward.priceSource = price.source || 'local';
        });
      }
      renderHistory();
      try { localStorage.setItem(storageKey, JSON.stringify(history)); } catch (_) {}
    } catch (_) { /* Stored exact-level values remain visible if lookup is unavailable. */ }
  }
  function mergeMPRewards(rewards) {
    const parts = rewards.filter(r => r.kind === 'item' && r.name.startsWith('MP'));
    if (!parts.length) return rewards.slice();
    const combined = parts.length === 1 ? parts[0] : {kind: 'item', name: 'MP',
      count: parts.reduce((total, r) => total + Number(r.count), 0), components: parts};
    return [combined, ...rewards.filter(reward => !parts.includes(reward))];
  }
  function orderedRewards(rewards) {
    const tokenGroups = new Map();
    const combined = [];
    mergeMPRewards(rewards).forEach(reward => {
      if (reward.kind !== 'item' || !/진화\s*재료.*토큰/.test(reward.name)) {
        combined.push(reward); return;
      }
      const group = tokenGroups.get(reward.name);
      if (group) {
        group.count += Number(reward.count);
        group.components.push(reward);
      } else {
        const token = {...reward, count: Number(reward.count), components: [reward]};
        tokenGroups.set(reward.name, token); combined.push(token);
      }
    });
    tokenGroups.forEach(token => { if (token.components.length === 1) delete token.components; });
    const players = combined.filter(reward => reward.kind === 'player').sort((a, b) =>
      b.ovr - a.ovr ||
      a.playerKor.normalize('NFKC').trim().localeCompare(b.playerKor.normalize('NFKC').trim(), 'ko') ||
      String(a.season).localeCompare(String(b.season), 'ko') ||
      Number(a.cid || 0) - Number(b.cid || 0));
    return [...combined.filter(reward => reward.kind !== 'player'), ...players];
  }
  const visibleRewards = result => result.displayRewards || result.rewards;
  const featuredReward = result => visibleRewards(result).find(reward => reward.kind === 'player') || visibleRewards(result)[0];
  function renderHistory() {
    // Quote responses can arrive mid-movie; rebuild history cards afterwards.
    if (state.busy && ['tunnel', 'reveal', 'hero'].includes(stage.dataset.phase)) {
      historyRenderPending = true; return;
    }
    historyRenderPending = false;
    $('history-total').textContent = `${number(history.opened)}개 오픈`;
    const totals = history.totals;
    $('history-fv').textContent = `${number(totals.fv)} FV`;
    $('history-mp').textContent = `${number(totals.mp)} MP`;
    $('history-players').textContent = `${number(totals.players)} MP`;
    $('history-value').textContent = `${number(totals.mp + totals.players)} MP`;
    const won = totals.fv * 7;
    // Compare acquired MP value directly with FV spent: 100m MP / 1,000 FV = 100k.
    const ratio = totals.fv > 0 && !totals.unknownFV ? (totals.mp + totals.players - totals.eventMP - totals.eventPlayers) / totals.fv : null;
    $('history-return').textContent = ratio == null ? '—' : ratio >= 10000
      ? `${(ratio / 10000).toLocaleString('ko-KR', {maximumFractionDigits:2})}만배`
      : `${ratio.toLocaleString('ko-KR', {maximumFractionDigits:0})}배`;
    $('history-won').textContent = won > 0 ? `약 ${number(Math.round(won))}원 기준` : '';
    $('history-event-moon').textContent = `${number(totals.moonSpent)}개`;
    const eventWon = totals.moonSpent * moonWon;
    $('history-event-cost').textContent = `${number(eventWon)}원`;
    $('history-event-value').textContent = `${number(totals.eventMP + totals.eventPlayers)} MP`;
    const eventRatio = eventWon > 0 && !totals.eventUnknownCost
      ? (totals.eventMP + totals.eventPlayers) / eventWon * eventMultiplierScale : null;
    $('history-event-return').textContent = eventRatio == null ? '—' : eventRatio >= 10000
      ? `${(eventRatio / 10000).toLocaleString('ko-KR', {maximumFractionDigits:2})}만배`
      : `${eventRatio.toLocaleString('ko-KR', {maximumFractionDigits:0})}배`;
    $('history-event-note').textContent = '조각달 500개 = 25,000원 · 5만원에 5억 MP = 10만배 기준';
    const notes = [];
    if (totals.unknownFV) notes.push(`가격 미확인 팩 ${number(totals.unknownFV)}개는 FV 합계에서 제외`);
    if (totals.unknownPlayers) notes.push(`가격 없는 선수 ${number(totals.unknownPlayers)}명은 가치 합계에서 제외`);
    if (totals.eventUnknownCost) notes.push(`이벤트 가격 미확인 상품 ${number(totals.eventUnknownCost)}개`);
    $('history-value-note').textContent = notes.join(' · ');
    $('history-undo').hidden = !historyBackup;
    $('history-reset').disabled = state.busy || !history.opened;
    const list = $('history-list'); list.replaceChildren();
    if (!history.rewards.length) { list.append(el('p', 'history-empty', '팩을 열면 이곳에 획득 기록이 쌓여요.')); return; }
    history.rewards.slice(0, 20).forEach(reward => {
      const item = el('div', 'history-item'); item.append(rewardCard(reward));
      if (reward.kind === 'player') item.append(priceCaption(reward, 'history-reward-price'));
      list.append(item);
    });
  }
  function saveResult(result) {
    const quantity = result.quantity || 1;
    history.opened += quantity;
    history.totals.opened += quantity;
    const eventProduct = result.categoryId === 'KKAEBI_BAT';
    if (eventProduct) {
      if (result.currency === '조각달' && result.spent != null) history.totals.moonSpent += result.spent;
      else history.totals.eventUnknownCost += quantity;
    } else if (result.spentFV != null) history.totals.fv += result.spentFV;
    else history.totals.unknownFV += quantity;
    result.rewards.forEach(reward => {
      const count = Number(reward.count) || 1;
      if (reward.kind === 'item' && reward.name.startsWith('MP')) {
        history.totals.mp += count;
        if (eventProduct) history.totals.eventMP += count;
      }
      if (reward.kind === 'player') {
        if (Number(reward.price) > 0) history.totals.players += Number(reward.price) * count;
        else history.totals.unknownPlayers += count;
        if (eventProduct && Number(reward.price) > 0) history.totals.eventPlayers += Number(reward.price) * count;
      }
    });
    const savedRewards = visibleRewards(result).map(({components, ...reward}) => {
      reward.categoryId = result.categoryId;
      if (reward.kind === 'player') reward.accountedPrice = Number(reward.price) > 0 ? Number(reward.price) : null;
      return reward;
    });
    history.rewards = [...savedRewards, ...history.rewards].slice(0, 100);
    try { localStorage.setItem(storageKey, JSON.stringify(history)); } catch (_) { /* Continue without saving. */ }
    renderHistory();
  }
  function shopPrice(pack) {
    const price = el('span', 'pack-price');
    if (pack.price === 0) {
      price.textContent = '무료'; price.title = pack.purchaseNote || '';
    } else if (Number.isSafeInteger(pack.price) && pack.price > 0) {
      const icon = pack.currency === 'FV' ? image('/static/pack-opener/images/fv-token-transparent.png', 'fv-icon', 'FV') : tokenImage(pack.currency, 'currency-icon');
      if (icon) price.append(icon);
      price.append(el('span', '', pack.currency === 'KRW' ? `${number(pack.price)}원` : number(pack.price)));
      price.setAttribute('aria-label', `${number(pack.price)} ${pack.currency === 'KRW' ? '원' : pack.currency}`);
      price.title = `사진 기준 팩 가격 · ${pack.priceAsOf}`;
      if (pack.currency === '조각달') price.title += ` · 약 ${number(pack.price * moonWon)}원 (500개 = 25,000원)`;
    } else {
      price.classList.add('price-unavailable'); price.textContent = '가격 미확인';
    }
    return price;
  }
  // Display regions of the supplied shop screenshots without changing the artwork.
  function sprite(art, className, label = '') {
    const node = el('span', `shop-art ${className}`);
    const [x, y, w, h] = art.crop, [sw, sh] = art.size;
    node.style.backgroundImage = `url("${art.src}")`;
    node.style.backgroundSize = `${sw / w * 100}% ${sh / h * 100}%`;
    node.style.backgroundPosition = `${x / (sw - w) * 100}% ${y / (sh - h) * 100}%`;
    node.style.aspectRatio = `${w} / ${h}`;
    if (label) { node.setAttribute('role', 'img'); node.setAttribute('aria-label', label); }
    else node.setAttribute('aria-hidden', 'true');
    return node;
  }
  function tokenImage(name, className) {
    const tokens = state.catalog?.tokenArt || {};
    const key = Object.keys(tokens).find(key => name.includes(key));
    if (!key) return null;
    return tokens[key].crop ? sprite(tokens[key], className, key) : image(tokens[key].src, className, key);
  }
  function renderPacks() {
    const list = $('pack-list'); list.replaceChildren();
    const query = $('pack-search').value.trim().toLowerCase();
    const packs = state.catalog.packs.filter(pack => (!query || pack.name.toLowerCase().includes(query)) &&
      (state.categoryFilter === 'all' || pack.categoryId === state.categoryFilter) &&
      (state.filter === 'all' || (state.filter === 'player' && pack.hasPlayers) || (state.filter === 'set' && pack.isSet)));
    $('pack-count').textContent = `${packs.length}개 팩`;
    if (!packs.length) { list.append(el('p', 'history-empty', '검색한 팩이 없어요.')); return; }
    const categories = [...new Set(packs.map(pack => pack.categoryId))];
    categories.forEach(category => {
      const section = el('section', 'pack-category');
      section.setAttribute('aria-label', packs.find(pack => pack.categoryId === category).categoryName);
      section.append(el('h3', 'pack-category-title', packs.find(pack => pack.categoryId === category).categoryName));
      packs.filter(pack => pack.categoryId === category).forEach(pack => {
      const button = el('button', 'pack-option' + (state.selected?.id === pack.id ? ' selected' : ''));
      button.type = 'button'; button.disabled = state.busy; button.setAttribute('aria-pressed', String(state.selected?.id === pack.id));
      const art = pack.art ? sprite(pack.art, 'pack-thumbnail', pack.name) :
        image(pack.hasPlayers ? '/static/pack-opener/images/pack.png' : '/static/pack-opener/images/mp-reward-transparent.png', 'pack-thumbnail');
      button.append(art);
      const text = el('span', 'pack-option-copy'); text.append(el('strong', '', pack.name));
      text.append(shopPrice(pack), el('small', '', pack.endsAt.startsWith('2038') ? '상시 상품' : `~ ${pack.endsAt}`)); button.append(text);
      if (state.selected?.id === pack.id) button.append(el('span', 'selection-mark', '✓'));
      button.addEventListener('click', () => selectPack(pack)); section.append(button);
      });
      list.append(section);
    });
  }
  function resetStage() {
    stopRun(); phase('idle'); cinematic.classList.remove('visible');
    $('pack-idle').hidden = false; $('hero-reward').classList.remove('visible'); $('hero-reward').replaceChildren();
    $('open-pack').hidden = false; $('show-results').hidden = true;
    $('stage-status').textContent = ''; updateQuantityCost();
    $('reward-flow').hidden = true;
  }
  function selectPack(pack) {
    if (state.busy) return;
    state.selected = pack; state.result = null; error(''); resetStage();
    $('pack-results').hidden = true; $('stage-pack-name').textContent = pack.name;
    $('selected-pack-name').textContent = pack.name;
    $('selected-pack-price').replaceChildren(shopPrice(pack));
    $('selected-pack-note').textContent = pack.purchaseNote || '';
    $('selected-pack-note').hidden = !pack.purchaseNote;
    $('mobile-pack-name').textContent = pack.name;
    if ($('pack-shop-dialog').open) $('pack-shop-dialog').close();
    $('open-pack').disabled = false; $('show-odds').disabled = false; renderPacks();
  }
  function prepareVideo(video, src) {
    video.muted = true; video.defaultMuted = true; video.playsInline = true;
    if (video.dataset.source === src && !video.error) return;
    // Native HTTP byte ranges, one URL/decoder, and no hidden-preload gate:
    // iOS may defer even metadata until play() or a user gesture.
    video.dataset.source = src; video.src = src; video.preload = 'auto';
    video.load();
  }
  async function preloadReward(reward) {
    await Promise.all([reward.card, reward.face, reward.flag, reward.club].filter(Boolean).map(src => new Promise(resolve => {
      const img = new Image(), timeout = setTimeout(resolve, 8000);
      img.onload = img.onerror = () => { clearTimeout(timeout); resolve(); }; img.src = src;
    })));
  }
  function setHint(reward, kind) {
    const node = $('reveal-hint'); if (node.dataset.kind === kind) return;
    node.dataset.kind = kind; node.replaceChildren();
    if (!kind) return;
    if (kind === 'position') { node.append(el('span', 'hint-position', reward.position || '')); sound('hint'); return; }
    const src = kind === 'flag' ? reward.flag : reward.club;
    const label = kind === 'flag' ? reward.nation : reward.team;
    if (src) node.append(image(src, '', label));
    else if (label) node.append(el('span', 'hint-text', label));
    sound('hint');
  }
  function heroReward(reward) {
    const node = $('hero-reward'); node.replaceChildren(rewardCard(reward));
    node.classList.add('visible'); flash(); particles(); sound('reveal');
  }
  async function playVideo(video, run, update, repeatFrom = null) {
    if (run !== state.run) return false;
    video.loop = false;
    if (video.readyState >= 1) video.currentTime = 0;
    let ended = false, active = true, waitingForGesture = false, playStarted = false, playAttempt = 0;
    let lastTime = -1, lastProgress = performance.now(), wasHidden = document.hidden;
    const resume = $('resume-opening');
    const current = () => active && state.run === run;
    const promptResume = () => {
      if (!current()) return;
      waitingForGesture = true; setLoading(false); resume.hidden = false;
      $('stage-status').textContent = '버튼을 눌러 연출을 계속해주세요.';
    };
    const requestPlay = () => {
      const attempt = ++playAttempt;
      waitingForGesture = false; playStarted = false; resume.hidden = true; lastProgress = performance.now();
      // Do not await play(): Safari may leave this promise pending indefinitely.
      // The progress watchdog must remain active while decoding starts.
      try {
        Promise.resolve(video.play()).then(() => {
          if (!current() || attempt !== playAttempt) return;
          waitingForGesture = false; playStarted = true; resume.hidden = true; $('stage-status').textContent = '';
        }).catch(err => {
          if (!current() || attempt !== playAttempt) return;
          if (err.name === 'NotAllowedError') promptResume();
          else if (!document.hidden) showResults('영상을 재생할 수 없어 결과를 표시했어요.');
        });
      } catch (_) { if (current()) showResults('영상을 재생할 수 없어 결과를 표시했어요.'); }
    };
    const resumePlayback = () => { if (current()) requestPlay(); };
    resume.onclick = resumePlayback;
    video.onended = () => {
      if (!current()) return;
      if (repeatFrom === null) { ended = true; return; }
      // Repeat only the scoreboard, without replacing the source or decoder.
      video.currentTime = repeatFrom; requestPlay();
    };
    video.classList.add('visible'); update(0);
    video.muted = true; video.playsInline = true;
    requestPlay();
    try {
      while (current() && !ended) {
        if (!(await wait(100, run))) return false;
        if (document.hidden) { wasHidden = true; lastProgress = performance.now(); continue; }
        if (wasHidden) {
          wasHidden = false; lastProgress = performance.now();
          if (video.paused && !waitingForGesture) requestPlay();
        }
        if (video.error) { showResults('영상을 재생할 수 없어 결과를 표시했어요.'); return false; }
        if (waitingForGesture) { lastProgress = performance.now(); continue; }
        update(video.currentTime);
        if (video.currentTime !== lastTime) {
          lastTime = video.currentTime; lastProgress = performance.now();
          if (lastTime > 0) { playStarted = true; setLoading(false); }
        }
        // Some iOS versions leave play() pending instead of rejecting it in
        // low-power/autoplay-restricted modes. Offer a real gesture immediately.
        if (!playStarted && performance.now() - lastProgress > 2000) { promptResume(); continue; }
        if (playStarted && !video.paused && performance.now() - lastProgress > 500) setLoading(true);
        if (performance.now() - lastProgress > 12000) {
          showResults('영상 재생이 지연되어 획득 결과를 표시했어요.'); return false;
        }
        // A system interruption can pause media without rejecting play().
        if (playStarted && video.paused && !video.ended && performance.now() - lastProgress > 1500) promptResume();
      }
      return current();
    } finally {
      active = false;
      if (state.run === run) {
        video.onended = null; releaseVideo(video); setLoading(false);
        if (resume.onclick === resumePlayback) { resume.onclick = null; resume.hidden = true; }
      }
    }
  }
  async function animate(result) {
    const run = stopRun(); phase('loading'); error('');
    $('pack-results').hidden = true; $('open-pack').hidden = true; $('show-results').hidden = true;
    $('reward-flow').hidden = true;
    $('hero-reward').classList.remove('visible');
    cinematic.classList.remove('visible'); $('pack-idle').hidden = false;
    const hero = featuredReward(result), player = hero.kind === 'player';
    $('stage-status').textContent = '';
    if (player) {
      prepareVideo(cinematic, `/static/pack-opener/videos/cinematic-v1/packopening_${hero.animation}_cinematic.mp4`);
    }
    await preloadReward(hero);
    if (run !== state.run) return;
    $('stage-status').textContent = ''; phase('burst'); sound('burst');
    if (!(await wait(1200, run))) return;
    flash(); particles();
    if (!(await wait(350, run))) return;
    $('pack-idle').hidden = true;
    if (!player) { showResults(); return; }
    // Explicit openings retain the movie and effects; reduced motion uses
    // soft fades and a small sparkle burst without large zooms or bright flashes.
    phase('tunnel'); $('reveal-hint').dataset.kind = '';
    let scoreboardShown = false, cardShown = false;
    await playVideo(cinematic, run, time => {
      if (time < scoreboardStart && !scoreboardShown) {
        const ratio = time / scoreboardStart;
        setHint(hero, ratio >= .23 && ratio < .43 ? 'flag' : ratio >= .46 && ratio < .65 ? 'position' : ratio >= .68 && ratio < .88 ? 'club' : '');
        if (ratio > .9 && !$('opening-flash').classList.contains('tunnel-flashed')) {
          $('opening-flash').classList.add('tunnel-flashed'); flash(); sound('burst');
        }
        return;
      }
      if (!scoreboardShown) {
        scoreboardShown = true; phase('reveal');
        $('opening-flash').classList.remove('tunnel-flashed'); setHint(hero, '');
      }
      if (time < scoreboardStart + .35 || cardShown) return;
      cardShown = true; phase('hero'); heroReward(hero);
      $('show-results').hidden = false;
      $('stage-status').textContent = visibleRewards(result).length > 1 ? `총 ${visibleRewards(result).length}개 보상 · 다음을 눌러 모두 확인하세요` : '';
    }, scoreboardStart);
  }

  function showResults(message = '', all = false) {
    if (!state.result) return;
    const revealedHero = $('hero-reward').classList.contains('visible') ? featuredReward(state.result) : null;
    stopRun(); setBusy(true);
    cinematic.classList.remove('visible'); $('hero-reward').classList.remove('visible');
    $('pack-idle').hidden = true; $('show-results').hidden = true;
    $('open-pack').hidden = true; $('stage-status').textContent = '';
    $('pack-results').hidden = true; $('pack-results').open = false;
    const grid = $('result-grid'); grid.replaceChildren();
    visibleRewards(state.result).forEach(reward => {
      const item = el('div', 'reward-entry'); item.append(rewardCard(reward));
      item.append(el('strong', '', reward.kind === 'player' ? `[${reward.season}] ${reward.playerKor}` : reward.name));
      item.append(el('small', '', reward.kind === 'player' ? `기본 OVR ${reward.baseOvr} · ${reward.enhance}진화` : `수량 ${number(reward.count)}`));
      if (reward.components) {
        const breakdown = el('details', 'mp-breakdown');
        breakdown.append(el('summary', '', `${reward.name} 합계 · ${reward.components.length}회 추첨 내역`));
        reward.components.forEach(part => breakdown.append(el('p', '', `${number(part.count)} ${reward.name} · 획득 확률 ${part.probability}%`)));
        item.append(breakdown);
      } else item.append(el('small', '', `획득 확률 ${reward.probability}%`));
      if (reward.kind === 'player' && !reward.matched) item.append(el('small', '', '선수 이미지 준비 중'));
      if (reward.cid) { const link = el('a', '', '선수 정보 ↗'); link.href = `/player/${reward.cid}`; link.target = '_blank'; link.rel = 'noopener'; link.style.fontSize = '10px'; item.append(link); }
      grid.append(item);
    });
    // The featured reward was already shown. Continue with the remaining rewards,
    // then include every original outcome in the final overview without drawing again.
    state.flowRewards = visibleRewards(state.result).filter(reward => reward !== revealedHero);
    $('reward-flow').dataset.itemsOnly = String(visibleRewards(state.result).every(reward => reward.kind === 'item'));
    state.flowIndex = 0; $('reward-flow-title').textContent = state.result.packName;
    $('reward-flow').hidden = false; error(message);
    if (state.flowRewards.length && !all) showRewardStep();
    else showRewardSummary();
  }
  function showRewardStep() {
    phase('reward-step'); $('reward-step').hidden = false; $('reward-summary').hidden = true;
    $('reveal-all').hidden = false; $('reward-next').hidden = true; $('flow-replay').hidden = true;
    const reward = state.flowRewards[state.flowIndex], remaining = state.flowRewards.length - state.flowIndex - 1;
    const current = $('reward-current'); current.replaceChildren(rewardCard(reward));
    current.dataset.kind = reward.kind;
    current.dataset.singleItem = String(reward.kind === 'item' && state.flowRewards.length === 1);
    $('reward-pack').hidden = remaining === 0;
    if (state.flowRewards.length === 1) { $('reveal-all').hidden = true; $('reward-next').hidden = false; }
    if (reward.kind === 'player') current.append(priceCaption(reward, 'flow-reward-label'));
    current.classList.remove('reward-arrives'); void current.offsetWidth; current.classList.add('reward-arrives');
    $('reward-remaining').textContent = String(remaining);
    $('reward-pack').setAttribute('aria-label', remaining ? `다음 보상 열기 · ${remaining}개 남음` : '전체 보상 보기');
    current.setAttribute('aria-label', `${reward.name} · ${remaining ? '다음 보상 확인' : '전체 보상 보기'}`);
    $('reward-flow-status').textContent = state.flowRewards.length === 1 ? '보상을 획득했어요 · 다음을 눌러 계속하세요' :
      remaining ? `팩을 눌러 다음 보상을 확인하세요 · ${remaining}개 남음` : '팩을 눌러 전체 보상을 확인하세요';
    sound('hint');
  }
  function advanceReward() {
    if (stage.dataset.phase !== 'reward-step') return;
    if (++state.flowIndex < state.flowRewards.length) showRewardStep();
    else showRewardSummary();
  }
  function showRewardSummary() {
    if (!state.result) return;
    if (!state.result.historyRecorded) {
      saveResult(state.result);
      state.result.historyRecorded = true;
      $('history-pending').hidden = true;
    }
    phase('reward-summary');
    // Revealed rewards are already recorded; the shop can accept another selection.
    setBusy(false);
    $('reward-step').hidden = true; $('reward-summary').hidden = false;
    $('reveal-all').hidden = true; $('reward-next').hidden = false; $('flow-replay').hidden = false;
    renderSummaryRewards();
    flash();
  }
  function renderSummaryRewards() {
    const rewards = visibleRewards(state.result);
    const grid = $('reward-summary-grid'); grid.replaceChildren();
    grid.dataset.itemsOnly = String(rewards.every(reward => reward.kind === 'item'));
    grid.dataset.count = String(rewards.length);
    grid.style.setProperty('--reward-columns', Math.min(rewards.length, 5));
    grid.dataset.many = String(rewards.length > 3);
    rewards.forEach(reward => {
      const item = el('div', 'flow-summary-reward'); item.append(rewardCard(reward));
      if (reward.kind === 'player') item.append(priceCaption(reward, 'flow-reward-label'));
      grid.append(item);
    });
    $('reward-summary').scrollTop = 0;
    $('reward-flow-status').textContent = `총 ${rewards.length}개 보상 획득`;
  }
  async function finishRewards() {
    if (state.busy) return;
    setBusy(true); stage.classList.add('returning-to-pack');
    await new Promise(resolve => setTimeout(resolve, 180));
    resetStage(); state.result = null; $('pack-results').hidden = true;
    stage.classList.remove('returning-to-pack'); stage.classList.add('pack-returned');
    setTimeout(() => stage.classList.remove('pack-returned'), 300);
    setBusy(false);
    $('stage-status').textContent = '';
  }
  function replayOpening() {
    if (!state.result) return;
    stopRun(); setBusy(true); animate(state.result).catch(() => showResults());
  }
  async function openPack() {
    if (state.busy || !state.selected) return;
    const quantity = Number($('pack-quantity').value);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100) {
      error('열 팩 수량은 1~100개로 입력해주세요.'); $('pack-quantity').focus(); return;
    }
    state.result = null; resetStage();
    setBusy(true); phase('loading'); error(''); $('stage-status').textContent = '';
    try {
      state.result = await request('/api/pack-opener/draw', {method: 'POST', headers: {'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify({pack: state.selected.id, quantity})});
      state.result.displayRewards = orderedRewards(state.result.rewards);
      // Resolve the displayed exact-evolution price before the reveal; history
      // records these same values only after the reward overview is reached.
      await refreshRewardPrices(state.result); await animate(state.result);
    } catch (err) {
      if (state.result) showResults('연출을 진행하지 못해 획득 결과를 표시했어요.');
      else { setBusy(false); resetStage(); error(err.message); }
    }
  }
  async function loadOdds() {
    const run = ++state.oddsRun, pack = state.selected.id, path = state.oddsPath.join('.');
    $('odds-body').replaceChildren(); $('odds-title').textContent = ''; setLoading(true);
    $('odds-prev').disabled = $('odds-next').disabled = true;
    try {
      const table = await request(`/api/pack-opener/odds?pack=${encodeURIComponent(pack)}&path=${encodeURIComponent(path)}&page=${state.oddsPage}`);
      if (run !== state.oddsRun) return;
      state.oddsPage = table.page; state.oddsPages = table.pages;
      $('odds-title').textContent = table.name; $('odds-back').hidden = !state.oddsPath.length;
      $('odds-page').textContent = `${table.page} / ${table.pages} · ${number(table.total)}개 항목`;
      $('odds-prev').disabled = table.page <= 1; $('odds-next').disabled = table.page >= table.pages;
      table.rows.forEach(row => {
        const tr = el('tr', ''), name = el('td', '');
        if (row.hasChildren) {
          const button = el('button', '', row.name + ' ›'); button.type = 'button';
          button.addEventListener('click', () => { state.oddsPath.push(row.index); state.oddsPage = 1; loadOdds(); }); name.append(button);
        } else name.textContent = row.name;
        tr.append(name, el('td', '', number(row.count)), el('td', '', row.ovr == null ? '—' : String(row.ovr)),
          el('td', '', row.enhance == null ? '—' : String(row.enhance)), el('td', '', row.probability + '%'));
        $('odds-body').append(tr);
      });
      document.querySelector('.odds-scroll').scrollTop = 0;
    } catch (err) { if (run === state.oddsRun) $('odds-title').textContent = err.message; }
    finally { if (run === state.oddsRun) setLoading(false); }
  }
  $('open-pack').addEventListener('click', openPack); $('open-again').addEventListener('click', openPack);
  function updateQuantityCost() {
    const quantity = Number($('pack-quantity').value), price = state.selected?.price;
    const valid = Number.isInteger(quantity) && quantity >= 1 && quantity <= 100;
    $('pack-quantity-cost').textContent = !valid ? '1~100개 입력' :
      Number.isSafeInteger(price) ? `총 ${number(price * quantity)} ${state.selected.currency === 'KRW' ? '원' : state.selected.currency}${state.selected.currency === '조각달' ? ` (약 ${number(price * quantity * moonWon)}원)` : ''}` : '가격 미확인';
    if (!state.busy) $('open-pack').textContent = valid && quantity > 1 ? `${number(quantity)}개 열기 →` : '팩 열기 →';
  }
  $('pack-quantity').addEventListener('input', updateQuantityCost);
  $('history-reset').addEventListener('click', () => {
    if (state.busy || !history.opened) return;
    historyBackup = history; history = emptyHistory();
    try {
      localStorage.setItem(storageKey + '.backup', JSON.stringify(historyBackup));
      localStorage.setItem(storageKey, JSON.stringify(history));
    } catch (_) {}
    renderHistory();
  });
  $('history-undo').addEventListener('click', () => {
    if (state.busy || !historyBackup) return;
    // Keep openings made after clearing rather than replacing them on undo.
    history.opened += historyBackup.opened;
    history.rewards = [...history.rewards, ...historyBackup.rewards].slice(0,100);
    Object.keys(emptyTotals()).forEach(key => { history.totals[key] += historyBackup.totals?.[key] || 0; });
    historyBackup = null;
    try { localStorage.setItem(storageKey, JSON.stringify(history)); localStorage.removeItem(storageKey + '.backup'); } catch (_) {}
    renderHistory();
  });
  $('show-results').addEventListener('click', () => showResults('', true));
  $('replay-opening').addEventListener('click', () => { if (!state.busy) replayOpening(); });
  $('flow-replay').addEventListener('click', replayOpening);
  $('reward-pack').addEventListener('click', advanceReward);
  $('reward-current').addEventListener('click', advanceReward);
  $('reveal-all').addEventListener('click', showRewardSummary);
  $('reward-next').addEventListener('click', () => {
    if (stage.dataset.phase === 'reward-step') showRewardSummary();
    else finishRewards();
  });
  $('pack-search').addEventListener('input', () => { if (state.catalog) renderPacks(); });
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    state.categoryFilter = button.dataset.category;
    const eventCategory = ['KKAEBI_BAT', 'FV_RELAY'].includes(state.categoryFilter);
    $('pack-type-filters').hidden = eventCategory;
    if (eventCategory) {
      state.filter = 'all';
      document.querySelectorAll('[data-filter]').forEach(filter => {
        const active = filter.dataset.filter === 'all';
        filter.classList.toggle('active', active); filter.setAttribute('aria-pressed', String(active));
      });
    }
    document.querySelectorAll('[data-category]').forEach(tab => {
      tab.classList.toggle('active', tab === button); tab.setAttribute('aria-pressed', String(tab === button));
    });
    if (state.catalog) renderPacks();
  }));
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    state.filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(other => {
      other.classList.toggle('active', other === button); other.setAttribute('aria-pressed', String(other === button));
    }); if (state.catalog) renderPacks();
  }));
  $('show-odds').addEventListener('click', () => {
    if (!state.selected) return; state.oddsPath = []; state.oddsPage = 1; $('odds-dialog').showModal(); loadOdds();
  });
  $('close-odds').addEventListener('click', () => $('odds-dialog').close());
  $('odds-back').addEventListener('click', () => { state.oddsPath.pop(); state.oddsPage = 1; loadOdds(); });
  $('odds-prev').addEventListener('click', () => { state.oddsPage -= 1; loadOdds(); });
  $('odds-next').addEventListener('click', () => { state.oddsPage += 1; loadOdds(); });
  $('odds-dialog').addEventListener('click', event => { if (event.target === $('odds-dialog')) {
    const box = event.target.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close();
  }});
  $('sound-toggle').addEventListener('click', () => {
    state.sound = !state.sound; $('sound-toggle').setAttribute('aria-pressed', String(state.sound));
    $('sound-toggle').setAttribute('aria-label', state.sound ? '소리 끄기' : '소리 켜기');
    $('sound-toggle').title = state.sound ? '소리 끄기' : '소리 켜기';
    $('sound-toggle').firstElementChild.className = state.sound ? 'bi bi-volume-up' : 'bi bi-volume-mute';
    if (state.sound) sound('hint');
  });
  // A click on the stage follows the same action as its current primary control.
  // Controls handle their own click; the final overview requires its Next button.
  stage.addEventListener('click', event => {
    if (event.target.closest('button, a, input, select, summary') || $('odds-dialog').open) return;
    if (!$('resume-opening').hidden) { $('resume-opening').click(); return; }
    const currentPhase = stage.dataset.phase;
    if (currentPhase === 'reward-summary') return;
    if (!state.busy) { if (state.selected) openPack(); return; }
    if (!state.result) return;
    if (currentPhase === 'reward-step') advanceReward();
    else if (currentPhase === 'hero') showResults('', true);
    else showResults('', true);
  });
  const stageFrame = $('stage-frame');
  const isExpanded = () => document.fullscreenElement === stageFrame ||
    document.webkitFullscreenElement === stageFrame || stageFrame.classList.contains('is-fullscreen');
  function fitStage() {
    const expanded = isExpanded();
    const width = stageFrame.clientWidth;
    const height = expanded ? stageFrame.clientHeight : width * 9 / 16;
    if (width <= 0 || height <= 0) return;
    stageFrame.style.setProperty('--stage-scale', Math.min(width / 1024, height / 576));
    stageFrame.classList.add('stage-fitted');
  }
  fitStage();
  if ('ResizeObserver' in window) new ResizeObserver(fitStage).observe(stageFrame);
  window.addEventListener('resize', fitStage);
  function syncFullscreen() {
    fitStage();
    const expanded = isExpanded();
    $('fullscreen-toggle').setAttribute('aria-label', expanded ? '전체 화면 종료' : '전체 화면');
    $('fullscreen-toggle').title = expanded ? '전체 화면 종료' : '전체 화면';
    $('fullscreen-toggle').setAttribute('aria-pressed', String(expanded));
  }
  document.addEventListener('fullscreenchange', syncFullscreen);
  document.addEventListener('webkitfullscreenchange', syncFullscreen);
  window.visualViewport?.addEventListener('resize', fitStage);
  function fallbackFullscreen(value) {
    stageFrame.classList.toggle('is-fullscreen', value);
    document.documentElement.classList.toggle('pack-fullscreen', value);
    syncFullscreen();
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && stageFrame.classList.contains('is-fullscreen')) fallbackFullscreen(false);
  });
  $('fullscreen-toggle').addEventListener('click', async () => {
    if (stageFrame.classList.contains('is-fullscreen')) { fallbackFullscreen(false); return; }
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (document.webkitFullscreenElement) document.webkitExitFullscreen();
      else if (stageFrame.requestFullscreen) { await stageFrame.requestFullscreen(); fitStage(); }
      else if (stageFrame.webkitRequestFullscreen) stageFrame.webkitRequestFullscreen();
      else fallbackFullscreen(true);
    } catch (_) { fallbackFullscreen(true); }
  });
  const shop = document.querySelector('.pack-shop'), shopDialog = $('pack-shop-dialog');
  const mobileShop = window.matchMedia('(max-width:740px)');
  function placeShop() {
    if (shopDialog.open) shopDialog.close();
    (mobileShop.matches ? $('mobile-shop-host') : $('desktop-shop-host')).append(shop);
  }
  mobileShop.addEventListener('change', placeShop); placeShop();
  $('choose-pack').addEventListener('click', () => { if (!state.busy) shopDialog.showModal(); });
  $('choose-bat-pack').addEventListener('click', () => {
    if (state.busy) return;
    $('pack-search').value = '';
    document.querySelector('[data-category="KKAEBI_BAT"]').click();
    if (mobileShop.matches) shopDialog.showModal();
    else {
      shop.scrollIntoView({block: 'start', behavior: 'smooth'});
      shop.querySelector('.pack-option')?.focus({preventScroll: true});
    }
    $('pack-list').scrollTop = 0;
  });
  $('close-pack-shop').addEventListener('click', () => shopDialog.close());
  shopDialog.addEventListener('click', event => { if (event.target === shopDialog) shopDialog.close(); });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !state.busy || $('odds-dialog').open || !state.result) return;
    if (stage.dataset.phase === 'reward-step') showRewardSummary();
    else if (stage.dataset.phase === 'reward-summary') return;
    else showResults();
  });
  async function initialize() {
    stage.classList.add('initial-loading');
    setLoading(true);
    renderHistory(); refreshHistoryPrices();
    try {
      state.catalog = await request('/api/pack-opener/catalog', {cache: 'no-store'}); $('pack-list').setAttribute('aria-busy', 'false');
      const dates = state.catalog.categoryFetchedAt;
      $('source-date').textContent = dates
        ? Object.entries(dates).map(([id, date]) => `${({STORE:'상점', KKAEBI_BAT:'방망이', FV_RELAY:'FV 릴레이'})[id] || id} ${date.slice(0, 10)}`).join(' · ') + ' 수집'
        : `${state.catalog.fetchedAt.slice(0, 10)} 수집`;
      renderHistory();
      selectPack(state.catalog.packs[0]);
    } catch (err) {
      $('pack-list').setAttribute('aria-busy', 'false'); $('pack-count').textContent = '불러오기 실패'; error(err.message);
      const retry = el('button', 'pack-option', '팩 목록 다시 불러오기'); retry.type = 'button'; retry.addEventListener('click', initialize);
      $('pack-list').replaceChildren(retry);
    }
    finally { stage.classList.remove('initial-loading'); setLoading(false); }
  }
  initialize();
})();
