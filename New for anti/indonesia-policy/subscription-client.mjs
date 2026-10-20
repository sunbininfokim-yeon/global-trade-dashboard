// A user session only. The service key is never accepted by this client.
export function subscriptionClient(client){
 const rpc=async(name,args)=>{
  const {data,error}=await client.rpc(name,args);
  if(error)throw Error('구독 설정을 불러오거나 저장하지 못했습니다. 로그인과 연결 상태를 확인하세요.');
  return data;
 };
 return {
  onChange(fn){client.auth.onAuthStateChange?.(()=>setTimeout(fn,0));},
  async user(){const {data,error}=await client.auth.getUser();return error?null:data.user;},
  async list(){const data=await rpc('idn_my_mail_subscriptions');if(data?.country!=='IDN'||!Array.isArray(data.subscriptions)||!Array.isArray(data.regions))throw Error('구독 응답을 확인하지 못했습니다.');return data;},
  async set(topic,region,enabled){
   if(typeof topic!=='string'||typeof region!=='string'||!region||typeof enabled!=='boolean')throw Error('품목·사업지역을 확인하세요.');
   return rpc('idn_set_my_mail_subscription',{p_topic:topic,p_region:region,p_enabled:enabled});
  },
 };
}
