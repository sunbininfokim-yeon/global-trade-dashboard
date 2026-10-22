// Run against preview.mjs with a real IDN DB. No writes or provider calls.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.IDN_BROWSER_NODE_MODULES||__dirname]}));
test('legal effect uses live reviewed evidence and preserves a usable mobile detail view',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const read=async url=>{const r=await page.request.get('http://127.0.0.1:4317'+url);assert.equal(r.status(),200);return r.json();};
  const effects=await read('/api/idn/legal-effect?ids=idn-perpres-44-2020,idn-perpres-191-2014,idn-perpres-10-2021');
  assert.deepEqual(effects.items.map(x=>x.status).sort(),['amended','fully_repealed','partially_repealed'].sort());
  const d=await read('/api/idn/documents/idn-perpres-16-2025');assert.equal(d.legal_effect.transition_review_required,true);
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?q=16%2F2025&type=Perpres');
  const card=page.locator('article:visible').filter({has:page.getByRole('heading',{name:d.title_ko,exact:true})});await card.waitFor();
  assert.ok((await card.innerText()).includes('시행일 확인 · 후속 개폐 미확인'));
  await card.getByRole('button',{name:'세부사항',exact:true}).click();await page.getByRole('heading',{name:'시행·개정·폐지 검토',exact:true}).waitFor();
  assert.ok((await page.locator('#detail-content').innerText()).includes('경과조치 확인'));
  await page.locator('#detail-content summary').filter({hasText:'시행 · Pasal 30'}).click();
  assert.ok((await page.locator('#detail-content').innerText()).includes('2025-03-19'));
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261019/legal-effect-desktop.png'});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('#detail').evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261019/legal-effect-mobile.png'});assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
test('real DB search/detail, country isolation, empty/error states and mobile layout',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.IDN_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:950}}),errors=[],responses=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',async r=>{if(r.url().includes('/api/idn/'))responses.push(await r.json());});
  const initial=await (await page.request.get('http://127.0.0.1:4317/api/idn/search')).json();
  const biofuel=await (await page.request.get('http://127.0.0.1:4317/api/idn/search?topic=biofuel')).json();
  const regencies=await (await page.request.get('http://127.0.0.1:4317/api/idn/search?level=regency')).json();
  assert.ok(initial.total>=11);assert.ok(biofuel.items.some(x=>x.document_id==='idn-kemenkeu-pmk-69-2025'));
  await page.goto('http://127.0.0.1:4317/indonesia-policy/');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('건 검색됨'));
  assert.equal(await page.locator('article:visible').count(),Math.min(initial.total,20));
  assert.ok(await page.locator('article a[data-source-type=pdf]').count()>0);
  if(initial.total>20){
   const firstTitle=await page.locator('article:visible h2').first().innerText();
   await page.getByRole('button',{name:'다음',exact:true}).click();
   await page.waitForFunction(()=>new URLSearchParams(location.search).get('offset')==='20'&&document.querySelector('article'));
   assert.equal(await page.locator('article:visible').count(),Math.min(initial.total-20,20));
   assert.notEqual(await page.locator('article:visible h2').first().innerText(),firstTitle);
   await page.getByRole('button',{name:'이전',exact:true}).click();
   await page.waitForFunction(()=>new URLSearchParams(location.search).get('offset')==='0'&&document.querySelector('article'));
  }
  await page.locator('.advanced summary').click();
  const government=page.locator('select[name=level]');
  await government.selectOption('national');
  await page.waitForFunction(()=>!document.querySelector('#status').textContent.includes('검색 중')&&document.querySelector('article'));
  assert.equal(await page.locator('#jurisdiction-filter').isVisible(),false);
  assert.equal(await page.locator('#jurisdictions').inputValue(),'');
  assert.ok((await page.locator('#filter-help').innerText()).includes('지방정부 문서는 포함하지'));
  await government.selectOption('regency');
  await page.waitForFunction(n=>document.querySelector('#jurisdictions').options.length===n+1&&document.querySelector('article'),regencies.jurisdictions.length);
  assert.equal(await page.locator('#jurisdiction-filter').isVisible(),true);
  await page.locator('#jurisdictions').selectOption('Kabupaten Paser');
  await page.waitForFunction(()=>!document.querySelector('#status').textContent.includes('검색 중')&&document.querySelector('article'));
  assert.equal(await page.locator('article:visible').count(),1);
  await government.selectOption('national');
  await page.waitForFunction(()=>!document.querySelector('#status').textContent.includes('검색 중')&&document.querySelector('article'));
  assert.equal(new URL(page.url()).searchParams.has('jurisdiction'),false);
  await government.selectOption('local');
  await page.waitForFunction(()=>!document.querySelector('#status').textContent.includes('검색 중')&&document.querySelector('article'));
  assert.ok((await page.locator('#filter-help').innerText()).includes('중앙정부 문서는 포함하지'));
  await government.selectOption('');
  await page.waitForFunction(()=>!document.querySelector('#status').textContent.includes('검색 중')&&document.querySelector('article'));
  await page.locator('#query').fill('니켈, 수출');await page.getByRole('button',{name:'검색',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.matches'));
  assert.ok(await page.locator('article:visible').count()>0);
  await page.getByRole('button',{name:'세부사항'}).first().click();
  await page.locator('#detail pre').waitFor();assert.ok((await page.locator('#detail pre').innerText()).length>=150);
  await page.getByRole('button',{name:'상세 닫기'}).click();
  await page.locator('#search-form select[name=topic]').selectOption('biofuel');
  await page.waitForFunction(()=>!document.querySelector('#status').textContent.includes('검색 중'));
  await page.locator('#query').fill('');await page.getByRole('button',{name:'검색',exact:true}).click();
  await page.waitForFunction(n=>document.querySelector('#status').textContent.startsWith(n+'건'),biofuel.total);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/search-mobile.png',fullPage:false});
  await page.setViewportSize({width:1360,height:950});
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/search-desktop.png',fullPage:false});
  await page.locator('#query').fill('해당없음987654');await page.getByRole('button',{name:'검색',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('찾지 못했습니다'));
  assert.equal(await page.locator('article:visible').count(),0);
  await page.route('**/api/idn/search?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'인도네시아 검색 연결이 준비되지 않았습니다.'})}));
  await page.getByRole('button',{name:'검색',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#coverage').textContent.includes('연결 오류'));
  assert.ok(responses.filter(x=>x.items).every(x=>x.country==='IDN'&&x.items.every(d=>d.document_id.startsWith('idn-'))));
  assert.deepEqual(errors,[]);console.log(JSON.stringify({initialDocuments:initial.total,biofuelDocuments:biofuel.total,viewportWidths:[1360,390],pageErrors:errors.length}));
 }finally{await browser.close();}
});
test('mineral/stage filters and common-law labels work without provider calls',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.IDN_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:950}});
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?group=business');
  await page.waitForFunction(()=>document.querySelector('article'));
  assert.equal(await page.locator('article .badges').first().locator('span').first().innerText(),'공통 사업법규');
  assert.ok(!(await page.locator('article .badges').allInnerTexts()).some(x=>x.includes('석탄')));
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/common-business-desktop.png'});
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?q=보크사이트,제련&topic=bauxite&stream=midstream');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('키워드·동의어 검색'));
  assert.equal(await page.locator('#search-form select[name=topic]').inputValue(),'bauxite');
  assert.equal(await page.locator('select[name=stream]').inputValue(),'midstream');
  assert.ok(await page.locator('article:visible').count()>0);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/value-chain-desktop.png'});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/value-chain-mobile.png'});
 }finally{await browser.close();}
});
test('four desktop groups preserve all page results and collapse to the original list on tablet/mobile',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.IDN_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:950}});
  const initial=await (await page.request.get('http://127.0.0.1:4317/api/idn/search')).json();
  await page.goto('http://127.0.0.1:4317/indonesia-policy/');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('건 검색됨'));
  const ids=async selector=>page.locator(selector).evaluateAll(es=>es.map(e=>e.dataset.documentId));
  const grouped=await ids('.grouped-results article'),compact=await ids('.compact-results article');
  assert.deepEqual([...grouped].sort(),[...compact].sort());
  assert.deepEqual(compact,initial.items.map(x=>x.document_id));
  assert.equal(await page.locator('.result-group').count(),4);
  if(initial.semantic_enabled!==true)assert.equal(await page.locator('[name=mode]').isDisabled(),true);
  for(const width of [1440,1024,390]){
   await page.setViewportSize({width,height:950});
   assert.equal(await page.locator('.grouped-results').isVisible(),width>=1180);
   assert.equal(await page.locator('.compact-results').isVisible(),width<1180);
   assert.equal(await page.locator('article:visible').count(),initial.items.length);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  }
 }finally{await browser.close();}
});
test('reviewed passages and business scope distinguish document matches, clause matches and unavailable context',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.IDN_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const query=new URLSearchParams({q:'니켈, 국산화율, 금융지원',stream:'midstream',match:'all'});
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?'+query);
  const card=page.locator('article:visible').filter({has:page.getByRole('heading',{name:'국산화율 TKDN·기업기여도 BMP 인증 규정',exact:true})});
  await card.waitFor();assert.ok((await card.innerText()).includes('3개 조건 중 3개 일치'));
  await card.getByText('일치 근거 보기',{exact:true}).click();
  await card.getByText('Pasal 52-54 · 3개 조건 중 2개 원문 일치',{exact:true}).click();
  assert.ok((await card.locator('.passage').first().innerText()).includes('자동 수급권'));
  await card.getByRole('button',{name:'세부사항',exact:true}).click();
  await page.locator('.review-context').waitFor();assert.ok((await page.locator('.review-context').innerText()).includes('개별 사업 적용성과 지원 자격은 미확인'));
  await page.locator('.review-context summary').filter({hasText:'Pasal 52-54'}).click();
  assert.ok((await page.locator('.review-context').innerText()).includes('제조'));
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261019/evidence-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('#detail').evaluate(e=>e.scrollWidth>e.clientWidth),false);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261019/evidence-mobile.png'});
  await page.getByRole('button',{name:'상세 닫기'}).click();
  await page.route('**/api/idn/context/**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Unavailable'})}));
  await card.getByRole('button',{name:'세부사항',exact:true}).click();
  await page.getByText('관계·사업 검토 근거를 불러오지 못했습니다. 원문 자료는 아래에서 확인하세요.',{exact:true}).waitFor();
  assert.ok((await page.locator('#detail pre').innerText()).length>1000);assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
