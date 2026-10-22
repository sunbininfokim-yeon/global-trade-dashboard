-- Requires the IDN corpus/isolation and ordered mailing migrations through
-- 20261002020000. Reuses delivery transport, never US document/favorite rows.
begin;
set local lock_timeout='3s';
create table if not exists policy_idn.mail_config (
 singleton boolean primary key default true check(singleton),
 delivery_enabled boolean not null default false,
 activated_at timestamptz
);
insert into policy_idn.mail_config(singleton) values(true) on conflict do nothing;
create table if not exists policy_idn.mail_subscriptions (
 subscription_id uuid primary key default gen_random_uuid(),
 user_id uuid not null references public.profiles(id) on delete cascade,
 topic text not null check(topic in ('coal','nickel_mining','palm_oil','biofuel','bauxite','copper','tin','cobalt','manganese','iron_steel','silica','gold_silver','rare_earths')),
 region text not null check(length(region) between 1 and 120),
 enabled boolean not null default true,
 generation uuid not null default gen_random_uuid(),
 activated_at timestamptz not null default now(),
 created_at timestamptz not null default now(),
 unique(user_id,topic,region)
);
create index if not exists idn_mail_subscriptions_match on policy_idn.mail_subscriptions(topic,region,user_id) where enabled;
create table if not exists policy_idn.mail_baselines (
 document_id text primary key references policy_idn.documents(document_id) on delete cascade,
 content_hash text not null,
 observed_at timestamptz not null
);
create table if not exists policy_idn.mail_changes (
 change_id uuid primary key default gen_random_uuid(),
 document_id text not null,
 content_hash text not null,
 previous_hash text,
 candidate_kind text not null check(candidate_kind in ('new_document','content_changed')),
 seen_at timestamptz not null default now(),
 state text not null default 'pending' check(state in ('pending','reviewed','held','ignored')),
 review jsonb,
 reviewed_at timestamptz,
 unique(document_id,content_hash),
 foreign key(document_id,content_hash) references policy_idn.versions(document_id,content_hash) on delete cascade
);
create index if not exists idn_mail_changes_pending on policy_idn.mail_changes(seen_at) where state='pending';
-- Existing documents establish a quiet baseline, including migration replay.
insert into policy_idn.mail_baselines(document_id,content_hash,observed_at)
 select distinct on(document_id) document_id,content_hash,observed_at from policy_idn.versions
 order by document_id,observed_at desc,content_hash
 on conflict(document_id) do nothing;
alter table policy_idn.mail_config enable row level security;
alter table policy_idn.mail_subscriptions enable row level security;
alter table policy_idn.mail_baselines enable row level security;
alter table policy_idn.mail_changes enable row level security;
revoke all on policy_idn.mail_config,policy_idn.mail_subscriptions,policy_idn.mail_baselines,policy_idn.mail_changes from public,anon,authenticated;
grant all on policy_idn.mail_config,policy_idn.mail_subscriptions,policy_idn.mail_baselines,policy_idn.mail_changes to service_role;
drop policy if exists idn_subscription_owner on policy_idn.mail_subscriptions;
create policy idn_subscription_owner on policy_idn.mail_subscriptions to authenticated
 using((select auth.uid())=user_id) with check((select auth.uid())=user_id);

create or replace function policy_idn.capture_mail_change()
returns trigger language plpgsql security definer set search_path='' as $$
declare b policy_idn.mail_baselines;
begin
 select * into b from policy_idn.mail_baselines where document_id=new.document_id for update;
 if found and (b.content_hash=new.content_hash or new.observed_at<b.observed_at) then return new; end if;
 insert into policy_idn.mail_changes(document_id,content_hash,previous_hash,candidate_kind)
 values(new.document_id,new.content_hash,b.content_hash,case when b.document_id is null then 'new_document' else 'content_changed' end)
 on conflict(document_id,content_hash) do nothing;
 insert into policy_idn.mail_baselines values(new.document_id,new.content_hash,new.observed_at)
 on conflict(document_id) do update set content_hash=excluded.content_hash,observed_at=excluded.observed_at;
 return new;
end $$;
revoke all on function policy_idn.capture_mail_change() from public,anon,authenticated;
drop trigger if exists idn_capture_mail_change on policy_idn.versions;
create trigger idn_capture_mail_change after insert on policy_idn.versions for each row execute function policy_idn.capture_mail_change();

