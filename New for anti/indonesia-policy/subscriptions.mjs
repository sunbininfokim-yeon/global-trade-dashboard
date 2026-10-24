import {subscriptionClient} from './subscription-client.mjs?v=2';
const topicNames={coal:'석탄',nickel_mining:'니켈',palm_oil:'팜유',biofuel:'바이오연료',bauxite:'보크사이트·알루미늄',copper:'구리',tin:'주석',cobalt:'코발트',manganese:'망간',iron_steel:'철광석·철강',silica:'실리카·석영',gold_silver:'금·은',rare_earths:'희토류',hydropower:'수력발전'};
const regionPairs=[['coal','Kalimantan Timur','동칼리만탄 · 석탄'],['coal','Kalimantan Tengah','중부칼리만탄 · 석탄'],['palm_oil','Kalimantan Barat','서칼리만탄 · 팜유'],['nickel_mining','Sulawesi Tenggara','동남술라웨시 · 니켈'],['hydropower','Sumatera Utara','북수마트라 · 수력발전']];
const priorityRegions=new Set(['Kalimantan Timur','Kalimantan Tengah','Kalimantan Barat','Sulawesi Tenggara','Sumatera Utara']);
const ALL='__all__',allLabel='인도네시아 전국';
const el=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
// Favourites are stars on products and regions; a mail alert is every starred
// product × every starred region, stored as the existing subscription rows.
// Anyone can see the stars; pressing one while signed out asks for a login
// and then applies that star.
export function mountSubscriptions(root,connect,{staticRegions=[]}={}){
 let api,user=null,serial=0,busy=false,limit=100,subs=[],pending=null;
 let regions=new Map([[ALL,{value:ALL,label:allLabel}],...staticRegions.map(r=>[r.value,r])]);
 const pendingTopics=new Set(),pendingRegions=new Set();
 const status=root.querySelector('[data-mail-status]'),list=root.querySelector('ul'),saved=root.querySelector('.fav-saved'),savedSummary=root.querySelector('[data-saved-summary]');
 const topicBox=root.querySelector('[data-topic-stars]'),regionMain=root.querySelector('[data-region-stars-main]'),regionBox=root.querySelector('[data-region-stars]'),filter=root.querySelector('[name=region_filter]'),count=root.querySelector('[data-fav-count]');
 const account=root.querySelector('[data-account]'),accountEmail=root.querySelector('[data-account-email]');
 const dialog=document.querySelector('#login-dialog'),loginForm=dialog?.querySelector('form[data-login-form]'),loginStatus=dialog?.querySelector('[data-login-status]');
 const enabled=()=>subs.filter(s=>s.enabled);
 const starredTopics=()=>new Set([...enabled().map(s=>s.topic),...pendingTopics]);
 const starredRegions=()=>new Set([...enabled().map(s=>s.region),...pendingRegions]);
 function star(kind,value,label,on,note=''){
  const chip=el('span');chip.className='fav-chip'+(on?' on':'');
  const b=el('button',on?'★':'☆');b.type='button';b.className='fav-star';b.disabled=busy;
  b.setAttribute('aria-pressed',String(on));b.setAttribute('aria-label',`${label} 즐겨찾기${on?' 해제':''}`);
  b.addEventListener('click',()=>void toggle(kind,value));
  let name;
  if(kind==='topic'){name=el('button',label);name.type='button';name.className='fav-name';name.title=`${label}(으)로 검색`;name.addEventListener('click',()=>searchTopic(value));}
  else{name=el('span',label);name.className='fav-name';}
  chip.append(b,name);if(note){const small=el('small',note);chip.append(small);}
  return chip;
 }
 function render(){
  const t=starredTopics(),r=starredRegions();
  topicBox.replaceChildren(...Object.entries(topicNames).map(([v,l])=>star('topic',v,l,t.has(v))));
  const others=[...regions.values()].filter(x=>x.value!==ALL);
  // The nationwide star and every starred province stay in view; the rest sit under 지역 더보기.
  regionMain.replaceChildren(star('region',ALL,allLabel,r.has(ALL)),...others.filter(x=>r.has(x.value)||priorityRegions.has(x.value)).map(x=>star('region',x.value,x.label,r.has(x.value),x.has_local_documents===false?'지방 자료 미확보':'')));
  regionBox.replaceChildren(...others.map(x=>star('region',x.value,x.label===x.value?x.value:x.label,r.has(x.value),x.has_local_documents===false?'지방 자료 미확보':'')));
  const pairBox=root.querySelector('[data-region-pairs]');
  if(pairBox)pairBox.replaceChildren(...regionPairs.map(([topic,region,label])=>{const on=enabled().some(s=>s.topic===topic&&s.region===region);const b=el('button',`${on?'★':'☆'} ${label}`);b.type='button';b.disabled=busy;b.setAttribute('aria-pressed',String(on));b.addEventListener('click',()=>void togglePair(topic,region));return b;}));
  filterRegions();
  list.replaceChildren(...subs.map(s=>{
   const row=el('li'),label=el('span',`${topicNames[s.topic]||s.topic} · ${regions.get(s.region)?.label||s.region} · ${s.enabled?'알림 중':'해제됨'}`),b=el('button',s.enabled?'해제':'다시 켜기');
   b.type='button';b.disabled=busy;b.addEventListener('click',()=>void run(()=>api.set(s.topic,s.region,!s.enabled)));row.append(label,b);return row;
  }));
  saved.hidden=!user||!subs.length;
  if(count)count.textContent=t.size||r.size?`품목 ${t.size} · 지역 ${r.size}`:'';
  savedSummary.textContent=`저장된 알림 조합 ${enabled().length}개`;
 }
 function filterRegions(){
  const q=(filter.value||'').trim().toLocaleLowerCase();
  for(const chip of regionBox.children)chip.hidden=!!q&&!chip.textContent.toLocaleLowerCase().includes(q);
 }
 function searchTopic(value){
  const select=document.querySelector('#search-form [name=topic]');if(!select)return;
  select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));
  document.querySelector('#search-form')?.scrollIntoView({behavior:'smooth',block:'start'});
 }
 function hint(){
  if(!user){status.textContent='☆를 눌러 품목·지역을 즐겨찾기하세요. 저장하려면 로그인이 필요합니다.';return;}
  const t=starredTopics(),r=starredRegions(),n=enabled().length;
  if(pendingRegions.size&&!t.size)status.textContent='알림을 받을 품목에도 ☆를 누르세요.';
  else if(!n)status.textContent='☆를 눌러 품목·지역을 즐겨찾기하세요. 지역을 고르지 않으면 전국으로 저장합니다.';
  else status.textContent=`품목 ${t.size}개 · 지역 ${r.size}개 · 알림 조합 ${n}개${deliveryNote}`;
 }
 let deliveryNote='';
 // The client sends 전국 on its own (a mixed list collapses to 전국 only).
 async function apply(topics,areas,on){
  const all=areas.includes(ALL),rest=areas.filter(a=>a!==ALL);
  if(all)await api.setMany(topics,[ALL],on);
  for(let i=0;i<rest.length;i+=50)await api.setMany(topics,rest.slice(i,i+50),on);
 }
 async function run(job,done){
  if(busy)return;busy=true;render();
  try{await job();await refresh();if(done)status.textContent=done;}
  catch(e){status.textContent=e.message;}
  finally{busy=false;render();}
 }
 async function togglePair(topic,region){
  if(!user){pending={kind:'pair',value:{topic,region}};openLogin();return;}
  const on=!enabled().some(s=>s.topic===topic&&s.region===region);
  return run(()=>api.set(topic,region,on));
 }
 async function toggle(kind,value){
  if(!user){pending={kind,value};openLogin();return;}
  const isTopic=kind==='topic',on=!(isTopic?starredTopics():starredRegions()).has(value);
  if(on){
   if(isTopic){
    const areas=[...starredRegions()];
    if(!areas.length)return run(()=>apply([value],[ALL],true),'지역을 고르지 않아 전국으로 저장했습니다.');
    if(areas.length+enabled().length>limit){status.textContent=`알림 조합은 최대 ${limit}개입니다. 지역 별표를 줄이거나 전국을 이용하세요.`;return;}
    return run(async()=>{await apply([value],areas,true);pendingRegions.clear();});
   }
   const topics=[...starredTopics()];
   if(!topics.length){pendingRegions.add(value);render();hint();return;}
   if(topics.length+enabled().length>limit){status.textContent=`알림 조합은 최대 ${limit}개입니다. 품목 별표를 줄이거나 전국을 이용하세요.`;return;}
   return run(async()=>{await apply(topics,[value],true);pendingRegions.delete(value);});
  }
  if(isTopic){pendingTopics.delete(value);const areas=enabled().filter(s=>s.topic===value).map(s=>s.region);if(!areas.length){render();hint();return;}return run(()=>apply([value],areas,false));}
  pendingRegions.delete(value);
  const topics=enabled().filter(s=>s.region===value).map(s=>s.topic);
  if(!topics.length){render();hint();return;}
  return run(()=>apply(topics,[value],false));
 }
 function openLogin(){
  if(!dialog||!api){status.textContent='로그인 연결을 확인하지 못했습니다. 메인 사이트에서 로그인하세요.';return;}
  loginStatus.textContent='';if(!dialog.open)dialog.showModal();loginForm.elements.email.focus();
 }
 function showAccount(){
  account.hidden=!user;accountEmail.textContent=user?`${user.email||'로그인한 계정'}`:'';
 }
 async function refresh(){
  const token=++serial;
  const u=await api.user();if(token!==serial)return;
  user=u;showAccount();
  if(!user){subs=[];pendingTopics.clear();pendingRegions.clear();render();hint();return;}
  const data=await api.list();if(token!==serial)return;
  subs=data.subscriptions;limit=data.max_active_combinations||100;
  regions=new Map(data.region_options.map(r=>[r.value,r.value===ALL?{...r,label:allLabel}:r]));
  deliveryNote=data.delivery_enabled?'':' · 인도네시아 자동 발송은 아직 준비 중입니다';
  render();hint();
 }
 const reload=()=>void refresh().catch(e=>{status.textContent=e.message;});
 filter.addEventListener('input',filterRegions);
 loginForm?.addEventListener('submit',async e=>{
  e.preventDefault();if(!api)return;
  const button=loginForm.querySelector('[type=submit]');button.disabled=true;loginStatus.textContent='로그인 중입니다.';
  try{
   await api.signIn(loginForm.elements.email.value,loginForm.elements.password.value);
   loginForm.elements.password.value='';dialog.close();window.dispatchEvent(new Event('site-auth-changed'));
   await refresh();
   const p=pending;pending=null;
   // The star pressed before logging in, unless the account already has it.
   if(p?.kind==='pair')await togglePair(p.value.topic,p.value.region);
   else if(p&&!(p.kind==='topic'?starredTopics():starredRegions()).has(p.value))await toggle(p.kind,p.value);
  }catch(err){loginStatus.textContent=err.message;}finally{button.disabled=false;}
 });
 dialog?.querySelector('[data-login-cancel]')?.addEventListener('click',()=>{pending=null;dialog.close();});
 root.querySelector('[data-logout]').addEventListener('click',async()=>{if(!api)return;try{await api.signOut();}finally{window.dispatchEvent(new Event('site-auth-changed'));await refresh().catch(()=>{});}});
 render();hint();
 const ready=(async()=>{
  try{
   api=subscriptionClient(await connect());api.onChange(reload);
   // A login in another tab of the site shows up when the reader comes back here.
   document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')reload();});
   await refresh();
  }catch(e){status.textContent=e.message||'즐겨찾기 연결을 확인하지 못했습니다.';}
 })();
 return {ready,refresh:async()=>{if(api)await refresh();}};
}
if(typeof document!=='undefined'){
 const root=document.querySelector('#mail-subscriptions');
 if(root){
  const staticRegions=await fetch(new URL('./mail-regions.json',import.meta.url)).then(r=>r.ok?r.json():{provinces:[]}).then(d=>d.provinces.map(([,value,label])=>({value,label}))).catch(()=>[]);
  mountSubscriptions(root,async()=>{
   const {createClient}=await import('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.118.0/+esm');
   if(!window.SUPABASE_URL||!window.SUPABASE_ANON_KEY)throw Error('즐겨찾기 연결 설정을 확인하지 못했습니다.');
   return createClient(window.SUPABASE_URL,window.SUPABASE_ANON_KEY);
  },{staticRegions});
 }
}
