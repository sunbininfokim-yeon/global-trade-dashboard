// IDN-only read API. No collection, provider calls, user data or US fallback.
export const TOPICS = {coal:'석탄',nickel_mining:'니켈·광산',palm_oil:'팜유',biofuel:'바이오연료'};
const GROUPS = [
 ['석탄','coal','batubara','batu bara'],
 ['유연탄','bituminous','bituminus'],['무연탄','anthracite','antrasit'],
 ['니켈','nickel','nikel','nickel_mining','ferronickel','feronikel'],
 ['광산','광업','mining','pertambangan'],
 ['팜유','palm oil','palm_oil','kelapa sawit','cpo'],
 ['바이오연료','biofuel','biofuels','bioenergi','bahan bakar nabati'],
 ['바이오디젤','biodiesel'],['바이오에탄올','bioethanol','bioetanol'],
 ['바이오항공유','bioavtur'],
 ['수출','export','ekspor'],['수출세','수출부담금','export levy','bea keluar','pungutan'],
 ['인허가','허가','permitting','perizinan','izin'],
 ['혼합의무','혼합 의무','blending','pencampuran'],
 ['지속가능성','지속가능','sustainability','berkelanjutan','ispo'],
 ['기금','fund','dana'],['보조금','지원금','subsidy','subsidi','bantuan','subsidies_incentives'],
 ['금융지원','financing','pembiayaan'],
 ['세금감면','세금 감면','법인세감면','tax allowance','tax holiday','tax_incentive','pengurangan pajak','fasilitas pajak','keringanan pajak'],
 ['투자인센티브','투자 인센티브','investment incentive','insentif','subsidies_incentives'],
 ['환경','environment','lingkungan','environmental_land'],
 ['로열티','royalty','royalties','iuran produksi','royalties_tax'],
 ['재식재','replanting','peremajaan'],['인프라지원','infrastructure_support','sarana dan prasarana'],
];
export function parseTerms(query) {
 if(query.length>240)throw Error('검색어는 240자 이내로 입력하세요.');
 const raw=query.trim().split(/[,，]+/).map(x=>x.trim()).filter(Boolean).flatMap(term=>
  GROUPS.some(g=>g.some(a=>a.toLowerCase()===term.toLowerCase()))||/^[a-z. -]+\s+\d[\d/. -]*$/i.test(term)
   ?[term]:term.split(/\s+/));
 if(raw.length>6)throw Error('검색 조건은 최대 6개입니다.');
 return [...new Set(raw)].map(term=>({term,aliases:GROUPS.find(g=>g.some(a=>a.toLowerCase()===term.toLowerCase()))||[term]}));
}
function response(body,status=200){return Response.json(body,{status,headers:{'Cache-Control':status===200?'public, max-age=60':'no-store','X-Content-Type-Options':'nosniff'}});}
export function createHandler(fetcher=fetch){
 return async function handleIdnPolicy(request,env){
  const url=new URL(request.url),path=url.pathname;
  if(request.method!=='GET')return response({error:'GET만 지원합니다.'},405);
  let rpc,args;
  try{
   if(path==='/api/idn/search'){
    const q=url.searchParams.get('q')||'';
    const topic=url.searchParams.get('topic')||null,level=url.searchParams.get('level')||null;
    const jurisdiction=url.searchParams.get('jurisdiction')||null,sort=url.searchParams.get('sort')||'relevance';
    if(topic&&!Object.hasOwn(TOPICS,topic)||level&&!['national','provincial','regency','city'].includes(level)||!['relevance','year'].includes(sort)||jurisdiction?.length>120)throw Error('필터를 확인하세요.');
    const limit=Number(url.searchParams.get('limit')||20),offset=Number(url.searchParams.get('offset')||0);
    if(!Number.isInteger(limit)||limit<1||limit>50||!Number.isInteger(offset)||offset<0||offset>10000)throw Error('페이지 범위를 확인하세요.');
    args={p_terms:parseTerms(q),p_topic:topic,p_level:level,p_jurisdiction:jurisdiction,p_sort:sort,
      p_require_all:url.searchParams.get('match')==='all',p_limit:limit,p_offset:offset};
    rpc='idn_search_documents';
   }else if(path.startsWith('/api/idn/documents/')){
    const id=decodeURIComponent(path.slice('/api/idn/documents/'.length));
    if(!/^idn-[a-z0-9-]{1,160}$/.test(id))throw Error('문서 ID를 확인하세요.');
    args={p_document_id:id};rpc='idn_get_document';
   }else return response({error:'인도네시아 API 경로를 찾을 수 없습니다.'},404);
  }catch(e){return response({error:e.message},400);}
  if(!env.SUPABASE_URL||!env.SUPABASE_SERVICE_ROLE_KEY)return response({error:'인도네시아 검색 연결이 준비되지 않았습니다.',unavailable:true},503);
  try{
   const key=env.SUPABASE_SERVICE_ROLE_KEY;
   const headers={apikey:key,'Content-Type':'application/json','Content-Profile':'public','Accept-Profile':'public'};
   if(key.startsWith('eyJ'))headers.Authorization=`Bearer ${key}`;
   const upstream=await fetcher(`${env.SUPABASE_URL.replace(/\/$/,'')}/rest/v1/rpc/${rpc}`,{
    method:'POST',headers,body:JSON.stringify(args),signal:AbortSignal.timeout(12000)});
   if(!upstream.ok){await upstream.body?.cancel();return response({error:'인도네시아 DB 조회에 실패했습니다.',unavailable:true},502);}
   const body=await upstream.json();
   if(body===null)return response({error:'저장된 문서가 없습니다.'},404);
   if(body.country!=='IDN')return response({error:'국가별 데이터 검증에 실패했습니다.'},502);
   return response(body);
  }catch{return response({error:'인도네시아 검색에 연결하지 못했습니다.',unavailable:true},502);}
 };
}
export const handleIdnPolicy=createHandler();
