-- Requires the existing profiles/favorites/commodity source preference migrations.
-- No historical bill notifications are replayed. No email is sent by this SQL.
begin;

create table if not exists public.mailing_preferences (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  policy_enabled boolean not null default true,
  commodity_enabled boolean not null default true
);
alter table public.mailing_preferences enable row level security;
drop policy if exists mailing_preferences_own on public.mailing_preferences;
create policy mailing_preferences_own on public.mailing_preferences
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
grant select, insert, update, delete on public.mailing_preferences to authenticated;

-- Update one preference atomically; callers can only address their own account.
create or replace function public.set_my_mailing_preference(p_kind text,p_enabled boolean)
returns void language plpgsql security definer set search_path = '' as $$
declare caller uuid := auth.uid();
begin
  if caller is null then raise exception 'authentication required'; end if;
  if p_kind is null or p_kind not in ('policy','commodity') or p_enabled is null then
    raise exception 'invalid preference';
  end if;
  insert into public.mailing_preferences(user_id) values(caller) on conflict do nothing;
  if p_kind='policy' then
    update public.mailing_preferences set policy_enabled=p_enabled where user_id=caller;
  else
    update public.mailing_preferences set commodity_enabled=p_enabled where user_id=caller;
  end if;
end;
$$;
revoke all on function public.set_my_mailing_preference(text,boolean) from public,anon;
grant execute on function public.set_my_mailing_preference(text,boolean) to authenticated;

create table if not exists public.mailing_config (
  singleton boolean primary key default true check (singleton),
  activated_at timestamptz not null default now()
);
insert into public.mailing_config(singleton) values(true) on conflict do nothing;

create table if not exists public.mailing_reports (
  report_id text primary key,
  source_id text not null,
  title text not null check (length(title) between 1 and 1000),
  summary text not null default '' check (length(summary) <= 600),
  url text not null check (url ~ '^https?://'),
  published_at timestamptz not null,
  commodities text[] not null,
  archived_at timestamptz not null default now()
);

create table if not exists public.mailing_deliveries (
  delivery_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  kind text not null check (kind in ('policy','commodity')),
  recipient text not null,
  state text not null default 'processing'
    check (state in ('processing','retry','sent','failed','uncertain','cancelled')),
  lease_token uuid,
  lease_until timestamptz,
  next_attempt_at timestamptz not null default now(),
  attempts integer not null default 1,
  request_payload jsonb,
  first_attempt_at timestamptz,
  provider_message_id text unique,
  accepted_at timestamptz,
  error_code text,
  created_at timestamptz not null default now()
);

create table if not exists public.mailing_outbox (
  outbox_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  event_key text not null,
  kind text not null check (kind in ('policy','commodity')),
  item_kind text not null check (item_kind in ('bill','executive_order','commodity')),
  item_id text not null,
  favorite_created_at timestamptz,
  content jsonb not null,
  due_at timestamptz not null,
  delivery_id uuid references public.mailing_deliveries(delivery_id),
  suppressed_at timestamptz,
  created_at timestamptz not null default now(),
  unique(user_id,event_key)
);
create index if not exists mailing_outbox_due_idx on public.mailing_outbox(due_at,user_id)
  where delivery_id is null and suppressed_at is null;
create index if not exists mailing_outbox_delivery_idx on public.mailing_outbox(delivery_id);
create index if not exists mailing_deliveries_retry_idx on public.mailing_deliveries(next_attempt_at)
  where state in ('processing','retry');
create index if not exists mailing_reports_published_idx on public.mailing_reports(published_at);

alter table public.mailing_config enable row level security;
alter table public.mailing_reports enable row level security;
alter table public.mailing_deliveries enable row level security;
alter table public.mailing_outbox enable row level security;
revoke all on public.mailing_config,public.mailing_reports,public.mailing_deliveries,public.mailing_outbox from anon,authenticated;
grant all on public.mailing_config,public.mailing_reports,public.mailing_deliveries,public.mailing_outbox,public.mailing_preferences to service_role;

