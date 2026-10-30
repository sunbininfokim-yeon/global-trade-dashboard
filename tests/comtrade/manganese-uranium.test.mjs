// Offline contracts: fixture figures are never published as observations.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const source=f=>fs.readFileSync(path.join(root,'New for anti',f),'utf8');
const host=v=>JSON.parse(JSON.stringify(v));
const products={manganese:'2602',uranium:'284410',uranium_ore:'261210'};
const d=new Date(); d.setUTCMonth(d.getUTCMonth()-2);
const month=d.toISOString().slice(0,7),period=month.replace('-','');

function data(rows=[]) {
    const requests=[],window={document:new Proxy({},{get:()=>()=>null}),addEventListener(){},
        CountryCoords:()=>[10,10]};
    const fetch=async url=>{
        if(!String(url).startsWith('/api/comtrade?')) return new Response('{}',{status:404});
        requests.push(new URL(String(url),'https://test.invalid'));
        return new Response(JSON.stringify({data:rows}),{headers:{'X-Comtrade-Period':'2025'}});
    };
    vm.runInNewContext(source('data.js'),{window,document:window.document,fetch,URLSearchParams,Response,
        console:{log(){},warn(){},error(){}},setTimeout,clearTimeout});
    return {window,requests};
}
function monthly() {
    const window={}; vm.runInNewContext(source('trade-monthly.js'),{window,console,Date});
    return window.TradeMonthly._internal;
}
function docs(cid,hs=products[cid]) {
    const point={month,value:10,unit:'kg',source:'comtrade_preview',hs,
        publication:{eligible_for_display:true}};
    return {comtrade:{reporters:{CAN:{flows:{exports:{commodities:{[cid]:{hs,points:[point]}}},
        imports:{commodities:{[cid]:{hs,points:[{...point,value:0}]}}}}}}},
        bilateralIndex:{entries:[]}};
}

test('ore and natural-uranium menus/configs are distinct, with no alloy or invented totals',()=>{
    const {window:w}=data();
    for(const [cid,hs] of Object.entries(products)) {
        assert.equal(w.ComtradeHsCodes[cid],hs);
        assert.equal(w.normalizeCommodity(cid),cid);
        assert.equal(w.normalizeCommodity(hs),cid);
        const p=w.TradeData[cid];
        assert.equal(p.observedOnly,true);
        assert.equal(p.totalVolume,'—'); assert.equal(p.topExporter,'—');
        assert.deepEqual(host(p.news),{}); assert.deepEqual(host(p.arcs),[]);
        assert.match(p.hsNote,new RegExp(hs));
        assert.match(source('index.html'),new RegExp(`data-target="${cid}"`));
    }
    for(const ambiguous of ['페로망간','ferromanganese','농축우라늄','enriched uranium','2844','2612','284420','261220']) {
        assert.ok(!Object.keys(products).includes(w.normalizeCommodity(ambiguous)),ambiguous);
    }
    assert.equal(w.normalizeCommodity('우라늄 정광'),'uranium_ore');
    assert.equal(w.ComtradeHsCodes.chromium,'2610,720241,720249');
});

