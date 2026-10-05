const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {sourceLoader,publicLawPackage}=require('../../scripts/lib/policy-search-source');
const {failureReason,reconcileMissingText}=require('../../scripts/sync-policy-search');
const bill={bill_id:'119-hr-1',title:'Trade rules',congress_number:119,bill_type:'hr',bill_number:1,congress_url:'https://www.congress.gov/bill/119th-congress/house-bill/1',source_updated_at:'2026-10-01T00:00:00Z'};
const oldUrl='https://www.govinfo.gov/content/pkg/BILLS-119hr1ih/html/BILLS-119hr1ih.htm';
const newUrl='https://www.govinfo.gov/content/pkg/BILLS-119hr1eh/html/BILLS-119hr1eh.htm';
async function fixture(fn){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'policy-source-')),key=process.env.CONGRESS_API_KEY;process.env.CONGRESS_API_KEY='fixture';
  try{await fn({cacheDir:root,gate:fn=>fn(),get:async table=>table==='bills'?[bill]:table==='bill_text_versions'?[{issued_on:'2025-01-01',html_url:oldUrl}]:[]});}
  finally{if(key===undefined)delete process.env.CONGRESS_API_KEY;else process.env.CONGRESS_API_KEY=key;fs.rmSync(root,{recursive:true,force:true});}
}
test('latest official text supersedes a stale DB version; unchanged source uses the private cache',()=>fixture(async options=>{
  const calls=[];
  const loader=sourceLoader({...options,fetch:async url=>{
    calls.push(new URL(url));
    if(new URL(url).hostname==='api.congress.gov')return Response.json({textVersions:[
      {date:'2025-01-01',formats:[{type:'Formatted Text',url:oldUrl}]},
      {date:'2026-02-11',formats:[{type:'Formatted Text',url:newUrl}]}]});
    assert.equal(String(url),newUrl);return new Response('<p>New enacted text about Canada tariffs.</p>');
  }});
  const one=await loader.document('bill',bill.bill_id),two=await loader.document('bill',bill.bill_id);
  assert.equal(one.input_hash,two.input_hash);assert.equal(calls.length,2);
  assert.ok(one.evidence_parts.some(p=>p.field==='body'&&p.source_url===newUrl&&p.text.includes('New enacted text')));
  assert.ok(!one.evidence_parts.some(p=>p.source_url===oldUrl));
  for(const file of fs.readdirSync(options.cacheDir))assert.ok(!fs.readFileSync(path.join(options.cacheDir,file),'utf8').includes('api_key=fixture'));
}));
test('official-source block fails the job instead of silently asserting stale text is current',()=>fixture(async options=>{
  const loader=sourceLoader({...options,fetch:async()=>new Response('blocked',{status:403})});
  await assert.rejects(()=>loader.document('bill',bill.bill_id),error=>error.status===403);
}));
const law={public_law_id:'119-public-112',law_title:'Hydropower Licensing Transparency Act',enacted_date:'2026-09-25',govinfo_url:null,official_text_url:null,source_package_id:null,source_updated_at:null,bill_id:bill.bill_id};
const lawText='https://www.govinfo.gov/content/pkg/PLAW-119publ112/text/PLAW-119publ112.txt';
test('newly announced law resolves official GovInfo text without a package identifier in DB',()=>fixture(async options=>{
  const loader=sourceLoader({...options,get:async table=>table==='public_laws'?[law]:table==='bills'?[{...bill,summary:null}]:[],fetch:async url=>{
    assert.equal(String(url),lawText);return new Response('Public Law 119-112. Approved hydropower licensing legislation.');
  }});
  const document=await loader.document('public_law',law.public_law_id);
  assert.equal(document.source_url,bill.congress_url);assert.equal(document.text_status,'body');
  assert.ok(document.evidence_parts.some(p=>p.field==='body'&&p.source_url===lawText));
}));
test('unpublished law text indexes official metadata only and never labels linked bill text as enacted law',()=>fixture(async options=>{
  const loader=sourceLoader({...options,get:async table=>table==='public_laws'?[law]:table==='bills'?[{...bill,summary:'Official CRS hydropower summary.'}]:[],fetch:async()=>new Response('not yet available',{status:404})});
  const document=await loader.document('public_law',law.public_law_id);
  assert.equal(document.source_url,bill.congress_url);assert.equal(document.text_status,'unavailable');
  assert.equal(document.body_characters,0);assert.ok(document.evidence_parts.every(p=>p.field!=='body'));
  assert.deepEqual(document.evidence_parts.map(p=>p.field),['title','summary']);
}));
test('a source without any official provenance fails before database persistence',()=>fixture(async options=>{
  const loader=sourceLoader({...options,get:async table=>table==='public_laws'?[{...law,bill_id:null}]:[],fetch:async()=>new Response('not yet available',{status:404})});
  await assert.rejects(()=>loader.document('public_law',law.public_law_id),error=>failureReason(error)==='missing_official_source');
  assert.equal(publicLawPackage('119-private-1'),null);assert.equal(publicLawPackage('119-public-112'),'PLAW-119publ112');
}));
test('operational error classifications retain actionable cause without arbitrary provider detail',()=>{
  const secret='fixture-secret-never-persisted';
  assert.equal(failureReason(new Error(`Supabase: HTTP 400 https://example.com?api_key=${secret}`)),'http_400');
  assert.equal(failureReason(new Error(`private detail ${secret}`)),'unexpected_error');
  assert.equal(failureReason(Object.assign(new Error(secret),{status:429})),'http_429');
  assert.equal(failureReason(new Error('Official source exceeds 5MB text limit')),'official_text_too_large');
});
test('GovInfo error-page redirect is unavailable text; unrelated redirects are never followed',()=>fixture(async options=>{
  const get=async table=>table==='public_laws'?[law]:table==='bills'?[bill]:[];
  const loader=sourceLoader({...options,get,fetch:async(url,init)=>{
    assert.equal(init.redirect,'manual');return new Response(null,{status:302,headers:{location:'https://www.govinfo.gov/error'}});
  }});
  const document=await loader.document('public_law',law.public_law_id);
  assert.equal(document.text_status,'unavailable');assert.deepEqual(document.evidence_parts.map(p=>p.field),['title']);
  const foreign=sourceLoader({...options,get,fetch:async()=>new Response(null,{status:302,headers:{location:'https://example.com/policy'}})});
  await assert.rejects(()=>foreign.document('public_law',law.public_law_id),error=>error.status===302&&!error.sourceUnavailable);
}));
test('delayed official text recheck is daily, bounded and skips unfinished or exhausted jobs',async()=>{
  const rows=['done','processing','queued','failed'].map((state,i)=>({document_id:`public_law:119-public-${i+1}`,source_type:'public_law',source_id:`119-public-${i+1}`,state}));
  const queued=[];let lookups=0;
  const count=await reconcileMissingText({now:Date.parse('2026-10-06T00:00:00Z'),get:async(table,query)=>{
    lookups++;
    if(table==='policy_search_documents'){
      assert.equal(query['coverage->>text_status'],'eq.unavailable');assert.equal(query.refreshed_at,'lt.2026-10-05T00:00:00.000Z');assert.equal(query.limit,'25');return rows;
    }
    return rows.map(row=>({document_id:row.document_id,status:row.state}));
  },rpc:async(name,args)=>{assert.equal(name,'enqueue_policy_search_document');queued.push(args);}});
  assert.equal(count,1);assert.equal(lookups,2);assert.deepEqual(queued,[{p_type:'public_law',p_id:'119-public-1'}]);
});
test('an empty text listing expires so later publication is found without a bill metadata change',()=>fixture(async options=>{
  let published=false,listings=0;
  const loader=sourceLoader({...options,get:async(table,query)=>table==='bills'?[bill]:[],fetch:async url=>{
    if(new URL(url).hostname==='api.congress.gov'){
      listings++;return Response.json({textVersions:published?[{date:'2026-10-06',formats:[{type:'Formatted Text',url:newUrl}]}]:[]});
    }
    return new Response('Newly published official bill text.');
  }});
  const initial=await loader.document('bill',bill.bill_id);assert.equal(initial.text_status,'unavailable');
  published=true;assert.equal((await loader.document('bill',bill.bill_id)).text_status,'unavailable');assert.equal(listings,1);
  const old=new Date(Date.now()-25*3600000);
  for(const file of fs.readdirSync(options.cacheDir))fs.utimesSync(path.join(options.cacheDir,file),old,old);
  const refreshed=await loader.document('bill',bill.bill_id);assert.equal(refreshed.text_status,'body');assert.equal(listings,2);
  assert.notEqual(refreshed.input_hash,initial.input_hash);
}));
