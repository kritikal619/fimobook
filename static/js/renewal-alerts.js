(() => {
  let csrf=document.currentScript.dataset.csrf, csrfRefresh=null, csrfFreshUntil=0, checkRetryAfter=0;
  const link=document.createElement('link');link.rel='stylesheet';link.href='/static/css/renewal-feedback.css?v=20260930-simple-2';document.head.append(link);
  let checking=false, configuration=null, registration=null, subscription=null, rootSubscription=null, legacyRegistration=null, preparing=null;
  const shown=new Set(), systemShown=new Set();

  async function refreshCsrf() {
    if(!csrfRefresh)csrfRefresh=(async()=>{
      const response=await fetch('/api/renewal-csrf',{credentials:'same-origin',cache:'no-store'});
      const result=await response.json().catch(()=>({}));
      if(!response.ok||response.redirected||typeof result.csrf_token!=='string'){
        const error=new Error('로그인 상태를 확인하고 새로고침해주세요.');
        error.status=response.redirected?401:response.status;throw error;
      }
      csrf=result.csrf_token;csrfFreshUntil=Date.now()+5*60*1000;
      const meta=document.querySelector('meta[name="csrf-token"]');if(meta)meta.content=csrf;
    })().finally(()=>{csrfRefresh=null;});
    return csrfRefresh;
  }
  async function request(url,data,headers={},retry=true) {
    // A page can remain open beyond the signed token's lifetime, or return from bfcache.
    if(data&&Date.now()>=csrfFreshUntil)await refreshCsrf();
    const response=await fetch(url,{method:data?'POST':'GET',credentials:'same-origin',cache:'no-store',
      headers:{...(data?{'Content-Type':'application/json','X-CSRFToken':csrf}:{}),...headers},body:data?JSON.stringify(data):undefined});
    const body=await response.text();let result={};try{result=JSON.parse(body);}catch(_){}
    if(data&&retry&&response.status===400&&/CSRF/i.test(body)){
      await refreshCsrf();return request(url,data,headers,false);
    }
    if(!response.ok||response.redirected){
      const error=new Error(/[가-힣]/.test(result.error||'')?result.error:'연결을 확인하고 다시 시도해주세요.');
      error.status=response.redirected?401:response.status;error.subscriptionExpired=result.subscription_expired===true;throw error;
    }
    return result;
  }
  function feedback(title,body='',type='success',url='') {
    let stack=document.getElementById('renewal-feedback-stack');
    if(!stack){stack=document.createElement('div');stack.id='renewal-feedback-stack';stack.className='renewal-feedback-stack';document.body.append(stack);}
    while(stack.children.length>=3)stack.firstElementChild.remove();
    const toast=document.createElement('div');toast.className='renewal-feedback'+(type==='error'?' is-error':'');toast.setAttribute('role',type==='error'?'alert':'status');
    const icon=document.createElement('span');icon.className='renewal-feedback-icon'+(type==='alarm'?' is-bell':'');icon.setAttribute('aria-hidden','true');icon.textContent=type==='alarm'?'♧':type==='error'?'!':'✓';
    if(type==='alarm'){icon.textContent='';const bell=document.createElement('i');bell.className='bi bi-bell';icon.append(bell);}
    const copy=document.createElement('div');const heading=document.createElement('strong');heading.textContent=title;copy.append(heading);
    if(body){const text=document.createElement('p');text.textContent=body;copy.append(text);}
    if(url){const action=document.createElement('a');action.href=url;action.textContent='확인하기 →';copy.append(action);}
    const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','알림 닫기');
    function dismiss(){toast.classList.add('is-leaving');setTimeout(()=>toast.remove(),220);}
    close.addEventListener('click',dismiss);toast.append(icon,copy,close);stack.append(toast);setTimeout(dismiss,7000);

  }
  function state(changes){Object.assign(window.fimoRenewal.push,changes);window.dispatchEvent(new Event('renewal-push-changed'));}
  async function config(){configuration=await request('/api/renewal-push',null,{'X-Fimo-Push-Endpoint':subscription?.endpoint||''});return configuration;}
  function supportError(){
    const installed=window.matchMedia?.('(display-mode: standalone)').matches||navigator.standalone;
    const ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1;
    if(ios&&!installed)return '아이폰은 홈 화면에 추가한 피모북 앱에서 알림을 켜주세요.';
    if(!window.isSecureContext||!('Notification'in window)||!('PushManager'in window)||!('serviceWorker'in navigator))return '푸시 알림을 지원하는 최신 브라우저에서 열어주세요. 아이폰은 iOS 16.4 이상이 필요합니다.';
    if(Notification.permission==='denied')return '휴대폰 또는 브라우저 설정에서 피모북 알림을 허용한 뒤 다시 열어주세요.';
    return '';
  }
  function matchingKey(value){
    const key=value?.options?.applicationServerKey;
    if(!key||!configuration?.vapid)return false;
    const expected=applicationKey(configuration.vapid),actual=new Uint8Array(key);
    return expected.length===actual.length&&expected.every((byte,index)=>byte===actual[index]);
  }
  async function worker(){
    if(registration?.active&&registration.scope===new URL('/',location.origin).href)return registration;
    registration=await (window.fimoPwaReady||navigator.serviceWorker.register('/firebase-messaging-sw.js',{scope:'/',updateViaCache:'none'}));
    if(!registration.active){
      await new Promise((resolve,reject)=>{
        const active=registration.installing||registration.waiting;
        if(!active){reject(new Error('푸시 연결을 다시 시도해주세요.'));return;}
        const timer=setTimeout(()=>reject(new Error('푸시 연결을 다시 시도해주세요.')),20000);
        function changed(){
          if(active.state==='activated'){clearTimeout(timer);resolve();}
          else if(active.state==='redundant'){clearTimeout(timer);reject(new Error('푸시 연결을 다시 시도해주세요.'));}
        }
        active.addEventListener('statechange',changed);changed();
      });
    }
    return registration;
  }
  async function prepare(){
    if(preparing)return preparing;
    preparing=(async()=>{
      const error=supportError();if(error)throw new Error(error);
      await worker();
      rootSubscription=await registration.pushManager.getSubscription();
      const legacy=await navigator.serviceWorker.getRegistration('/renewal-push/');
      legacyRegistration=legacy?.scope===new URL('/renewal-push/',location.origin).href?legacy:null;
      const oldSubscription=await legacyRegistration?.pushManager.getSubscription();
      subscription=rootSubscription||oldSubscription||null;
      let cfg=await config();
      if(!cfg.ready)throw new Error('푸시 연결을 준비하고 있습니다. 잠시 후 다시 시도해주세요.');
      if(oldSubscription&&(!matchingKey(rootSubscription)||!cfg.enabled&&!cfg.coupons_enabled)){
        subscription=oldSubscription;cfg=await config();
      }
      state({ready:true,enabled:Notification.permission==='granted'&&cfg.enabled,couponsEnabled:Notification.permission==='granted'&&cfg.coupons_enabled});return cfg;
    })().finally(()=>{preparing=null;});
    return preparing;
  }
  function applicationKey(value){const raw=atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4));return Uint8Array.from(raw,char=>char.charCodeAt(0));}
  navigator.serviceWorker?.addEventListener('message',event=>{
    if(event.data?.type!=='renewal-push')return;
    const data=event.data.payload||{};
    showAlarm(data.title||'갱신시간',data.body||'',data.tag||`${data.title}:${data.body}`,data.url||'/times');
  });
  function showAlarm(title,body,tag,url='/notifications'){
    if(shown.has(tag))return;shown.add(tag);if(shown.size>100)shown.delete(shown.values().next().value);
    feedback(title,body,'alarm',url);
  }
  async function restore(){
    if(window.fimoRenewal.push.busy)return;
    state({busy:true});
    try{
      const cfg=await prepare();
      if((cfg.enabled||cfg.coupons_enabled)&&subscription&&Notification.permission==='granted'){
        await request('/api/renewal-push',{endpoint:subscription.endpoint,action:'heartbeat'});
        state({enabled:cfg.enabled,couponsEnabled:cfg.coupons_enabled,error:'',help:subscription!==rootSubscription?'알림 연결을 업데이트하려면 테스트를 눌러주세요.':''});
      }else state({enabled:false,couponsEnabled:false,error:'',help:''});
    }catch(error){state({ready:false,enabled:false,couponsEnabled:false,error:/[가-힣]/.test(error.message)?error.message:'연결을 다시 확인해주세요.'});}
    finally{state({busy:false});}
  }
  window.fimoRenewal={names:new Set(),loaded:false,clockOffset:0,quiet:{enabled:false,start:'00:00',end:'07:00',loaded:false},push:{enabled:false,couponsEnabled:false,busy:false,ready:false,error:'',help:''},feedback,
    async load(){const data=await request('/api/renewal-interests');this.names=new Set(data.names);this.loaded=true;if(data.server_time)this.clockOffset=Date.parse(data.server_time)-Date.now();window.dispatchEvent(new Event('renewal-interests-changed'));state({});},
    async save(name,enabled){const data=await request('/api/renewal-interests',{name,enabled});this.names=new Set(data.names);window.dispatchEvent(new Event('renewal-interests-changed'));},
    async loadQuiet(){const data=await request('/api/renewal-quiet-hours');this.quiet={...data,loaded:true};window.dispatchEvent(new Event('renewal-quiet-changed'));},
    async saveQuiet(values){const data=await request('/api/renewal-quiet-hours',values);this.quiet={...data,loaded:true};window.dispatchEvent(new Event('renewal-quiet-changed'));feedback(data.enabled?'방해금지 시간을 저장했습니다':'방해금지를 껐습니다');},
    async connectPush(topic){
      // Preparation happens before the tap. Subscribe must be the first async
      // operation in this click path so Safari retains the user gesture.
      const previous={enabled:this.push.enabled,couponsEnabled:this.push.couponsEnabled};
      const oldSubscription=subscription;
      if(rootSubscription&&!matchingKey(rootSubscription)){
        await rootSubscription.unsubscribe();rootSubscription=null;
        throw new Error('이전 연결을 정리했습니다. 알림 켜기 또는 테스트를 한 번 더 눌러주세요.');
      }
      const next=rootSubscription||await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:applicationKey(configuration.vapid)});
      rootSubscription=next;
      if(oldSubscription&&oldSubscription.endpoint!==next.endpoint&&(previous.enabled||previous.couponsEnabled)){
        await request('/api/renewal-push',{endpoint:oldSubscription.endpoint,action:'heartbeat'});
      }
      let data=await request('/api/renewal-push',{subscription:next.toJSON(),action:'enable',topic});
      const other=topic==='coupon'?'renewal':'coupon',otherSetting=other==='coupon'?'couponsEnabled':'enabled';
      if(previous[otherSetting]&&!data[other==='coupon'?'coupons_enabled':'enabled'])data=await request('/api/renewal-push',{subscription:next.toJSON(),action:'enable',topic:other});
      subscription=next;
      // Retire only this browser's old registration after both settings are saved.
      if(oldSubscription&&oldSubscription.endpoint!==next.endpoint){
        if(legacyRegistration&&oldSubscription!==next)await oldSubscription.unsubscribe().catch(()=>{});
      }
      state({enabled:data.enabled,couponsEnabled:data.coupons_enabled,error:'',help:''});
    },
    async togglePush(topic='renewal') {
      if (!['renewal','coupon'].includes(topic)||this.push.busy) return;
      const setting=topic==='coupon'?'couponsEnabled':'enabled';
      const label=topic==='coupon'?'쿠폰 알림':'갱신 알림';
      state({busy:true,error:''});
      try {
        if (this.push[setting]) {
          const data=await request('/api/renewal-push',{action:'disable',topic,endpoint:subscription?.endpoint});
          state({enabled:data.enabled,couponsEnabled:data.coupons_enabled});feedback(label+'을 껐습니다');
        } else {
          const error=supportError();if(error)throw new Error(error);
          if(!this.push.ready){await prepare();throw new Error('연결 준비를 마쳤습니다. 알림 켜기를 한 번 더 눌러주세요.');}
          await this.connectPush(topic);feedback(label+'을 켰습니다');
        }
      } catch(error) {
        state({error:error.name==='NotAllowedError'?'휴대폰 또는 브라우저 설정에서 피모북 알림을 허용해주세요.':/[가-힣]/.test(error.message)?error.message:'연결하지 못했습니다. 다시 시도해주세요.'});feedback(label+' 연결 확인',this.push.error,'error');
      } finally { state({busy:false}); }
    },
    async testPush(topic='renewal') {
      if(!['renewal','coupon'].includes(topic)||this.push.busy)return;
      state({busy:true,error:''});
      try {
        if(!('Notification'in window)||Notification.permission!=='granted')throw new Error('브라우저 설정에서 알림을 허용해주세요.');
        if(!this.push.ready){await prepare();throw new Error('연결 준비를 마쳤습니다. 테스트를 한 번 더 눌러주세요.');}
        await this.connectPush(topic);
        await request('/api/renewal-push',{endpoint:subscription?.endpoint,action:'test',topic});
        feedback(topic==='coupon'?'쿠폰 테스트 알림을 전송했습니다':'갱신 테스트 알림을 전송했습니다');
      }
      catch(error) {
        if(error.subscriptionExpired){
          await rootSubscription?.unsubscribe().catch(()=>{});rootSubscription=null;subscription=null;
          state({enabled:false,couponsEnabled:false,help:''});
        }
        state({error:/[가-힣]/.test(error.message)?error.message:'전송하지 못했습니다. 알림을 다시 연결해주세요.'});feedback('전송 확인',this.push.error,'error');
      }
      finally {state({busy:false});}
    }

  };
  async function check(){
    if(checking||document.hidden||Date.now()<checkRetryAfter)return;checking=true;
    try{const {alerts}=await request('/api/renewal-alerts/check',{});for(const alert of alerts)showAlarm(alert.title||`${alert.name} 1분 후 갱신`,alert.message.split('\n').slice(1).join('\n'),alert.tag||alert.message);}
    catch(error){checkRetryAfter=error.status===401?Infinity:Date.now()+60000;}finally{checking=false;}
  }
  window.fimoRenewal.load().catch(()=>window.dispatchEvent(new Event('renewal-interests-error')));
  restore();
  window.addEventListener('pageshow',event=>{if(event.persisted)restore();});
  window.fimoRenewal.loadQuiet().catch(()=>window.dispatchEvent(new Event('renewal-quiet-error')));
  check();setInterval(check,15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden){check();restore();}});
})();