-- The private schema is not exposed. These two narrow Auth RPCs are the only
-- customer entry points; no caller-supplied user ID or privileged claims.
create or replace function public.idn_my_mail_subscriptions()
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare caller uuid:=auth.uid();
begin
 if caller is null then raise exception 'authentication required'; end if;
 return jsonb_build_object('country','IDN','delivery_enabled',(select delivery_enabled from policy_idn.mail_config where singleton),
 'regions',coalesce((select jsonb_agg(jurisdiction order by jurisdiction) from (select distinct jurisdiction from policy_idn.documents where issuer_level in ('provincial','regency','city')) r),'[]'::jsonb),
 'subscriptions',coalesce((select jsonb_agg(jsonb_build_object('id',subscription_id,'topic',topic,'region',region,'enabled',enabled) order by created_at,subscription_id) from policy_idn.mail_subscriptions where user_id=caller),'[]'::jsonb));
end $$;
create or replace function public.idn_set_my_mail_subscription(p_topic text,p_region text,p_enabled boolean)
returns uuid language plpgsql security definer set search_path='' as $$
declare caller uuid:=auth.uid(); result uuid;
begin
 if caller is null or not exists(select 1 from auth.users where id=caller and email_confirmed_at is not null) then raise exception 'confirmed authentication required'; end if;
 if p_enabled is null then raise exception 'enabled required'; end if;
 -- Serialize the per-user limit and never trust a browser user_id.
 perform 1 from public.profiles where id=caller for update;
 if not found then raise exception 'profile required'; end if;
 if not exists(select 1 from policy_idn.mail_subscriptions where user_id=caller and topic=p_topic and region=p_region) then
  if not exists(select 1 from policy_idn.documents where jurisdiction=p_region and issuer_level in ('provincial','regency','city')) then raise exception 'unsupported region'; end if;
  if (select count(*) from policy_idn.mail_subscriptions where user_id=caller)>=30 then raise exception 'subscription limit'; end if;
 end if;
 insert into policy_idn.mail_subscriptions(user_id,topic,region,enabled) values(caller,p_topic,p_region,p_enabled)
 on conflict(user_id,topic,region) do update set enabled=excluded.enabled,
 generation=case when not policy_idn.mail_subscriptions.enabled and excluded.enabled then gen_random_uuid() else policy_idn.mail_subscriptions.generation end,
 activated_at=case when not policy_idn.mail_subscriptions.enabled and excluded.enabled then now() else policy_idn.mail_subscriptions.activated_at end
 returning subscription_id into result;
 return result;
end $$;
revoke all on function public.idn_my_mail_subscriptions(),public.idn_set_my_mail_subscription(text,text,boolean) from public,anon;
grant execute on function public.idn_my_mail_subscriptions(),public.idn_set_my_mail_subscription(text,text,boolean) to authenticated;

-- Review records are tied to exact stored bytes. A textual change is never
-- automatically promoted to amendment/repeal or business applicability.
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
   if not exists(select 1 from policy_idn.documents where jurisdiction=t and issuer_level in ('provincial','regency','city')) then raise exception 'unsupported region'; end if;
   if d.issuer_level<>'national' and d.jurisdiction<>t then raise exception 'unverified local region relationship'; end if;
  end loop;
 end if;
 update policy_idn.mail_changes set state='reviewed',review=p_review,reviewed_at=now() where change_id=p_change_id;
 return true;
end $$;

alter table public.mailing_outbox drop constraint if exists mailing_outbox_item_kind_check;
alter table public.mailing_outbox add constraint mailing_outbox_item_kind_check check(item_kind in ('bill','executive_order','commodity','idn_policy'));
alter table public.mailing_outbox drop constraint if exists idn_mailing_policy_kind;
alter table public.mailing_outbox add constraint idn_mailing_policy_kind check(item_kind<>'idn_policy' or kind='policy');

create or replace function policy_idn.mail_item_active(o public.mailing_outbox)
returns boolean language sql stable security invoker set search_path='' as $$
 select exists(select 1 from policy_idn.mail_config where singleton and delivery_enabled)
 and coalesce((select policy_enabled from public.mailing_preferences where user_id=o.user_id),true)
 and exists(select 1 from policy_idn.mail_changes c,policy_idn.mail_subscriptions s
 where c.change_id::text=o.content->>'change_id' and c.state='reviewed' and c.document_id=o.item_id
 and exists(select 1 from policy_idn.mail_config where singleton and delivery_enabled and activated_at<=c.seen_at)
 and s.user_id=o.user_id and s.enabled and s.activated_at<=c.seen_at
 and (o.content->'subscription_generations')->>s.subscription_id::text=s.generation::text
 and c.review->'topics' ? s.topic
 and (c.review->>'scope'='national' or c.review->'regions' ? s.region))
$$;

