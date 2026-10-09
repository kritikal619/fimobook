(function () {
 "use strict";
 const root=document.getElementById('normalPowerRanking');
 if(!root)return;
 let data;
 try{data=JSON.parse(document.getElementById('normalPowerRankingData').textContent);}catch(e){return;}
 const editions=Array.isArray(data.editions)&&data.editions.length?data.editions:[data];
 const $=id=>document.getElementById(id);
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const norm=s=>String(s??'').toLocaleLowerCase('ko-KR').replace(/\s+/g,'');
 const positions=['ALL','ST','CF','LW','RW','CAM','CM','CDM','LM','RM','LB','CB','RB','GK'];
 const scopes=[['total','TOP 1–100'],['top_1_50','TOP 1–50'],['top_51_100','TOP 51–100']];
 let edition=editions[0],scope='total',position='ST',query='',limit=20,expanded=false,excludeEternal=false;
 function ranges(){return edition.meta?.rank_ranges||{top_1_50:50,top_51_100:50};}
 function count(p){return scope==='total'?Number(p.counts?.top_1_50||0)+Number(p.counts?.top_51_100||0):Number(p.counts?.[scope]||0);}
 function users(p){return (p.users||[]).filter(u=>scope==='total'||u.range===scope||(!u.range&&((scope==='top_1_50'&&u.rank<=50)||(scope==='top_51_100'&&u.rank>50))));}
 function isEternal(p){return ['EI','EI26'].includes(String(p.season_abbr||'').toUpperCase())||/ETERNAL/i.test(p.class_name||'')||/ETERNAL/i.test(p.cardArt?.cardProgram||'');}
 function filtered(){return (edition.players||[]).filter(p=>count(p)>0&&(!excludeEternal||!isEternal(p))&&(position==='ALL'||p.position===position)&&(!query||norm([p.player_name,p.class_name,p.season_abbr,p.class_label,p.class_alias,...users(p).map(u=>u.name)].join(' ')).includes(query))).sort((a,b)=>count(b)-count(a)||String(a.player_name).localeCompare(String(b.player_name),'ko')||String(a.season_abbr).localeCompare(String(b.season_abbr)));}
 function priceLabel(p){const value=Number(p.price);return `<span class="power-price" title="0진화 기준 가격"> — ${value>0?`${value.toLocaleString('en-US')}<img src="/static/pack-opener/images/mp-token-transparent.png" alt="MP" loading="lazy">`:'가격 정보 없음'}</span>`;}
 function artwork(p){
  const meta=p.cardArt;
  if(meta){
   return `<span class="power-card" data-fimo-player-card="${esc(JSON.stringify(meta))}" role="img" aria-label="${esc(p.player_name)} 기본 OVR ${esc(meta.ovr)}, ${esc(meta.position)}, ${esc(meta.nation)}, ${esc(meta.team)}"><img class="card-background" src="${esc(p.card_image)}" alt="" loading="lazy"><img class="card-face" src="${esc(p.face_image)}" alt="" loading="lazy"></span>`;
  }
  if(p.art_image)return `<img class="power-card-composite" src="${esc(p.art_image)}" alt="" loading="lazy">`;
  return `<span class="power-card" data-fimo-card-cid="${Number(p.cid)||0}"><img class="card-background" src="${esc(p.card_image)}" alt="" loading="lazy"><img class="card-face" src="${esc(p.face_image)}" alt="" loading="lazy"></span>`;
 }
 function rankerButton(u){
  const title=(u.rank?u.rank+'위 ':'순위 미확인 ')+u.name;
  if(!Number.isInteger(u.source_index))return `<span class="power-user">${esc(title)}</span>`;
  return `<button type="button" class="power-user power-ranker-link" data-squad-index="${u.source_index}" data-squad-name="${esc(title)}" aria-label="${esc(title)} 스쿼드 보기">${esc(title)}</button>`;
 }
 function render(){
  $('powerPositions').innerHTML=positions.map(p=>`<button type="button" data-position="${p}" aria-pressed="${p===position}" class="${p===position?'is-active':''}">${p==='ALL'?'전체':p}</button>`).join('');
  $('powerScopes').innerHTML=scopes.map(([key,label])=>{const disabled=key==='total'?!(ranges().top_1_50&&ranges().top_51_100):!ranges()[key];return `<button type="button" data-scope="${key}" ${disabled?'disabled':''} aria-pressed="${key===scope}" class="${key===scope?'is-active':''}">${label}${disabled?' · 미집계':''}</button>`;}).join('');
  const meta=edition.meta||{};
  const sample=scope==='total'?Number(ranges().top_1_50)+Number(ranges().top_51_100):Number(ranges()[scope]);
  const rows=filtered();$('powerListTitle').textContent=position==='ALL'?'전체 포지션 카드 사용 현황':`${position} 카드 사용 현황`;
  $('powerRows').innerHTML=rows.slice(0,limit).map((p,i)=>{
   const us=users(p);const rate=meta.squad_count&&sample?Math.round(count(p)/sample*1000)/10:null;const ranks=us.map(rankerButton).join('');
   return `<article class="power-rank-row"><span class="power-rank-number">${i+1}</span><div class="power-player">${artwork(p)}<div><span class="power-class">${esc(p.class_label||p.season_abbr||p.class_name)}</span><a class="power-rank-name" href="/player/${Number(p.cid)||0}">${esc(p.player_name)}</a><span class="power-position-tag">${esc(p.position)}</span>${priceLabel(p)}${p.note?`<small>${esc(p.note)}</small>`:''}</div></div><div class="power-usage"><strong>${count(p)}</strong><span>명</span></div><div class="power-rate">${rate!==null?`<strong>${rate}%</strong><span>${count(p)}/${sample}명</span><i aria-hidden="true" style="--usage:${Math.min(100,rate)}%"></i>`:'<span>—</span>'}</div><div class="power-users">${us.length?`<details ${expanded?'open':''}><summary><span>${us.slice(0,2).map(rankerButton).join(' · ')}${us.length>2?` 외 ${us.length-2}명`:''}</span><em>전체 보기</em></summary><div class="power-user-list">${ranks}</div></details>`:'<span class="power-unavailable">사용 랭커 원자료 없음</span>'}</div></article>`;
  }).join('')||'<div class="power-empty">일치하는 카드가 없습니다. 다른 포지션이나 검색어를 선택해 주세요.</div>';
  $('powerMore').hidden=rows.length<=limit;$('powerMore').textContent=`${Math.min(20,rows.length-limit)}종 더 보기`;
  $('powerExpandAll').textContent=expanded?'랭커 접기':'랭커 펼치기';
  const url=String(meta.source_url||'');
  $('powerCredit').innerHTML=`${/^https:\/\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">카페 원본 보기 ↗</a> · `:''}자료: ${esc(meta.source_name||'입력 자료')}`;
 }
 function selectEdition(index){edition=editions[index]||editions[0];scope=ranges().top_51_100?'total':'top_1_50';limit=20;expanded=false;render();}
 $('powerEdition').innerHTML=editions.map((e,i)=>`<option value="${i}">${esc(e.meta?.updated_at||'날짜 미입력')}</option>`).join('');
 $('powerEdition').addEventListener('change',e=>selectEdition(Number(e.target.value)));
 $('powerScopes').addEventListener('click',e=>{const b=e.target.closest('button[data-scope]');if(!b||b.disabled)return;scope=b.dataset.scope;limit=20;render();});
 $('powerPositions').addEventListener('click',e=>{const b=e.target.closest('button[data-position]');if(!b)return;position=b.dataset.position;limit=20;render();});
 $('powerSearch').addEventListener('input',e=>{query=norm(e.target.value);limit=20;render();});
 $('powerExcludeEternal').addEventListener('change',e=>{excludeEternal=e.target.checked;limit=20;render();});
 $('powerMore').addEventListener('click',()=>{limit+=20;render();});
 $('powerExpandAll').addEventListener('click',()=>{expanded=!expanded;render();});
 const dialog=$('powerSquadDialog');
 $('powerRows').addEventListener('click',e=>{
  const button=e.target.closest('button[data-squad-index]');if(!button)return;
  e.preventDefault();e.stopPropagation();
  const date=String(edition.meta?.updated_at||'').slice(0,10);if(!/^\d{4}-\d{2}-\d{2}$/.test(date))return;
  const img=$('powerSquadImage');$('powerSquadTitle').textContent=button.dataset.squadName+' 스쿼드';$('powerSquadDate').textContent=date+' 기준';
  $('powerSquadError').hidden=true;img.hidden=false;img.alt=button.dataset.squadName+' 원본 스쿼드';
  img.src=`/static/ranking/${date}/squads/${String(Number(button.dataset.squadIndex)).padStart(2,'0')}.png`;
  dialog.showModal();
 });
 $('powerSquadImage').addEventListener('error',()=>{$('powerSquadImage').hidden=true;$('powerSquadError').hidden=false;});
 $('powerSquadClose').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();});
 selectEdition(0);
})();
