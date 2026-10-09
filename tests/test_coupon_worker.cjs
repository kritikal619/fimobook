const fs=require('fs'),vm=require('vm'),assert=require('assert');
(async()=>{
 const handlers={},notifications=[],messages=[],navigations=[];
 const client={postMessage:message=>messages.push(message),navigate:async url=>navigations.push(url),focus:async()=>true};
 const self={addEventListener:(type,handler)=>handlers[type]=handler,skipWaiting:()=>{},location:{origin:'https://fcbook.info'},
  registration:{showNotification:async(title,options)=>notifications.push({title,options})},
  clients:{claim:async()=>{},matchAll:async()=>[client],openWindow:async url=>navigations.push(url)}};
 vm.runInNewContext(fs.readFileSync('static/js/renewal-push-sw.js','utf8'),{self,URL});
 let work;
 handlers.push({data:{json:()=>({kind:'coupon',title:'FC모바일 새 쿠폰',body:'NEWCODE',tag:'coupon-NEWCODE',url:'/coupons/'})},waitUntil:promise=>work=promise});await work;
 assert.equal(notifications[0].title,'FC모바일 새 쿠폰');assert.equal(notifications[0].options.data.url,'/coupons/');assert.equal(messages[0].payload.kind,'coupon');
 handlers.push({data:{json:()=>({kind:'renewal',title:'갱신시간',url:'/times'})},waitUntil:promise=>work=promise});await work;assert.equal(notifications.length,2);
 handlers.push({data:{json:()=>({kind:'other'})},waitUntil:()=>assert.fail('unrelated push handled')});
 handlers.notificationclick({notification:{close:()=>{},data:{url:'/coupons/'}},waitUntil:promise=>work=promise});await work;assert.equal(navigations[0],'https://fcbook.info/coupons/');
 handlers.notificationclick({notification:{close:()=>{},data:{url:'https://example.com/'}},waitUntil:promise=>work=promise});await work;assert.equal(navigations[1],'https://fcbook.info/times');
 console.log('PASS: coupon and renewal background notifications, foreground forwarding, notification click, same-origin navigation');
})().catch(error=>{console.error(error);process.exit(1)});
