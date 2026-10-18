import {test} from 'node:test';
import assert from 'node:assert/strict';
import {documentLinks,officialUrl} from '../../New for anti/indonesia-policy/source-links.mjs';
test('only confirmed official text sources become PDF links; failed candidates remain unavailable',()=>{
 const base={source_url:'https://jdih.example.go.id/dok/record',text_source_url:'https://jdih.example.go.id/api/download/fulltext/doc.pdf',content_kind:'official_text'};
 assert.deepEqual(documentLinks(base).map(x=>x.type),['record','pdf']);
 const metadata=documentLinks({...base,content_kind:'official_metadata',download_candidates:[{url:base.text_source_url}]});
 assert.equal(metadata.length,1);assert.equal(metadata[0].type,'record');
 assert.deepEqual(documentLinks({...base,source_url:base.text_source_url}).map(x=>x.type),['pdf']);
 assert.deepEqual(documentLinks({...base,text_source_url:base.source_url}).map(x=>x.type),['text']);
 assert.equal(officialUrl('https://jdih.example.go.id.evil.test/doc.pdf'),null);
 assert.equal(officialUrl('javascript:alert(1)'),null);
 assert.equal(officialUrl('http://example.go.id/doc.pdf'),null);
 assert.ok(documentLinks({...base,text_source_url:'https://evil.test/doc.pdf'}).every(x=>x.type==='record'));
});
