'use strict';
// Auditable, conservative concept aliases. Unknown terms remain literal.
const GROUPS = [
  ['캐나다', '케나다', 'canada', 'canadian'],
  ['관세', 'tariff', 'tariffs', 'customs duty', 'customs duties', 'import duty', 'import duties', 'ad valorem duty', 'ad valorem duties', 'ad valorem rate of duty', 'imposing duties'],
  ['중국', '중화인민공화국', '중화 인민 공화국', 'china', 'chinese', "people's republic of china", 'people’s republic of china'], ['멕시코', 'mexico', 'mexican'], ['한국', 'south korea', 'republic of korea'],
  ['일본', 'japan', 'japanese'], ['유럽연합', '유럽 연합', 'european union'],
  ['기후', 'climate'], ['환경', 'environment', 'environmental'], ['비상사태', '비상 사태', 'emergency'],
  ['안보', 'security'], ['혁신', 'innovation'], ['일자리', 'jobs'],
  ['인프라', '기반시설', '기반 시설', 'infrastructure'], ['공급망', '공급 망', 'supply chain', 'supply chains'],
  ['알래스카', 'alaska'], ['세계보건기구', '세계 보건 기구', 'world health organization'],
  ['에너지', 'energy'], ['에너지안보', '에너지 안보', 'energy security'],
  ['원유', 'crude oil', 'crude petroleum'], ['석유', 'petroleum'],
  ['천연가스', '천연 가스', 'natural gas'],
  ['액화천연가스', '액화 천연가스', 'lng', 'liquefied natural gas', 'liquified natural gas'],
  ['전력', '전기', 'electricity', 'electric power'], ['전력망', 'electric grid', 'electrical grid', 'power grid'],
  ['원자력', '원자력에너지', '원자력 에너지', 'nuclear energy', 'nuclear power'], ['우라늄', 'uranium'],
  ['재생에너지', '재생 에너지', 'renewable energy'], ['태양광', 'solar energy', 'solar power'],
  ['풍력', 'wind energy', 'wind power'], ['수소', 'hydrogen'], ['석탄', 'coal'],
  ['시추', 'drilling'], ['정유', 'oil refining', 'petroleum refining'],
  ['탄소포집', '탄소 포집', 'carbon capture'], ['온실가스', '온실 가스', 'greenhouse gas', 'greenhouse gases'],
  ['구리', 'copper'], ['알루미늄', 'aluminum', 'aluminium'],
  ['농업', 'agriculture', 'agricultural'], ['보건의료', '보건 의료', 'health care', 'healthcare'],
  ['해운', 'maritime shipping', 'ocean shipping'], ['보조금', 'subsidy', 'subsidies'],
  ['경제제재', '경제 제재', 'economic sanction', 'economic sanctions'],
  // Policy topics stay distinct; ambiguous abbreviations are not aliases.
  ['금융', 'finance', 'financial'], ['금융시장', '금융 시장', 'financial market', 'financial markets'],
  ['금융규제', '금융 규제', 'financial regulation', 'financial regulations', 'financial regulatory'],
  ['은행', 'banking', 'commercial bank', 'commercial banks', 'depository institution', 'depository institutions', 'bank holding company', 'bank holding companies'],
  ['자본시장', '자본 시장', 'capital market', 'capital markets'], ['증권', 'securities'],
  ['보험', 'insurance'], ['금리', 'interest rate', 'interest rates'],
  ['스테이블코인', '스테이블 코인', 'stablecoin', 'stablecoins', 'stable coin', 'stable coins'],
  ['자금세탁', '자금 세탁', 'money laundering'],
  ['자금세탁방지', '자금 세탁 방지', 'anti money laundering'],
  ['외국인투자', '외국인 투자', 'foreign investment', 'foreign investments', 'foreign direct investment'],
  ['해외투자', '해외 투자', 'outbound investment', 'outbound investments'],
  ['미중관계', '미중', '미중 관계', 'us china relations', 'united states china relations'],
  ['중국공산당', '중국 공산당', 'chinese communist party', 'communist party of china'],
  ['대만', 'taiwan', 'taiwanese'], ['홍콩', 'hong kong'],
  ['국가안보', '국가 안보', 'national security'], ['경제안보', '경제 안보', 'economic security'],
  ['인공지능', '인공 지능', 'artificial intelligence'],
  ['첨단반도체', '첨단 반도체', 'advanced semiconductor', 'advanced semiconductors'],
  ['반도체장비', '반도체 장비', 'semiconductor equipment', 'semiconductor manufacturing equipment'],
  ['반도체소재', '반도체 소재', 'semiconductor material', 'semiconductor materials'],
  ['반도체제조', '반도체 제조', 'semiconductor manufacturing', 'semiconductor fabrication'],
  ['집적회로', '집적 회로', 'integrated circuit', 'integrated circuits'],
  ['고대역폭메모리', '고대역폭 메모리', 'hbm', 'high bandwidth memory'],
  ['첨단패키징', '첨단 패키징', 'advanced packaging'],
  ['첨단산업', '첨단 산업', 'advanced industry', 'advanced industries', 'high tech industry', 'high tech industries'],
  ['첨단기술', '첨단 기술', 'advanced technology', 'advanced technologies', 'frontier technology', 'frontier technologies'],
  ['핵심신흥기술', '핵심 신흥 기술', 'critical and emerging technology', 'critical and emerging technologies'],
  ['첨단제조', '첨단 제조', 'advanced manufacturing'],
  ['양자컴퓨팅', '양자 컴퓨팅', 'quantum computing', 'quantum computation'],
  ['양자기술', '양자 기술', 'quantum technology', 'quantum technologies'],
  ['로봇공학', '로봇 공학', 'robotics'],
  ['생명공학', '생명 공학', 'biotechnology', 'biotechnologies'],
  ['항공우주', '항공 우주', 'aerospace'],
  ['수입규제', '수입 규제', 'import restriction', 'import restrictions', 'import ban', 'import bans'],
  ['무역협정', '무역 협정', 'trade agreement', 'trade agreements', 'free trade agreement', 'free trade agreements'],
  ['니켈', 'nickel'],
  ['수출통제', '수출 통제', '수출규제', '수출 규제', 'export control', 'export controls', 'export restriction', 'export restrictions', 'export ban', 'export bans', 'export licensing', 'export license', 'export licenses'],
  ['배터리', 'battery', 'batteries', '이차전지', '이차 전지', 'secondary battery', 'secondary batteries'],
  ['리튬', 'lithium'], ['코발트', 'cobalt'], ['반도체', 'semiconductor', 'semiconductors'],
  ['희토류', 'rare earth', 'rare earths'], ['핵심광물', '핵심 광물', 'critical mineral', 'critical minerals'],
  ['암호화폐', 'cryptocurrency', 'cryptocurrencies', 'crypto', 'digital asset', 'digital assets', 'digital commodity', 'digital commodities'],
];
const normalize = value => String(value || '').normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim();
function parse(query) {
  if (!/[,，]/u.test(query)) return null;
  if (query.length > 200) throw new Error('조건 검색은 200자 이내로 입력해 주세요.');
  const parts=query.split(/[,，]/u).map(normalize).filter(Boolean);
  const terms=[];
  for(const label of parts){
    if(label.length>60 || !/^[\p{L}\p{N}\s-]+$/u.test(label)) throw new Error('각 조건은 문자·숫자·공백·하이픈으로 입력해 주세요.');
    const aliases=GROUPS.find(g=>g.includes(label)) || [label];
    const key=aliases[0];
    if(!terms.some(t=>t.key===key))terms.push({key,label,aliases});
  }
  if(!terms.length) throw new Error('쉼표 사이에 검색 조건을 입력해 주세요.');
  if(terms.length>5) throw new Error('조건은 최대 5개까지 입력해 주세요.');
  return terms;
}
function plain(value){return normalize(String(value||'').replace(/<[^>]*>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&'));}
function evidence(text,alias){
  const escaped=alias.replace(/[.*+?^${}()|[\]\\]/g,'\\$&').replace(/ /g,'[\\s-]+');
  const re=new RegExp(`${/^[a-z0-9]/.test(alias)?'(?<![a-z0-9])':''}${escaped}${/[a-z0-9]$/.test(alias)?'(?![a-z0-9])':''}`,'iu');
  const found=re.exec(text);if(!found)return null;
  return text.slice(Math.max(0,found.index-75),Math.min(text.length,found.index+found[0].length+110));
}
// A shared 360-character window proves proximity, not legal applicability.
function relationship(fields,terms,matches){
  const matched=terms.filter((t,i)=>matches[i].matched);
  if(matched.length<2)return null;
  for(const part of fields){
    for(let offset=0;offset<part.text.length;offset+=180){
      const window=part.text.slice(offset,offset+360);
      if(matched.every(t=>t.aliases.some(a=>evidence(window,a))))
        return part.field==='cited_document'?'cited_shared_passage':'shared_passage';
    }
  }
  const cited=matches.filter(m=>m.matched&&m.field==='cited_document');
  return cited.length===matched.length?'cited_separate_mentions':cited.length?'mixed_citation':'separate_mentions';
}
const TYPES=['bill','public_law','executive_order','regulation'];
// Quotas are applied only after relevance filtering, so irrelevant empty lanes
// are never filled. Preserve ranked order inside each lane.
function balancedLimit(items,limit){
  const lanes=TYPES.map(t=>items.filter(i=>i.type===t));const picked=new Set();
  for(let depth=0;picked.size<limit&&lanes.some(l=>l.length>depth);depth++)
    for(const lane of lanes)if(lane[depth]&&picked.size<limit)picked.add(lane[depth]);
  return items.filter(i=>picked.has(i));
}
// Fuse independent lexical and semantic ranks within each type. An exact short
// title remains first; raw cosine and arbitrary lexical scores are not added.
function fuse(items){
  const scores=new Map();
  for(const type of TYPES){
    const lane=items.filter(i=>i.type===type);
    const lists=[lane.filter(i=>i.relevance_rank>0).sort((a,b)=>b.relevance_rank-a.relevance_rank||Number(b.match_type==='exact_title')-Number(a.match_type==='exact_title')||String(b.latest_action_date||b.enacted_date||b.publication_date||'').localeCompare(String(a.latest_action_date||a.enacted_date||a.publication_date||''))||String(a.id).localeCompare(String(b.id))),
      lane.filter(i=>i.similarity_score!=null).sort((a,b)=>b.similarity_score-a.similarity_score||String(a.id).localeCompare(String(b.id)))];
    for(const list of lists)list.forEach((i,n)=>scores.set(i,(scores.get(i)||0)+1/(60+n+1)));
  }
  return items.map(i=>({...i,fusion_score:scores.get(i)||0})).sort((a,b)=>Number(b.relevance_rank===4)-Number(a.relevance_rank===4)||Number(b.match_type==='exact_title')-Number(a.match_type==='exact_title')||b.fusion_score-a.fusion_score||String(a.id).localeCompare(String(b.id)));
}
function annotate(item,terms){
  const fields=[{field:'title',text:plain(item.title)},{field:'summary',text:plain(item.summary)},
    ...(item.evidence_parts||[]).map(p=>({...p,text:plain(p.text)}))];
  const matches=terms.map(t=>{
    for(const part of fields)for(const alias of t.aliases){const snippet=evidence(part.text,alias);if(snippet)return {term:t.label,matched:true,alias,field:part.field,snippet,
      ...(part.source_url?{source_url:part.source_url}:{}),...(part.target_id?{target_type:part.target_type,target_id:part.target_id,citation:part.citation,citation_url:part.citation_url}:{})};}
    return {term:t.label,matched:false};
  });
  const count=matches.filter(m=>m.matched).length;
  return {...item,summary:undefined,evidence_parts:undefined,condition_matches:matches,matched_condition_count:count,total_condition_count:terms.length,condition_relationship:relationship(fields,terms,matches),match_level:count===terms.length?'all':count?'partial':'semantic_only'};
}
function clause(fields,term){
  return `or(${fields.flatMap(field=>term.aliases.map(alias=>`${field}.ilike.${JSON.stringify('*'+alias.replace(/ /g,'*')+'*')}`)).join(',')})`;
}
function rank(items,terms,limit){
  return items.map(i=>annotate(i,terms)).filter(i=>i.matched_condition_count>0 || (i.semantic_candidate && i.similarity_score>=0.65))
    .sort((a,b)=>b.matched_condition_count-a.matched_condition_count || Number(['shared_passage','cited_shared_passage'].includes(b.condition_relationship))-Number(['shared_passage','cited_shared_passage'].includes(a.condition_relationship)) || (b.similarity_score||0)-(a.similarity_score||0) || String(a.id).localeCompare(String(b.id)))
    .slice(0,limit);
}
function single(query) {
  // PostgREST syntax and LIKE wildcards must never become user operators.
  const label=normalize(query).replace(/[^\p{L}\p{N}\s-]/gu,' ').replace(/\s+/g,' ').trim();
  return {label,aliases:GROUPS.find(g=>g.includes(label))||[label]};
}
function lexicalRank(item,term) {
  const title=plain(item.title),summary=plain(item.summary);
  if(term.aliases.some(a=>title===a))return 4;
  // CRS summaries conventionally start with the official short title in bold.
  // Read only that heading; an incidental act mentioned later is not an alias.
  const heading=String(item.summary||'').match(/^\s*<p>\s*<(?:strong|b)>([\s\S]*?)<\/(?:strong|b)>\s*<\/p>/i)?.[1];
  if(heading && plain(heading).split(/\s+or\s+(?:the\s+)?/).some(name=>term.aliases.includes(name.replace(/\s+of\s+\d{4}$/,''))))return 4;
  if(term.aliases.some(a=>evidence(title,a)))return 3;
  if(term.aliases.some(a=>evidence(summary,a)))return 1;
  if((item.evidence_parts||[]).some(p=>term.aliases.some(a=>evidence(plain(p.text),a))))return 1;
  return 0;
}
module.exports={parse,annotate,clause,rank,single,lexicalRank,balancedLimit,fuse};
