const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {sourceLoader}=require('../../scripts/lib/policy-search-source');
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
