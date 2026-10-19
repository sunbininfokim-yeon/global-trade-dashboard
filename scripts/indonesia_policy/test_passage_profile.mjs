import {test} from 'node:test';import assert from 'node:assert/strict';
import {passageText} from './embed-passages.mjs';
test('passage vectors bind immutable reviewed evidence, not mutable catalogue metadata',()=>{
 const r={document_id:'idn-example',article:'Pasal 52',interpretation_ko:'인증 비용 지원 검토; 자격 미확인',quote:'Menteri dapat memberikan fasilitas Sertifikasi. '.repeat(3),title:'Old title',title_ko:'구 제목'};
 const text=passageText(r);assert.ok(text.includes(r.quote));assert.ok(text.includes('applicability unverified'));
 assert.equal(passageText({...r,title:'New catalogue title',title_ko:'새 제목'}),text);
 assert.notEqual(passageText({...r,interpretation_ko:'검토 설명이 바뀌면 새 근거를 작성한다'}),text);
 assert.throws(()=>passageText({...r,quote:'X'.repeat(6000)}),/budget/);
});
