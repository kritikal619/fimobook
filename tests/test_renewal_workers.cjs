const assert=require('assert');
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const root=path.resolve(__dirname,'..');
async function testWorker(){
 const listeners={},shown=[],messages=[];
 const sandbox={URL,self:{
  location:{origin:'https://fcbook.info'},skipWaiting(){},
  addEventListener(type,fn){(listeners[type]??=[]).push(fn);},
  registration:{async showNotification(title,options){shown.push({title,...options});}},
  clients:{claim(){},async matchAll(){return [{postMessage(data){messages.push(data);},async navigate(){},async focus(){}}];}}
 }};
 vm.runInNewContext(fs.readFileSync(root+'/static/js/renewal-push-sw.js','utf8'),sandbox);
 listeners.push.push(event=>{shown.push({title:'FC모바일 쿠폰',body:'새 쿠폰이 도착했습니다.'});});
 async function push(payload){let stopped=false,pending;const event={data:{json:()=>payload},stopImmediatePropagation(){stopped=true;},waitUntil(promise){pending=promise;}};for(const listener of listeners.push){listener(event);if(stopped)break;}await pending;}
 await push({kind:'renewal_test',title:'갱신 알림 테스트',body:'관심 클래스가 갱신되기 1분 전에 알려드립니다.'});
 assert.equal(shown.length,1);assert.equal(shown[0].title,'갱신 알림 테스트');assert(!shown[0].body.includes('쿠폰'));assert.equal(messages[0].payload.kind,'renewal_test');
 await push({kind:'renewal',title:'FCA27 LIVE 1분 후 갱신',body:'17:14 한국시간에 갱신됩니다.'});assert.equal(shown[1].title,'FCA27 LIVE 1분 후 갱신');
 await push({kind:'coupon_test',title:'쿠폰 알림 테스트',body:'이 기기에 새 쿠폰 알림이 도착합니다.'});assert.equal(shown[2].title,'쿠폰 알림 테스트');
 await push({notification:{title:'기존 Firebase 알림'}});assert.equal(shown[3].title,'FC모바일 쿠폰');
 assert(fs.readFileSync(root+'/templates/firebase-messaging-sw.js','utf8').startsWith('importScripts("/static/js/renewal-push-sw.js?'));
}
async function testClient(){
 const calls=[],events={},element=()=>({children:[],classList:{add(){},remove(){}},append(...nodes){this.children.push(...nodes);},setAttribute(){},addEventListener(){},remove(){}});
 const subscription=endpoint=>({endpoint,toJSON(){return {endpoint,keys:{p256dh:'test',auth:'test'}};}});
 const old=subscription('https://fcm.googleapis.com/fcm/send/legacy-root'),fresh=subscription('https://fcm.googleapis.com/fcm/send/native-renewal');
 const native={scope:'https://fcbook.info/renewal-push/',active:{},pushManager:{async getSubscription(){return fresh;}}};
 let newEnabled=false,newCoupons=false;
 const window={isSecureContext:true,dispatchEvent(event){(events[event.type]||[]).forEach(fn=>fn(event));}};
 const sandbox={window,URL,Event,Uint8Array,Set,Date,JSON,atob,setInterval(){},setTimeout(){},location:{origin:'https://fcbook.info'},Notification:{permission:'granted'},navigator:{serviceWorker:{addEventListener(){},async getRegistration(){return {scope:'https://fcbook.info/',active:{},update:async()=>{},pushManager:{async getSubscription(){return old;}}};},async register(url,options){calls.push({register:url,scope:options.scope});return native;}}},document:{currentScript:{dataset:{csrf:'csrf'}},head:element(),body:element(),createElement:element,getElementById(){return null;},addEventListener(){}},async fetch(url,options){const data=options.body?JSON.parse(options.body):null;calls.push({url,data});let result={};if(url==='/api/renewal-interests')result={names:[]};if(url==='/api/renewal-quiet-hours')result={enabled:false,start:'00:00',end:'07:00'};if(url==='/api/renewal-alerts/check')result={alerts:[]};if(url==='/api/renewal-push'){if(!data)result={ready:true,vapid:'AA',enabled:true,coupons_enabled:true};else{if(data.action==='enable'){if(data.topic==='renewal')newEnabled=true;else newCoupons=true;}result={enabled:newEnabled,coupons_enabled:newCoupons,ok:true};}}return {ok:true,redirected:false,json:async()=>result};}};
 window.Notification=sandbox.Notification;
 vm.runInNewContext(fs.readFileSync(root+'/static/js/renewal-alerts.js','utf8'),sandbox);
 await new Promise(resolve=>setImmediate(resolve));
 await window.fimoRenewal.testPush('renewal');
 assert(calls.some(call=>call.register==='/renewal-push-sw.js'&&call.scope==='/renewal-push/'));
 const test=calls.find(call=>call.data?.action==='test');assert.equal(test.data.endpoint,fresh.endpoint);assert.equal(test.data.topic,'renewal');
 assert(calls.some(call=>call.data?.action==='enable'&&call.data.topic==='coupon'),'coupon setting preserved during repair');
 assert(window.fimoRenewal.push.enabled&&window.fimoRenewal.push.couponsEnabled);
 assert.equal(window.fimoRenewal.push.busy,false);
}
(async()=>{await testWorker();await testClient();console.log('PASS: renewal worker prevents coupon fallback, legacy worker compatibility, test reconnects exact native scope, coupon preference preserved');})().catch(error=>{console.error(error);process.exit(1);});
