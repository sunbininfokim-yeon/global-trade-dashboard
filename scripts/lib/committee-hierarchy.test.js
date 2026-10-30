'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { committeeHierarchy: parse } = require('./committee-hierarchy');
test('official API type and parent restore orphan subcommittee', () => {
  assert.deepEqual(parse({ type: 'Subcommittee', parent: { systemCode: 'ssfr00' } },119,'senate'), { committee_type:'subcommittee', parent_committee_id:'119-senate-ssfr00' });
});
test('partial bill metadata does not invent standing or erase parent', () => {
  assert.deepEqual(parse({name:'Africa'},119,'senate'), {});
});
test('directory classification preserves select special and joint types', () => {
  for (const type of ['Select','Special','Joint','Standing','Commission or Caucus','Task Force'])
    assert.equal(parse({committeeTypeCode:type},119,'senate').committee_type,type.toLowerCase().replaceAll(' ','_'));
});
test('explicit parent and array parent accepted; incompatible parent rejected', () => {
  assert.equal(parse({parent:[{systemCode:'ssfr00'}]},119,'senate').parent_committee_id,'119-senate-ssfr00');
  assert.equal(parse({},119,'house','119-house-hsag00').committee_type,'subcommittee');
  assert.throws(() => parse({parent:{systemCode:'hsag00',chamber:'House'}},119,'senate'));
  assert.throws(() => parse({},119,'senate','118-senate-ssfr00'));
});
test('Senate classification resolves API Other without name heuristics', () => {
 assert.equal(parse({systemCode:'slia00',type:'Other'},119,'senate').committee_type,'select');
 assert.equal(parse({systemCode:'scnc00',type:'Other'},119,'senate').committee_type,'caucus');
 assert.equal(parse({type:'Task Force',parent:{systemCode:'hsgo00'}},119,'house').committee_type,'task_force');
});
