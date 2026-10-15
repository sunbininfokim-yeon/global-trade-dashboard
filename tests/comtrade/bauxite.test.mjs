// Run without a provider key or network: node --test tests/comtrade/bauxite.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const source=(file)=>fs.readFileSync(path.join(root,'New for anti',file),'utf8');
const host=(value)=>JSON.parse(JSON.stringify(value));
const month=(()=>{const d=new Date(); d.setUTCMonth(d.getUTCMonth()-2); return d.toISOString().slice(0,7);})();

function loadData(answer={data:[]}) {
    const requests=[];
    const window={document:new Proxy({},{get:()=>()=>null}),addEventListener(){},
        CountryCoords:(name)=>({Guinea:[-10,10],Jamaica:[-77,18],China:[105,35]})[name]};
    const fetch=async(url)=>{
        if(!String(url).startsWith('/api/comtrade')) return new Response('{}',{status:404});
        requests.push(new URL(String(url),'https://test.invalid'));
        return new Response(JSON.stringify(answer),{headers:{'X-Comtrade-Period':'2025'}});
    };
    const ctx=vm.createContext({window,document:window.document,fetch,URLSearchParams,Response,
        console:{log(){},warn(){},error(){}},setTimeout,clearTimeout});
    vm.runInContext(source('data.js'),ctx);
    return {window,requests};
}

function monthly() {
    const window={};
    vm.runInContext(source('trade-monthly.js'),vm.createContext({window,console,Date}));
    return window.TradeMonthly._internal;
}

function docs() {
    const pt=(value)=>({month,value,unit:'kg',source:'comtrade_preview',hs:'2606',
        publication:{eligible_for_display:true}});
    return {comtrade:{reporters:{BRA:{flows:{
        exports:{commodities:{bauxite:{hs:'2606',points:[pt(20)]},aluminum:{hs:'7601',points:[pt(999)]}}},
        imports:{commodities:{bauxite:{hs:'2606',points:[pt(0)]}}}}}}},bilateralIndex:{entries:[]}};
}

test('bauxite is a distinct taxonomy, menu and HS2606 profile without invented totals/news',()=>{
    const {window:w}=loadData();
    for(const alias of ['bauxite','보크사이트','알루미늄광','2606','260600']) assert.equal(w.normalizeCommodity(alias),'bauxite');
    assert.equal(w.normalizeCommodity('알루미늄'),'aluminum');
    assert.equal(w.ComtradeHsCodes.bauxite,'2606');
    assert.equal(w.ComtradeHsCodes.aluminum,'7601');
    assert.equal(w.TradeData.bauxite.totalVolume,'—');
    assert.equal(w.TradeData.bauxite.topExporter,'—');
    assert.deepEqual(host(w.TradeData.bauxite.arcs),[]);
    assert.deepEqual(host(w.TradeData.bauxite.news),{});
    assert.match(w.TradeData.bauxite.hsNote,/281820.*7601/);
    assert.match(source('index.html'),/data-target="bauxite">보크사이트/);
    assert.match(source('app.js'),/'guinea': 'GIN'/);
});

test('annual bauxite requests include Guinea/Jamaica and preserve source year and directions',async()=>{
    const {window:w,requests}=loadData({data:[
        {reporterCode:324,partnerCode:156,flowCode:'X',period:2025,primaryValue:20e6,netWgt:40e6},
        {reporterCode:156,partnerCode:324,flowCode:'M',period:2025,primaryValue:21e6,netWgt:42e6},
        {reporterCode:388,partnerCode:156,flowCode:'X',period:2025,primaryValue:5e6,netWgt:10e6},
    ]});
    const arcs=await w.fetchComtradeArcs('bauxite');
    assert.equal(requests.length,1);
    const q=requests[0].searchParams;
    assert.equal(q.get('hs'),'2606');
    assert.equal(q.get('period'),null);
    for(const field of ['reporters','partners']) {
        assert.ok(q.get(field).split(',').includes('324'));
        assert.ok(q.get(field).split(',').includes('388'));
    }
    assert.equal(arcs.length,2);
    const guinea=arcs.find(a=>a.sourceName==='Guinea');
    assert.equal(guinea.targetName,'China');
    assert.equal(guinea.volume,21); // one route, not added exporter + mirror
    assert.equal(guinea.period,'2025');
    assert.equal(guinea.freq,'A');
    assert.equal(guinea.typeName,'2606');
    await w.fetchComtradeArcs('aluminum');
    assert.equal(requests[1].searchParams.get('hs'),'7601');
    assert.equal(requests[1].searchParams.get('reporters'),null);
});

test('monthly bauxite isolates metal, retains official zero and labels missing bilateral observations',()=>{
    const t=monthly(),view=t.buildView(docs(),'bauxite','BRA');
    assert.equal(t.MONTHLY_ID.bauxite,'bauxite');
    assert.equal(view.cid,'bauxite');
    assert.equal(view.series.length,2);
    assert.ok(view.series.every(s=>s.hs==='2606'));
    assert.equal(view.series.find(s=>s.flow==='M').points[0].value,0);
    assert.equal(view.bilateral,null);
    assert.match(t.monthlyHtml(view),/월별 상대국별 자료 미확보/);
    assert.match(t.monthlyHtml(view),/지도의 노선은 연간 데이터/);
    assert.equal(t.buildView(docs(),'bauxite','GIN'),null);
});

test('monthly bilateral selection requires HS2606 for the same country, never HS7601',()=>{
    const d=docs();
    const entry={frequency:'M',reporter_iso3:'BRA',hs:'2606',period:month.replace('-',''),path:`parts/${'a'.repeat(64)}.json`};
    d.bilateralIndex.entries=[{...entry,hs:'7601',path:`parts/${'b'.repeat(64)}.json`},entry];
    const t=monthly(),view=t.buildView(d,'bauxite','BRA');
    assert.equal(view.bilateral.hs,'2606');
    assert.doesNotMatch(t.monthlyHtml(view),/월별 상대국별 자료 미확보/);
});

test('monthly observations and display holds are not filled from annual or aluminium data',()=>{
    const d=docs();
    const p=d.comtrade.reporters.BRA.flows.exports.commodities.bauxite.points[0];
    p.publication.eligible_for_display=false;
    delete d.comtrade.reporters.BRA.flows.imports;
    assert.equal(monthly().buildView(d,'bauxite','BRA'),null);
});
