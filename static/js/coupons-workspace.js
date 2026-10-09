(() => {
  // Put the existing ad below the list on mobile, preserving DOM focus order.
  const ad=document.querySelector('.coupon-page > .fimo-ad-shell');
  if(ad){
    const anchor=document.createComment('coupon-ad-position');ad.before(anchor);
    const mobile=matchMedia('(max-width:640px)');
    const place=()=>{if(mobile.matches)document.querySelector('.coupon-guide').before(ad);else anchor.after(ad);};
    mobile.addEventListener('change',place);place();
  }
  const cards=[...document.querySelectorAll('.coupon-card')];
  const active=cards.filter(card=>card.dataset.active==='true');
  const feedback=document.getElementById('coupon-feedback');
  const copyAll=document.getElementById('coupon-copy-all');
  const copiedKey='fimobook-copied-coupons';
  let copied=new Set(),filter='active',polling=false;
  let known=new Set(active.map(card=>card.dataset.code));
  try{copied=new Set(JSON.parse(localStorage.getItem(copiedKey)||'[]'));}catch(_){}
  function message(value,error=false){feedback.textContent=value;feedback.classList.toggle('is-error',error);}
  function filterCards(){
    cards.forEach(card=>card.hidden=filter==='active'&&card.dataset.active!=='true');
    document.getElementById('coupon-filter-empty').hidden=filter!=='active'||active.length>0||cards.length===0;
  }
  function mark(card){
    copied.add(card.dataset.code);card.classList.add('is-copied');
    try{localStorage.setItem(copiedKey,JSON.stringify([...copied].slice(-100)));}catch(_){}
  }
  async function copy(value,button,list){
    button.disabled=true;
    try{
      await navigator.clipboard.writeText(value);list.forEach(mark);
      button.textContent='복사 완료';button.classList.add('is-success');message(list.length>1?`쿠폰 코드 ${list.length}개를 줄별로 복사했습니다.`:'복사했습니다. 쿠폰 등록에서 붙여 넣으세요.');
      window.fimoAnalytics?.track?.('coupon_copy',{source_surface:list.length>1?'coupon_copy_all':'coupon_list'});
      setTimeout(()=>{button.textContent=button===copyAll?'모두 복사':'복사';button.classList.remove('is-success');},1500);
    }catch(_){
      if(list.length===1){const range=document.createRange();range.selectNodeContents(list[0].querySelector('.code-chip'));const selection=getSelection();selection.removeAllRanges();selection.addRange(range);}
      message('복사하지 못했습니다. 코드를 선택해 직접 복사해주세요.',true);
    }finally{button.disabled=false;}
  }
  for(const card of cards){
    const button=card.querySelector('.copy-btn');
    if(copied.has(card.dataset.code)&&card.dataset.active==='true'){card.classList.add('is-copied');button.textContent='복사';}
    button.addEventListener('click',()=>copy(card.dataset.code,button,[card]));
  }
  copyAll.disabled=active.length===0;
  copyAll.addEventListener('click',()=>copy(active.map(card=>card.dataset.code).join('\n'),copyAll,active));
  document.getElementById('coupon-active-count').textContent=active.length;
  document.querySelectorAll('[data-coupon-filter]').forEach(button=>button.addEventListener('click',()=>{
    filter=button.dataset.couponFilter;document.querySelectorAll('[data-coupon-filter]').forEach(el=>el.setAttribute('aria-pressed',String(el===button)));filterCards();
  }));
  function pushState(){
    const button=document.getElementById('coupon-push-toggle');if(!button)return;
    const state=window.fimoRenewal?.push;
    button.disabled=!window.fimoRenewal?.loaded||Boolean(state?.busy);
    const enabled=Boolean(state?.couponsEnabled);
    document.getElementById('coupon-push-state').textContent=state?.busy?'연결 중':enabled?'켜짐':'꺼짐';
    button.textContent=enabled?'끄기':'알림 켜기';
    const test=document.getElementById('coupon-push-test');test.hidden=!enabled;test.disabled=Boolean(state?.busy);
    document.getElementById('coupon-push-error').textContent=state?.error||state?.help||'';
  }
  document.getElementById('coupon-push-toggle')?.addEventListener('click',()=>window.fimoRenewal.togglePush('coupon'));
  document.getElementById('coupon-push-test')?.addEventListener('click',async()=>{
    const button=document.getElementById('coupon-push-test');button.disabled=true;try{await window.fimoRenewal.testPush('coupon');}finally{button.disabled=false;}
  });
  window.addEventListener('renewal-push-changed',pushState);
  window.addEventListener('renewal-interests-error',()=>{document.getElementById('coupon-push-error').textContent='연결을 확인하고 새로고침해주세요.';});
  filterCards();pushState();
  async function checkNew(){
    if(polling||document.hidden)return;polling=true;
    try{
      const response=await fetch('/coupons/api',{cache:'no-store'});if(!response.ok)return;
      const data=await response.json();if(!Array.isArray(data))return;
      const fresh=data.filter(card=>card.code&&!card.boolExpires&&!known.has(card.code));
      data.forEach(card=>{if(card.code)known.add(card.code);});
      if(fresh.length){
        const notice=document.getElementById('coupon-new-notice');notice.hidden=false;notice.textContent=`새 쿠폰 ${fresh.length}개 보기`;
        message(fresh.length===1?`새 쿠폰: ${fresh[0].code}`:`새 쿠폰 ${fresh.length}개가 추가되었습니다.`);
      }
    }catch(_){}finally{polling=false;}
  }
  document.getElementById('coupon-new-notice').addEventListener('click',()=>location.reload());
  setInterval(checkNew,60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkNew();});
})();
