import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validateCases,evaluateResult} from './evaluate-search.mjs';
test('live evaluation detects lost evidence and all-term regressions without accepting fixed result totals',()=>{
 const c={query:'석탄,RKAB',topic:'coal',expected_id:'idn-example',condition_count:2};
 const result={country:'IDN',search_mode:'keyword_alias',total:12,passage_annotations_available:true,items:[{document_id:'idn-example',matched_condition_count:2,total_condition_count:2,matched_passages:[{article:'Pasal 2'}]}]};
 assert.deepEqual(validateCases({country:'IDN',cases:[c]}),[c]);
 assert.equal(evaluateResult(c,result).passed,true);
 assert.equal(evaluateResult(c,{...result,total:999}).passed,true);
 assert.equal(evaluateResult(c,{...result,passage_annotations_available:false}).passed,false);
 assert.equal(evaluateResult(c,{...result,country:'USA'}).passed,false);
 assert.equal(evaluateResult(c,{...result,search_mode:'hybrid'}).passed,false);
 assert.equal(evaluateResult(c,{...result,items:[{...result.items[0],matched_condition_count:1}]}).passed,false);
 assert.equal(evaluateResult(c,{...result,items:[]}).passed,false);
 assert.throws(()=>validateCases({country:'IDN',cases:[{...c,condition_count:3}]}));
 assert.throws(()=>validateCases({country:'IDN',cases:[{...c,expected_id:'us-example'}]}));
});
