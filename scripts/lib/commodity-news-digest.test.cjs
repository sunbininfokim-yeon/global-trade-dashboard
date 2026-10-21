// News-outlet items (Mining.com, Google News...) in the weekly commodity digest
// and the mypage source filter. Run: node --test scripts/lib/commodity-news-digest.test.cjs
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const {pickDigestItems}=require('../notify-commodity-digest');

const item=(id,extra={})=>({id,source_id:'eia',commodities:['nickel'],...extra});
const news=(id)=>item(id,{source_id:'int_mining_all',publisher_type:'news'});

test('news headlines take at most two of a commodity\'s eight digest slots',()=>{
 // Newest first, and the newest ten are all news: the agency reports behind them must still get in.
 const items=[...Array.from({length:10},(_,i)=>news(`n${i}`)),...Array.from({length:8},(_,i)=>item(`a${i}`))];
 const got=pickDigestItems(items,new Set(['nickel']),undefined,new Set(),'u').get('nickel');
 assert.equal(got.length,8);
 assert.equal(got.filter(i=>i.publisher_type==='news').length,2);
 assert.deepEqual(got.slice(0,2).map(i=>i.id),['n0','n1']);
 assert.equal(got.filter(i=>!i.publisher_type).length,6);
});
test('without news the digest is exactly what it was: newest eight, one listing per item',()=>{
 const items=Array.from({length:12},(_,i)=>item(`a${i}`,{commodities:i===0?['nickel','cobalt']:['nickel']}));
 const got=pickDigestItems(items,new Set(['nickel','cobalt']),undefined,new Set(),'u');
 assert.equal(got.get('nickel').length,8);
 assert.equal(got.has('cobalt'),false);   // a0 is listed once, under the first favorited commodity
});
test('sent items and turned-off sources stay out; nothing picked leaves no entry',()=>{
 const items=[item('a'),news('n'),item('b',{source_id:'off'})];
 const got=pickDigestItems(items,new Set(['nickel']),new Set(['off','int_mining_all']),new Set(['u:a']),'u');
 assert.equal(got.size,0);
});
test('mypage names an aggregator source by the source, not by whichever outlet came first',()=>{
 const context={window:{}};
 vm.runInNewContext(fs.readFileSync(require.resolve('../../New for anti/mypage.js'),'utf8').replace('window.MyPage = { render, unmount }','window.MyPage = { groupSourcesByCommodity }'),context);
 const {groups}=context.window.MyPage.groupSourcesByCommodity({
  commodity_labels:{nickel:'니켈'},
  items:[
   {source_id:'gn_a',commodities:['nickel'],agency:'Sunsirs · Google News',agency_ko:'Sunsirs (구글 뉴스 경유)',source_agency:'Google News',source_agency_ko:'구글 뉴스 경유'},
   {source_id:'gn_a',commodities:['nickel'],agency:'Reuters · Google News',agency_ko:'Reuters (구글 뉴스 경유)',source_agency:'Google News',source_agency_ko:'구글 뉴스 경유'},
   {source_id:'eia',commodities:['nickel'],agency:'EIA',agency_ko:'미국 에너지정보청'},
  ]});
 const src=groups[0].sources;
 assert.equal(src.length,2);
 assert.equal(src.find(s=>s.source_id==='gn_a').agency,'Google News');
 assert.equal(src.find(s=>s.source_id==='gn_a').agency_ko,'구글 뉴스 경유');
 assert.equal(src.find(s=>s.source_id==='eia').agency,'EIA');
});
