import {subscriptionClient} from './subscription-client.mjs';
const topicNames={coal:'석탄',nickel_mining:'니켈',palm_oil:'팜유',biofuel:'바이오연료',bauxite:'보크사이트·알루미늄',copper:'구리',tin:'주석',cobalt:'코발트',manganese:'망간',iron_steel:'철광석·철강',silica:'실리카·석영',gold_silver:'금·은',rare_earths:'희토류'};
const el=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
export function mountSubscriptions(root,connect){
 let api,started=false,serial=0,busy=false,limit=100,regions=new Map();
 const status=root.querySelector('[role=status]'),form=root.querySelector('form'),list=root.querySelector('ul'),selection=root.querySelector('[data-selection-status]'),saved=root.querySelector('[data-save-status]');
 const checked=name=>[...form.querySelectorAll(`input[name="${name}"]:checked`)].map(e=>e.value);
 const chosen=()=>({topics:checked('topic'),regions:checked('region').includes('__all__')?['__all__']:checked('region')});
 function controls(){
  const picked=chosen(),nationwide=picked.regions.includes('__all__'),count=picked.topics.length*picked.regions.length;
  for(const e of form.elements)e.disabled=busy;
  for(const e of form.querySelectorAll('[data-region-options] input'))e.disabled=busy||nationwide;
  for(const b of list.querySelectorAll('button'))b.disabled=busy;
  form.querySelector('[type=submit]').disabled=busy||!count||count>limit;
  selection.textContent=count?`${picked.topics.length}개 품목 × ${nationwide?'전국':picked.regions.length+'개 지역'} · ${count}개 조합${count>limit?' · 한 번에 최대 '+limit+'개 조합입니다. 전국 선택도 이용할 수 있습니다.':''}`:'품목과 지역을 하나 이상 체크하세요.';
 }
 function choice(name,value,label,selected=false,note=''){
  const row=el('label');row.className='mail-choice';const input=el('input');input.type='checkbox';input.name=name;input.value=value;input.checked=selected;
  const text=el('span',label);if(note){const small=el('small',note);small.className='search-help';text.append(small);}row.append(input,text);return row;
 }
 form.querySelector('[data-topic-options]').replaceChildren(...Object.entries(topicNames).map(([value,label])=>choice('topic',value,label)));
 function filterRegions(){
  const q=form.elements.region_filter.value.trim().toLocaleLowerCase();
  for(const row of form.querySelectorAll('[data-region-options] label'))row.hidden=!row.textContent.toLocaleLowerCase().includes(q);
 }
 async function refresh(){
  const token=++serial;list.replaceChildren();form.hidden=true;
  if(!await api.user()){if(token===serial)status.textContent='로그인한 계정으로 구독을 저장합니다. 마이페이지에서 로그인 후 이 화면으로 돌아오세요.';return;}
  const data=await api.list();if(token!==serial)return;
  const selected=new Set(checked('region'));regions=new Map(data.region_options.map(r=>[r.value,r]));limit=data.max_active_combinations||100;
  form.querySelector('[data-region-options]').replaceChildren(...data.region_options.filter(r=>r.value!=='__all__').map(r=>choice('region',r.value,r.label===r.value?r.value:`${r.label} (${r.value})`,selected.has(r.value),r.has_local_documents===false?'지방 자료 미확보 · 전국 적용 규정 포함':'')));
  filterRegions();
  status.textContent=data.delivery_enabled?'확인된 변경 근거를 알립니다. 전국 적용 규정도 포함합니다.':'구독 설정을 저장할 수 있습니다. 인도네시아 자동 발송은 아직 준비 중입니다.';
  form.hidden=false;
  for(const s of data.subscriptions){
   const row=el('li'),label=el('span',`${topicNames[s.topic]||s.topic} · ${regions.get(s.region)?.label||s.region} · ${s.enabled?'구독 중':'해제됨'}`),button=el('button',s.enabled?'구독 해제':'다시 구독');
   button.type='button';button.addEventListener('click',()=>void save([s.topic],[s.region],!s.enabled,true));row.append(label,button);list.append(row);
  }
  controls();
 }
 async function save(topics,areas,enabled,single=false){
  if(busy)return;busy=true;controls();
  try{if(single)await api.set(topics[0],areas[0],enabled);else await api.setMany(topics,areas,enabled);await refresh();saved.textContent=enabled?`${topics.length*areas.length}개 조합의 구독을 저장했습니다.`:'구독을 해제했습니다.';}catch(e){saved.textContent=e.message;}finally{busy=false;controls();}
 }
 root.addEventListener('toggle',async()=>{
  if(!root.open||started)return;started=true;status.textContent='로그인·구독 정보를 확인하는 중입니다.';
  try{if(!api){api=subscriptionClient(await connect());api.onChange(()=>{void refresh().catch(e=>{status.textContent=e.message;form.hidden=true;});});}await refresh();}catch(e){status.textContent=e.message||'구독 연결을 확인하지 못했습니다.';started=false;}
 });
 form.addEventListener('change',controls);
 form.elements.region_filter.addEventListener('input',filterRegions);
 for(const button of form.querySelectorAll('[data-topics]'))button.addEventListener('click',()=>{for(const input of form.querySelectorAll('[name=topic]'))input.checked=button.dataset.topics==='all';controls();});
 form.querySelector('[data-regions]').addEventListener('click',()=>{for(const input of form.querySelectorAll('[name=region]'))input.checked=false;controls();});
 form.addEventListener('submit',e=>{e.preventDefault();const p=chosen();if(p.topics.length&&p.regions.length&&p.topics.length*p.regions.length<=limit)void save(p.topics,p.regions,true);});
 controls();
 return {refresh:async()=>{if(api)await refresh();}};
}
if(typeof document!=='undefined'){
 const root=document.querySelector('#mail-subscriptions');
 if(root)mountSubscriptions(root,async()=>{
  const {createClient}=await import('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.118.0/+esm');
  if(!window.SUPABASE_URL||!window.SUPABASE_ANON_KEY)throw Error('구독 연결 설정을 확인하지 못했습니다.');
  return createClient(window.SUPABASE_URL,window.SUPABASE_ANON_KEY);
 });
}
