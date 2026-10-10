/* FC모바일 진화 시뮬레이터: 넥슨 공식 확률표(static/data/evolution_probabilities.json)로 성공률을 계산하고
   게임의 '선수 진화' 화면과 진화 연출을 같은 좌표로 재현한다. */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('evo-data').textContent);
  const steps = data.steps;
  const materials = data.materials;
  const enhanceSteps = data.enhanceSteps;
  const enhanceTotals = enhanceSteps.reduce((acc, step, i) => { acc.push((acc[i - 1] || 0) + step); return acc; }, []);
  const MAX_LEVEL = steps.length;
  const badge = level => `/static/squad/evolution/${level}.png`;
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const fmt = value => {
    const number = Number(String(value ?? '').replace(/[^0-9.-]/g, ''));
    return Number.isFinite(number) && number > 0 ? Math.round(number).toLocaleString('ko-KR') : '-';
  };
  const pct = value => `${(Math.round(value * 100) / 100).toFixed(2)}%`;

  const state = {
    player: null, level: 0, slots: [], lastMaterials: [], protect: false,
    log: {tries: 0, success: 0, fail: 0, materials: 0, protect: 0, entries: []},
  };
  const views = {menu: $('[data-view="menu"]'), picker: $('[data-view="picker"]'), scene: $('[data-view="scene"]')};
  const els = {
    targetCard: $('[data-target-card]'), targetBadge: $('[data-target-badge]'), targetEmpty: $('[data-target-empty]'),
    levelSelect: $('[data-level-select]'), valueNow: $('[data-value-now]'), valueNext: $('[data-value-next]'),
    fromBadge: $('[data-from-badge]'), toBadge: $('[data-to-badge]'), failNote: $('[data-fail-note]'),
    gainOvr: $('[data-gain-ovr]'), gainStat: $('[data-gain-stat]'),
    protect: $('[data-protect]'), protectNa: $('[data-protect-na]'), protectCount: $('[data-protect-count]'),
    protectToggle: $('[data-protect-toggle]'), protectState: $('[data-protect-state]'),
    go: $('[data-go]'), materialLevel: $('[data-material-level]'), materialGrid: $('[data-material-grid]'), baseOvr: $('[data-base-ovr]'),
    playerDialog: $('[data-player-dialog]'), playerSearch: $('[data-player-search]'), playerResults: $('[data-player-results]'),
    infoDialog: $('[data-info-dialog]'), infoRows: $('[data-info-rows]'), alert: $('[data-alert]'), skipAnim: $('[data-skip-anim]'),
  };

  const loading = $('[data-loading]');
  let loadingCount = 0;
  function setLoading(on) {
    loadingCount = Math.max(0, loadingCount + (on ? 1 : -1));
    loading.hidden = loadingCount === 0;
  }

  function showView(name) {
    Object.entries(views).forEach(([key, view]) => { view.hidden = key !== name; });
  }

  // ---------- 확률 ----------
  const currentStep = () => (state.level < MAX_LEVEL ? steps[state.level] : null);
  function diffKey(diff) {
    if (diff < -20) return 'lt-20';
    if (diff <= -11) return '-20~-11';
    if (diff >= 10) return 'ge10';
    return String(diff);
  }
  function materialRate(step, material) {
    if (!step || !state.player) return 0;
    const row = step.byOvrDiff[diffKey(material.ovr - state.player.ovr)] || [];
    return Number(row[Math.min(material.level, row.length - 1)] || 0);
  }
  function totalRate(step = currentStep()) {
    if (!step) return 0;
    return Math.min(state.slots.reduce((sum, material) => sum + materialRate(step, material), 0), step.maxRate);
  }

  // ---------- 카드 ----------
  function setCard(element, player, level = 0, ovrOverride) {
    element.replaceChildren();
    element.className = element.className.split(' ').filter(name => !name.startsWith('fimo-card')).join(' ');
    delete element.dataset.fimoCardCid; delete element.dataset.fimoCardOvr;
    if (!player) return;
    [[player.card, 'card-background'], [player.face, 'card-face']].forEach(([src, className]) => {
      if (!src) return;
      const img = document.createElement('img');
      img.className = className; img.src = src; img.alt = ''; img.decoding = 'async'; img.draggable = false;
      element.append(img);
    });
    element.dataset.fimoCardOvr = String(ovrOverride ?? (player.ovr + (enhanceTotals[level] || 0)));
    element.dataset.fimoCardCid = String(player.cid);
  }
  function fillBar(bar, share) {
    bar.replaceChildren(...Array.from({length: 5}, (_, i) => {
      const cell = document.createElement('i');
      cell.style.setProperty('--cell', Math.max(0, Math.min(1, share * 5 - i)).toFixed(3));
      return cell;
    }));
  }

  // ---------- 렌더 ----------
  function renderSelects() {
    els.levelSelect.replaceChildren(...Array.from({length: MAX_LEVEL + 1}, (_, level) => new Option(`${level}진화`, level)));
    els.materialLevel.replaceChildren(...Array.from({length: 16}, (_, level) => new Option(`재료 ${level}진화`, level)));
  }
  function renderGauges(step) {
    const fill = step && state.player ? totalRate(step) / step.maxRate : 0;
    $$('[data-gauge]').forEach(gauge => {
      gauge.replaceChildren(...Array.from({length: 5}, (_, i) => {
        const cell = document.createElement('span');
        cell.style.setProperty('--cell', Math.max(0, Math.min(1, fill * 5 - i)).toFixed(3));
        cell.innerHTML = `<b>${i + 1}</b>`;
        return cell;
      }));
    });
    const text = step && state.player ? `성공 확률 <b>${pct(totalRate(step))}</b>` : '';
    $$('[data-rate-readout]').forEach(node => { node.innerHTML = text; });
  }
  function renderSlots(step) {
    const slotCount = step ? step.slots : 0;
    $$('[data-slots]').forEach(container => {
      const inPicker = !!container.closest('.evo-picker');
      const cells = [];
      for (let i = 0; i < 9; i += 1) {
        const cell = document.createElement('button');
        cell.type = 'button'; cell.className = 'evo-slot'; cell.dataset.slot = i;
        const material = state.slots[i];
        if (i >= slotCount) {
          cell.classList.add('is-locked'); cell.disabled = true;
          cell.innerHTML = '<i class="bi bi-lock-fill" aria-hidden="true"></i>';
          cell.setAttribute('aria-label', '잠긴 슬롯');
        } else if (material) {
          cell.classList.add('is-filled');
          cell.innerHTML = `<span class="evo-card"></span>${material.level ? `<img class="evo-card-badge" src="${badge(material.level)}" alt="">` : ''}<span class="evo-bar"></span>`;
          setCard(cell.querySelector('.evo-card'), material, material.level);
          fillBar(cell.querySelector('.evo-bar'), step ? materialRate(step, material) / step.maxRate : 0);
          cell.setAttribute('aria-label', inPicker ? `${material.playerKor} 재료 빼기` : `${material.playerKor} 재료 변경`);
        } else {
          cell.classList.add('is-empty');
          cell.disabled = !state.player || !step;
          cell.innerHTML = '<i class="bi bi-plus-lg" aria-hidden="true"></i>';
          cell.setAttribute('aria-label', '재료 추가');
        }
        cells.push(cell);
      }
      container.replaceChildren(...cells);
    });
  }
  function render() {
    const step = currentStep();
    const player = state.player;
    if (step) state.slots = state.slots.slice(0, step.slots); else state.slots = [];
    els.levelSelect.value = String(state.level);
    els.targetEmpty.hidden = !!player;
    els.targetBadge.hidden = !player || state.level === 0;
    els.targetBadge.src = badge(state.level);
    setCard(els.targetCard, player, state.level);

    els.fromBadge.src = badge(state.level);
    els.toBadge.src = badge(Math.min(state.level + 1, MAX_LEVEL));
    const gain = step ? enhanceSteps[step.to] : 0;
    els.gainOvr.textContent = `+${gain}`;
    els.gainStat.textContent = `+${gain}`;
    els.failNote.textContent = !step ? '최대 진화 단계입니다.' : (state.level === 0 ? '진화 실패 시 단계가 유지됩니다.' : '진화 실패 시 등급이 하락합니다.');
    const prices = player?.priceByEnhance || {};
    els.valueNow.textContent = player ? fmt(prices[state.level]) : '-';
    els.valueNext.textContent = player && step ? fmt(prices[step.to]) : '-';

    const protection = step?.protection;
    els.protect.hidden = !protection;
    els.protectNa.hidden = !!protection || !step;
    if (!protection) state.protect = false;
    if (protection) els.protectCount.textContent = `[${protection.tier}] ${protection.count}개`;
    els.protectToggle.checked = state.protect;
    els.protectState.textContent = state.protect ? 'ON' : 'OFF';

    renderGauges(step);
    renderSlots(step);
    if (!views.picker.hidden) renderMaterials();
    els.go.disabled = !player || !step || !state.slots.length;
  }

  function renderMaterials() {
    const step = currentStep();
    const level = Number(els.materialLevel.value || 0);
    const showBase = els.baseOvr.checked;
    const rows = materials.map(material => ({material, rate: materialRate(step, {...material, level})}))
      .sort((a, b) => b.rate - a.rate || b.material.ovr - a.material.ovr);
    els.materialGrid.replaceChildren(...rows.map(({material, rate}) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'evo-mat'; button.dataset.cid = material.cid;
      if (rate <= 0) button.classList.add('is-zero');
      button.setAttribute('aria-label', `${material.playerKor} OVR ${material.ovr} 재료 추가, 성공률 ${pct(rate)}`);
      button.innerHTML = `<span class="evo-card"></span>${level ? `<img class="evo-card-badge" src="${badge(level)}" alt="">` : ''}<span class="evo-mat-rate">+${pct(rate)}</span><span class="evo-bar"></span>`;
      setCard(button.querySelector('.evo-card'), material, level, showBase ? material.ovr : undefined);
      fillBar(button.querySelector('.evo-bar'), step ? rate / step.maxRate : 0);
      return button;
    }));
  }
  function addMaterial(cid) {
    const step = currentStep();
    const material = materials.find(item => String(item.cid) === String(cid));
    if (!step || !material || state.slots.length >= step.slots) return;
    state.slots.push({...material, level: Number(els.materialLevel.value || 0)});
    render();
  }
  function autofill() {
    const step = currentStep();
    if (!step || !state.player) return;
    const level = Number(els.materialLevel.value || 0);
    // 성공률을 가장 많이 올리는 NG 선수부터 게이지가 찰 때까지 채운다.
    const best = materials.map(material => ({material, rate: materialRate(step, {...material, level})}))
      .filter(item => item.rate > 0).sort((a, b) => b.rate - a.rate || a.material.ovr - b.material.ovr)[0];
    if (!best) return;
    state.slots = [];
    let sum = 0;
    while (state.slots.length < step.slots && sum < step.maxRate) { state.slots.push({...best.material, level}); sum += best.rate; }
    render();
  }

  function renderInfo() {
    els.infoRows.replaceChildren(...steps.map(step => {
      const row = document.createElement('tr');
      if (step.from === state.level) row.className = 'is-current';
      row.innerHTML = `<td>${step.from}→${step.to}</td><td>${step.maxRate}%</td><td>${step.slots}개</td><td>${step.protection ? `${step.protection.tier} ${step.protection.count}개` : '-'}</td>`;
      return row;
    }));
  }

  // ---------- 선수 선택 ----------
  let searchTimer = 0, searchSeq = 0;
  async function searchPlayers(query) {
    const seq = ++searchSeq;
    els.playerResults.innerHTML = '<p class="evo-muted">불러오는 중…</p>';
    try {
      const params = new URLSearchParams({q: query, limit: '30', sort: query ? 'recommend' : 'ovr_desc'});
      const response = await fetch(`/api/squad_players?${params}`);
      if (!response.ok) throw new Error(String(response.status));
      const list = await response.json();
      if (seq !== searchSeq) return;
      if (!Array.isArray(list) || !list.length) { els.playerResults.innerHTML = '<p class="evo-muted">검색 결과가 없습니다.</p>'; return; }
      els.playerResults.replaceChildren(...list.map(player => {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'evo-player-row'; button.dataset.cid = player.cid;
        button.innerHTML = '<span class="evo-card"></span><span class="evo-player-meta"><b></b><small></small></span>';
        button.querySelector('b').textContent = player.playerKor || '';
        button.querySelector('small').textContent = `${player.className || ''} · ${player.position || ''} · OVR ${player.ovr}`;
        setCard(button.querySelector('.evo-card'), {
          cid: player.cid, ovr: Number(player.ovr),
          card: player.bimageThumbSmall || player.bimageThumb || player.bimage,
          face: player.pimageThumbSmall || player.pimageThumb || player.pimage,
        });
        return button;
      }));
    } catch (_) {
      if (seq === searchSeq) els.playerResults.innerHTML = '<p class="evo-muted">선수를 불러오지 못했습니다. 다시 시도해 주세요.</p>';
    }
  }
  async function choosePlayer(cid) {
    els.playerDialog.close();
    setLoading(true);
    try {
      const response = await fetch(`/api/evolution-simulator/player/${cid}`);
      if (!response.ok) throw new Error(String(response.status));
      state.player = await response.json();
      state.slots = []; state.lastMaterials = [];
      render();
    } catch (_) {
      els.playerDialog.showModal();
      els.playerResults.insertAdjacentHTML('afterbegin', '<p class="evo-muted">선수 정보를 불러오지 못했습니다.</p>');
    } finally {
      setLoading(false);
    }
  }

  // ---------- 기록 ----------
  function renderLog() {
    const log = state.log;
    $('[data-log-tries]').textContent = log.tries;
    $('[data-log-success]').textContent = log.success;
    $('[data-log-fail]').textContent = log.fail;
    $('[data-log-materials]').textContent = log.materials;
    $('[data-log-protect]').textContent = log.protect.toLocaleString('ko-KR');
    $('[data-log-rate]').textContent = log.tries ? `${Math.round(log.success / log.tries * 1000) / 10}%` : '-';
    $('[data-log-empty]').hidden = log.entries.length > 0;
    $('[data-log-list]').replaceChildren(...log.entries.slice(0, 50).map(entry => {
      const item = document.createElement('li');
      item.className = entry.success ? 'is-success' : (entry.protected ? 'is-fail is-protected' : 'is-fail');
      item.innerHTML = '<span class="evo-log-no"></span><span class="evo-log-name"></span><span class="evo-log-step"><img alt=""><i class="bi bi-chevron-double-right" aria-hidden="true"></i><img alt=""></span><span class="evo-log-result"></span><span class="evo-log-rate"></span>';
      item.querySelector('.evo-log-no').textContent = `#${entry.no}`;
      item.querySelector('.evo-log-name').textContent = entry.name;
      const [from, to] = item.querySelectorAll('img');
      from.src = badge(entry.from); from.alt = `${entry.from}진화`;
      to.src = badge(entry.to); to.alt = `${entry.to}진화`;
      item.querySelector('.evo-log-result').textContent = entry.success ? '성공' : (entry.protected ? '보호' : '실패');
      item.querySelector('.evo-log-rate').textContent = pct(entry.rate);
      return item;
    }));
  }

  // ---------- 진화 시도 ----------
  function attempt() {
    const step = currentStep();
    const rate = totalRate(step);
    const success = Math.random() * 100 < rate;
    const protectedFail = !success && state.protect && !!step.protection;
    const from = state.level;
    const to = success ? from + 1 : (protectedFail || from === 0 ? from : from - 1);
    state.lastMaterials = state.slots.map(material => ({...material}));
    const log = state.log;
    log.tries += 1; log[success ? 'success' : 'fail'] += 1; log.materials += state.slots.length;
    if (state.protect && step.protection) log.protect += step.protection.count;
    log.entries.unshift({no: log.tries, from, to, success, protected: protectedFail, rate, name: state.player.playerKor});
    state.level = to;
    state.slots = [];
    return {from, to, success, protectedFail, rate};
  }
  function startEvolution() {
    const step = currentStep();
    if (!step || !state.player || !state.slots.length) return;
    if (step.protection && !state.protect) { els.alert.hidden = false; $('[data-alert-ok]').focus(); return; }
    run();
  }
  function run() {
    els.alert.hidden = true;
    const result = attempt();
    renderLog();
    playShow(result);
  }

  // ---------- 연출 ----------
  const scene = views.scene;
  const show = {
    card: $('[data-show-card]'), flip: $('[data-show-flip]'), oldBadge: $('[data-show-old]'), newBadge: $('[data-show-new]'),
    title: $('[data-show-title]'), wipeText: $('[data-wipe-text]'), canvas: $('[data-confetti]'),
    token: 0, particles: [], fountains: false, running: false, last: null,
  };
  const wait = (ms, token) => new Promise(resolve => setTimeout(() => resolve(token === show.token), ms));
  // 연출 시각은 녹화 영상에서 카드가 무대에 나타난 순간(0ms)을 기준으로 잰 값이다.
  const until = (start, at, token) => wait(Math.max(0, at - (performance.now() - start)), token);

  // 소리: 녹화 영상의 성공/실패 구간 (카드 등장 순간부터)
  const sounds = {success: new Audio('/static/evolution-sim/success.m4a'), fail: new Audio('/static/evolution-sim/fail.m4a')};
  Object.values(sounds).forEach(audio => { audio.preload = 'auto'; });
  const soundButton = $('[data-sound]');
  // 연출 배경(숨겨진 화면 안)과 소리를 미리 받아 둔다. 오래 걸려도 6초 뒤에는 그냥 진행한다.
  const timeout = ms => new Promise(resolve => setTimeout(resolve, ms));
  const loadImage = src => new Promise(resolve => {
    const img = new Image();
    img.onload = () => { img.decode?.().catch(() => {}); resolve(); };
    img.onerror = resolve;
    img.src = src;
  });
  const assetsReady = Promise.race([
    Promise.all([
      ...$$('.evo-plate').map(plate => loadImage(plate.currentSrc || plate.src)),
      ...Object.values(sounds).map(audio => new Promise(resolve => {
        if (audio.readyState >= 2) { resolve(); return; }
        audio.addEventListener('loadeddata', resolve, {once: true});
        audio.addEventListener('error', resolve, {once: true});
        audio.load();
      })),
    ]),
    timeout(6000),
  ]);
  let soundOn = true;
  try { soundOn = localStorage.getItem('evoSound') !== 'off'; } catch (_) { /* 저장소를 못 쓰면 기본값 */ }
  function renderSound() {
    soundButton.setAttribute('aria-pressed', String(soundOn));
    soundButton.setAttribute('aria-label', soundOn ? '소리 끄기' : '소리 켜기');
    soundButton.innerHTML = `<i class="bi ${soundOn ? 'bi-volume-up-fill' : 'bi-volume-mute-fill'}" aria-hidden="true"></i>`;
  }
  function stopSounds() { Object.values(sounds).forEach(audio => { audio.pause(); }); }
  function playSound(name) {
    stopSounds();
    if (!soundOn) return;
    const audio = sounds[name];
    audio.currentTime = 0;
    audio.play().catch(() => { /* 자동 재생이 막히면 소리 없이 진행 */ });
  }
  function setPhases(...names) { scene.className = ['evo-view', 'evo-scene', ...names].join(' '); }
  function addPhase(name) { scene.classList.add(name); }

  async function typeTitle(text, token) {
    for (let i = 1; i <= text.length; i += 1) {
      if (token !== show.token) return;
      show.title.textContent = text.slice(0, i);
      if (i < text.length) { const cursor = document.createElement('span'); cursor.className = 'evo-cursor'; show.title.append(cursor); }
      await new Promise(resolve => setTimeout(resolve, 95));
    }
  }

  // 금색 분수와 꽃가루
  const GOLD = ['#fff3c4', '#ffd45c', '#f2b632', '#d99a1e', '#fffbea', '#e9e9e9'];
  function sizeCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const w = show.canvas.clientWidth, h = show.canvas.clientHeight;
    show.canvas.width = Math.max(1, Math.round(w * ratio)); show.canvas.height = Math.max(1, Math.round(h * ratio));
    show.canvas.getContext('2d').setTransform(ratio, 0, 0, ratio, 0, 0);
  }
  function spawn(count, origin) {
    const w = show.canvas.clientWidth, h = show.canvas.clientHeight, k = h / 554;
    for (let i = 0; i < count; i += 1) {
      if (origin) {
        const x0 = origin === 'left' ? 0.235 : 0.765;
        show.particles.push({
          x: w * x0 + (Math.random() - 0.5) * 14 * k, y: h * 0.9,
          vx: (Math.random() - 0.5) * 6.4 * k, vy: -(10 + Math.random() * 11) * k, g: 0.14 * k,
          size: (1.8 + Math.random() * 3) * k, spark: true, life: 100 + Math.random() * 60,
          color: GOLD[Math.floor(Math.random() * 5)], rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4,
        });
      } else {
        show.particles.push({
          x: Math.random() * w, y: -10 - Math.random() * h * 0.6,
          vx: (Math.random() - 0.5) * 0.6 * k, vy: (0.7 + Math.random() * 1.3) * k, g: 0.004 * k,
          size: (3 + Math.random() * 5) * k, spark: false, life: 520,
          color: GOLD[Math.floor(Math.random() * GOLD.length)], rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.18,
        });
      }
    }
  }
  let lastTick = 0;
  function tick(now) {
    if (scene.hidden) { show.running = false; return; }
    const dt = Math.min(3, lastTick ? (now - lastTick) / 16.67 : 1);
    lastTick = now;
    const ctx = show.canvas.getContext('2d');
    const w = show.canvas.clientWidth, h = show.canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    if (show.fountains) { const n = Math.round(22 * dt); spawn(n, 'left'); spawn(n, 'right'); }
    show.particles = show.particles.filter(p => p.life > 0 && p.y < h + 30);
    for (const p of show.particles) {
      p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.vr * dt; p.life -= dt;
      if (!p.spark) p.vx += Math.sin(p.rot) * 0.02;
      ctx.globalAlpha = Math.min(1, p.life / 30);
      ctx.fillStyle = p.color;
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
      const flat = 0.25 + Math.abs(Math.sin(p.rot * 2)) * 0.75;
      if (p.spark) ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * flat);
      else ctx.fillRect(-p.size / 2, -p.size * 0.3, p.size, p.size * 0.6 * flat);
      ctx.restore();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(tick);
  }
  function startParticles() {
    sizeCanvas(); show.particles = []; show.fountains = false;
    if (!show.running) { show.running = true; lastTick = 0; requestAnimationFrame(tick); }
  }

  function prepareResult(result) {
    const player = state.player;
    $('[data-result-title]').textContent = result.success ? '진화 성공' : '진화 실패';
    $('[data-result-from]').src = badge(result.from);
    $('[data-result-to]').src = badge(result.to);
    setCard($('[data-result-card]'), player, result.to);
    const cardBadge = $('[data-result-card-badge]');
    cardBadge.src = badge(result.to); cardBadge.hidden = result.to === 0;
    const delta = (enhanceTotals[result.to] || 0) - (enhanceTotals[result.from] || 0);
    $('[data-result-stats]').replaceChildren(...(player.summary || []).map(item => {
      const row = document.createElement('div');
      row.innerHTML = '<dt></dt><dd></dd>';
      const dt = row.querySelector('dt'); const dd = row.querySelector('dd');
      dt.textContent = item.label;
      if (delta) { const em = document.createElement('em'); em.textContent = `${delta > 0 ? '+' : ''}${delta}`; if (delta < 0) em.className = 'is-down'; dt.append(em); }
      dd.textContent = item.value + (enhanceTotals[result.to] || 0);
      if (delta) dd.className = delta > 0 ? 'is-up' : 'is-down';
      return row;
    }));
    const strip = $('[data-result-strip]');
    const diff = result.to - result.from;
    strip.textContent = diff > 0 ? `스킬 포인트+${diff}` : (diff < 0 ? `스킬 포인트${diff}` : '진화 등급 유지');
    strip.className = `evo-r-strip${diff < 0 ? ' is-down' : (diff === 0 ? ' is-hold' : '')}`;
  }

  async function playShow(result) {
    const token = ++show.token;
    show.last = result;
    setLoading(true);
    await assetsReady;
    setLoading(false);
    if (token !== show.token) return;
    showView('scene');
    startParticles();
    show.title.textContent = '';
    show.oldBadge.src = badge(result.from);
    show.newBadge.src = badge(result.to);
    setCard(show.card, state.player, result.from);
    setCard(show.flip, state.player, result.to);
    prepareResult(result);
    if (els.skipAnim.checked) { finishShow(result); return; }

    setPhases(); await wait(40, token);
    const t0 = performance.now();
    playSound(result.success ? 'success' : 'fail');
    setPhases('p-stage');
    if (!await until(t0, 200, token)) return;
    addPhase('p-beam');

    if (result.success) {
      if (!await until(t0, 1600, token)) return;
      addPhase('p-wipe');
      if (!await until(t0, 2400, token)) return;
      addPhase('p-wipe-white');
      if (!await until(t0, 2500, token)) return;
      addPhase('p-wipe-fill');
      if (!await until(t0, 2600, token)) return;
      addPhase('p-success'); addPhase('p-reveal');
      spawn(90);
      if (!await until(t0, 2750, token)) return;
      await typeTitle('진화 성공', token);
      if (!await until(t0, 3600, token)) return;
      addPhase('p-upgrade');
      show.fountains = true; spawn(60);
      if (!await until(t0, 5200, token)) return;
      show.fountains = false;
      if (!await until(t0, 6300, token)) return;
      addPhase('p-flip');
      if (!await until(t0, 6450, token)) return;
      show.fountains = true;
      if (!await until(t0, 6800, token)) return;
      show.fountains = false;
      if (!await until(t0, 6900, token)) return;
    } else {
      if (!await until(t0, 1600, token)) return;
      setPhases('p-fail-flash');
      if (!await until(t0, 1800, token)) return;
      addPhase('p-fail');
      if (!await until(t0, 2600, token)) return;
      addPhase(result.to < result.from ? 'p-drop' : 'p-hold');
      if (!await until(t0, 3200, token)) return;
      await typeTitle('진화 실패', token);
      if (!await until(t0, 4400, token)) return;
      addPhase('p-flip');
      if (!await until(t0, 5000, token)) return;
    }
    finishShow(result);
  }
  function finishShow(result) {
    show.token += 1;
    setPhases(result.success ? 'p-success' : 'p-fail', 'p-result');
    scene.classList.toggle('is-fail-result', !result.success);
    if (result.success) spawn(40);
    $('[data-next]').focus({preventScroll: true});
  }
  function closeShow() {
    show.token += 1;
    stopSounds();
    show.fountains = false;
    showView('menu');
    render();
  }

  // ---------- 이벤트 ----------
  $('[data-open-player]').addEventListener('click', () => {
    els.playerDialog.showModal();
    els.playerSearch.focus();
    if (!els.playerResults.childElementCount) searchPlayers('');
  });
  els.playerSearch.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => searchPlayers(els.playerSearch.value.trim()), 220);
  });
  els.playerResults.addEventListener('click', event => {
    const row = event.target.closest('[data-cid]');
    if (row) choosePlayer(row.dataset.cid);
  });
  els.levelSelect.addEventListener('change', () => { state.level = Number(els.levelSelect.value); render(); });
  $$('[data-slots]').forEach(container => container.addEventListener('click', event => {
    const cell = event.target.closest('.evo-slot');
    if (!cell || cell.disabled) return;
    const inPicker = !!container.closest('.evo-picker');
    if (inPicker && cell.classList.contains('is-filled')) { state.slots.splice(Number(cell.dataset.slot), 1); render(); return; }
    if (!inPicker) { showView('picker'); render(); }
  }));
  els.materialGrid.addEventListener('click', event => {
    const item = event.target.closest('[data-cid]');
    if (item) addMaterial(item.dataset.cid);
  });
  els.materialLevel.addEventListener('change', renderMaterials);
  els.baseOvr.addEventListener('change', renderMaterials);
  $('[data-autofill]').addEventListener('click', autofill);
  $$('[data-picker-done]').forEach(button => button.addEventListener('click', () => { showView('menu'); render(); }));
  els.protectToggle.addEventListener('change', () => { state.protect = els.protectToggle.checked; render(); });
  els.go.addEventListener('click', startEvolution);
  $('[data-alert-ok]').addEventListener('click', run);
  $$('[data-alert-cancel]').forEach(button => button.addEventListener('click', () => { els.alert.hidden = true; els.go.focus(); }));
  $$('[data-open-info]').forEach(button => button.addEventListener('click', () => { renderInfo(); els.infoDialog.showModal(); }));
  $$('.evo-dialog').forEach(dialog => dialog.addEventListener('click', event => {
    if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
  }));
  $('[data-reset-log]').addEventListener('click', () => {
    state.log = {tries: 0, success: 0, fail: 0, materials: 0, protect: 0, entries: []};
    renderLog();
  });
  $('[data-next]').addEventListener('click', closeShow);
  $('[data-again]').addEventListener('click', () => {
    closeShow();
    const step = currentStep();
    if (step) { state.slots = state.lastMaterials.slice(0, step.slots).map(material => ({...material})); render(); }
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (!els.alert.hidden) { els.alert.hidden = true; return; }
    if (!views.picker.hidden) { showView('menu'); render(); }
  });
  window.addEventListener('resize', () => { if (!scene.hidden) sizeCanvas(); });
  soundButton.addEventListener('click', () => {
    soundOn = !soundOn;
    try { localStorage.setItem('evoSound', soundOn ? 'on' : 'off'); } catch (_) { /* 무시 */ }
    if (!soundOn) stopSounds();
    renderSound();
  });
  renderSound();


  renderSelects();
  render();
  renderLog();
  Promise.race([Promise.all([loadImage('/static/evolution-sim/menu.webp'), assetsReady]), timeout(6000)]).then(() => setLoading(false));
  setLoading(true);
})();
