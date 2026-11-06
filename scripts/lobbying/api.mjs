import { cases } from './cases.mjs';

const SELECT = 'record_id,source,kind,source_url,source_date,registrant_name,client_name,title,country_raw,country_codes,related_countries,topics,text_state,updated_at';
const TOPICS = new Set(['supply_chain','mining','agriculture','semiconductors','data_centers','steel']);
const TYPES = new Set(['bill','public_law','executive_order','regulation']);
const json = (body, status=200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'public, max-age=60' }
});
const identity = value => /^[a-zA-Z0-9:_-]{1,200}$/.test(value || '');
const bounded = (value, fallback, max) => Math.min(max, Math.max(0, Number.isSafeInteger(Number(value)) && value !== null ? Number(value) : fallback));

export async function handleLobbying(request, env, read, rpc) {
  if (request.method !== 'GET') return json({error:'Method not allowed'},405);
  const url = new URL(request.url), q = url.searchParams;
  const path = url.pathname.replace(/^\/api\/us\/lobbying\/?/, '').replace(/\/$/,'');
  try {
    if (path === 'cases') return json({items:cases});
    if (path.startsWith('cases/')) {
      const item = cases.find(c=>c.case_id===path.slice(6));
      return item ? json(item) : json({error:'사안을 찾을 수 없습니다.'},404);
    }
    if (path === 'coverage') return json(await rpc(env,'lobby_coverage',{}));
    if (path.startsWith('records/')) {
      const id=decodeURIComponent(path.slice(8));
      if (!identity(id)) return json({error:'Invalid record ID'},400);
      const filter=new URLSearchParams({record_id:`eq.${id}`,limit:'1'});
      const [rows,activities,links]=await Promise.all([
        read(env,'lobby_records',new URLSearchParams({...Object.fromEntries(filter),select:`${SELECT},pages,body_sha256,text_error,filing_year:raw_payload->>filing_year,filing_period:raw_payload->>filing_period,income:raw_payload->>income,expenses:raw_payload->>expenses`}).toString()),
        read(env,'lobby_activities',new URLSearchParams({record_id:`eq.${id}`,select:'activity_id,grain,description,issue_code,government_entities,topics,evidence',limit:'200'}).toString()),
        read(env,'lobby_policy_links',new URLSearchParams({record_id:`eq.${id}`,select:'target_type,target_id,raw_reference,resolution_status,evidence',limit:'200'}).toString())
      ]);
      return rows[0] ? json({record:rows[0],activities,links}) : json({error:'아직 수집하지 않은 문서입니다.'},404);
    }
    if (path !== '' && path !== 'records') return json({error:'Unknown endpoint'},404);
    const filter=new URLSearchParams({select:SELECT,kind:'eq.document',order:'source_date.desc.nullslast,record_id.asc'});
    const limit=Math.max(1,bounded(q.get('limit'),25,50)), offset=bounded(q.get('offset'),0,1000000);
    filter.set('limit',String(limit+1)); filter.set('offset',String(offset));
    if (q.has('source')) {
      if (!['fara','lda'].includes(q.get('source'))) return json({error:'Invalid source'},400);
      filter.set('source',`eq.${q.get('source')}`);
    }
    if (q.has('country')) {
      const country=q.get('country');
      if (!/^[A-Z]{2}$/.test(country)) return json({error:'Invalid country'},400);
      filter.set('or',`(country_codes.cs.{${country}},related_countries.cs.{${country}})`);
    }
    if (q.has('topic')) {
      if (!TOPICS.has(q.get('topic'))) return json({error:'Invalid topic'},400);
      filter.set('topics',`cs.{${q.get('topic')}}`);
    }
    if (q.has('q')) {
      const term=q.get('q').trim();
      if (term.length>120 || !/^[\p{L}\p{N}\s._-]+$/u.test(term)) return json({error:'검색어는 문자·숫자로 입력해 주세요.'},400);
      filter.set('search_vector',`plfts(simple).${term}`);
    }
    if (q.has('policy_id') || q.has('policy_type')) {
      if (!TYPES.has(q.get('policy_type')) || !identity(q.get('policy_id'))) return json({error:'Invalid policy identity'},400);
      const links=await read(env,'lobby_policy_links',new URLSearchParams({select:'record_id',
        target_type:`eq.${q.get('policy_type')}`,target_id:`eq.${q.get('policy_id')}`,resolution_status:'eq.confirmed',limit:'1000'}).toString());
      const ids=[...new Set(links.map(l=>l.record_id).filter(identity))];
      if (!ids.length) return json({items:[],has_more:false,offset,link_status:'confirmed_only'});
      filter.set('record_id',`in.(${ids.join(',')})`);
    }
    const rows=await read(env,'lobby_records',filter.toString());
    return json({items:rows.slice(0,limit),has_more:rows.length>limit,offset,
      note:'원문 목록과 본문 확보 상태가 다릅니다. 검색 결과 없음은 로비가 없다는 뜻이 아닙니다.'});
  } catch (error) {
    // Do not expose DB diagnostics/keys to public clients.
    console.error('Lobbying read failed', {name:error.name});
    return json({error:'로비 데이터를 불러오지 못했습니다. 수집·DB 연결 상태를 확인해 주세요.'},503);
  }
}
