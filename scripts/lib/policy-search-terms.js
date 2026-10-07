'use strict';
// Auditable, conservative concept aliases. Unknown terms remain literal.
const GROUPS = [
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
function annotate(item,terms){
  const fields=[['title',plain(item.title)],['summary',plain(item.summary)]];
  const matches=terms.map(t=>{
    for(const [field,text]of fields)for(const alias of t.aliases){const snippet=evidence(text,alias);if(snippet)return {term:t.label,matched:true,alias,field,snippet};}
    return {term:t.label,matched:false};
  });
  const count=matches.filter(m=>m.matched).length;
  return {...item,summary:undefined,condition_matches:matches,matched_condition_count:count,total_condition_count:terms.length,match_level:count===terms.length?'all':'partial'};
}
function clause(fields,term){
  return `or(${fields.flatMap(field=>term.aliases.map(alias=>`${field}.ilike.${JSON.stringify('*'+alias.replace(/ /g,'*')+'*')}`)).join(',')})`;
}
function rank(items,terms,limit){
  return items.map(i=>annotate(i,terms)).filter(i=>i.matched_condition_count>0)
    .sort((a,b)=>b.matched_condition_count-a.matched_condition_count || (b.similarity_score||0)-(a.similarity_score||0) || String(a.id).localeCompare(String(b.id)))
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
  return 0;
}
module.exports={parse,annotate,clause,rank,single,lexicalRank};
