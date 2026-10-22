-- Nationwide is a subscription scope, never a claim that a local rule is national.
begin;
set local lock_timeout='3s';
create table if not exists policy_idn.mail_regions (
 region text primary key,
 bps_code text not null unique,
 label_ko text not null,
 source_url text not null,
 checked_on date not null
);
alter table policy_idn.mail_regions enable row level security;
revoke all on policy_idn.mail_regions from public,anon,authenticated;
grant all on policy_idn.mail_regions to service_role;
insert into policy_idn.mail_regions(bps_code,region,label_ko,source_url,checked_on) values
('11','Aceh','아체','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('12','Sumatera Utara','북수마트라','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('13','Sumatera Barat','서수마트라','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('14','Riau','리아우','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('15','Jambi','잠비','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('16','Sumatera Selatan','남수마트라','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('17','Bengkulu','벵쿨루','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('18','Lampung','람풍','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('19','Kepulauan Bangka Belitung','방카블리퉁 제도','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('21','Kepulauan Riau','리아우 제도','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('31','DKI Jakarta','자카르타','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('32','Jawa Barat','서자바','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('33','Jawa Tengah','중앙자바','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('34','DI Yogyakarta','욕야카르타','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('35','Jawa Timur','동자바','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('36','Banten','반텐','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('51','Bali','발리','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('52','Nusa Tenggara Barat','서누사틍가라','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('53','Nusa Tenggara Timur','동누사틍가라','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('61','Kalimantan Barat','서칼리만탄','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('62','Kalimantan Tengah','중앙칼리만탄','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('63','Kalimantan Selatan','남칼리만탄','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('64','Kalimantan Timur','동칼리만탄','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('65','Kalimantan Utara','북칼리만탄','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('71','Sulawesi Utara','북술라웨시','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('72','Sulawesi Tengah','중앙술라웨시','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('73','Sulawesi Selatan','남술라웨시','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('74','Sulawesi Tenggara','동남술라웨시','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('75','Gorontalo','고론탈로','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('76','Sulawesi Barat','서술라웨시','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('81','Maluku','말루쿠','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('82','Maluku Utara','북말루쿠','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('91','Papua Barat','서파푸아','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('92','Papua Barat Daya','남서파푸아','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('94','Papua','파푸아','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('95','Papua Selatan','남파푸아','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('96','Papua Tengah','중앙파푸아','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21'),
('97','Papua Pegunungan','파푸아 고원','https://sirusa.web.bps.go.id/metadata/variabel/991eb20f-b1a9-ae36-10a3-daf62e89226e','2026-10-21')
on conflict(region) do update set label_ko=excluded.label_ko,source_url=excluded.source_url,checked_on=excluded.checked_on;

create or replace function policy_idn.supported_mail_region(p_region text)
returns boolean language sql stable security invoker set search_path='' as $$
 select p_region='__all__' or exists(select 1 from policy_idn.mail_regions where region=p_region)
 or exists(select 1 from policy_idn.documents where jurisdiction=p_region and issuer_level in ('provincial','regency','city'))
$$;
revoke all on function policy_idn.supported_mail_region(text) from public,anon,authenticated;
grant execute on function policy_idn.supported_mail_region(text) to service_role;

create or replace function policy_idn_user.idn_my_mail_subscriptions()
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare caller uuid:=auth.uid(); choices jsonb;
begin
 if caller is null then raise exception 'authentication required'; end if;
 select jsonb_agg(jsonb_build_object('value',r.region,'label',r.label_ko,'level',r.level,
  'has_local_documents',exists(select 1 from policy_idn.documents d where d.jurisdiction=r.region and d.issuer_level in ('provincial','regency','city'))) order by r.region)
 into choices from (
  select region,label_ko,'provincial'::text level from policy_idn.mail_regions
  union all select distinct jurisdiction,jurisdiction,issuer_level from policy_idn.documents
   where issuer_level in ('provincial','regency','city') and not exists(select 1 from policy_idn.mail_regions where region=jurisdiction)
 ) r;
 choices:=jsonb_build_array(jsonb_build_object('value','__all__','label','인도네시아 전국 · 중앙·모든 지방','level','all'))||coalesce(choices,'[]'::jsonb);
 return jsonb_build_object('country','IDN','delivery_enabled',(select delivery_enabled from policy_idn.mail_config where singleton),
  'max_active_combinations',100,'region_options',choices,
  'regions',(select jsonb_agg(v->>'value') from jsonb_array_elements(choices) v),
  'subscriptions',coalesce((select jsonb_agg(jsonb_build_object('id',subscription_id,'topic',topic,'region',region,'enabled',enabled)
    order by topic,region) from policy_idn.mail_subscriptions where user_id=caller),'[]'::jsonb));
end $$;

create or replace function policy_idn_user.idn_set_my_mail_subscriptions(p_topics text[],p_regions text[],p_enabled boolean default true)
returns jsonb language plpgsql security definer set search_path='' as $$
declare caller uuid:=auth.uid(); t text; r text; topics text[]; regions text[]; n integer; active_count integer;
begin
 if caller is null or not exists(select 1 from auth.users where id=caller and email_confirmed_at is not null) then raise exception 'confirmed authentication required'; end if;
 if p_enabled is null or coalesce(array_ndims(p_topics),0)<>1 or coalesce(array_ndims(p_regions),0)<>1
  or cardinality(p_topics) not between 1 and 13 or cardinality(p_regions) not between 1 and 50 then raise exception 'invalid subscription selection'; end if;
 foreach t in array p_topics loop
  if t is null or t not in ('coal','nickel_mining','palm_oil','biofuel','bauxite','copper','tin','cobalt','manganese','iron_steel','silica','gold_silver','rare_earths') then raise exception 'unsupported topic'; end if;
 end loop;
 foreach r in array p_regions loop
  if r is null or length(r) not between 1 and 120 or (p_enabled and not policy_idn.supported_mail_region(r)) then raise exception 'unsupported region'; end if;
 end loop;
 select array_agg(distinct x) into topics from unnest(p_topics) x;
 select array_agg(distinct x) into regions from unnest(p_regions) x;
 if '__all__'=any(regions) and cardinality(regions)>1 then raise exception 'nationwide must be selected alone'; end if;
 if cardinality(topics)*cardinality(regions)>100 then raise exception 'subscription combination limit'; end if;
 perform 1 from public.profiles where id=caller for update;
 if not found then raise exception 'profile required'; end if;
 if p_enabled then
  select count(*) into active_count from policy_idn.mail_subscriptions
   where user_id=caller and enabled and not(topic=any(topics) and region=any(regions));
  if active_count+cardinality(topics)*cardinality(regions)>100 then raise exception 'subscription combination limit'; end if;
  insert into policy_idn.mail_subscriptions(user_id,topic,region,enabled)
   select caller,selected_topic.value,selected_region.value,true
    from unnest(topics) as selected_topic(value) cross join unnest(regions) as selected_region(value)
  on conflict(user_id,topic,region) do update set enabled=true,
   generation=case when not policy_idn.mail_subscriptions.enabled then gen_random_uuid() else policy_idn.mail_subscriptions.generation end,
   activated_at=case when not policy_idn.mail_subscriptions.enabled then now() else policy_idn.mail_subscriptions.activated_at end;
 else
  update policy_idn.mail_subscriptions set enabled=false where user_id=caller and topic=any(topics) and region=any(regions) and enabled;
 end if;
 get diagnostics n=row_count;
 return jsonb_build_object('country','IDN','affected',n,'enabled',p_enabled,
  'active_combinations',(select count(*) from policy_idn.mail_subscriptions where user_id=caller and enabled));
end $$;

-- Retain the existing single-combination Auth API for old deployed clients.
create or replace function policy_idn_user.idn_set_my_mail_subscription(p_topic text,p_region text,p_enabled boolean)
returns uuid language plpgsql security definer set search_path='' as $$
begin
 perform policy_idn_user.idn_set_my_mail_subscriptions(array[p_topic],array[p_region],p_enabled);
 return (select subscription_id from policy_idn.mail_subscriptions where user_id=auth.uid() and topic=p_topic and region=p_region);
end $$;
create or replace function public.idn_set_my_mail_subscriptions(p_topics text[],p_regions text[],p_enabled boolean default true)
returns jsonb language sql security invoker set search_path='' as $$
 select policy_idn_user.idn_set_my_mail_subscriptions(p_topics,p_regions,p_enabled)
$$;
revoke all on function policy_idn_user.idn_my_mail_subscriptions(),policy_idn_user.idn_set_my_mail_subscription(text,text,boolean),
 policy_idn_user.idn_set_my_mail_subscriptions(text[],text[],boolean) from public,anon;
grant execute on function policy_idn_user.idn_my_mail_subscriptions(),policy_idn_user.idn_set_my_mail_subscription(text,text,boolean),
 policy_idn_user.idn_set_my_mail_subscriptions(text[],text[],boolean) to authenticated;
revoke all on function public.idn_set_my_mail_subscriptions(text[],text[],boolean) from public,anon;
grant execute on function public.idn_set_my_mail_subscriptions(text[],text[],boolean) to authenticated;

create or replace function policy_idn.mail_scope_matches(p_review jsonb,p_topic text,p_region text)
returns boolean language sql immutable security invoker set search_path='' as $$
 select coalesce(p_review->'topics' ? p_topic and
  (p_region='__all__' or p_review->>'scope'='national' or p_review->'regions' ? p_region),false)
$$;
revoke all on function policy_idn.mail_scope_matches(jsonb,text,text) from public,anon,authenticated;
grant execute on function policy_idn.mail_scope_matches(jsonb,text,text) to service_role;

create or replace function public.idn_review_mail_change(p_change_id uuid,p_review jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare c policy_idn.mail_changes; d policy_idn.documents; v policy_idn.versions; t text;
begin
 select * into c from policy_idn.mail_changes where change_id=p_change_id for update;
 if not found then raise exception 'change not found'; end if;
 if c.state='reviewed' and c.review=p_review then return false; end if;
 if c.state<>'pending' then raise exception 'change is not pending'; end if;
 select * into d from policy_idn.documents where document_id=c.document_id;
 select * into v from policy_idn.versions where document_id=c.document_id and content_hash=c.content_hash;
 if p_review is null or octet_length(p_review::text)>16000 or jsonb_typeof(p_review)<>'object'
 or coalesce(p_review->>'event_type','') not in ('new_document','amended','repealed','effective','official_content_changed')
 or length(coalesce(p_review->>'summary','')) not between 20 and 600
 or length(coalesce(p_review->>'reviewer','')) not between 1 and 80
 or length(coalesce(p_review->>'quote','')) not between 20 and 2000
 or strpos(v.text_content,p_review->>'quote')=0
 or p_review->>'source_url' is distinct from v.source_url
 or v.source_url !~ '^https://([a-zA-Z0-9-]+\.)*go\.id/'
 or jsonb_typeof(p_review->'topics') is distinct from 'array'
 or jsonb_array_length(p_review->'topics') not between 1 and 13
 or coalesce(p_review->>'scope','') not in ('national','regions')
 then raise exception 'invalid review evidence'; end if;
 for t in select jsonb_array_elements_text(p_review->'topics') loop
  if t is null or not t=any(d.topics) then raise exception 'topic outside document review scope'; end if;
 end loop;
 if p_review->>'scope'='national' then
  if d.issuer_level<>'national' then raise exception 'local issuer cannot assert nationwide applicability'; end if;
  if coalesce(p_review->'regions','[]'::jsonb)<>'[]'::jsonb then raise exception 'nationwide scope has no selected region'; end if;
 else
  if jsonb_typeof(p_review->'regions') is distinct from 'array' or jsonb_array_length(p_review->'regions') not between 1 and 30 then raise exception 'regions required'; end if;
  for t in select jsonb_array_elements_text(p_review->'regions') loop
   if t='__all__' or not policy_idn.supported_mail_region(t) then raise exception 'unsupported region'; end if;
   if d.issuer_level<>'national' and d.jurisdiction<>t then raise exception 'unverified local region relationship'; end if;
  end loop;
 end if;
 update policy_idn.mail_changes set state='reviewed',review=p_review,reviewed_at=now() where change_id=p_change_id;
 return true;
end $$;

create or replace function policy_idn.mail_item_active(o public.mailing_outbox)
returns boolean language sql stable security invoker set search_path='' as $$
 select exists(select 1 from policy_idn.mail_config where singleton and delivery_enabled)
 and coalesce((select policy_enabled from public.mailing_preferences where user_id=o.user_id),true)
 and exists(select 1 from policy_idn.mail_changes c,policy_idn.mail_subscriptions s
 where c.change_id::text=o.content->>'change_id' and c.state='reviewed' and c.document_id=o.item_id
 and exists(select 1 from policy_idn.mail_config where singleton and delivery_enabled and activated_at<=c.seen_at)
 and s.user_id=o.user_id and s.enabled and s.activated_at<=c.seen_at
 and (o.content->'subscription_generations')->>s.subscription_id::text=s.generation::text
 and policy_idn.mail_scope_matches(c.review,s.topic,s.region))
$$;

create or replace function public.idn_enqueue_mail_change(p_change_id uuid,p_write boolean default false)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare c policy_idn.mail_changes; n integer; added integer:=0;
begin
 select * into c from policy_idn.mail_changes where change_id=p_change_id for update;
 if not found or c.state<>'reviewed' then raise exception 'review required'; end if;
 select count(distinct s.user_id)::int into n from policy_idn.mail_subscriptions s
 where s.enabled and s.activated_at<=c.seen_at and policy_idn.mail_scope_matches(c.review,s.topic,s.region)
 and coalesce((select policy_enabled from public.mailing_preferences where user_id=s.user_id),true);
 if p_write is null then raise exception 'write flag required'; end if;
 if p_write then
  if not exists(select 1 from policy_idn.mail_config where singleton and delivery_enabled and activated_at<=c.seen_at) then raise exception 'IDN delivery disabled or pre-activation baseline'; end if;
  insert into public.mailing_outbox(user_id,event_key,kind,item_kind,item_id,content,due_at)
  select s.user_id,'idn:'||c.change_id::text,'policy','idn_policy',c.document_id,
   jsonb_build_object('country','IDN','change_id',c.change_id,'title',left(d.title_ko,1000),
   'event_type',c.review->>'event_type','detail',c.review->>'summary','scope',c.review->>'scope',
   'regions',coalesce(c.review->'regions','[]'::jsonb),'topics',c.review->'topics','url',c.review->>'source_url',
   'subscription_generations',jsonb_object_agg(s.subscription_id::text,s.generation::text)),public.mail_next_due('policy',now())
  from policy_idn.mail_subscriptions s join policy_idn.documents d on d.document_id=c.document_id
  where s.enabled and s.activated_at<=c.seen_at and policy_idn.mail_scope_matches(c.review,s.topic,s.region)
   and coalesce((select policy_enabled from public.mailing_preferences where user_id=s.user_id),true)
  group by s.user_id,d.title_ko on conflict(user_id,event_key) do nothing;
  get diagnostics added=row_count;
 end if;
 return jsonb_build_object('country','IDN','matching_users',n,'enqueued',added,'write',p_write);
end $$;
revoke all on function public.idn_review_mail_change(uuid,jsonb),public.idn_enqueue_mail_change(uuid,boolean),policy_idn.mail_item_active(public.mailing_outbox) from public,anon,authenticated;
grant execute on function public.idn_review_mail_change(uuid,jsonb),public.idn_enqueue_mail_change(uuid,boolean),policy_idn.mail_item_active(public.mailing_outbox) to service_role;
notify pgrst,'reload schema';
commit;
