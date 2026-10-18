// Run against preview.mjs with a real IDN DB. No writes or provider calls.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.IDN_BROWSER_NODE_MODULES||__dirname]}));
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
  assert.equal(await page.locator('article').count(),Math.min(initial.total,20));
  assert.ok(await page.locator('article a[data-source-type=pdf]').count()>0);
  if(initial.total>20){
   const firstTitle=await page.locator('article h2').first().innerText();
   await page.getByRole('button',{name:'다음',exact:true}).click();
   await page.waitForFunction(()=>new URLSearchParams(location.search).get('offset')==='20'&&document.querySelector('article'));
   assert.equal(await page.locator('article').count(),Math.min(initial.total-20,20));
   assert.notEqual(await page.locator('article h2').first().innerText(),firstTitle);
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
  assert.equal(await page.locator('article').count(),1);
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
  assert.ok(await page.locator('article').count()>0);
  await page.getByRole('button',{name:'세부사항'}).first().click();
  await page.locator('#detail pre').waitFor();assert.ok((await page.locator('#detail pre').innerText()).length>=150);
  await page.getByRole('button',{name:'상세 닫기'}).click();
  await page.locator('select[name=topic]').selectOption('biofuel');
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
  assert.equal(await page.locator('article').count(),0);
  await page.route('**/api/idn/search?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'인도네시아 검색 연결이 준비되지 않았습니다.'})}));
  await page.getByRole('button',{name:'검색',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#coverage').textContent.includes('연결 오류'));
  assert.ok(responses.filter(x=>x.items).every(x=>x.country==='IDN'&&x.items.every(d=>d.document_id.startsWith('idn-'))));
  assert.deepEqual(errors,[]);console.log(JSON.stringify({initialDocuments:initial.total,biofuelDocuments:biofuel.total,viewportWidths:[1360,390],pageErrors:errors.length}));
 }finally{await browser.close();}
});
test('mineral/stage filters, common-law labels and hybrid overview remain distinct',async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.IDN_BROWSER_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:950}});
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?group=business');
  await page.waitForFunction(()=>document.querySelector('article'));
  assert.equal(await page.locator('article .badges').first().locator('span').first().innerText(),'공통 사업법규');
  assert.ok(!(await page.locator('article .badges').allInnerTexts()).some(x=>x.includes('석탄')));
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/common-business-desktop.png'});
  await page.goto('http://127.0.0.1:4317/indonesia-policy/?q=보크사이트,제련&topic=bauxite&stream=midstream&mode=hybrid');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('의미검색'));
  assert.equal(await page.locator('select[name=topic]').inputValue(),'bauxite');
  assert.equal(await page.locator('select[name=stream]').inputValue(),'midstream');
  assert.ok(await page.locator('article').count()>0);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/value-chain-desktop.png'});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/value-chain-mobile.png'});
 }finally{await browser.close();}
});
