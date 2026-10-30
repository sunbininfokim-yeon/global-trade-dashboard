import {test} from 'node:test';import assert from 'node:assert/strict';
import {resultGroup,groupedResults} from '../../New for anti/indonesia-policy/result-groups.mjs';
test('issuer hierarchy precedes document type and groups retain server order without losing unknown documents',()=>{
 const rows=[{document_id:'local',issuer_level:'provincial',document_type:'Keputusan'},
 {document_id:'law',issuer_level:'national',document_type:'UU'},
 {document_id:'pp',issuer_level:'national',document_type:'PP'},
 {document_id:'pmk',issuer_level:'national',document_type:'PMK'},
 {document_id:'pres',issuer_level:'national',document_type:'Perpres'},
 {document_id:'unknown',document_type:'UU'}];
 assert.equal(resultGroup(rows[0]),'local');assert.equal(resultGroup(rows[5]),'unknown');
 const g=groupedResults(rows);assert.deepEqual(g.find(g=>g.key==='regulation').items.map(d=>d.document_id),['pp','pmk']);
 assert.equal(g.flatMap(x=>x.items).length,rows.length);
 assert.equal(groupedResults([]).length,4);
});
