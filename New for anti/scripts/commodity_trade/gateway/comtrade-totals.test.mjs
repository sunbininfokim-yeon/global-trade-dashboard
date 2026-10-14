import test from 'node:test';
import assert from 'node:assert/strict';
import {selectComtradeTotals} from './comtrade-totals.mjs';
test('BRA detail cannot replace the total regardless of response order',()=>{
  const total={reporterCode:76,period:202606,cmdCode:'1201',flowCode:'X',partnerCode:0,partner2Code:0,customsCode:'C00',motCode:0,primaryValue:6266777036,netWgt:14505018184.774};
  const detail={...total,motCode:1,primaryValue:2312,netWgt:245};
  assert.deepEqual(selectComtradeTotals([total,detail]),[total]);
  assert.deepEqual(selectComtradeTotals([detail,total,total]),[total]);
  assert.throws(()=>selectComtradeTotals([total,{...total,netWgt:1}]));
});
test('statistical detail scopes do not masquerade as totals',()=>{
  for(const detail of [{partner2Code:156},{customsCode:'C01'},{motCode:4}]) {
    assert.deepEqual(selectComtradeTotals([detail]),[]);
  }
});
test('invalid metrics and malformed rows fail closed',()=>{
  for(const value of [NaN,Infinity,-1,true,'1']) {
    assert.throws(()=>selectComtradeTotals([{primaryValue:value}]));
  }
  assert.throws(()=>selectComtradeTotals([[]]));
});