test('favourite stars: visible signed out, a star asks for login, then stars become product × region mail alerts without changing search',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.IDN_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1024,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const provinces=require('./mail-regions.json').provinces;
  await page.addInitScript(provinces=>{
   window.__idnMailCalls=[];window.__idnSubscriptions=[];let session=null;const listeners=new Set();
   window.__idnMockClient={auth:{getSession:async()=>({data:{session},error:null}),getUser:async()=>({data:{user:session?.user||null},error:session?null:{message:'signed out'}}),onAuthStateChange:f=>{listeners.add(f);return {data:{subscription:{unsubscribe(){}}}};},
     signInWithPassword:async({email})=>{session={user:{id:'fixture-self',email}};listeners.forEach(f=>f());return {error:null};},signOut:async()=>{session=null;listeners.forEach(f=>f());return {error:null};}},
    rpc:async(name,args)=>{window.__idnMailCalls.push({name,args});
     if(name==='idn_my_mail_subscriptions')return {data:{country:'IDN',delivery_enabled:false,max_active_combinations:100,region_options:[{value:'__all__',label:'인도네시아 전국 · 중앙·모든 지방',level:'all'},...provinces.map(([,value,label])=>({value,label,level:'provincial',has_local_documents:value==='Kalimantan Timur'}))],subscriptions:window.__idnSubscriptions},error:null};
     if(name==='idn_set_my_mail_subscriptions'){for(const topic of args.p_topics)for(const region of args.p_regions){let s=window.__idnSubscriptions.find(s=>s.topic===topic&&s.region===region);if(!s){s={id:topic+':'+region,topic,region};window.__idnSubscriptions.push(s);}s.enabled=args.p_enabled;}return {data:{country:'IDN',affected:args.p_topics.length*args.p_regions.length},error:null};}
     if(name==='idn_set_my_mail_subscription'){let s=window.__idnSubscriptions.find(s=>s.topic===args.p_topic&&s.region===args.p_region);s.enabled=args.p_enabled;return {data:s.id,error:null};}
     throw Error('unexpected RPC');}};
  },provinces);
  await page.route('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.118.0/+esm',r=>r.fulfill({contentType:'text/javascript',body:'export function createClient(){return window.__idnMockClient}'}));
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?q=석탄');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('건 검색됨'));
  const root=page.locator('#mail-subscriptions'),star=name=>root.getByRole('button',{name,exact:true});
  assert.equal(await root.evaluate(d=>d.open),false);await root.locator(':scope > summary').click();
  assert.equal(await root.locator('[data-topic-stars] .fav-chip').count(),13);assert.equal(await root.locator('[data-region-stars] .fav-chip').count(),38);
  assert.equal(await page.evaluate(()=>window.__idnMailCalls.length),0);
  await star('석탄 즐겨찾기').click();assert.equal(await page.locator('#login-dialog').evaluate(d=>d.open),true);
  await page.fill('#login-dialog [name=email]','fixture@example.test');await page.fill('#login-dialog [name=password]','pw');await page.click('#login-dialog [type=submit]');
  await star('석탄 즐겨찾기 해제').waitFor();
  assert.deepEqual(await page.evaluate(()=>window.__idnSubscriptions.map(s=>[s.topic,s.region,s.enabled])),[['coal','__all__',true]]);
  await root.locator('.fav-more summary').click();await root.locator('[name=region_filter]').fill('동칼리만탄');
  assert.equal(await root.locator('[data-region-stars] .fav-chip:visible').count(),1);
  await root.locator('[data-region-stars]').getByRole('button',{name:'동칼리만탄 즐겨찾기',exact:true}).click();
  await star('니켈 즐겨찾기').waitFor();await star('니켈 즐겨찾기').click();
  await root.getByText('2개 품목 × 2개 지역',{exact:false}).waitFor();
  assert.ok((await root.innerText()).includes('자동 발송은 아직 준비 중'));
  await star('석탄 즐겨찾기 해제').click();await root.getByText('1개 품목 × 2개 지역',{exact:false}).waitFor();
  assert.deepEqual(await page.evaluate(()=>window.__idnSubscriptions.filter(s=>s.enabled).map(s=>[s.topic,s.region]).sort()),[['nickel_mining','Kalimantan Timur'],['nickel_mining','__all__']]);
  assert.equal(new URL(page.url()).searchParams.get('q'),'석탄');assert.equal(await page.locator('#search-form [name=topic]').inputValue(),'');
  const calls=await page.evaluate(()=>window.__idnMailCalls);
  assert.ok(calls.every(c=>['idn_my_mail_subscriptions','idn_set_my_mail_subscription','idn_set_my_mail_subscriptions'].includes(c.name)));
  assert.ok(calls.filter(c=>c.name==='idn_set_my_mail_subscriptions').every(c=>!(c.args.p_regions.includes('__all__')&&c.args.p_regions.length>1)));
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261021/mailing/multiscope-subscriptions-desktop.png'});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await root.scrollIntoViewIfNeeded();await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261021/mailing/multiscope-subscriptions-mobile.png'});
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
