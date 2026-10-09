const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('assert');
const origin=process.env.FIMOBOOK_PREVIEW_ORIGIN || 'http://127.0.0.1:5058';
(async()=>{
 const b=await chromium.launch({executablePath:process.env.FIMOBOOK_CHROME_PATH || undefined,headless:true});
 const context=await b.newContext({viewport:{width:1440,height:1100},permissions:['clipboard-read','clipboard-write']});
 const p=await context.newPage(); const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
 const base=origin+'/player_compare';
 const ready=async()=>{await p.locator('.compare-names').waitFor();await p.waitForTimeout(100)};
 for(const width of [320,360,390,430,768,1440]){
  await p.setViewportSize({width,height:1100});
  await p.goto(base+'?left=40000266&right=40000263&le=3&re=5');await ready();
  let metrics=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,rows:document.querySelectorAll('.stat-row').length,small:[...document.querySelectorAll('input,select')].filter(e=>e.getClientRects().length&&e.type!=='checkbox'&&parseFloat(getComputedStyle(e).fontSize)<16).length}));
  assert(!metrics.overflow,`overflow ${width}`);assert(metrics.rows>20);
  if(width<=760) assert.equal(metrics.small,0);
  await p.locator('[data-compare-group="속도"]').click();assert.equal(await p.locator('.stat-row').count(),2);
  await p.locator('#compareDifferencesOnly').check();
  assert(await p.locator('.stat-row').evaluateAll(rows=>rows.every(r=>r.querySelector('.left .stat-main').textContent!==r.querySelector('.right .stat-main').textContent)));
  await p.locator('[data-compare-group="전체"]').click();await p.locator('#compareDifferencesOnly').uncheck();
  if(width===1440){await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:'artifacts/compare-desktop.png'});}
  if(width===390){await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:'artifacts/compare-mobile.png'});await p.locator('.stats-panel').evaluate(e=>e.scrollIntoView({block:'start'}));await p.screenshot({path:'artifacts/compare-mobile-stats.png'});}
  console.log(width,JSON.stringify(metrics));
 }
 await p.locator('[data-stat-code="STT"]').evaluate(e=>e.scrollIntoView({block:'start'}));
 const sticky=await p.locator('.compare-names').boundingBox();assert(sticky.y>=55&&sticky.y<=58,`sticky name header ${sticky.y}`);
 // Point allocation must survive copying/reloading and swapping.
 await p.goto(base+'?left=22902502&right=22902505&le=4&re=4');await ready();
 await p.locator('[data-slot="0"] .skill-settings').evaluate(e=>e.open=true);
 await p.locator('[data-slot="0"] [data-skill-select="0"]').selectOption('2');
 const saved=await p.evaluate(()=>JSON.parse(JSON.stringify(state[0].skillLevels)));
 assert(new URL(p.url()).searchParams.has('ls'));
 const statBefore=await p.locator('[data-stat-code="ACC"] .left .stat-main').textContent();
 await p.locator('[data-copy-compare]').click();await p.waitForFunction(()=>document.querySelector('[data-copy-compare]').textContent==='복사 완료');assert.equal(await p.locator('[data-copy-compare]').innerText(),'복사 완료');
 const copied=await p.evaluate(()=>navigator.clipboard.readText());assert.equal(copied,p.url());
 await p.goto(copied);await ready();assert.deepEqual(await p.evaluate(()=>state[0].skillLevels),saved);
 assert.equal(await p.locator('[data-stat-code="ACC"] .left .stat-main').textContent(),statBefore);
 await p.locator('[data-swap-players]').click();assert.equal(new URL(p.url()).searchParams.get('right'),'22902502');
 assert.deepEqual(await p.evaluate(()=>state[1].skillLevels),saved);
 // Same card at the same settings has no difference rows.
 await p.goto(base+'?left=40000266&right=40000266');await ready();await p.locator('#compareDifferencesOnly').check();assert.equal(await p.locator('.stat-row').count(),0);assert(await p.locator('#compareTable').textContent().then(t=>t.includes('다른 스탯이 없습니다')));
 // GK categories remain correct.
 await p.goto(base+'?left=40000261&right=40000280');await ready();assert(await p.locator('[data-compare-group="골키퍼"]').count());assert.equal(await p.locator('[data-compare-group="슈팅"]').count(),0);
 // Stale search results must not overwrite a newer query.
 await p.goto(base);
 await p.route('**/api/squad_players?**',async r=>{const q=new URL(r.request().url()).searchParams.get('q');await new Promise(ok=>setTimeout(ok,q==='느린'?800:10));await r.fulfill({json:[{cid:40000266,playerKor:q==='느린'?'느린 결과':'빠른 결과',ovr:148,position:'CM'}]})});
 const input=p.locator('[data-slot="0"] .player-search');await input.fill('느린');await p.waitForTimeout(300);await input.fill('빠른');await p.waitForTimeout(1000);assert.equal(await p.locator('.result-name').textContent(),'빠른 결과');
 await input.fill('');assert.equal(await p.locator('.result-list.open').count(),0);
 await p.unroute('**/api/squad_players?**');
 // Reset while a player request is pending must remain reset.
 await p.route('**/api/player_compare?cid=40000266',async r=>{await new Promise(ok=>setTimeout(ok,500));await r.continue()});
 await p.evaluate(()=>{selectPlayer(panels()[0],0,'40000266')});await p.locator('[data-reset-compare]').click();await p.waitForTimeout(900);assert.equal(await p.evaluate(()=>state.filter(s=>s.player).length),0);
 await p.unroute('**/api/player_compare?cid=40000266');
 await p.setViewportSize({width:390,height:1100});await p.goto(base+'?left=40000266&right=40000263&le=3&re=5');await ready();
 await p.evaluate(()=>document.documentElement.setAttribute('data-theme','dark'));await p.waitForTimeout(300);await p.screenshot({path:'artifacts/compare-mobile-dark.png'});
 await p.locator('.stats-panel').evaluate(e=>e.scrollIntoView({block:'start'}));await p.screenshot({path:'artifacts/compare-mobile-stats-dark.png'});
 assert.deepEqual(errors,[]); console.log('PASS: responsive, categories, differences, skill links, copy, swap, GK, stale searches, pending reset, dark, no JS errors');
 await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
