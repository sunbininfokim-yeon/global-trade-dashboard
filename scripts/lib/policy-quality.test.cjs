const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const {embeddingQuality}=require('../../New for anti/policy-evidence');
test('embedding freshness requires matching input, model and dimensions; timestamps alone cannot certify it',()=>{
 const bill={embedding:[1],embedding_model:'gemini-embedding-001',embedded_at:'2026-10-05',raw_source:{embedding_current_input_hash:'abc',embedding_provenance:{input_hash:'abc',model:'gemini-embedding-001',dimensions:1536}}};
 assert.equal(embeddingQuality(bill).status,'current');
 assert.equal(embeddingQuality({...bill,embedding:null}).status,'not_embedded');
 assert.equal(embeddingQuality({...bill,raw_source:{}}).status,'unknown');
 assert.equal(embeddingQuality({...bill,embedding_model:'other'}).status,'unknown');
 assert.equal(embeddingQuality({...bill,raw_source:{...bill.raw_source,embedding_current_input_hash:'changed'}}).status,'stale');
 assert.equal(embeddingQuality({...bill,raw_source:{embedding_refresh_required:true}}).status,'stale');
});
test('RSS quality separates source failure and retained/undated/unclassified items from no publication',()=>{
 const context={window:{}};
 vm.runInNewContext(fs.readFileSync(require.resolve('../../New for anti/mypage.js'),'utf8').replace('window.MyPage = { render, unmount }','window.MyPage = { reportQualityText }'),context);
 const html=context.window.MyPage.reportQualityText({generated_at:'2026-10-01T00:00:00Z',feed_status:[{ok:true},{ok:false,carried_over:3}],stats:{unclassified:7},items:[{published_at:null,commodities:['oil']}]},Date.parse('2026-10-05'));
 assert.match(html,/갱신 지연/);assert.match(html,/1\/2 응답/);assert.match(html,/수집 실패 1/);assert.match(html,/이전 자료 보존 3/);assert.match(html,/발행일 미확인 1/);assert.match(html,/주제 미분류 7/);assert.match(html,/미발행을 뜻하지 않습니다/);
});
test('collection retains a deferred refresh flag across resync without pretending the old vector is current',()=>{
 const {prepareEmbedding}=require('../sync-congress');
 const row={title:'Updated law',summary:'New summary',raw_source:{source:'congress.gov'}};
 const previous={title:'Old law',summary:'Old summary',embedding:[1]};
 assert.equal(prepareEmbedding(row,previous),true);
 assert.equal(embeddingQuality({...row,embedding:[1]}).status,'stale');
 const repeat={title:row.title,summary:row.summary,raw_source:{}};
 assert.equal(prepareEmbedding(repeat,{...row,embedding:[1],embedding_refresh_required:row.raw_source.embedding_refresh_required}),true);
 const vectorProof={input_hash:repeat.raw_source.embedding_current_input_hash,model:'gemini-embedding-001',dimensions:1536};
 const afterSuccess={title:row.title,summary:row.summary,raw_source:{}};
 assert.equal(prepareEmbedding(afterSuccess,{...row,embedding:[1],embedding_provenance:vectorProof,embedding_refresh_required:false}),false);
 assert.equal(embeddingQuality({...afterSuccess,embedding:[1],embedding_model:'gemini-embedding-001'}).status,'current');
 const unchanged={title:'Old law',summary:'Old summary',raw_source:{}};
 assert.equal(prepareEmbedding(unchanged,previous),false); // no mass paid backfill on an unknown vector
 assert.equal(embeddingQuality({...unchanged,embedding:[1]}).status,'unknown');
});
