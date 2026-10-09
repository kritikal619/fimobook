self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('push',event=>{
  let payload;
  try{payload=event.data.json();}catch(_){return;}
  if(!/^(renewal|coupon)(_|$)/.test(String(payload.kind||'')))return;
  event.stopImmediatePropagation();
  event.waitUntil((async()=>{
    await self.registration.showNotification(payload.title||'갱신시간',{
      body:payload.body||'',tag:payload.tag,icon:'/static/icons/pwa-icon-192.png',
      badge:'/static/icons/android-launchericon-72-72.png',vibrate:[100,70,100],data:{url:payload.url||'/times',fimoNative:true}
    });
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    windows.forEach(client=>client.postMessage({type:'renewal-push',payload}));
  })());
});
self.addEventListener('notificationclick',event=>{
  if(!event.notification.data?.fimoNative)return;
  event.stopImmediatePropagation();
  event.notification.close();
  const target=new URL(event.notification.data?.url||'/times',self.location.origin);
  const url=target.origin===self.location.origin?target.href:self.location.origin+'/times';
  event.waitUntil((async()=>{
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of windows){if('focus'in client){await client.navigate(url);return client.focus();}}
    return self.clients.openWindow(url);
  })());
});
