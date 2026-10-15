/* Rules and rewards follow the supplied screenshots and recording. Pack contents
   are kept as awarded packs; unrelated shop-pack odds are never substituted. */
(() => {
  'use strict';
  const $ = id => document.getElementById(`trap-${id}`);
  const KEY = 'fimobook.trapping.v1';
  const MODES = {
    chest: {name: '가슴', gain: 3, rate: 30, superRate: 50},
    head: {name: '머리', gain: 2, rate: 50, superRate: 65},
    foot: {name: '발', gain: 1, rate: 70, superRate: 80},
  };
  const REWARDS = [
    '[3-6진화][GC27 포함] 선수 136-148 또는 3000만 MP',
    '[3-6진화][GC27 포함] 선수 136-148 또는 4000만 MP',
    '[NG] 선수 142-148 x2',
    '[3-6진화][GC27 포함] 선수 137-148 또는 7000만 MP',
    '[3-6진화][GC27 포함] 선수 138-148',
    '행운의 MP상자 (1억-2억)',
    '[3-6진화][GC27 포함] 선수 139-148 또는 1.8억 MP',
    '[3-6진화][GC27 포함] 선수 140-148',
    '행운의 MP상자 (2억-4억)',
    '[0-3진화][GC27&CMP26&KL26] 선수 142-148',
    '[7-10진화][GC27 포함] 선수 138-148 또는 5.5억 MP',
    '[7-10진화][GC27 포함] 선수 140-148',
    '[9-12진화][GC27 포함] 선수 140-148 또는 7.5억 MP',
    '행운의 MP상자 (7.5억-15억)',
    '[10-12진화][GC27 포함] 선수 138-148',
    '[3-5진화][TOP100] 선수 132-144',
    '[7-10진화][GC27 포함] 선수 142-148 또는 16억 MP',
    '[13진화][GC27 포함] 선수 136-148',
    '[3-5진화][TOP200] 선수 138-148',
    '행운의 MP상자 (30억-60억)',
    '[13진화][GC27 포함] 선수 139-148 또는 36억 MP',
    '[0-3진화][GC27&FCA27&CMP26] 선수 146-148',
    '행운의 MP상자 (70억-140억)',
    '[10-12진화][GC27 포함] 선수 144-148 또는 90억 MP',
    '[3-5진화][TOP20] 선수 145-148',
  ];
  const ATTENDANCE = [
    {count:5, reward:'[NG] 선수 142-148 x1'},
    {count:10, reward:'[NG] 선수 142-148 x2'},
    {count:25, reward:'[NG] 선수 144-148 x1'},
    {count:40, reward:'[NG] 선수 144-148 x2'},
    {count:60, reward:'[NG] 선수 144-148 x3'},
    {count:100, reward:'[NG] 선수 144-148 x4'},
    {count:200, reward:'[NG] 선수 144-148 x6'},
  ];
  const RANKS = [{name:'아마추어',cost:100},{name:'세미프로',cost:80},{name:'프로',cost:70}];
  const rankForBest = best => best >= 21 ? 2 : best >= 12 ? 1 : 0;
  const rankIndex = () => state.rankOverride ?? rankForBest(state.best);
  const currentRank = () => RANKS[rankIndex()];
  const rewardAt = points => REWARDS[points] || `${points}P 달성 보상`;
  const fmt = n => n.toLocaleString('ko-KR');
  const isSuper = points => points > 0 && points < 24 && points % 3 === 0;
  const int = (value, max = 1000000000) => Number.isSafeInteger(value) && value >= 0 && value <= max;
  const fresh = () => ({version:2,tickets:1000,best:0,attempts:0,success:0,rolls:0,usedTickets:0,gain:{mp:0,players:0,count:0},
    rankOverride:null,claimed:[],mailbox:[],received:[],delivery:null,history:[],round:null,sound:false,fast:false,revision:0});
  let needsMigration = false;
  function validMail(mail) {
    return mail && typeof mail.id === 'string' && typeof mail.name === 'string' &&
      typeof mail.source === 'string' && int(mail.tickets) && Number.isFinite(mail.at);
  }
  function read() {
    try {
      const s = JSON.parse(localStorage.getItem(KEY));
      if (!s || ![1,2].includes(s.version)) return null;
      if (!['tickets','best','attempts','success','rolls','usedTickets','revision'].every(k => int(s[k]))) return null;
      if (s.best > 24 || s.success > s.rolls || !Array.isArray(s.claimed) || !Array.isArray(s.history)) return null;
      if (s.round && (!int(s.round.points,24) || !Array.isArray(s.round.moves) || !['playing','failed','capped'].includes(s.round.phase))) return null;
      const data = {...fresh(),tickets:s.tickets,best:s.best,attempts:s.attempts,success:s.success,rolls:s.rolls,
        usedTickets:s.usedTickets,revision:s.revision,round:s.round,sound:s.sound === true,fast:s.fast === true,
        claimed:s.claimed.filter(n => ATTENDANCE.some(item => item.count === n)),history:s.history.slice(0,100)};
      const gain=s.gain;
      if (gain && ['mp','players','count'].every(k => Number.isFinite(gain[k]) && gain[k] >= 0)) data.gain={mp:gain.mp,players:gain.players,count:gain.count};
      if (s.version === 1) {
        if (!Array.isArray(s.inventory)) return null;
        // Old inventory already credited its point tickets. Move packs only.
        data.mailbox = s.inventory.filter(item => item && typeof item.name === 'string').map((item,index) => ({
          id:`legacy-${item.at || 0}-${index}`,name:item.name,source:item.source || '트래핑 보상',tickets:0,at:Number(item.at)||Date.now(),
        }));
        needsMigration = true;
      } else {
        if (!Array.isArray(s.mailbox) || !Array.isArray(s.received)) return null;
        data.rankOverride = s.rankOverride === null || int(s.rankOverride,2) ? s.rankOverride : null;
        data.mailbox = s.mailbox.filter(validMail);
        data.received = s.received.filter(validMail).slice(0,200);
        if (s.delivery && typeof s.delivery.id === 'string' && Array.isArray(s.delivery.mails) && s.delivery.mails.every(validMail)) data.delivery=s.delivery;
      }
      return data;
    } catch { return null; }
  }
  let state = read() || fresh();
  let busy = false;
  let soundContext;
  let storageWorking = true;
  let animationRun = 0;
  let messageTimer;
  let visibleReceiptId = null;
  let drawing = false;
  let failedPrompt = false;
  let drawFailed = false;
  let flow = null;
  let returnScrollY = 0;
  let dialogName = '';
  const dialog = $('dialog');
  const body = $('dialog-body');
  const footer = $('dialog-footer');
  const modes = [...document.querySelectorAll('[data-mode]')];
  const byId = id => document.getElementById(id);
  const frame = $('reward-frame');
  function save() {
    state.revision += 1;
    try { localStorage.setItem(KEY,JSON.stringify(state)); }
    catch { storageWorking = false; message('기록을 저장하지 못했습니다.'); }
  }
  function sync() {
    if (!storageWorking) return;
    const latest = read();
    if (latest && latest.revision !== state.revision) { state=latest; render(); }
  }
  function message(text) {
    clearTimeout(messageTimer); $('message').textContent=text;
    if (text) messageTimer=setTimeout(() => { $('message').textContent=''; },2500);
  }
  function element(tag,text,className) {
    const node=document.createElement(tag);
    if (text !== undefined) node.textContent=text;
    if (className) node.className=className;
    return node;
  }
  function image(src,className,alt='') {
    const node=element('img',undefined,className);node.src=src;node.alt=alt;node.draggable=false;return node;
  }
  function action(label,callback,secondary=false) {
    const button=element('button',label,secondary?'secondary':'');button.type='button';button.addEventListener('click',callback);footer.append(button);return button;
  }
  function showDialog(name,title) {
    dialogName=name;$('dialog-title').textContent=title;body.replaceChildren();footer.replaceChildren();
    if (!dialog.open) dialog.showModal();
  }
  function closeDialog() { dialogName='';dialog.close(); }
  $('dialog-close').addEventListener('click',closeDialog);
  dialog.addEventListener('close',() => {
    dialogName='';
    // Dismissing the failure notice still sends the participation reward.
    if(failedPrompt && state.round?.phase==='failed' && !state.delivery) {failedPrompt=false;finish(false);}
  });
  dialog.addEventListener('click',event => {
    if (event.target !== dialog) return;
    const r=dialog.getBoundingClientRect();
    if (event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) closeDialog();
  });
  const WON_PER_TICKET = 25000/1500;
  // Same convention as the pack opener's event multiplier: 5억 MP for 5만원 = 10만배.
  const MULTIPLIER_SCALE = 10;
  function formatMP(value) {
    if (value >= 1e8) return `${(value/1e8).toLocaleString('ko-KR',{maximumFractionDigits:2})}억 MP`;
    if (value >= 1e4) return `${Math.round(value/1e4).toLocaleString('ko-KR')}만 MP`;
    return `${fmt(Math.round(value))} MP`;
  }
  function renderRatio() {
    const spent=state.usedTickets*WON_PER_TICKET,value=state.gain.mp+state.gain.players;
    $('used').textContent=`${fmt(state.usedTickets)}장`;
    $('spent').textContent=`${fmt(Math.round(spent))}원`;
    $('gain').textContent=formatMP(value);
    const ratio=spent>0?value/spent*MULTIPLIER_SCALE:null;
    $('multiple').textContent=ratio===null?'—':ratio>=10000
      ?`${(ratio/10000).toLocaleString('ko-KR',{maximumFractionDigits:2})}만배`
      :`${ratio.toLocaleString('ko-KR',{maximumFractionDigits:0})}배`;
  }
  function render() {
    const r=state.round,points=r?.points || 0,tier=currentRank();
    const locked=busy || !!state.delivery;
    const boost=!!r && isSuper(points);
    $('rank-name').textContent=tier.name;
    $('rank-badge').hidden=rankIndex()!==0;
    $('rank-icon').hidden=rankIndex()===0;
    $('rank-icon').style.color=rankIndex()===2?'#ffdf26':'#dae9ff';
    $('tickets').textContent=`${fmt(state.tickets)}장`;
    renderRatio();
    $('points').textContent=`${points} P`;
    $('event').classList.toggle('is-super',boost);
    $('event').classList.toggle('is-active',r?.phase==='playing' || r?.phase==='capped');
    // The entry strip (ticket cost) stays visible during a round; only the action changes.
    const inRound=!!r && r.phase!=='failed';
    $('start').hidden=false;
    $('start').disabled=locked || inRound;
    $('start').textContent=r?.phase==='failed'?'참가 보상받기':inRound?'대회 진행 중':'트래핑 대회 참가 ›';
    $('collect').hidden=!r || r.phase==='failed' || points===0;
    $('collect').disabled=locked;
    $('collect').textContent=points===24?'보상받기':'보상 받고 종료';
    $('entry-note').textContent=!r?`참가권 ${tier.cost}장`:r.phase==='failed'?'트래핑 실패':`참가권 ${fmt(r.cost)}장 · ${r.phase==='capped'?'24P 달성':boost?'슈퍼 트래핑':'대회 진행 중'}`;
    modes.forEach(button => {
      const mode=MODES[button.dataset.mode],rate=boost?mode.superRate:mode.rate;
      button.disabled=r?.phase!=='playing' || locked;
      button.querySelector('[data-rate]').textContent=`${rate}%`;
      button.querySelector('[data-mode-label]').textContent=`${boost?'슈퍼 ':''}${mode.name} 트래핑`;
      button.querySelector('.trap-mode-flame').hidden=!boost;
      button.setAttribute('aria-label',`${mode.name} 트래핑, ${boost?'슈퍼 ':''}성공 확률 ${rate}%, 성공 시 ${mode.gain}포인트`);
    });
    $('best').textContent=`${state.best} P`;
    $('total').textContent=`${fmt(state.attempts)}회`;
    $('attempts').textContent=fmt(state.attempts);
    $('fast').checked=state.fast;$('fast').disabled=locked;
    $('sound').setAttribute('aria-pressed',String(state.sound));
    $('sound').setAttribute('aria-label',state.sound?'소리 끄기':'소리 켜기');
    $('sound').firstElementChild.className=state.sound?'bi bi-volume-up':'bi bi-volume-mute';
    $('sound').disabled=locked;
    document.querySelectorAll('[data-dialog]').forEach(button => { button.disabled=locked; });
    const count=state.mailbox.length;
    $('mail-count').textContent=fmt(count);$('mail-count').hidden=count===0;
    $('mailbox-button').setAttribute('aria-label',`우편함${count?`, ${fmt(count)}개`:''}`);
    renderRewards(r);renderAttendance();
    if (state.delivery) renderReceipt();
    else {
      $('game-view').hidden=false;$('reward-screen').hidden=true;
      visibleReceiptId=null;flow=null;cinematicRun+=1;cleanupCinematic();
    }
  }
  function renderRewards(round) {
    $('reward-rows').replaceChildren(...REWARDS.map((reward,points) => {
      const current=round && (points===0?round.phase==='failed':round.points===points && ['playing','capped'].includes(round.phase));
      const row=element('tr',undefined,current?'is-current':'');
      if (current) row.setAttribute('aria-current','true');
      row.append(element('td',points===0?'참가 보상':String(points)));
      const cell=element('td'),content=element('div',undefined,'trap-reward-name');
      content.append(element('span',reward || '보상 정보 확인 중',reward?'':'trap-unknown'));
      if (points) content.append(element('span',`+ 참가권 ${points}장`,'trap-bonus-tickets'));
      cell.append(content);row.append(cell);
      const button=element('button','보상받기','trap-row-claim');button.type='button';button.disabled=!current || busy || !!state.delivery;
      button.setAttribute('aria-label',`${points?`${points}포인트`:'참가'} 보상받기`);
      button.addEventListener('click',() => finish(points!==0));
      const controls=element('td');controls.append(button);row.append(controls);return row;
    }));
  }
  function renderAttendance() {
    $('attendance-rows').replaceChildren(...ATTENDANCE.map(item => {
      const row=element('tr');row.append(element('td',String(item.count)),element('td',item.reward));
      const claimed=state.claimed.includes(item.count);
      const button=element('button',claimed?'발송 완료':'보상받기','trap-row-claim');button.type='button';
      button.disabled=claimed || state.attempts<item.count || busy || !!state.delivery;
      button.setAttribute('aria-label',`${item.count}회 참가 보상 ${claimed?'발송 완료':'받기'}`);
      button.addEventListener('click',() => {
        sync();if (busy || state.delivery || state.attempts<item.count || state.claimed.includes(item.count)) return;
        state.claimed.push(item.count);addMail(item.reward,`${item.count}회 참가 보상`);save();render();message('우편함으로 보냈습니다.');
      });
      const cell=element('td');cell.append(button);row.append(cell);return row;
    }));
  }
  function uniqueId() {
    return window.crypto.randomUUID?.() || `${Date.now()}-${window.crypto.getRandomValues(new Uint32Array(2)).join('-')}`;
  }
  function addMail(name,source,tickets=0) {
    // Pending mail is never truncated; only completed history has a limit.
    state.mailbox.unshift({id:uniqueId(),name,source,tickets,at:Date.now()});
  }
  function playTone(ok) {
    if (!state.sound) return;
    try {
      soundContext ||= new (window.AudioContext || window.webkitAudioContext)();soundContext.resume().catch(() => {});
      const now=soundContext.currentTime;
      (ok?[523.25,659.25,783.99]:[246.94,196]).forEach((frequency,index) => {
        const oscillator=soundContext.createOscillator(),gain=soundContext.createGain();
        oscillator.connect(gain);gain.connect(soundContext.destination);oscillator.frequency.value=frequency;
        gain.gain.setValueAtTime(0,now+index*.085);gain.gain.linearRampToValueAtTime(.06,now+index*.085+.01);gain.gain.exponentialRampToValueAtTime(.001,now+index*.085+.22);
        oscillator.start(now+index*.085);oscillator.stop(now+index*.085+.24);
      });
    } catch { /* Sound is optional. */ }
  }
  function startRound() {
    sync();if (busy || state.delivery) return;
    if (state.round) { if (state.round.phase==='failed') finish(false);return; }
    const tier=currentRank();
    if (state.tickets<tier.cost) { openDialog('add');return; }
    state.tickets-=tier.cost;state.usedTickets+=tier.cost;state.attempts+=1;
    state.round={points:0,phase:'playing',moves:[],cost:tier.cost,started:Date.now()};save();render();
  }
  function drawPercent() {
    const values=new Uint32Array(1);
    do { window.crypto.getRandomValues(values); } while (values[0]>=4294967200);
    return values[0]%100;
  }
  function clearMotion() {
    $('event').classList.remove('is-animating');
    modes.forEach(button => {
      button.classList.remove('is-striking','is-hit');
      button.querySelector('.trap-mode-points').textContent='';
      button.querySelector('.trap-mode-confetti').replaceChildren();
    });
  }
  function scatterConfetti(button) {
    const colors=['#ffdf00','#63ddff','#ff687a','#a87aff'];
    button.querySelector('.trap-mode-confetti').replaceChildren(...Array.from({length:16},(_,index) => {
      const piece=element('i');
      piece.style.cssText=`--confetti-x:${(index*37)%101}%;--confetti-y:${18+(index*19)%54}%;--confetti-drift:${((index*23)%81)-40}px;--confetti-spin:${index%2?360:-280}deg;--confetti-delay:${(index%5)*35}ms;background:${colors[index%colors.length]}`;
      return piece;
    }));
  }
  async function attempt(key) {
    sync();if (busy || state.delivery || !MODES[key] || state.round?.phase!=='playing') return;
    const mode=MODES[key],round=state.round,boost=isSuper(round.points),rate=boost?mode.superRate:mode.rate;
    let roll;
    try { roll=drawPercent(); } catch { message('추첨을 시작하지 못했습니다.');return; }
    clearMotion();busy=true;const run=++animationRun,ok=roll<rate,gain=ok?Math.min(mode.gain,24-round.points):0;
    round.moves.push({mode:key,ok,gain,rate,super:boost});state.rolls+=1;
    if (ok) {state.success+=1;round.points+=gain;state.best=Math.max(state.best,round.points);if(round.points===24)round.phase='capped';}
    else round.phase='failed';
    // Refresh keeps the saved result instead of drawing again.
    save();render();
    if (!state.fast && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const button=modes.find(item => item.dataset.mode===key);
      $('event').classList.add('is-animating');button.classList.add('is-striking');
      await new Promise(resolve => setTimeout(resolve,160));
      if(run!==animationRun)return;
      button.classList.remove('is-striking');
      if(ok) {
        button.querySelector('.trap-mode-points').textContent=`${gain}P`;
        scatterConfetti(button);button.classList.add('is-hit');
      }
      playTone(ok);
      // The next attempt unlocks 0.5s after the press; the hit effect may finish while it plays.
      await new Promise(resolve => setTimeout(resolve,ok?340:140));
      if(run!==animationRun)return;
    } else playTone(ok);
    if(ok && !state.fast)setTimeout(() => {if(run===animationRun)clearMotion();},260);else clearMotion();
    busy=false;render();
    $('announcement').textContent=ok?`${mode.name} 트래핑 성공. ${gain}포인트 획득, 현재 ${round.points}포인트.`:`${mode.name} 트래핑 실패. 대회가 종료되었습니다.`;
    if (!ok) {if(state.fast)finish(false);else failedDialog();}
    else if(round.phase==='capped')completionDialog();
    else modes.find(button => button.dataset.mode===key).focus({preventScroll:true});
  }
  function prizeOption(title,name,tickets) {
    const option=element('div',undefined,'trap-prize-option');
    option.append(element('strong',title),image('/static/pack-opener/images/pack.png','',''),element('p',name));
    if(tickets)option.append(element('small',`+ 참가권 ${tickets}장`));
    return option;
  }
  function completionDialog() {
    if(state.round?.phase!=='capped')return;
    showDialog('complete','24P 달성');
    body.append(prizeOption('최종 보상',rewardAt(24),24));
    action('보상받기',() => finish(true));
  }
  function failedDialog() {
    const r=state.round;
    if(!r || r.phase!=='failed')return;
    failedPrompt=true;
    showDialog('failed','트래핑 실패');
    body.append(element('p','트래핑에 실패했습니다.','trap-fail-note'));
    action('참가 보상받기',() => finish(false));
  }
  function finish(success) {
    sync();if(busy || state.delivery || !state.round)return;
    const r=state.round;
    if(success?!['playing','capped'].includes(r.phase)||!r.points:r.phase!=='failed')return;
    const points=success?r.points:0,name=rewardAt(points);
    addMail(name,success?`${points}P 달성 보상`:'참가 보상',r.points);
    state.history.unshift({points:r.points,success,cost:r.cost,moves:r.moves,reward:name,at:Date.now()});state.history=state.history.slice(0,100);
    failedPrompt=false;state.round=null;save();closeDialog();render();message(success?'우편함으로 보냈습니다.':'트래핑 실패 · 참가 보상을 우편함으로 보냈습니다.');
  }
  function openMailbox() {
    showDialog('mailbox','우편함');
    if(!state.mailbox.length) {body.append(element('p','도착한 우편이 없습니다.','trap-empty'));action('확인',closeDialog);return;}
    body.append(element('p',`전체 우편 ${fmt(state.mailbox.length)}개`,'trap-mail-total'));
    state.mailbox.forEach(mail => {
      const row=element('div',undefined,'trap-mail-entry');row.append(image('/static/pack-opener/images/pack.png','',''));
      const detail=element('div');detail.append(element('strong',mail.name));
      if(mail.tickets)detail.append(element('p',`참가권 ${fmt(mail.tickets)}장`));
      detail.append(element('small',`${mail.source} · ${new Date(mail.at).toLocaleDateString('ko-KR')}`));
      const button=element('button','받기');button.type='button';button.setAttribute('aria-label',`${mail.name} 받기`);
      button.addEventListener('click',() => claimMail([mail.id]));row.append(detail,button);body.append(row);
    });
    action('모두 받기',() => claimMail(state.mailbox.map(mail => mail.id)));
  }
  const withMailLock = callback => navigator.locks?.request ? navigator.locks.request(`${KEY}.mail`,callback) : Promise.resolve().then(callback);
  async function claimMail(ids) {
    if(busy)return;
    busy=true;render();dialog.querySelectorAll('button').forEach(button => {button.disabled=true;});
    try {
      await withMailLock(() => {
        sync();
        if(state.delivery)return;
        const selected=new Set(ids),mails=state.mailbox.filter(mail => selected.has(mail.id));
        if(!mails.length)return;
        // Credit tickets once, and persist the reveal in the same saved object.
        const tickets=mails.reduce((sum,mail) => sum+mail.tickets,0);
        if(!int(state.tickets+tickets))throw new Error('ticket_limit');
        state.tickets+=tickets;
        state.mailbox=state.mailbox.filter(mail => !selected.has(mail.id));
        state.received=[...mails,...state.received].slice(0,200);
        state.delivery={id:uniqueId(),mails,at:Date.now()};save();
      });
      busy=false;closeDialog();render();
      if(state.delivery)playTone(true);
      else openMailbox();
    } catch {busy=false;render();openMailbox();}
    finally {dialog.querySelectorAll('button').forEach(button => {button.disabled=false;});}
  }
  const PACK_ID_PREFIX = 'PAID_WEBG_';
  function packIdFor(mail) {
    let match = mail.source.match(/^(\d+)P 달성 보상$/);
    if (match && Number(match[1]) >= 1 && Number(match[1]) <= 24) return `${PACK_ID_PREFIX}261015_TRAPPINGGOD_REWARD_${match[1].padStart(2,'0')}`;
    if (mail.source === '참가 보상') return `${PACK_ID_PREFIX}TRAPPINGGOD_NORMAL_REWARD_261015`;
    match = mail.source.match(/^(\d+)회 참가 보상$/);
    if (match && ATTENDANCE.some(item => item.count === Number(match[1]))) return `${PACK_ID_PREFIX}NG_TRAPPINGGOD_261015_ACCREWARD_${match[1]}`;
    // Pre-v2 mail carries only the reward text.
    const index = REWARDS.indexOf(mail.name);
    if (index === 0) return `${PACK_ID_PREFIX}TRAPPINGGOD_NORMAL_REWARD_261015`;
    if (index > 0) return `${PACK_ID_PREFIX}261015_TRAPPINGGOD_REWARD_${String(index).padStart(2,'0')}`;
    const attendance = ATTENDANCE.find(item => item.reward === mail.name);
    return attendance ? `${PACK_ID_PREFIX}NG_TRAPPINGGOD_261015_ACCREWARD_${attendance.count}` : null;
  }
  async function drawReceipt() {
    const receipt = state.delivery;
    if (!receipt || receipt.result || drawing) return;
    drawing = true; drawFailed = false;
    const quantities = new Map();
    receipt.mails.forEach(mail => {
      const id = packIdFor(mail);
      if (id) quantities.set(id,(quantities.get(id) || 0)+1);
    });
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(),25000);
    try {
      let rewards = [];
      if (quantities.size) {
        const response = await fetch('/api/trapping-simulator/draw',{
          method:'POST',signal:controller.signal,
          headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="fimobook-page-token"]')?.content || ''},
          body:JSON.stringify({packs:[...quantities].map(([pack,quantity]) => ({pack,quantity}))}),
        });
        if (!response.ok) throw new Error('draw_failed');
        rewards = (await response.json()).rewards;
        if (!Array.isArray(rewards)) throw new Error('draw_failed');
      }
      // Persist the drawn result so a refresh restores it instead of redrawing.
      await withMailLock(() => {
        sync();
        if (state.delivery?.id === receipt.id && !state.delivery.result) {
          state.delivery.result = {rewards};
          // Accumulate the received value once, together with the saved reveal.
          rewards.forEach(reward => {
            if (reward.kind === 'player') {
              state.gain.count += 1;
              if (Number(reward.price) > 0) state.gain.players += Number(reward.price);
            } else if (String(reward.name).startsWith('MP')) state.gain.mp += Number(reward.count) || 0;
          });
          save();
        }
      });
    } catch { drawFailed = true; }
    finally { clearTimeout(timeout); drawing = false; render(); }
  }
  function receiptRewards(receipt) {
    const players = [], items = new Map();
    const addItem = (kind,name,count) => {
      const key = `${kind}:${name}`, existing = items.get(key);
      if (existing) existing.count += count; else items.set(key,{kind,name,count});
    };
    receipt.result.rewards.forEach(reward => {
      if (reward.kind === 'player') players.push(reward);
      else addItem(reward.name.startsWith('MP') ? 'mp' : 'pack',reward.name,Number(reward.count) || 1);
    });
    // Mail without an official probability table is still shown as the awarded pack.
    receipt.mails.forEach(mail => {
      if (packIdFor(mail)) return;
      const quantity = mail.name.match(/\s+[x×](\d+)$/i);
      addItem('pack',quantity ? mail.name.slice(0,quantity.index) : mail.name,quantity ? Number(quantity[1]) : 1);
    });
    players.sort((a,b) => b.ovr-a.ovr || String(a.playerKor).localeCompare(String(b.playerKor),'ko') || Number(a.cid || 0)-Number(b.cid || 0));
    const ordered = [...items.values(),...players];
    const tickets = receipt.mails.reduce((sum,mail) => sum+mail.tickets,0);
    return {steps:ordered,summary:tickets ? [...ordered,{kind:'ticket',name:'트래핑 참가권',count:tickets}] : ordered};
  }
  function rewardCard(reward) {
    if (reward.kind === 'player') {
      const card = element('div',undefined,'player-card');
      card.setAttribute('aria-label',`${reward.season} ${reward.playerKor} ${reward.ovr} ${reward.position || ''} ${reward.enhance}진화`);
      window.FimoCardArt.render(card,reward,{ovr:reward.ovr,enhance:reward.enhance});
      return card;
    }
    const card = element('div',undefined,'item-reward');
    const icon = reward.kind === 'ticket' ? '/static/trapping-sim/ticket.webp'
      : reward.kind === 'mp' ? '/static/pack-opener/images/mp-reward-transparent.png' : '/static/pack-opener/images/pack.png';
    card.append(image(icon,reward.kind === 'mp' ? 'item-icon mp-icon' : 'item-icon'),element('strong',reward.name));
    if (reward.count > 1 || reward.kind === 'ticket') card.append(element('small',`× ${fmt(reward.count)}`));
    return card;
  }
  function priceCaption(reward) {
    const caption = element('div',undefined,'flow-reward-label reward-price'),line = element('span',undefined,'reward-price-line');
    const value = Number(reward.price);
    line.append(image('/static/pack-opener/images/mp-token-transparent.png','reward-price-coin'),
      element('span',Number.isFinite(value) && value > 0 ? `${fmt(value)} MP` : '가격 정보 없음','reward-price-amount'));
    caption.append(element('small','현재 가치','reward-price-heading'),line);
    return caption;
  }
  function fitRewardScreen() {
    if($('reward-screen').hidden || !frame.clientWidth)return;
    const fullscreen=document.fullscreenElement===frame;
    const scale=fullscreen?Math.min(frame.clientWidth/1024,frame.clientHeight/576):frame.clientWidth/1024;
    frame.style.setProperty('--stage-scale',String(scale));frame.classList.add('stage-fitted');
  }
  const SCOREBOARD_START = 7; // Same keyframe as the pack opener's cinematic videos.
  let cinematicRun = 0;
  const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
  function setHint(hero,kind) {
    const node=$('reveal-hint');
    if(node.dataset.kind===kind)return;
    node.dataset.kind=kind;node.replaceChildren();
    if(!kind)return;
    if(kind==='position'){node.append(element('span',hero.position || '','hint-position'));return;}
    const src=kind==='flag'?hero.flag:hero.club,label=kind==='flag'?hero.nation:hero.team;
    if(src)node.append(image(src,'',label));else if(label)node.append(element('span',label,'hint-text'));
  }
  function cleanupCinematic() {
    const video=$('cinematic-video');
    video.onended=null;video.pause();video.classList.remove('visible');
    video.removeAttribute('src');video.dataset.source='';video.load();
    $('hero-reward').classList.remove('visible');$('hero-reward').replaceChildren();
    $('reveal-hint').dataset.kind='';$('reveal-hint').replaceChildren();
    $('cinematic-next').hidden=true;
  }
  function endCinematic(revealed) {
    if(!flow || flow.mode!=='cinematic')return;
    cinematicRun+=1;cleanupCinematic();
    flow.heroRevealed=revealed;flow.index=0;
    const steps=receiptRewards(state.delivery).steps,heroIndex=steps.findIndex(reward => reward.kind==='player');
    const remaining=steps.length-(revealed && heroIndex>=0?1:0);
    flow.mode=remaining>0?'step':'summary';
    renderReceipt();
  }
  async function playCinematic(receipt) {
    const hero=receiptRewards(receipt).steps.find(reward => reward.kind==='player'),run=++cinematicRun;
    const current=() => run===cinematicRun && flow?.id===receipt.id && flow.mode==='cinematic';
    const video=$('cinematic-video');
    flow.started=true;
    video.muted=true;video.playsInline=true;video.loop=false;
    video.src=`/static/pack-opener/videos/cinematic-v1/packopening_${hero.animation || 'DEFAULT26'}_cinematic.mp4`;video.load();
    await Promise.all([hero.card,hero.face,hero.flag,hero.club].filter(Boolean).map(src => new Promise(resolve => {
      const img=new Image(),timeout=setTimeout(resolve,8000);
      img.onload=img.onerror=() => {clearTimeout(timeout);resolve();};img.src=src;
    })));
    if(!current())return;
    $('reward-stage').dataset.phase='tunnel';video.classList.add('visible');
    try { await video.play(); } catch { if(current())endCinematic(false);return; }
    let shown=false,revealed=false,lastTime=-1,lastProgress=performance.now();
    video.onended=() => {
      if(!current())return;
      if(!revealed){endCinematic(false);return;}
      video.currentTime=SCOREBOARD_START;video.play().catch(() => {});
    };
    $('cinematic-next').hidden=false;$('cinematic-next').textContent='건너뛰기';
    while(current()) {
      await sleep(100);
      if(!current())return;
      if(video.error){endCinematic(false);return;}
      const time=video.currentTime;
      if(time!==lastTime){lastTime=time;lastProgress=performance.now();}
      else if(performance.now()-lastProgress>8000){endCinematic(revealed);return;}
      if(time<SCOREBOARD_START && !shown) {
        const ratio=time/SCOREBOARD_START;
        setHint(hero,ratio>=.23 && ratio<.43?'flag':ratio>=.46 && ratio<.65?'position':ratio>=.68 && ratio<.88?'club':'');
      } else {
        if(!shown){shown=true;$('reward-stage').dataset.phase='reveal';setHint(hero,'');}
        if(time>=SCOREBOARD_START+.35 && !revealed) {
          revealed=true;$('reward-stage').dataset.phase='hero';
          const node=$('hero-reward');node.replaceChildren(rewardCard(hero));node.classList.add('visible');
          $('reward-flash').classList.remove('flash');void $('reward-flash').offsetWidth;$('reward-flash').classList.add('flash');
          $('cinematic-next').textContent='다음';flow.heroRevealed=true;
          playTone(true);
        }
      }
    }
  }
  function renderReceipt() {
    const receipt=state.delivery;
    if(!receipt)return;
    const first=visibleReceiptId!==receipt.id;
    if(first)returnScrollY=window.scrollY;
    // Back from the reward screen should land on the game, not leave the page.
    if(history.state?.trapReceipt!==receipt.id)history.pushState({trapReceipt:receipt.id},'');
    closeDialog();$('game-view').hidden=true;$('reward-screen').hidden=false;
    const stage=$('reward-stage'),next=byId('reward-next'),status=byId('reward-flow-status'),replay=byId('flow-replay'),reveal=byId('reveal-all');
    byId('reward-flow').hidden=false;byId('reward-flow-title').textContent='보상 획득';
    if(!receipt.result) {
      stage.dataset.phase='reward-summary';
      byId('reward-step').hidden=true;byId('reward-summary').hidden=true;reveal.hidden=true;next.hidden=true;
      replay.hidden=!drawFailed;replay.textContent='다시 시도';
      status.textContent=drawFailed?'보상을 불러오지 못했어요':'보상을 여는 중이에요…';
      visibleReceiptId=receipt.id;fitRewardScreen();
      if(!drawing && !drawFailed)drawReceipt();
      return;
    }
    replay.textContent='다시 보기';
    const view=receiptRewards(receipt);
    if(!flow || flow.id!==receipt.id) {
      const hasPlayer=view.steps.some(reward => reward.kind==='player');
      flow={id:receipt.id,index:0,mode:hasPlayer?'cinematic':view.steps.length>0?'step':'summary',started:false,heroRevealed:false};
    }
    // After the opening, the featured player is not repeated in the pack-by-pack step flow.
    const heroIndex=flow.heroRevealed?view.steps.findIndex(reward => reward.kind==='player'):-1;
    view.steps=view.steps.filter((reward,index) => index!==heroIndex);
    byId('reward-flow').hidden=flow.mode==='cinematic';
    byId('reward-step').hidden=flow.mode!=='step';byId('reward-summary').hidden=flow.mode!=='summary';
    if(flow.mode==='cinematic') {
      byId('reveal-all').hidden=true;byId('reward-next').hidden=true;replay.hidden=true;
      visibleReceiptId=receipt.id;fitRewardScreen();
      if(first)$('reward-screen').scrollIntoView({block:'start',behavior:'instant'});
      if(!flow.started)playCinematic(receipt);
      return;
    }
    if(flow.mode==='step') {
      stage.dataset.phase='reward-step';
      const reward=view.steps[flow.index],remaining=view.steps.length-flow.index-1;
      const current=byId('reward-current');current.replaceChildren(rewardCard(reward));
      current.dataset.kind=reward.kind==='player'?'player':'item';
      current.dataset.singleItem='false';
      if(reward.kind==='player')current.append(priceCaption(reward));
      current.classList.remove('reward-arrives');void current.offsetWidth;current.classList.add('reward-arrives');
      byId('reward-pack').hidden=remaining===0;byId('reward-remaining').textContent=String(remaining);
      byId('reward-pack').setAttribute('aria-label',remaining?`다음 보상 열기 · ${remaining}개 남음`:'전체 보상 보기');
      current.setAttribute('aria-label',`${reward.name || reward.playerKor} · ${remaining?'다음 보상 확인':'전체 보상 보기'}`);
      status.textContent=remaining?`팩을 눌러 다음 보상을 확인하세요 · ${remaining}개 남음`:'팩을 눌러 전체 보상을 확인하세요';
      // Same as the pack opener: a lone reward shows Next instead of Open All.
      const single=view.steps.length===1;
      reveal.hidden=single;next.hidden=!single;next.textContent='다음';next.disabled=busy;replay.hidden=true;
      if(single)status.textContent='보상을 획득했어요 · 다음을 눌러 계속하세요';
    } else {
      stage.dataset.phase='reward-summary';
      const rewards=view.summary,grid=byId('reward-summary-grid');
      grid.dataset.itemsOnly=String(rewards.every(reward => reward.kind!=='player'));
      grid.dataset.count=String(rewards.length);grid.dataset.many=String(rewards.length>3);
      grid.style.setProperty('--reward-columns',Math.min(rewards.length,5));
      grid.replaceChildren(...rewards.map(reward => {
        const slot=element('div',undefined,'flow-summary-reward');slot.append(rewardCard(reward));
        if(reward.kind==='player')slot.append(priceCaption(reward));
        return slot;
      }));
      status.textContent=`총 ${fmt(rewards.length)}개 보상 획득`;
      reveal.hidden=true;replay.hidden=true;next.hidden=false;next.textContent='다음';next.disabled=busy;
    }
    visibleReceiptId=receipt.id;fitRewardScreen();
    if(first) {
      byId('reward-summary').scrollTop=0;
      $('reward-screen').scrollIntoView({block:'start',behavior:'instant'});
      $('reward-flash').classList.remove('flash');void $('reward-flash').offsetWidth;$('reward-flash').classList.add('flash');
    }
  }
  function advanceFlow() {
    if(!flow || flow.mode!=='step' || !state.delivery?.result)return;
    const steps=receiptRewards(state.delivery).steps;
    const count=steps.length-(flow.heroRevealed && steps.some(reward => reward.kind==='player')?1:0);
    if(++flow.index>=count)flow.mode='summary';
    renderReceipt();
  }
  async function finishReceipt() {
    if(busy || !state.delivery)return;
    const receiptId=state.delivery.id,scroll=returnScrollY;
    busy=true;byId('reward-next').disabled=true;
    try {
      if(document.fullscreenElement===frame)await document.exitFullscreen().catch(() => {});
      await withMailLock(() => {sync();if(state.delivery?.id===receiptId){state.delivery=null;save();}});
    } finally {
      busy=false;render();
      if(!state.delivery){
        window.scrollTo({top:scroll,behavior:'instant'});$('mailbox-button').focus({preventScroll:true});
        if(history.state?.trapReceipt)history.back();
      }
    }
  }
  function addDialog() {
    showDialog('add','참가권 추가');
    const label=element('label','추가할 참가권');
    const input=element('input');input.type='number';input.min='1';input.max='1000000';input.step='1';input.value='1000';input.inputMode='numeric';label.append(input);body.append(label);
    const choices=element('div',undefined,'trap-quantity-options');
    [100,1000,10000].forEach(amount => {const button=element('button',`${fmt(amount)}장`);button.type='button';button.addEventListener('click',() => {input.value=String(amount);update();});choices.append(button);});body.append(choices);
    const cost=element('p',undefined,'trap-add-cost');body.append(cost);
    const error=element('p',undefined,'trap-dialog-error');error.setAttribute('role','alert');body.append(error);
    action('취소',closeDialog,true);
    const submit=action('추가하기',() => {
      sync();const count=Number(input.value);
      if(!Number.isSafeInteger(count) || count<1 || count>1000000 || !int(state.tickets+count)){error.textContent='수량을 확인해 주세요.';return;}
      state.tickets+=count;save();render();closeDialog();message(`참가권 ${fmt(count)}장 추가`);
    });
    function update(){
      const n=Number(input.value),valid=Number.isSafeInteger(n) && n>=1 && n<=1000000;
      submit.disabled=!valid;
      // Rough cash value: 1,500 tickets = 25,000 won.
      cost.textContent=valid?`현금 약 ${fmt(Math.round(n*WON_PER_TICKET/10)*10)}원 (1,500장 = 25,000원 기준)`:'';
    }
    input.addEventListener('input',update);update();
  }
  function openDialog(name) {
    sync();
    if(busy || state.delivery)return;
    if(name==='mailbox'){openMailbox();return;}
    if(name==='add'){addDialog();return;}
    if(name==='rank') {
      showDialog(name,'등급 선택');
      const options=element('div',undefined,'trap-rank-options');options.setAttribute('role','radiogroup');options.setAttribute('aria-label','등급');
      RANKS.forEach((tier,index) => {
        const button=element('button');button.type='button';button.setAttribute('role','radio');button.setAttribute('aria-checked',String(rankIndex()===index));
        const icon=element('i',undefined,'bi bi-award-fill');icon.setAttribute('aria-hidden','true');
        button.append(icon,element('strong',tier.name),element('span',`참가권 ${tier.cost}장`));
        button.addEventListener('click',() => {sync();state.rankOverride=index;save();render();closeDialog();});options.append(button);
      });body.append(options);return;
    }
    if(name==='odds') {
      showDialog(name,'트래핑 확률');
      body.innerHTML='<table><thead><tr><th>트래핑</th><th>획득 P</th><th>일반</th><th>슈퍼</th></tr></thead><tbody><tr><td>가슴</td><td>+3</td><td>30%</td><td>50%</td></tr><tr><td>머리</td><td>+2</td><td>50%</td><td>65%</td></tr><tr><td>발</td><td>+1</td><td>70%</td><td>80%</td></tr></tbody></table>';action('확인',closeDialog);return;
    }
    if(name==='history') {
      showDialog(name,'참여 내역');
      if(!state.history.length)body.append(element('p','참여 내역이 없습니다.','trap-empty'));
      state.history.forEach(entry => {
        const row=element('div',undefined,'trap-history-entry'),detail=element('div');
        detail.append(element('p',`${entry.success?'보상 발송':'트래핑 실패'} · ${new Date(entry.at).toLocaleString('ko-KR')}`),element('p',entry.reward));
        row.append(element('strong',`${entry.points}P`),detail);body.append(row);
      });action('확인',closeDialog);return;
    }
    if(name==='reset') {
      showDialog(name,'시뮬레이터 초기화');body.append(element('p','진행 중인 대회, 우편함과 기록을 초기화할까요?'));
      action('취소',closeDialog,true);action('초기화',() => {const revision=state.revision;state={...fresh(),revision};animationRun+=1;save();render();closeDialog();});
    }
  }
  document.querySelectorAll('[data-dialog]').forEach(button => button.addEventListener('click',() => openDialog(button.dataset.dialog)));
  document.querySelectorAll('[data-scroll]').forEach(button => button.addEventListener('click',() => document.getElementById(button.dataset.scroll).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'})));
  modes.forEach(button => button.addEventListener('click',() => attempt(button.dataset.mode)));
  $('start').addEventListener('click',startRound);$('collect').addEventListener('click',() => finish(true));
  $('fast').addEventListener('change',event => {sync();state.fast=event.target.checked;save();});
  $('sound').addEventListener('click',() => {sync();state.sound=!state.sound;save();render();if(state.sound)playTone(true);});
  byId('reward-next').addEventListener('click',() => {
    if(flow?.mode==='step'){flow.mode='summary';renderReceipt();} else finishReceipt();
  });
  byId('reward-pack').addEventListener('click',advanceFlow);
  byId('reward-current').addEventListener('click',advanceFlow);
  byId('reveal-all').addEventListener('click',() => {if(flow){flow.mode='summary';renderReceipt();}});
  byId('flow-replay').addEventListener('click',() => {if(drawFailed){drawFailed=false;renderReceipt();}});
  $('cinematic-next').addEventListener('click',() => endCinematic(!!flow?.heroRevealed));
  $('reward-stage').addEventListener('click',event => {
    if(event.target.closest('button,a,input,select,summary'))return;
    if(flow?.mode==='cinematic')endCinematic(!!flow.heroRevealed);else advanceFlow();
  });
  $('reward-fullscreen').addEventListener('click',async () => {
    try {if(document.fullscreenElement===frame)await document.exitFullscreen();else await frame.requestFullscreen();}catch{/* Fullscreen is optional. */}
  });
  window.addEventListener('popstate',() => {
    // The reward is already credited; going back is the same as pressing Next.
    if(state.delivery && !$('reward-screen').hidden)finishReceipt();
  });
  document.addEventListener('fullscreenchange',fitRewardScreen);
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(fitRewardScreen).observe(frame);
  window.addEventListener('resize',fitRewardScreen);
  window.addEventListener('storage',event => {
    if(event.key!==KEY)return;
    const wasMailbox=dialogName==='mailbox';
    state=read()||fresh();animationRun+=1;clearMotion();busy=false;closeDialog();render();
    if(wasMailbox && !state.delivery)openMailbox();
  });
  if(needsMigration)save();
  render();
  if(state.round?.phase==='failed' && !state.delivery) {if(state.fast)finish(false);else failedDialog();}
})();
