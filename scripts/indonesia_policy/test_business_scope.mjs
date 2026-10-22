import {test} from 'node:test';import assert from 'node:assert/strict';
import {businessCandidate} from './business-scope.mjs';
test('coal AND East Kalimantan includes national environmental candidates without treating other provinces as local matches',()=>{
 const scope={topic:'coal',region:'Kalimantan Timur'};
 const central={topics:['coal','environmental_land'],issuer_level:'national',jurisdiction:'Indonesia'};
 assert.equal(businessCandidate(central,scope).include,true);
 assert.equal(businessCandidate(central,scope).applicability,'review_needed');
 assert.equal(businessCandidate({...central,topics:['palm_oil']},scope).include,false);
 assert.equal(businessCandidate({...central,issuer_level:'provincial',jurisdiction:'Kalimantan Timur'},scope).include,true);
 assert.equal(businessCandidate({...central,issuer_level:'provincial',jurisdiction:'Sulawesi Tengah'},scope).include,false);
 assert.equal(businessCandidate({...central,issuer_level:'regency',jurisdiction:'Kabupaten Kutai Timur'},scope).include,false);
 assert.throws(()=>businessCandidate(central,{topic:'coal'}));
});
