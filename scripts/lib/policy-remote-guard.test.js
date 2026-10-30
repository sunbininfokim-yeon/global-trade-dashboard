'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {remoteState}=require('./policy-remote-guard');
test('only disabled workflow with completed remote runs permits local writes',()=>{
 assert.equal(remoteState({state:'disabled_manually'},[{status:'completed'}]),'safe');
 for(const status of ['queued','in_progress','waiting'])assert.equal(remoteState({state:'disabled_manually'},[{status}]),'active');
 assert.equal(remoteState({state:'active'},[{status:'completed'}]),'active');
});
test('malformed/network responses fail closed and remain retryable',()=>{
 for(const [w,r]of [[null,[]],[{state:'disabled_manually'},null],[{},[]],[{state:'disabled_manually'},[{}]]])assert.equal(remoteState(w,r),'unknown');
});
