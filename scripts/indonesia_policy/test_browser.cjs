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
  assert.ok(initial.total>=11);assert.ok(biofuel.items.some(x=>x.document_id==='idn-kemenkeu-pmk-69-2025'));
  await page.goto('http://127.0.0.1:4317/indonesia-policy/');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('건 검색됨'));
  assert.equal(await page.locator('article').count(),Math.min(initial.total,20));
  if(initial.total>20){
   const firstTitle=await page.locator('article h2').first().innerText();
   await page.getByRole('button',{name:'다음',exact:true}).click();
   await page.waitForFunction(()=>new URLSearchParams(location.search).get('offset')==='20'&&document.querySelector('article'));
   assert.equal(await page.locator('article').count(),Math.min(initial.total-20,20));
   assert.notEqual(await page.locator('article h2').first().innerText(),firstTitle);
   await page.getByRole('button',{name:'이전',exact:true}).click();
   await page.waitForFunction(()=>new URLSearchParams(location.search).get('offset')==='0'&&document.querySelector('article'));
  }
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
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/search-mobile.png',fullPage:true});
  await page.setViewportSize({width:1360,height:950});
  await page.screenshot({path:'/Users/yeoninair/Documents/policy-downloads/indonesia-20261017/search-desktop.png',fullPage:true});
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
