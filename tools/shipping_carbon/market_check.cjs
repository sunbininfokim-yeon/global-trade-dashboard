const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.CARBON_BASE_URL||'http://127.0.0.1:8774';
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PW_CHANNEL?{channel:process.env.PW_CHANNEL}:{})});
 const page=await browser.newPage({viewport:{width:1100,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const market=await (await page.request.get(base+'/api/market')).json();
 const latest=Number(market.prices.sources.eex_eua_auction.latest_observations[0].price).toLocaleString('ko-KR',{maximumFractionDigits:2});
 await page.goto(base+'/climate');
 await page.waitForFunction(value=>document.querySelector('#cd-price').textContent.includes(value),latest);
 assert.ok(await page.locator('#cd-price-chart .cd-price-line').count());
 assert.ok(await page.locator('#cd-volume-chart rect').count()>10);
 const oi=market.market_structure.records.reduce((n,r)=>n+r.gross_oi_lots,0).toLocaleString('ko-KR');
 assert.ok((await page.locator('#cd-oi-total').innerText()).includes(oi));
 await page.locator('#cd-window').selectOption('all');
 assert.match(await page.locator('#cd-hover').innerText(),/2026-/);
 const auction=await page.locator('#cd-auction option').nth(1).getAttribute('value');
 await page.locator('#cd-auction').selectOption(auction);
 assert.equal(await page.locator('#cd-auction-rows tr td small').first().innerText(),auction);
 await page.locator('#cd-auction').selectOption('all');await page.locator('#cd-window').selectOption('90');
 for(const [name,value] of Object.entries({demand:'10300',inventory:'1000',forward:'1000',hedge:'50'}))await page.locator('#cd-procurement [name='+name+']').fill(value);
 await page.locator('#cd-procurement button').click();
 assert.match(await page.locator('#cd-risk-output').innerText(),/8,300 EUA/);
 assert.match(await page.locator('#cd-risk-output').innerText(),/21,500 EUR/);
 await page.locator('#cd-procurement [name=demand]').fill('11000');assert.match(await page.locator('#cd-risk-output').innerText(),/다시 계산/);
 await page.locator('[data-role=dealer]').click();
 for(const [name,value] of Object.entries({inventory:'1000',delivery:'6000',lots:'4'}))await page.locator('#cd-dealer [name='+name+']').fill(value);
 await page.locator('#cd-dealer button').click();assert.match(await page.locator('#cd-risk-output').innerText(),/-1,000 EUA/);
 // Explicit test fixture exercises imports, never shipped as an observed quote.
 const header='observation_date,venue,product,expiry_month,settlement_eur,volume_lots,open_interest_lots,price_type,source_url';
 const fixture=header+'\n2026-10-30,ICE Endex,EUA,2026-12,90,10,100,settlement,https://www.ice.com/products/197/eua-futures\n2026-10-30,ICE Endex,EUA,2027-12,94,20,200,settlement,https://www.ice.com/products/197/eua-futures';
 await page.locator('#cd-curve-file').setInputFiles({name:'test-only.csv',mimeType:'text/csv',buffer:Buffer.from(fixture)});
 await page.locator('#cd-curve-chart .cd-price-line').waitFor();assert.match(await page.locator('#cd-curve-status').innerText(),/ユーザー|사용자/);
 await page.locator('#cd-curve-file').setInputFiles({name:'bad-test.csv',mimeType:'text/csv',buffer:Buffer.from(fixture.replace('2027-12,94','2026-12,94'))});
 await page.waitForFunction(()=>document.querySelector('#cd-import-error').textContent.includes('중복'));
 assert.equal(await page.locator('#cd-curve-chart').count(),0);
 await page.reload();await page.waitForFunction(value=>document.querySelector('#cd-price').textContent.includes(value),latest);
 for(const module of ['weather','agri','data','audit','combined','carbon']){await page.locator('[data-module='+module+']').click();assert.ok(await page.locator('[data-view='+module+']').isVisible());}
 await page.locator('[data-module=combined]').click();await page.locator('#cd-combined-example').click();
 await page.locator('#cd-combined-form button[type=submit]').click();
 await page.locator('#cd-combined-export:not([disabled])').waitFor();
 assert.match(await page.locator('#cd-combined-output').innerText(),/수익 미인식/);
 assert.match(await page.locator('#cd-combined-output').innerText(),/41,000,000/);
 assert.match(await page.locator('#cd-combined-output').innerText(),/가상 예제/);
 const output=process.env.CARBON_SCREENSHOTS||path.join(__dirname,'source_data');fs.mkdirSync(output,{recursive:true});
 await page.screenshot({path:path.join(output,'market-combined.png'),fullPage:true});
 await page.locator('#cd-combined-form [name=baseline_tonnes]').fill('2000');
 assert.equal(await page.locator('#cd-combined-export').isDisabled(),true);
 assert.match(await page.locator('#cd-combined-output').innerText(),/다시 계산/);
 await page.locator('[data-module=audit]').click();
 if(market.fueleu_audit.status==='observed_source_audit'){
  assert.match(await page.locator('#cd-audit-coverage').innerText(),new RegExp(market.fueleu_audit.full_reports.toLocaleString('ko-KR')));
  assert.equal(await page.locator('#cd-audit-scenarios tbody tr').count(),5);
  await page.screenshot({path:path.join(output,'market-audit.png'),fullPage:true});
 }
 await page.locator('[data-module=carbon]').click();
 const widths=[];for(const width of [1100,736,390,320]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(100);const m=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,path:!!document.querySelector('#cd-price-chart path')}));assert.ok(m.scroll<=m.width);widths.push(m);}
 for(const module of ['combined','audit','weather','agri','data']){await page.locator('[data-module='+module+']').click();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.locator('[data-module=carbon]').click();
 await page.setViewportSize({width:1100,height:1000});await page.screenshot({path:path.join(output,'market-desktop.png'),fullPage:true});
 await page.emulateMedia({colorScheme:'dark'});await page.screenshot({path:path.join(output,'market-dark.png'),fullPage:true});
 await page.setViewportSize({width:390,height:1000});await page.screenshot({path:path.join(output,'market-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);await browser.close();console.log(JSON.stringify({status:'passed',widths,errors,checks:'observed chart/volume/OI, filters, corporate/dealer stress, stale-input invalidation, valid/rejected curve CSV, modules, responsive, light/dark'}));
})().catch(e=>{console.error(e);process.exit(1);});
