// IDN-only read API. No collection, provider calls, user data or US fallback.
import {embedTexts} from './embeddings.mjs';
// The site Worker keeps its Google AI Studio key as AI_STUDIO_API_KEY (US policy
// search uses it); local tools set GEMINI_API_KEY. Same API, either works.
const geminiKey=env=>env.GEMINI_API_KEY||env.AI_STUDIO_API_KEY;
export const TOPICS = {coal:'석탄',nickel_mining:'니켈',palm_oil:'팜유',biofuel:'바이오연료',bauxite:'보크사이트·알루미늄',copper:'구리',tin:'주석',cobalt:'코발트',manganese:'망간',iron_steel:'철광석·철강',silica:'실리카·석영',gold_silver:'금·은',rare_earths:'희토류',hydropower:'수력발전'};
const GROUPS = [
 ['석탄','coal','batubara','batu bara'],
 ['수력발전','수력','hydropower','hydro power','tenaga air','plta'],
 ['북수마트라','sumatera utara'],['중부칼리만탄','중앙칼리만탄','kalimantan tengah'],['서칼리만탄','kalimantan barat'],['동칼리만탄','kalimantan timur'],['동남술라웨시','sulawesi tenggara'],
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
 ['환경영향평가','환경평가','amdal','ukl-upl','sppl','environmental_assessment'],
 ['산림','forest','forestry','kehutanan'],['토지','land rights','hak atas tanah','land_rights'],
 ['공간계획','토지이용','spatial planning','tata ruang','spatial_planning'],
 ['폐수','오폐수','wastewater','air limbah'],['폐기물','유해폐기물','hazardous waste','limbah b3','hazardous_waste'],
 ['대기오염','대기배출','air emissions','emisi','air_emissions'],
 ['광산복구','폐광','reclamation','reklamasi','pascatambang'],
 ['작업예산계획','연간작업계획','rkab','rencana kerja dan anggaran biaya'],
 ['국내공급의무','내수공급의무','dmo','domestic market obligation','kebutuhan batubara dalam negeri','kepentingan dalam negeri'],
 // HBA is a reference index; HPB is a sale-price benchmark. Do not equate them.
 ['석탄기준지수','hba','harga batubara acuan'],
 ['판매기준가격','가격기준','기준가격','hpb','harga patokan','harga patokan batubara'],
 ['석탄혼합','석탄 혼합','coal blending','pencampuran batubara'],
 ['복구보증금','광산복구보증금','jaminan reklamasi'],
 ['허가구역중복','광구중복','중복허가','permit overlap','tumpang tindih'],
 ['행정제재','administrative sanctions','sanksi administratif'],
 ['벌크화물','벌크 화물','벌크통관','bulk cargo','barang impor curah','barang ekspor curah'],
 ['이탄지','peatland','gambut'],['기후적응','climate adaptation','adaptasi perubahan iklim','climate_adaptation'],
 ['환경성과평가','기업환경평가','proper','properlink','environmental_performance'],
 ['로열티','royalty','royalties','iuran produksi','royalties_tax'],
 ['재식재','replanting','peremajaan'],['인프라지원','infrastructure_support','sarana dan prasarana'],
 // Business-law relevance is a retrieval aid, never a finding of applicability.
 ['민법','civil law','kuhperdata','kitab undang-undang hukum perdata','civil_law'],
 ['상법','commercial law','hukum dagang','kuhd','kitab undang-undang hukum dagang','commercial_law'],
 ['계약','계약서','contract','kontrak','perjanjian','contract_law'],
 ['매매','sale and purchase','jual beli','sale_purchase'],
 ['채무불이행','계약위반','breach of contract','wanprestasi','contract_breach'],
 ['불가항력','force majeure','keadaan memaksa','overmacht'],
 ['회사법','회사설립','company law','perseroan terbatas','corporate_law'],
 ['지분인수','기업인수','acquisition','pengambilalihan','share_acquisition'],
 ['담보','담보권','security interest','jaminan','collateral'],
 ['양도담보','fiduciary security','fidusia','fiduciary_security'],
 ['파산','도산','bankruptcy','kepailitan','insolvency'],
 ['채무재조정','지급의무유예','pkpu','penundaan kewajiban pembayaran utang','debt_restructuring'],
 ['중재','arbitration','arbitrase'],['분쟁해결','dispute resolution','penyelesaian sengketa'],
 ['투자','investment','penanaman modal'],
 ['트레이딩','무역','trading','trade','perdagangan'],
 ['보크사이트','알루미늄','bauxite','bauksit','alumina','aluminium','aluminum'],
 ['구리','copper','tembaga'],['주석','tin','timah'],['코발트','cobalt','kobal'],
 ['망간','manganese','mangan'],['철광석','철강','iron ore','iron_steel','bijih besi','besi baja'],
 ['실리카','석영','silica','silika','kuarsa'],['금·은','금은','금광','은광','gold_silver','gold','silver','emas','perak'],
 ['희토류','rare earths','rare_earths','logam tanah jarang'],
 ['상류','upstream','hulu','stream_upstream'],['중류','midstream','stream_midstream'],
 ['하류','downstream','hilir','stream_downstream'],
 ['제련','정련','smelter','pemurnian','pengolahan'],['배터리','battery','baterai'],
 ['인증','certification','sertifikasi'],['대통령령','perpres','peraturan presiden'],
 ['국산화','국산화율','현지조달','local content','tkdn','tingkat komponen dalam negeri','local_content'],
 ['기업기여도','bmp','bobot manfaat perusahaan'],
 ['산업정보보고','산업정보 보고','산업보고','siinas','sistem informasi industri nasional','industrial_reporting'],
];
export function parseTerms(query) {
 if(query.length>240)throw Error('검색어는 240자 이내로 입력하세요.');
 const raw=query.trim().split(/[,，]+/).map(x=>x.trim()).filter(Boolean).flatMap(term=>
  GROUPS.some(g=>g.some(a=>a.toLowerCase()===term.toLowerCase()))||/^[a-z. -]+\s+\d[\d/. -]*$/i.test(term)
   ?[term]:term.split(/\s+/));
 if(raw.length>6)throw Error('검색 조건은 최대 6개입니다.');
 return [...new Set(raw)].map(term=>{const lookup=term==='금'?'금광':term==='은'?'은광':term;return {term,aliases:GROUPS.find(g=>g.some(a=>a.toLowerCase()===lookup.toLowerCase()))||[term]};});
}
function response(body,status=200){return Response.json(body,{status,headers:{'Cache-Control':status===200?'public, max-age=60':'no-store','X-Content-Type-Options':'nosniff'}});}
export function createHandler(fetcher=fetch){
 const queryCache=new Map();
 return async function handleIdnPolicy(request,env){
  const url=new URL(request.url),path=url.pathname;
  if(request.method!=='GET')return response({error:'GET만 지원합니다.'},405);
  let rpc,args;
  try{
   if(path==='/api/idn/search'){
    const q=url.searchParams.get('q')||'';
    const topic=url.searchParams.get('topic')||null,level=url.searchParams.get('level')||null;
    const jurisdiction=url.searchParams.get('jurisdiction')||null,sort=url.searchParams.get('sort')||'relevance';
    if(topic&&!Object.hasOwn(TOPICS,topic)||level&&!['national','local','provincial','regency','city'].includes(level)||!['relevance','year'].includes(sort)||jurisdiction?.length>120)throw Error('필터를 확인하세요.');
    if(level==='national'&&jurisdiction)throw Error('중앙정부 문서는 지방 발행지역을 선택하지 않고 검색하세요.');
    const limit=Number(url.searchParams.get('limit')||20),offset=Number(url.searchParams.get('offset')||0);
    if(!Number.isInteger(limit)||limit<1||limit>50||!Number.isInteger(offset)||offset<0||offset>10000)throw Error('페이지 범위를 확인하세요.');
    const stream=url.searchParams.get('stream')||null,group=url.searchParams.get('group')||null,type=url.searchParams.get('type')||null;
    if(stream&&!['upstream','midstream','downstream','trading'].includes(stream)||group&&!['business','sector'].includes(group)||type&&!['UU','PP','Perpres','Inpres','Permen','Permendag','PMK','Perda','Pergub','Perbup','Keputusan','Kepmen','Permentan','Permenperin'].includes(type))throw Error('사업단계·자료 필터를 확인하세요.');
    const mode=url.searchParams.get('mode')||'keyword';if(!['keyword','hybrid'].includes(mode))throw Error('검색 방식을 확인하세요.');
    if(mode==='hybrid'&&q.trim()&&(env.IDN_SEMANTIC_ENABLED!=='true'||!geminiKey(env)))return response({error:'인도네시아 문서개요 의미검색이 이 서버에서 활성화되지 않았습니다.'},503);
    const terms=parseTerms(q);
    if(!env.SUPABASE_URL||!env.SUPABASE_SERVICE_ROLE_KEY)return response({error:'인도네시아 검색 연결이 준비되지 않았습니다.',unavailable:true},503);
    let queryVector=null;
    if(mode==='hybrid'&&q.trim()){
     try{
      const cached=queryCache.get(q);
      if(cached&&cached.expires>Date.now())queryVector=cached.vector;
      else{[queryVector]=await embedTexts([q],geminiKey(env),'RETRIEVAL_QUERY',fetcher);if(queryCache.size>=64)queryCache.delete(queryCache.keys().next().value);queryCache.set(q,{vector:queryVector,expires:Date.now()+600000});}
     }catch{return response({error:'의미검색 연결에 실패했습니다. 키워드 검색을 이용하세요.'},503);}
    }
    args={p_terms:terms,p_topic:topic,p_level:level,p_jurisdiction:jurisdiction,p_sort:sort,
      p_require_all:url.searchParams.get('match')==='all',p_limit:limit,p_offset:offset,p_stream:stream,p_group:group,p_type:type,p_query_embedding:queryVector};
    rpc='idn_search_documents_v2';
   }else if(path==='/api/idn/legal-effect'){
    const ids=(url.searchParams.get('ids')||'').split(',');
    if(ids.length>50||ids.some(id=>!/^idn-[a-z0-9-]{1,160}$/.test(id)))throw Error('효력 검토 문서 범위를 확인하세요.');
    rpc='idn_legal_effect';args={p_document_ids:ids};
   }else if(path==='/api/idn/catalogue-status'){
    rpc='idn_catalogue_status';args={};
   }else if(path==='/api/idn/catalogue-gaps'){
    const source=url.searchParams.get('source')||null,limit=Number(url.searchParams.get('limit')||100),offset=Number(url.searchParams.get('offset')||0);
    if(source&&!/^[a-z0-9-]{1,100}$/.test(source)||!Number.isInteger(limit)||limit<1||limit>200||!Number.isInteger(offset)||offset<0||offset>10000)throw Error('목록 대조 범위를 확인하세요.');
    rpc='idn_catalogue_gaps';args={p_source_id:source,p_limit:limit,p_offset:offset};
   }else if(path==='/api/idn/coverage'){
    const topic=url.searchParams.get('topic')||null,rawPriority=url.searchParams.get('priority');
    const priority=rawPriority===null?null:Number(rawPriority);
    if(topic&&!Object.hasOwn(TOPICS,topic)||priority!==null&&(!Number.isInteger(priority)||priority<1||priority>3))throw Error('공백 목록 필터를 확인하세요.');
    rpc='idn_coverage';args={p_topic:topic,p_priority:priority};
   }else if(path==='/api/idn/business'){
    const role=url.searchParams.get('role'),region=url.searchParams.get('region')||null,issue=url.searchParams.get('issue')||null;
    if(!['miner','smelter','trader','plantation','bioenergy','manufacturer','investor','transporter'].includes(role)||region?.length>120||issue&&!/^[a-z_]{1,80}$/.test(issue))throw Error('사업자·지역·검토사항을 확인하세요.');
    rpc='idn_business_search';args={p_role:role,p_region:region,p_issue:issue};
   }else if(path.startsWith('/api/idn/documents/')||path.startsWith('/api/idn/context/')){
    const context=path.startsWith('/api/idn/context/');
    const id=decodeURIComponent(path.slice((context?'/api/idn/context/':'/api/idn/documents/').length));
    if(!/^idn-[a-z0-9-]{1,160}$/.test(id))throw Error('문서 ID를 확인하세요.');
    args={p_document_id:id};rpc=context?'idn_document_context':'idn_get_document';
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
   if(rpc==='idn_search_documents_v2')body.semantic_enabled=env.IDN_SEMANTIC_ENABLED==='true'&&Boolean(geminiKey(env));
   if(rpc==='idn_search_documents_v2'&&body.items?.length&&args.p_terms?.length){
    // Optional evidence annotations cannot change document ranking, totals or hard filters.
    body.passage_annotations_available=false;
    try{
     const notes=await fetcher(`${env.SUPABASE_URL.replace(/\/$/,'')}/rest/v1/rpc/idn_search_passages`,{
      method:'POST',headers,body:JSON.stringify({p_document_ids:body.items.map(x=>x.document_id),p_terms:args.p_terms,p_query_embedding:args.p_query_embedding}),signal:AbortSignal.timeout(12000)});
     if(!notes.ok){await notes.body?.cancel();throw Error('Unavailable evidence');}
     const evidence=await notes.json();if(evidence.country!=='IDN'||!Array.isArray(evidence.items))throw Error('Invalid evidence');
     for(const item of body.items)item.matched_passages=evidence.items.filter(x=>x.document_id===item.document_id);
     body.passage_annotations_available=true;
    }catch{/* A failed evidence lookup is unavailable, never a verified empty set. */}
   }
   const documents=rpc==='idn_get_document'?[body]:['idn_search_documents_v2','idn_business_search'].includes(rpc)?body.items:[];
   if(documents?.length){
    body.legal_effect_available=false;
    try{
     // Bounded annotations preserve ranking, hard filters and original records on failure.
     const notes=await fetcher(`${env.SUPABASE_URL.replace(/\/$/,'')}/rest/v1/rpc/idn_legal_effect`,{
      method:'POST',headers,body:JSON.stringify({p_document_ids:documents.slice(0,50).map(x=>x.document_id)}),signal:AbortSignal.timeout(12000)});
     if(!notes.ok){await notes.body?.cancel();throw Error('Unavailable legal effect');}
     const effects=await notes.json();if(effects.country!=='IDN'||!Array.isArray(effects.items))throw Error('Invalid legal effect');
     for(const item of documents)item.legal_effect=effects.items.find(x=>x.document_id===item.document_id)||null;
     body.legal_effect_available=true;
    }catch{/* Unavailable evidence never means in force. */}
   }
   return response(body);
  }catch{return response({error:'인도네시아 검색에 연결하지 못했습니다.',unavailable:true},502);}
 };
}
export const handleIdnPolicy=createHandler();