create or replace function public.idn_enqueue_mail_change(p_change_id uuid,p_write boolean default false)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare c policy_idn.mail_changes; n integer; added integer:=0;
begin
 select * into c from policy_idn.mail_changes where change_id=p_change_id for update;
 if not found or c.state<>'reviewed' then raise exception 'review required'; end if;
 select count(distinct s.user_id)::int into n from policy_idn.mail_subscriptions s
 where s.enabled and s.activated_at<=c.seen_at and c.review->'topics' ? s.topic
 and (c.review->>'scope'='national' or c.review->'regions' ? s.region)
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
  where s.enabled and s.activated_at<=c.seen_at and c.review->'topics' ? s.topic
   and (c.review->>'scope'='national' or c.review->'regions' ? s.region)
   and coalesce((select policy_enabled from public.mailing_preferences where user_id=s.user_id),true)
  group by s.user_id,d.title_ko on conflict(user_id,event_key) do nothing;
  get diagnostics added=row_count;
 end if;
 return jsonb_build_object('country','IDN','matching_users',n,'enqueued',added,'write',p_write);
end $$;
create or replace function public.idn_set_mail_delivery_enabled(p_enabled boolean)
returns void language plpgsql security invoker set search_path='' as $$
begin
 if p_enabled is null then raise exception 'enabled required'; end if;
 update policy_idn.mail_config set delivery_enabled=p_enabled,
 activated_at=case when p_enabled and not delivery_enabled then now() else activated_at end where singleton;
end $$;
create or replace function public.idn_hold_mail_change(p_change_id uuid)
returns void language sql security invoker set search_path='' as $$
 update policy_idn.mail_changes set state='held' where change_id=p_change_id
$$;
create or replace function public.idn_mail_review_queue(p_limit integer default 20)
returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('country','IDN','delivery_enabled',(select delivery_enabled from policy_idn.mail_config where singleton),
 'states',(select coalesce(jsonb_object_agg(state,n),'{}'::jsonb) from(select state,count(*) n from policy_idn.mail_changes group by state) s),
 'pending',coalesce((select jsonb_agg(to_jsonb(r)) from(select c.change_id,c.document_id,c.content_hash,c.previous_hash,c.candidate_kind,c.seen_at,d.title_ko,d.issuer_level,d.jurisdiction,v.source_url
 from policy_idn.mail_changes c join policy_idn.documents d using(document_id) join policy_idn.versions v using(document_id,content_hash)
 where c.state='pending' order by c.seen_at,c.change_id limit least(50,greatest(1,coalesce(p_limit,20)))) r),'[]'::jsonb))
$$;
revoke all on function public.idn_mail_review_queue(integer) from public,anon,authenticated;
grant execute on function public.idn_mail_review_queue(integer) to service_role;
revoke all on function public.idn_review_mail_change(uuid,jsonb),public.idn_enqueue_mail_change(uuid,boolean),public.idn_set_mail_delivery_enabled(boolean),public.idn_hold_mail_change(uuid),policy_idn.mail_item_active(public.mailing_outbox) from public,anon,authenticated;
grant execute on function public.idn_review_mail_change(uuid,jsonb),public.idn_enqueue_mail_change(uuid,boolean),public.idn_set_mail_delivery_enabled(boolean),public.idn_hold_mail_change(uuid),policy_idn.mail_item_active(public.mailing_outbox) to service_role;

-- Keep the existing US favorite generation/opt-out and commodity receipt guards.
create or replace function public.mail_item_active(o public.mailing_outbox)
returns boolean language sql stable security definer set search_path='' as $$
 select case when o.item_kind='idn_policy' then policy_idn.mail_item_active(o)
 when o.kind='policy' then
 coalesce((select p.policy_enabled from public.mailing_preferences p where p.user_id=o.user_id),true)
 and not coalesce((select p.bill_notifications_paused from public.profiles p where p.id=o.user_id),false)
 and exists(select 1 from public.user_favorites f where f.user_id=o.user_id and f.item_kind=o.item_kind and f.item_id=o.item_id and f.created_at=o.favorite_created_at and f.notify_enabled)
 else coalesce((select p.commodity_enabled from public.mailing_preferences p where p.user_id=o.user_id),true)
 and not exists(select 1 from public.commodity_report_notifications n where n.user_id=o.user_id and n.report_id=o.item_id)
 and exists(select 1 from public.user_favorites f where f.user_id=o.user_id and f.item_kind='commodity' and f.notify_enabled and (o.content->'commodities') ? f.item_id and f.created_at<=(o.content->>'published_at')::timestamptz)
 and not exists(select 1 from public.commodity_digest_source_prefs p where p.user_id=o.user_id and p.source_id=o.content->>'source_id') end
$$;
revoke all on function public.mail_item_active(public.mailing_outbox) from public,anon,authenticated;
grant execute on function public.mail_item_active(public.mailing_outbox) to service_role;
notify pgrst,'reload schema';
commit;
