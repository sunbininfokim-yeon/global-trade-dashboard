// A user session only. The service key is never accepted by this client.
export function subscriptionClient(client){
 const rpc=async(name,args)=>{
  const {data,error}=await client.rpc(name,args);
  if(error){if(error.code==='P0001'&&error.message==='subscription combination limit')throw Error('활성 구독은 최대 100개 조합입니다. 기존 구독을 해제하거나 전국 선택을 이용하세요.');throw Error('구독 설정을 불러오거나 저장하지 못했습니다. 로그인과 연결 상태를 확인하세요.');}
  return data;
 };
 return {
  onChange(fn){client.auth.onAuthStateChange?.(()=>setTimeout(fn,0));},
  // The stored session decides first: the site's own login (auth.js) writes the
  // same Supabase session, so a reader signed in there is signed in here.
  async user(){
   if(client.auth.getSession){const {data,error}=await client.auth.getSession();if(!error&&data?.session?.user)return data.session.user;}
   if(!client.auth.getUser)return null;
   const {data,error}=await client.auth.getUser();return error?null:data.user;
  },
  async signIn(email,password){
   if(typeof email!=='string'||!email.includes('@')||typeof password!=='string'||!password)throw Error('이메일과 비밀번호를 입력하세요.');
   const {error}=await client.auth.signInWithPassword({email:email.trim(),password});
   if(error)throw Error('로그인하지 못했습니다. 이메일과 비밀번호를 확인하세요.');
  },
  async signOut(){await client.auth.signOut();},
  async list(){const data=await rpc('idn_my_mail_subscriptions');if(data?.country!=='IDN'||!Array.isArray(data.subscriptions)||!Array.isArray(data.region_options)||!data.region_options.every(r=>typeof r.value==='string'&&typeof r.label==='string'))throw Error('구독 응답을 확인하지 못했습니다.');return data;},
  async set(topic,region,enabled){
   if(typeof topic!=='string'||typeof region!=='string'||!region||typeof enabled!=='boolean')throw Error('품목·사업지역을 확인하세요.');
   return rpc('idn_set_my_mail_subscription',{p_topic:topic,p_region:region,p_enabled:enabled});
  },
  async setMany(topics,regions,enabled=true){
   if(!Array.isArray(topics)||!Array.isArray(regions)||topics.length<1||topics.length>14||regions.length<1||regions.length>50||typeof enabled!=='boolean'||![...topics,...regions].every(v=>typeof v==='string'&&v.length>0))throw Error('품목과 지역을 하나 이상 선택하세요.');
   const data=await rpc('idn_set_my_mail_subscriptions',{p_topics:[...new Set(topics)],p_regions:regions.includes('__all__')?['__all__']:[...new Set(regions)],p_enabled:enabled});
   if(data?.country!=='IDN'||!Number.isInteger(data.affected))throw Error('구독 저장 결과를 확인하지 못했습니다. 다시 조회해 주세요.');
   return data;
  },
 };
}
