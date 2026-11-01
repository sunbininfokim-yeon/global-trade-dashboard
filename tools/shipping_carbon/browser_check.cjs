const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const baseURL = process.env.CARBON_BASE_URL || 'http://127.0.0.1:8769';
require('node:fs').mkdirSync(path.join(__dirname,'source_data'),{recursive:true});
(async () => {
  const browser = await chromium.launch({headless:true,...(process.env.PW_CHANNEL ? {channel:process.env.PW_CHANNEL} : {})});
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto(baseURL);
  await page.locator('#ship-view .metric').first().waitFor();
  assert.match(await page.locator('#ship-view').innerText(), /50,000 EUA/);
  assert.match(await page.locator('#ship-view').innerText(), /4,000,000 EUR/);
  await page.locator('#dealer-tab').click();
  assert.equal(await page.locator('#ship-view').isHidden(),true);
  assert.match(await page.locator('#dealer-view').innerText(),/500,000 EUR/);
  async function change(name,value,select=false){
    const response=page.waitForResponse(r=>r.url().endsWith('/api/calculate')&&r.request().method()==='POST');
    const el=page.locator(`[name="${name}"]`);
    if(select) await el.selectOption(value); else {await el.fill(value);await el.dispatchEvent('change');}
    await response; await page.waitForTimeout(150);
  }
  await change('price_shock','10');
  assert.match(await page.locator('#ship-view').innerText(),/300,000 EUR/);
  await change('delivery_date','2027-10-01');
  assert.match(await page.locator('#ship-view').innerText(),/80,000 EUA/);
  await change('price_mode','manual',true);
  assert.match(await page.locator('#ship-view').innerText(),/미확인/);
  await change('available_eua','-1');
  assert.notEqual(await page.locator('#error').innerText(),'');
  assert.equal(await page.locator('#dealer-view').innerText(),'');
  await page.locator('#reset').click();
  await page.locator('#dealer-view .metric').first().waitFor();
  await page.screenshot({path:path.join(__dirname,'source_data','viewer-dealer.png'),fullPage:true});
  await page.locator('#ship-tab').click();
  await page.screenshot({path:path.join(__dirname,'source_data','viewer-shipowner.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  assert.deepEqual(errors,[]);
  await browser.close();
  console.log('PASS: synthetic price reference, both views, shared shock, late delivery, missing price, input errors, reset, mobile width; no browser JS errors.');
})().catch(e=>{console.error(e);process.exit(1)});
