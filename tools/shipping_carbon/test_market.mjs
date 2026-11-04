import test from 'node:test';
import assert from 'node:assert/strict';
import {dailyAuctions,windowRows,auctionStats,exactFx,procurement,dealerRisk,curveHeader,parseCurve} from './market-math.mjs';

test('same-date VWAP weights actual supply; missing/synthetic is not zero',()=>{
 const rows=dailyAuctions({status:'observed',observations:[
  {observation_date:'2026-10-28',price:'80',auction_volume_tco2:'100',auction_name:'EU'},
  {observation_date:'2026-10-28',price:'100',auction_volume_tco2:'300',auction_name:'DE'},
  {observation_date:'2026-10-30',price:'90',auction_volume_tco2:'100',auction_name:'EU'}]});
 assert.equal(rows.length,2);assert.equal(rows[0].price,95);assert.equal(rows[0].count,2);
 assert.equal(windowRows(rows,'2').length,1);assert.equal(auctionStats(rows).volume,500);
 assert.equal(dailyAuctions({status:'synthetic',observations:[]}).length,0);
});
test('FX requires the same observation date and correct quote unit',()=>{
 const s={status:'observed',unit:'KRW/EUR',observations:[{observation_date:'2026-10-29',price:'1500'}]};
 assert.equal(exactFx(s,'2026-10-30'),null);assert.equal(exactFx(s,'2026-10-29'),1500);
 assert.equal(exactFx({...s,unit:'EUR/KRW'},'2026-10-29'),null);
});
test('shortfall, lot rounding and VM use separate physical/price/cash exposures',()=>{
 const r=procurement({demand:10300,inventory:1000,forward:1000,hedge:50},80,1500);
 assert.equal(r.shortage,8300);assert.equal(r.lots,4);assert.equal(r.roundingEua,150);
 assert.equal(r.budgetEur,664000);assert.equal(r.budgetKrw,996000000);
 assert.equal(r.netCostUp5Eur,21500);assert.equal(r.futuresDown5VmEur,20000);
 assert.throws(()=>procurement({demand:100,inventory:'',forward:0,hedge:50},80,null));
 const surplus=procurement({demand:100,inventory:200,forward:0,hedge:100},80,null);
 assert.equal(surplus.budgetEur,0);assert.equal(surplus.budgetKrw,null);
});
test('dealer supply liability and signed futures positions',()=>{
 const r=dealerRisk({inventory:1000,delivery:6000,lots:4});
 assert.equal(r.delta,-1000);assert.equal(r.pnlUp5Eur,-5000);assert.equal(r.futuresDown5CashEur,-20000);
 assert.equal(dealerRisk({inventory:0,delivery:0,lots:-2}).futuresDown5CashEur,10000);
});
const csv=curveHeader+'\n2026-10-30,ICE Endex,EUA,2026-12,90,0,,settlement,https://www.ice.com/products/197/eua-futures\n2026-10-30,ICE Endex,EUA,2027-12,94,10,200,settlement,https://www.ice.com/products/197/eua-futures';
test('curve preserves missing versus zero and accepts only one comparable snapshot',()=>{
 const r=parseCurve(csv,'2026-11-02');assert.equal(r[0].volume_lots,0);assert.equal(r[0].open_interest_lots,null);
 assert.throws(()=>parseCurve(csv.replace('2027-12,94','2026-12,94'),'2026-11-02'),/중복/);
 assert.throws(()=>parseCurve(csv.replace('2027-12,94','2027-12,NaN'),'2026-11-02'));
 assert.throws(()=>parseCurve(csv.replaceAll('2026-10-30','2026-11-03'),'2026-11-02'),/미래/);
 assert.throws(()=>parseCurve(csv.replace('2026-10-30,ICE Endex,EUA,2027','2026-10-29,ICE Endex,EUA,2027'),'2026-11-02'),/동일/);
 assert.throws(()=>parseCurve(csv.replace('2026-10-30,ICE Endex,EUA,2027','2026-10-30,EEX,EUA,2027'),'2026-11-02'),/동일/);
 assert.throws(()=>parseCurve(csv.replaceAll('settlement','auction'),'2026-11-02'));
});