for(const [cid,hs] of Object.entries(products)) {
    test(`${cid}: annual request and row scope exclude parents / alloy / other uranium forms`,async()=>{
        const row={reporterCode:124,partnerCode:156,flowCode:'X',period:'2025',primaryValue:10e6,netWgt:100};
        const {window:w,requests}=data([{...row,cmdCode:hs},
            ...['720211','720219','2844','284420','284430','2612','261220'].map(cmdCode=>({...row,cmdCode,primaryValue:999e6}))]);
        const arcs=await w.fetchComtradeArcs(cid);
        assert.equal(requests[0].searchParams.get('hs'),hs);
        assert.ok(requests[0].searchParams.get('partners').split(',').includes('516'));
        assert.ok(requests[0].searchParams.get('partners').split(',').includes('562'));
        assert.equal(arcs.length,1); assert.equal(arcs[0].volume,10);
        assert.equal(arcs[0].period,'2025');
    });
    test(`${cid}: monthly zero retained, unrelated point rejected and absent partners not fabricated`,()=>{
        const t=monthly(),input=docs(cid);
        input.comtrade.reporters.CAN.flows.exports.commodities[cid].points.push({month,value:999,unit:'kg',hs:'720211'});
        const view=t.buildView(input,cid,'CAN');
        assert.equal(view.series.length,2);
        assert.equal(view.series.find(s=>s.flow==='X').points[0].value,10/1e6);
        assert.equal(view.series.find(s=>s.flow==='M').points[0].value,0);
        assert.equal(view.bilateral,null);
        assert.match(t.monthlyHtml(view),/상대국별 자료 미확보/);
        assert.match(t.monthlyHtml(view),new RegExp(hs));
        assert.equal(t.buildView(input,cid,'KAZ'),null);
    });
    test(`${cid}: bilateral-only data links without a totals file and rejects broader HS`,()=>{
        const t=monthly(),entry={frequency:'M',reporter_iso3:'CAN',hs,period,path:`parts/${'a'.repeat(64)}.json`};
        const other={...entry,hs:cid==='manganese'?'720211':cid==='uranium'?'2844':'2612'};
        const view=t.buildView({bilateralIndex:{entries:[other,entry]}},cid,'CAN');
        assert.equal(view.series.length,0); assert.equal(view.bilateral.hs,hs);
        assert.equal(t.buildView({bilateralIndex:{entries:[other]}},cid,'CAN'),null);
    });
}

test('broader legacy uranium totals and publication holds cannot supply a narrow series',()=>{
    const t=monthly();
    assert.equal(t.buildView(docs('uranium','2844'),'uranium','CAN'),null);
    assert.equal(t.buildView(docs('uranium_ore','2612'),'uranium_ore','CAN'),null);
    const input=docs('uranium');
    for(const f of Object.values(input.comtrade.reporters.CAN.flows))
        f.commodities.uranium.points[0].publication.eligible_for_display=false;
    assert.equal(t.buildView(input,'uranium','CAN'),null);
});

test('Brazil supplemental manganese remains visible with explicit HS bridge; not world/alloy data',()=>{
    const t=monthly(),input={monthly:{sectors:{minerals:{supplemental_commodities:{manganese:{
        hs_stems:['2602'],countries:{BRA:{points:[{month,value:12,unit:'kg',source:'brazil_comexstat',hs_bridge:'2602'}]}}
    }}}}}};
    const view=t.buildView(input,'manganese','BRA');
    assert.equal(view.series.length,1); assert.equal(view.series[0].hs,'2602');
    assert.equal(view.series[0].sourceLabel,'브라질 MDIC Comex Stat');
});

test('live scoped monthly response preserves explicit zero but not unknown quantity or alien HS',()=>{
    const t=monthly(),row={period,flowCode:'X',partnerCode:0,cmdCode:'284410',primaryValue:0,netWgt:0};
    const got=t.aggregateComtradeMonthly([row,{...row,cmdCode:'284420',primaryValue:999}], '284410');
    assert.deepEqual(host(got.X),[{month,usd:0,kg:0,kgKnown:true}]);
    const unknown=t.aggregateComtradeMonthly([{...row,primaryValue:12,netWgt:null}],'284410');
    assert.equal(unknown.X[0].kgKnown,false);
});

test('scoped monthly totals never pick a detail row or the larger conflicting total',()=>{
    const t=monthly(),row={period,flowCode:'X',partnerCode:0,cmdCode:'284410',primaryValue:12,netWgt:10};
    const detail={...row,motCode:1,primaryValue:999};
    assert.equal(t.aggregateComtradeMonthly([detail,row],'284410').X[0].usd,12);
    assert.equal(t.aggregateComtradeMonthly([row,{...row,primaryValue:13}],'284410').X.length,0);
    assert.equal(t.aggregateComtradeMonthly([row,{...row}],'284410').X.length,1);
});

test('no date-picker callback can alter any product, observed-only or not (#602 A10)',()=>{
    const app=source('app.js');
    assert.equal(app.includes("getElementById('historical-date').addEventListener"),false);
    assert.equal(/Math\.random\(\)[^\n]*\n[\s\S]{0,400}TradeData\[currentCommodity\]\.arcs/.test(app),false);
    assert.match(app,/getElementById\('historical-date'\)\?\.setAttribute\('disabled', ''\)/);
});
