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
    unlockMedia();
    playShow(result);
  }

  // ---------- 연출 ----------
  // 녹화한 게임 영상(카드·배지 자리를 지운 것)을 재생하고, 그 위 같은 위치에 고른 선수의 카드와 배지를 올린다.
  // 아래 시각(초)은 모두 그 영상 안의 재생 시각이다.
  const scene = views.scene;
  const screenEl = $('[data-screen]');
  const show = {
    card: $('[data-show-card]'), cardWrap: $('.evo-s-card'), flip: $('[data-show-flip]'), flipWrap: $('[data-show-flip-wrap]'),
    flipBack: $('.evo-s-back'), oldBadge: $('[data-show-old]'), newBadge: $('[data-show-new]'), canvas: $('[data-confetti]'),
    token: 0, particles: [], fountains: false, running: false, last: null,
  };
  const videos = {success: $('[data-video="success"]'), fail: $('[data-video="fail"]')};
  const sounds = {success: new Audio('/static/evolution-sim/success.m4a'), fail: new Audio('/static/evolution-sim/fail.m4a')};
  Object.values(sounds).forEach(audio => { audio.preload = 'auto'; });
  const soundButton = $('[data-sound]');
  const u = () => screenEl.clientWidth / 1200;

  // 첫 진화 전에 영상·배경·소리를 받아 둔다. 오래 걸려도 8초 뒤에는 그냥 진행한다.
  const timeout = ms => new Promise(resolve => setTimeout(resolve, ms));
  const loadImage = src => new Promise(resolve => {
    const img = new Image();
    img.onload = () => resolve(); img.onerror = () => resolve();
    img.src = src;
  });
  const mediaReady = media => new Promise(resolve => {
    if (media.readyState >= 3) { resolve(); return; }
    media.addEventListener('canplay', resolve, {once: true});
    media.addEventListener('loadeddata', resolve, {once: true});
    media.addEventListener('error', resolve, {once: true});
  });
  const assetsReady = Promise.race([
    Promise.all([
      ...$$('.evo-plate').map(plate => loadImage(plate.currentSrc || plate.src)),
      ...Object.values(videos).map(mediaReady),
      ...Object.values(sounds).map(mediaReady),
    ]),
    timeout(8000),
  ]);
  // iOS 등은 사용자가 누른 그 순간에만 소리 재생을 허락하므로, 진화 버튼을 누를 때 미리 깨워 둔다.
  let mediaUnlocked = false;
  function unlockMedia() {
    if (mediaUnlocked) return;
    mediaUnlocked = true;
    Object.values(sounds).forEach(audio => {
      audio.muted = true;
      audio.play().then(() => { audio.pause(); audio.currentTime = 0; audio.muted = false; }).catch(() => { audio.muted = false; });
    });
  }
  let soundOn = true;
  try { soundOn = localStorage.getItem('evoSound') !== 'off'; } catch (_) { /* 저장소를 못 쓰면 기본값 */ }
  function renderSound() {
    soundButton.setAttribute('aria-pressed', String(soundOn));
    soundButton.setAttribute('aria-label', soundOn ? '소리 끄기' : '소리 켜기');
    soundButton.innerHTML = `<i class="bi ${soundOn ? 'bi-volume-up-fill' : 'bi-volume-mute-fill'}" aria-hidden="true"></i>`;
  }
  function stopMedia() {
    Object.values(sounds).forEach(audio => audio.pause());
    Object.values(videos).forEach(video => video.pause());
  }
  const wait = (ms, token) => new Promise(resolve => setTimeout(() => resolve(token === show.token), ms));
  function setScene(...names) { scene.className = ['evo-view', 'evo-scene', ...names].join(' '); }

  // 영상 재생 시각이 sec 에 이를 때까지 기다린다. 다른 연출이 시작되면 false.
  function at(video, sec, token) {
    return new Promise(resolve => {
      const check = () => {
        if (token !== show.token) { resolve(false); return; }
        if (video.currentTime >= sec || video.ended) { resolve(true); return; }
        setTimeout(check, 16);
      };
      check();
    });
  }
  const fade = (el, from, to, ms) => el.animate([{opacity: from}, {opacity: to}], {duration: ms, fill: 'forwards'});
  function resetOverlays() {
    [show.cardWrap, show.oldBadge, show.newBadge, show.flipWrap, show.flipBack, show.flip].forEach(el => {
      el.getAnimations().forEach(anim => anim.cancel());
      el.style.opacity = '';
    });
  }

  // 결과 전 꽃가루와 카드 등장 때의 금색 불꽃
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
        const x0 = origin === 'left' ? 0.2 : 0.78;
        show.particles.push({
          x: w * x0 + (Math.random() - 0.5) * 14 * k, y: h * 0.86,
          vx: (Math.random() - 0.5) * 5 * k, vy: -(8 + Math.random() * 9) * k, g: 0.16 * k,
          size: (1.6 + Math.random() * 2.6) * k, spark: true, life: 70 + Math.random() * 50,
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
    if (show.fountains) { const n = Math.round(16 * dt); spawn(n, 'left'); spawn(n, 'right'); }
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

  // 배지·카드 움직임 (게임 영상에서 프레임 단위로 잰 위치와 시간)
  const PEDESTAL = 188;   // 배지 기본 위치(가운데)에서 받침대까지 아래로 (1200 기준 px)
  const PEDESTAL_SCALE = 1.15;
  const ease = 'cubic-bezier(.2, .8, .2, 1)';
  function badgeIn(el, ms = 120) { return el.animate([{opacity: 0}, {opacity: 1}], {duration: ms, fill: 'forwards'}); }
  function flipToResult(token) {
    // 배지가 작아지며 사라지고, 카드 뒷면이 돌아 앞면이 나온 뒤 왼쪽 결과 자리로 이동한다.
    const k = u();
    [show.oldBadge, show.newBadge].forEach(el => el.animate(
      [{transform: 'scale(1)', opacity: getComputedStyle(el).opacity}, {transform: 'scale(.35)', opacity: 0}],
      {duration: 110, fill: 'forwards'}));
    show.flipWrap.style.opacity = '1';
    show.flipBack.animate([{opacity: 1, transform: 'scaleX(.12)'}, {opacity: 1, transform: 'scaleX(1)', offset: .5}, {opacity: 1, transform: 'scaleX(.05)'}],
      {duration: 200, delay: 100, fill: 'forwards'});
    show.flip.animate([{opacity: 0, transform: 'scaleX(.05)'}, {opacity: 1, transform: 'scaleX(1)'}],
      {duration: 160, delay: 300, fill: 'both', easing: ease});
    show.flipWrap.animate([{transform: 'none'}, {transform: `translate(${-271 * k}px, ${20 * k}px)`}],
      {duration: 140, delay: 460, fill: 'forwards', easing: ease});
    setTimeout(() => { if (token === show.token) { show.fountains = true; } }, 380);
    setTimeout(() => { show.fountains = false; }, 900);
  }

  async function playShow(result) {
    const token = ++show.token;
    show.last = result;
    setLoading(true);
    await assetsReady;
    setLoading(false);
    if (token !== show.token) return;
    const name = result.success ? 'success' : 'fail';
    const video = videos[name];
    resetOverlays();
    show.oldBadge.src = badge(result.from);
    show.newBadge.src = badge(result.to);
    setCard(show.card, state.player, result.from);
    setCard(show.flip, state.player, result.to);
    prepareResult(result);
    showView('scene');
    startParticles();
    if (els.skipAnim.checked) { finishShow(result); return; }

    setScene(`v-${name}`);
    video.currentTime = 0;
    try { await video.play(); } catch (_) {
      // 불러오는 중에 재생이 끊기면 한 번 더 시도한다.
      await timeout(200);
      if (token !== show.token) return;
      try { video.currentTime = 0; await video.play(); } catch (__) { finishShow(result); return; }
    }
    if (soundOn) { const audio = sounds[name]; audio.currentTime = 0; audio.play().catch(() => {}); }
    const k = u();
    // 카드가 무대에 놓였다가 하얗게 바뀌는 순간까지 (영상 속 카드 자리는 지워져 있다)
    show.cardWrap.animate([{opacity: 0, transform: 'scale(.96)'}, {opacity: 1, transform: 'scale(1)', offset: .25}, {opacity: 1, offset: .8}, {opacity: 0, filter: 'brightness(3)'}],
      {duration: 300, fill: 'forwards'});

    if (result.success) {
      // 초록 전환이 걷히며 작게 보이는 배지 → 무대 가운데 배지
      if (!await at(video, 2.50, token)) return;
      show.oldBadge.animate([{opacity: 0, transform: 'scale(.42)'}, {opacity: 1, transform: 'scale(.45)', offset: .3}, {opacity: 1, transform: 'scale(1)'}],
        {duration: 230, fill: 'forwards', easing: ease});
      if (!await at(video, 3.55, token)) return;
      // 이전 배지가 하얗게 빛나며 떠오르고, 새 배지가 받침대에서 나타난다
      show.oldBadge.animate([{opacity: 1, transform: 'none', filter: 'none'}, {opacity: .9, transform: `translateY(${-30 * k}px)`, filter: 'brightness(2.6) saturate(0)', offset: .45}, {opacity: 0, transform: `translateY(${-60 * k}px)`, filter: 'brightness(3) saturate(0)'}],
        {duration: 230, fill: 'forwards'});
      show.newBadge.animate([{opacity: 0, transform: `translateY(${PEDESTAL * k}px) scale(${PEDESTAL_SCALE * .9})`, filter: 'brightness(3)'}, {opacity: 1, transform: `translateY(${PEDESTAL * k}px) scale(${PEDESTAL_SCALE})`, filter: 'brightness(1.4)'}],
        {duration: 160, fill: 'forwards'});
      if (!await at(video, 3.95, token)) return;
      show.newBadge.animate([
        {opacity: 1, transform: `translateY(${PEDESTAL * k}px) scale(${PEDESTAL_SCALE})`, filter: 'brightness(1.2)'},
        {opacity: 1, transform: `translateY(${-14 * k}px) scale(1)`, filter: 'none', offset: .7},
        {opacity: 1, transform: 'translateY(0) scale(1)', filter: 'none'}],
        {duration: 380, fill: 'forwards', easing: 'cubic-bezier(.3, .6, .3, 1)'});
      if (!await at(video, 4.33, token)) return;
      show.newBadge.animate([{filter: 'none'}, {filter: 'brightness(2.3)', offset: .4}, {filter: 'none'}], {duration: 300});
      if (!await at(video, 6.36, token)) return;
      setScene('plate-success');
      flipToResult(token);
      if (!await wait(700, token)) return;
    } else {
      // 회색으로 번쩍이는 순간의 작은 배지
      if (!await at(video, 1.50, token)) return;
      show.oldBadge.animate([{opacity: 0, transform: 'scale(.5)', filter: 'grayscale(1) brightness(1.6)'}, {opacity: 1, transform: 'scale(.55)', filter: 'grayscale(1) brightness(1.6)', offset: .4}, {opacity: 1, transform: 'scale(1)', filter: 'none'}],
        {duration: 220, fill: 'forwards', easing: ease});
      if (!await at(video, 2.55, token)) return;
      if (result.to < result.from) {
        // 이전 배지는 아래로 떨어지고, 낮은 배지가 위에서 내려와 자리를 잡는다
        show.oldBadge.animate([{opacity: 1, transform: 'none'}, {opacity: 0, transform: `translateY(${120 * k}px) rotate(8deg) scale(.9)`}],
          {duration: 150, fill: 'forwards', easing: 'ease-in'});
        show.newBadge.animate([
          {opacity: 0, transform: `translateY(${-139 * k}px)`},
          {opacity: 1, transform: `translateY(${-150 * k}px)`, offset: .15},
          {opacity: 1, transform: `translateY(${-183 * k}px)`, offset: .45},
          {opacity: 1, transform: `translateY(${10 * k}px)`, offset: .85},
          {opacity: 1, transform: 'none'}],
          {duration: 520, fill: 'forwards', easing: 'ease-in-out'});
      } else {
        // 보호권(또는 0진화)으로 등급이 유지될 때
        show.oldBadge.animate([{transform: 'none'}, {transform: `translateX(${-8 * k}px) rotate(-4deg)`}, {transform: `translateX(${7 * k}px) rotate(3deg)`}, {transform: `translateX(${-4 * k}px)`}, {transform: 'none'}],
          {duration: 500, iterations: 2, composite: 'add'});
      }
      if (!await at(video, 4.36, token)) return;
      setScene('plate-fail');
      flipToResult(token);
      if (!await wait(700, token)) return;
    }
    finishShow(result);
  }
  function finishShow(result) {
    show.token += 1;
    show.fountains = false;
    setScene(result.success ? 'plate-success' : 'plate-fail', 'p-result');
    scene.classList.toggle('is-fail-result', !result.success);
    if (result.success) spawn(60);
    $('[data-next]').focus({preventScroll: true});
  }
  function closeShow() {
    show.token += 1;
    stopMedia();
    show.fountains = false;
    resetOverlays();
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
    if (!soundOn) Object.values(sounds).forEach(audio => audio.pause());
    renderSound();
  });
  renderSound();


  renderSelects();
  render();
  renderLog();
  Promise.race([Promise.all([loadImage('/static/evolution-sim/menu.webp'), assetsReady]), timeout(6000)]).then(() => setLoading(false));
  setLoading(true);
})();
