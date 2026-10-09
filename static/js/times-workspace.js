(() => {
  const signedIn = document.currentScript.dataset.signedIn === 'true';
  const cards = JSON.parse(document.getElementById('renewal-card-data').textContent);
  const byName = new Map(cards.map(card => [card.name, card]));
  const hours = {0:[0,2,8,10,12,14,16,18,20,22],1:[1,7,9,11,13,15,17,19,21,23]};
  const body = document.getElementById('times-body');
  const watch = document.getElementById('watch-cards');
  const search = document.getElementById('times-search');
  const filter = document.getElementById('interest-filter');
  let onlySaved = false;
  let saved = new Set();
  let visible = [];
  let ready = !signedIn;
  let currentMinute = -1;
  const now = () => Date.now() + (window.fimoRenewal?.clockOffset || 0);
  const text = (tag, value, className) => { const el = document.createElement(tag); el.textContent = value; if (className) el.className = className; return el; };
  function image(card) { const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy'; img.src = '/static/times/' + String(card.image || '').replace(/^\.\//,''); return img; }
  function timing(card, stamp = now()) {
    if (!card?.available) return null;
    const korea = new Date(stamp + 9*3600000);
    const day = Date.UTC(korea.getUTCFullYear(),korea.getUTCMonth(),korea.getUTCDate());
    let next=Infinity, previous=-Infinity, updating=false;
    for (let offset=-1;offset<=1;offset++) for (const hour of hours[card.eo] || []) {
      const start=day+offset*86400000+hour*3600000+card.min*60000+(card.sec||0)*1000-9*3600000;
      if(start>stamp) next=Math.min(next,start); else previous=Math.max(previous,start);
      if(Number.isFinite(card.endMin)) {
        const end=start+(card.endMin-card.min)*60000+((card.endSec||0)-(card.sec||0))*1000;
        if(stamp>=start&&stamp<=end) updating=true;
      }
    }
    const secs=Math.max(0,Math.ceil((next-stamp)/1000));
    return {next,previous,secs,updating,progress:Math.max(0,Math.min(1,(stamp-previous)/(next-previous)))};
  }
  function countdown(value) {
    if (!value) return '정보 없음';
    if (value.updating) return '갱신 중';
    const h=Math.floor(value.secs/3600), m=Math.floor(value.secs%3600/60), sec=value.secs%60;
    return `${h ? h+'시간 ' : ''}${m ? m+'분 ' : ''}${sec}초 후 갱신`;
  }
  function listTiming(card, stamp = now()) {
    if (!card?.available) return null;
    const korea = new Date(stamp + 9*3600000);
    const hour = korea.getUTCHours();
    if (!(hours[card.eo] || []).includes(hour)) return null;
    const start = Date.UTC(korea.getUTCFullYear(), korea.getUTCMonth(), korea.getUTCDate(), hour, card.min, card.sec || 0) - 9*3600000;
    if (Number.isFinite(card.endMin)) {
      const end = start + (card.endMin-card.min)*60000 + ((card.endSec||0)-(card.sec||0))*1000;
      if (stamp >= start && stamp <= end) return {updating:true,secs:0};
    }
    if (stamp >= start) return null;
    return {updating:false,secs:Math.ceil((start-stamp)/1000)};
  }
  function timeLabel(stamp) { return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(stamp); }
  function recurrence(card) {
    let value=`${card.eo===0?'짝수시':'홀수시'} ${card.min}분`;
    if(card.sec) value+=` ${card.sec}초`;
    if(Number.isFinite(card.endMin)) value+=` ~ ${card.endMin}분${card.endSec?' '+card.endSec+'초':''}`;
    return value;
  }
  function footer(message, error=false) {
    const el=document.getElementById('interest-status');
    el.textContent=message;el.classList.toggle('is-error',error);
  }
  async function save(name, enabled, button) {
    if (!signedIn) { location.href='/login?next=/times';return; }
    button.disabled=true;footer('저장 중');
    try { await window.fimoRenewal.save(name,enabled); footer(enabled?'관심에 저장했습니다':'관심을 해제했습니다'); }
    catch(error) { button.disabled=false;footer(error.message||'저장하지 못했습니다',true); }
  }
  function renderRows() {
    const query=search.value.trim().toUpperCase();
    visible=cards.filter(card=>(!onlySaved||saved.has(card.name))&&(!query||[card.name,...(card.otherNames||[])].some(name=>String(name).toUpperCase().includes(query))));
    body.replaceChildren();document.getElementById('times-count').textContent=visible.length;
    if (!visible.length) { body.append(text('div',onlySaved?'관심 목록이 비어 있습니다':'검색 결과가 없습니다','times-empty'));return; }
    const fragment=document.createDocumentFragment();
    for (const card of visible) {
      const row=text('div','','table-row');row.dataset.name=card.name;row.classList.toggle('status-dim',!card.available);
      const pic=text('div','','image-col');const img=image(card);img.className='card-img';pic.append(img);row.append(pic);
      const name=text('div','','name-col');name.append(text('div',card.name,'card-name'));
      const star=text('button',saved.has(card.name)?'★':'☆','season-star');star.type='button';star.dataset.name=card.name;
      star.setAttribute('aria-label',`${card.name} ${saved.has(card.name)?'관심 해제':'관심 등록'}`);star.setAttribute('aria-pressed',String(saved.has(card.name)));
      star.disabled=!card.available||!ready;star.addEventListener('click',()=>save(card.name,!saved.has(card.name),star));name.append(star);row.append(name);
      row.append(text('div',recurrence(card),'time-col time-text'));
      const remain=text('div','','remain-col');remain.append(text('span','—','remain'));row.append(remain);fragment.append(row);
    }
    body.append(fragment);updateClocks();
  }
  function renderWatch() {
    watch.replaceChildren();document.getElementById('watch-count').textContent=saved.size;
    document.getElementById('watch-empty').hidden=saved.size>0;
    const list=[...saved].map(name=>byName.get(name)||{name,available:false}).sort((a,b)=>(timing(a)?.next||Infinity)-(timing(b)?.next||Infinity));
    for (const card of list) {
      const item=text('div','','interest-item');item.dataset.name=card.name;
      item.append(text('strong',card.name),text('time',countdown(timing(card))));
      const remove=text('button','×');remove.type='button';remove.setAttribute('aria-label',`${card.name} 관심 해제`);remove.addEventListener('click',()=>save(card.name,false,remove));item.append(remove);watch.append(item);
    }
    updateClocks();
  }
  function updateClocks() {
    const stamp=now();document.getElementById('times-clock').textContent=timeLabel(stamp);
    for (const row of body.querySelectorAll('.table-row[data-name]')) {
      const value=listTiming(byName.get(row.dataset.name),stamp), remain=row.querySelector('.remain');
      remain.textContent=value ? countdown(value) : '—';remain.classList.toggle('is-idle',!value);remain.classList.toggle('soon',Boolean(value&&value.secs<=60));remain.classList.toggle('is-updating',Boolean(value?.updating));
    }
    for (const item of watch.children) item.querySelector('time').textContent=countdown(timing(byName.get(item.dataset.name),stamp));
    const minute=Math.floor(stamp/60000);
    if (currentMinute!==minute) { currentMinute=minute;[...watch.children].sort((a,b)=>(timing(byName.get(a.dataset.name),stamp)?.next||Infinity)-(timing(byName.get(b.dataset.name),stamp)?.next||Infinity)).forEach(item=>watch.append(item)); }
  }
  function syncInterests() { ready=true;saved=new Set(window.fimoRenewal.names);renderRows();renderWatch(); }
  function pushState() {
    const state=window.fimoRenewal?.push||{enabled:false},button=document.getElementById('push-toggle');if (!button) return;
    document.getElementById('push-state').textContent=state.busy?'연결 중':state.enabled?'갱신 알림 켜짐':'갱신 알림 꺼짐';
    document.getElementById('push-detail').textContent=state.error||state.help||'';
    button.disabled=Boolean(state.busy||!window.fimoRenewal?.loaded);document.getElementById('push-toggle-label').textContent=state.busy?'연결 중':state.enabled?'알림 켜짐':'알림 켜기';button.setAttribute('aria-pressed',String(Boolean(state.enabled)));button.querySelector('i').className=state.enabled?'bi bi-bell-fill':'bi bi-bell';button.title=state.enabled?'눌러서 갱신 알림 끄기':'갱신 알림 켜기';button.setAttribute('aria-label',button.title);
    const test=document.getElementById('push-test');test.hidden=!state.enabled;test.disabled=Boolean(state.busy);
  }
  const quietForm=document.getElementById('quiet-form');
  function quietState() {
    if(!quietForm)return;
    const settings=window.fimoRenewal?.quiet;
    if(!settings?.loaded)return;
    document.getElementById('quiet-enabled').checked=settings.enabled;
    document.getElementById('quiet-start').value=settings.start;
    document.getElementById('quiet-end').value=settings.end;
    document.getElementById('quiet-summary').textContent=settings.enabled?`방해금지 ${settings.start} ~ ${settings.end}`:'방해금지 꺼짐';
    quietForm.querySelectorAll('input,button').forEach(el=>el.disabled=false);
  }
  quietForm?.addEventListener('input',()=>{document.getElementById('quiet-status').textContent='변경 후 저장해주세요.';});
  quietForm?.addEventListener('submit',async event=>{
    event.preventDefault();
    const status=document.getElementById('quiet-status'),button=document.getElementById('quiet-save');
    if(button.disabled)return;
    button.disabled=true;status.textContent='저장 중';
    try{
      await window.fimoRenewal.saveQuiet({enabled:document.getElementById('quiet-enabled').checked,start:document.getElementById('quiet-start').value,end:document.getElementById('quiet-end').value});
      status.textContent='저장했습니다.';
    }catch(error){status.textContent=error.message;}
    finally{button.disabled=false;}
  });
  window.addEventListener('renewal-quiet-changed',quietState);
  window.addEventListener('renewal-quiet-error',()=>{if(quietForm)document.getElementById('quiet-status').textContent='설정을 불러오지 못했습니다. 새로고침해주세요.';});
  quietState();
  const alertSettings=document.querySelector('.alert-settings');
  document.addEventListener('click',event=>{if(alertSettings?.open&&!alertSettings.contains(event.target))alertSettings.open=false;});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&alertSettings?.open){alertSettings.open=false;alertSettings.querySelector('summary').focus();}});
  search.addEventListener('input',renderRows);
  filter.addEventListener('click',()=>{onlySaved=!onlySaved;filter.setAttribute('aria-pressed',String(onlySaved));renderRows();});
  document.getElementById('push-toggle')?.addEventListener('click',()=>window.fimoRenewal.togglePush());
  document.getElementById('push-test')?.addEventListener('click',async()=>{const button=document.getElementById('push-test');button.disabled=true;try{await window.fimoRenewal.testPush();}finally{button.disabled=false;}});
  window.addEventListener('renewal-interests-changed',syncInterests);
  window.addEventListener('renewal-push-changed',pushState);
  window.addEventListener('renewal-interests-error',()=>footer('관심 목록을 불러오지 못했습니다. 새로고침해주세요.',true));
  if(window.fimoRenewal?.loaded)syncInterests();else { renderRows();renderWatch(); }
  if(signedIn)pushState();
  setInterval(updateClocks,1000);
})();