create or replace function public.mail_next_due(p_kind text,p_at timestamptz)
returns timestamptz language sql immutable set search_path = '' as $$
  select case when p_kind='policy'
    then (date_trunc('day',p_at at time zone 'Asia/Seoul') + interval '1 day 6 hours') at time zone 'Asia/Seoul'
    else (date_trunc('week',p_at at time zone 'Asia/Seoul') + interval '8 hours'
      + case when p_at at time zone 'Asia/Seoul' < date_trunc('week',p_at at time zone 'Asia/Seoul') + interval '8 hours'
        then interval '0 days' else interval '7 days' end) at time zone 'Asia/Seoul'
  end;
$$;

-- Capture in the same transaction as bills. Date-only source timestamps do not
-- collapse two stage changes on the same day. Favorite creation is the baseline.
create or replace function public.mail_capture_bill_stage()
returns trigger language plpgsql security definer set search_path = '' as $$
declare event_id text := 'bill-stage:' || gen_random_uuid()::text;
begin
  if old.current_stage is not distinct from new.current_stage then return new; end if;
  insert into public.mailing_outbox(user_id,event_key,kind,item_kind,item_id,favorite_created_at,content,due_at)
  select f.user_id,event_id,'policy','bill',new.bill_id,f.created_at,
    jsonb_build_object('title',left(new.title,1000),'from_stage',old.current_stage,'to_stage',new.current_stage,
      'detail',left(coalesce(new.latest_action_text,''),1000),'source_date',new.status_updated_at,
      'observed_at',now(),'url','https://chokemonitor.com/policy/us'),
    public.mail_next_due('policy',now())
  from public.user_favorites f
  where f.item_kind='bill' and f.item_id=new.bill_id;
  return new;
end;
$$;
drop trigger if exists mail_bill_stage_changed on public.bills;
create trigger mail_bill_stage_changed after update of current_stage on public.bills
  for each row execute function public.mail_capture_bill_stage();

-- Preserve existing EO favorites, but only a content change creates an event.
create or replace function public.mail_capture_eo_summary()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if old.summary is not distinct from new.summary or nullif(trim(new.summary),'') is null then return new; end if;
  insert into public.mailing_outbox(user_id,event_key,kind,item_kind,item_id,favorite_created_at,content,due_at)
  select f.user_id,'eo-summary:' || new.eo_number::text || ':' || md5(new.summary),'policy','executive_order',new.eo_number::text,f.created_at,
    jsonb_build_object('title',left(new.title,1000),'detail',left(new.summary,1000),'observed_at',now(),
      'url','https://chokemonitor.com/policy/us'),public.mail_next_due('policy',now())
  from public.user_favorites f where f.item_kind='executive_order' and f.item_id=new.eo_number::text
  on conflict(user_id,event_key) do nothing;
  return new;
end;
$$;
drop trigger if exists mail_eo_summary_changed on public.executive_orders;
create trigger mail_eo_summary_changed after update of summary on public.executive_orders
  for each row execute function public.mail_capture_eo_summary();

create or replace function public.mail_capture_report()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  -- A fixed activation cutoff avoids a launch-time archive blast; unlike a
  -- rolling eight-day window it never ages an already queued item out.
  if new.published_at < (select activated_at-interval '8 days' from public.mailing_config where singleton) then return new; end if;
  insert into public.mailing_outbox(user_id,event_key,kind,item_kind,item_id,content,due_at)
  select distinct f.user_id,'report:' || new.report_id,'commodity','commodity',new.report_id,
    jsonb_build_object('title',left(new.title,1000),'detail',new.summary,'url',new.url,'source_id',new.source_id,
      'commodities',to_jsonb(new.commodities),'published_at',new.published_at),
    public.mail_next_due('commodity',new.published_at)
  from public.user_favorites f
  where f.item_kind='commodity' and f.item_id=any(new.commodities) and f.created_at<=new.published_at
    and not exists(select 1 from public.commodity_report_notifications n where n.user_id=f.user_id and n.report_id=new.report_id)
  on conflict(user_id,event_key) do nothing;
  return new;
end;
$$;
drop trigger if exists mail_report_archived on public.mailing_reports;
create trigger mail_report_archived after insert on public.mailing_reports
  for each row execute function public.mail_capture_report();

