import {subscriptionClient} from './subscription-client.mjs';
const topicNames={coal:'석탄',nickel_mining:'니켈',palm_oil:'팜유',biofuel:'바이오연료',bauxite:'보크사이트·알루미늄',copper:'구리',tin:'주석',cobalt:'코발트',manganese:'망간',iron_steel:'철광석·철강',silica:'실리카·석영',gold_silver:'금·은',rare_earths:'희토류'};
const regionNames={'Kalimantan Timur':'동칼리만탄','Kalimantan Barat':'서칼리만탄','Sulawesi Tenggara':'동남술라웨시'};
const el=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
export function mountSubscriptions(root,connect){
 let api,started=false,serial=0,busy=false;
 const status=root.querySelector('[role=status]'),form=root.querySelector('form'),list=root.querySelector('ul'),region=form.elements.region;
 const controls=()=>{for(const e of form.elements)e.disabled=busy;for(const b of list.querySelectorAll('button'))b.disabled=busy;};
 async function refresh(){
  const token=++serial;list.replaceChildren();form.hidden=true;
  if(!await api.user()){if(token===serial)status.textContent='로그인한 계정으로 구독을 저장합니다. 마이페이지에서 로그인 후 이 화면으로 돌아오세요.';return;}
  const data=await api.list();if(token!==serial)return;
  region.replaceChildren(...data.regions.map(r=>new Option(regionNames[r]?`${regionNames[r]} (${r})`:r,r)));
  status.textContent=data.delivery_enabled?'확인된 변경 근거를 알립니다. 전국 적용 규정도 포함합니다.':'구독 설정을 저장할 수 있습니다. 인도네시아 자동 발송은 아직 준비 중입니다.';
  form.hidden=false;form.querySelector('button').disabled=!data.regions.length;
  for(const s of data.subscriptions){
   const row=el('li'),label=el('span',`${topicNames[s.topic]||s.topic} · ${regionNames[s.region]||s.region} · ${s.enabled?'구독 중':'해제됨'}`),button=el('button',s.enabled?'구독 해제':'다시 구독');
   button.type='button';button.addEventListener('click',()=>void save(s.topic,s.region,!s.enabled));row.append(label,button);list.append(row);
  }
 }
 async function save(topic,area,enabled){
  if(busy)return;busy=true;controls();
  try{await api.set(topic,area,enabled);await refresh();}catch(e){status.textContent=e.message;}finally{busy=false;controls();}
 }
 root.addEventListener('toggle',async()=>{
  if(!root.open||started)return;started=true;status.textContent='로그인·구독 정보를 확인하는 중입니다.';
  try{api=subscriptionClient(await connect());api.onChange(()=>{void refresh().catch(e=>{status.textContent=e.message;form.hidden=true;});});await refresh();}catch(e){status.textContent=e.message||'구독 연결을 확인하지 못했습니다.';started=false;}
 });
 form.addEventListener('submit',e=>{e.preventDefault();void save(form.elements.topic.value,region.value,true);});
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
