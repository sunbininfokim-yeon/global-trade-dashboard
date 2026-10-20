import {test} from 'node:test';import assert from 'node:assert/strict';
import {subscriptionClient} from '../../New for anti/indonesia-policy/subscription-client.mjs';
test('IDN subscription client uses only own-user Auth RPCs and propagates errors without arbitrary user IDs',async()=>{
 const calls=[],client={auth:{getUser:async()=>({data:{user:{id:'self'}},error:null})},rpc:async(name,args)=>{
  calls.push({name,args});return {data:name==='idn_my_mail_subscriptions'?{country:'IDN',regions:['Kalimantan Timur'],subscriptions:[]}:crypto.randomUUID(),error:null};
 }};
 const api=subscriptionClient(client);assert.equal((await api.user()).id,'self');assert.equal((await api.list()).country,'IDN');
 await api.set('coal','Kalimantan Timur',true);await api.set('coal','Kalimantan Timur',false);
 assert.deepEqual(calls.map(x=>x.name),['idn_my_mail_subscriptions','idn_set_my_mail_subscription','idn_set_my_mail_subscription']);
 assert.equal(calls[1].args.p_enabled,true);assert.equal(calls[2].args.p_enabled,false);assert.equal('p_user_id' in calls[1].args,false);
 client.rpc=async()=>({error:{message:'sensitive backend detail'}});await assert.rejects(api.list(),/구독 설정/);
 client.auth.getUser=async()=>({error:Error('expired'),data:{user:null}});assert.equal(await api.user(),null);
});