create or replace function public.mail_item_active(o public.mailing_outbox)
returns boolean language sql stable security definer set search_path = '' as $$
  select case when o.kind='policy' then
    coalesce((select p.policy_enabled from public.mailing_preferences p where p.user_id=o.user_id),true)
    and exists(select 1 from public.user_favorites f where f.user_id=o.user_id and f.item_kind=o.item_kind
      and f.item_id=o.item_id and f.created_at=o.favorite_created_at)
  else
    coalesce((select p.commodity_enabled from public.mailing_preferences p where p.user_id=o.user_id),true)
    -- The legacy sender may finish after archival but before the cutover.
    -- Recheck its receipt both when claiming and immediately before sending.
    and not exists(select 1 from public.commodity_report_notifications n
      where n.user_id=o.user_id and n.report_id=o.item_id)
    and exists(select 1 from public.user_favorites f where f.user_id=o.user_id and f.item_kind='commodity'
      and (o.content->'commodities') ? f.item_id and f.created_at<=(o.content->>'published_at')::timestamptz)
    and not exists(select 1 from public.commodity_digest_source_prefs p
      where p.user_id=o.user_id and p.source_id=o.content->>'source_id') end;
$$;

create or replace function public.mail_claim(p_kind text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare d public.mailing_deliveries; o public.mailing_outbox; ids uuid[]; verified_email text;
begin
  if p_kind is not null and p_kind not in ('policy','commodity') then raise exception 'invalid mail kind'; end if;
  -- Resend deduplicates for 24h only. Ambiguous old attempts require operator
  -- reconciliation, never a new blind send with an expired idempotency key.
  update public.mailing_deliveries set state='uncertain',error_code='idempotency_window_expired'
    where state in ('processing','retry') and first_attempt_at<now()-interval '23 hours'
      and (lease_until is null or lease_until<now());
  select * into d from public.mailing_deliveries
    where state in ('processing','retry') and next_attempt_at<=now()
      and (lease_until is null or lease_until<now()) and (p_kind is null or kind=p_kind)
    order by next_attempt_at,delivery_id for update skip locked limit 1;
  if found then
    update public.mailing_deliveries set state='processing',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',attempts=attempts+1
      where delivery_id=d.delivery_id returning * into d;
  else
    update public.mailing_outbox x set suppressed_at=now()
      where delivery_id is null and suppressed_at is null and due_at<=now() and not public.mail_item_active(x);
    select x.* into o from public.mailing_outbox x join auth.users u on u.id=x.user_id
      where x.delivery_id is null and x.suppressed_at is null and x.due_at<=now()
        and u.email_confirmed_at is not null and nullif(u.email,'') is not null
        and (p_kind is null or x.kind=p_kind)
      order by x.due_at,x.outbox_id for update of x skip locked limit 1;
    if not found then return null; end if;
    select email into verified_email from auth.users where id=o.user_id and email_confirmed_at is not null;
    select array_agg(outbox_id) into ids from (
      select x.outbox_id from public.mailing_outbox x where x.user_id=o.user_id and x.kind=o.kind
        and x.delivery_id is null and x.suppressed_at is null and x.due_at<=now()
      order by x.due_at,x.outbox_id for update skip locked limit 20
    ) picked;
    insert into public.mailing_deliveries(user_id,kind,recipient,lease_token,lease_until)
      values(o.user_id,o.kind,verified_email,gen_random_uuid(),now()+interval '5 minutes') returning * into d;
    update public.mailing_outbox set delivery_id=d.delivery_id where outbox_id=any(ids);
  end if;
  return to_jsonb(d) || jsonb_build_object('items',(
    select jsonb_agg(jsonb_build_object('item_kind',x.item_kind,'item_id',x.item_id,'content',x.content) order by x.due_at,x.created_at,x.outbox_id)
    from public.mailing_outbox x where x.delivery_id=d.delivery_id));
end;
$$;

create or replace function public.mail_prepare(p_delivery_id uuid,p_lease_token uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare d public.mailing_deliveries;
begin
  select * into d from public.mailing_deliveries where delivery_id=p_delivery_id for update;
  if not found or d.state<>'processing' or d.lease_token is distinct from p_lease_token or d.lease_until<=now() then return null; end if;
  if not exists(select 1 from auth.users u where u.id=d.user_id and u.email=d.recipient and u.email_confirmed_at is not null)
    or exists(select 1 from public.mailing_outbox o where o.delivery_id=d.delivery_id and not public.mail_item_active(o)) then
    update public.mailing_deliveries set state='cancelled',error_code='recipient_or_subscription_changed',lease_until=null where delivery_id=d.delivery_id;
    -- Before any network attempt, eligible items may be safely regrouped.
    if d.first_attempt_at is null then
      update public.mailing_outbox o set delivery_id=null,
        suppressed_at=case when public.mail_item_active(o) then null else now() end where delivery_id=d.delivery_id;
    end if;
    return null;
  end if;
  if d.first_attempt_at<now()-interval '23 hours' then
    update public.mailing_deliveries set state='uncertain',error_code='idempotency_window_expired' where delivery_id=d.delivery_id;
    return null;
  end if;
  if d.request_payload is null then
    if p_payload->>'to' is distinct from d.recipient or nullif(p_payload->>'html','') is null or nullif(p_payload->>'text','') is null then
      raise exception 'invalid mail payload';
    end if;
    update public.mailing_deliveries set request_payload=p_payload,first_attempt_at=now()
      where delivery_id=d.delivery_id returning * into d;
  end if;
  return d.request_payload;
end;
$$;

create or replace function public.mail_complete(p_delivery_id uuid,p_lease_token uuid,p_message_id text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare d public.mailing_deliveries;
begin
  if nullif(p_message_id,'') is null then raise exception 'message id required'; end if;
  select * into d from public.mailing_deliveries where delivery_id=p_delivery_id for update;
  if not found then return false; end if;
  if d.state='sent' then return d.provider_message_id=p_message_id; end if;
  if d.state<>'processing' or d.lease_token is distinct from p_lease_token then return false; end if;
  update public.mailing_deliveries set state='sent',provider_message_id=p_message_id,accepted_at=now(),lease_until=null,error_code=null
    where delivery_id=d.delivery_id;
  insert into public.commodity_report_notifications(user_id,report_id)
    select user_id,item_id from public.mailing_outbox where delivery_id=d.delivery_id and kind='commodity'
    on conflict(user_id,report_id) do nothing;
  return true;
end;
$$;

create or replace function public.mail_fail(p_delivery_id uuid,p_lease_token uuid,p_state text,p_error_code text,p_retry_seconds integer default 600)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if p_state not in ('retry','failed','uncertain') then raise exception 'invalid failure state'; end if;
  update public.mailing_deliveries set state=p_state,error_code=left(p_error_code,100),lease_until=null,
    next_attempt_at=now()+make_interval(secs=>greatest(60,least(coalesce(p_retry_seconds,600),86400)))
    where delivery_id=p_delivery_id and lease_token=p_lease_token and state='processing';
  return found;
end;
$$;

create or replace function public.mail_status()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('pending',(select count(*) from public.mailing_outbox where delivery_id is null and suppressed_at is null),
    'overdue',(select count(*) from public.mailing_outbox where delivery_id is null and suppressed_at is null and due_at<now()),
    'policy_past_7am',(select count(*) from public.mailing_outbox o left join public.mailing_deliveries d using(delivery_id)
      where o.kind='policy' and o.suppressed_at is null and o.due_at+interval '1 hour'<=now()
        and (o.delivery_id is null or d.state in ('processing','retry','failed','uncertain'))),
    'states',(select coalesce(jsonb_object_agg(state,n),'{}'::jsonb) from (select state,count(*) n from public.mailing_deliveries group by state)s));
$$;

-- All privileged RPCs and trigger helpers are server-only, including resolver
-- functions that can read Auth emails. RLS alone does not secure DEFINER RPCs.
do $$ declare r record; begin
  for r in select p.oid::regprocedure signature from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in ('mail_next_due','mail_capture_bill_stage','mail_capture_eo_summary','mail_capture_report',
      'mail_item_active','mail_claim','mail_prepare','mail_complete','mail_fail','mail_status') loop
    execute format('revoke all on function %s from public, anon, authenticated',r.signature);
    execute format('grant execute on function %s to service_role',r.signature);
  end loop;
end $$;
notify pgrst, 'reload schema';
commit;
