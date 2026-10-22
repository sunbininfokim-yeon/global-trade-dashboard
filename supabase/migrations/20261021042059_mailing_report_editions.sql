-- A permanent report URL can publish more than one edition. Keep the public
-- report_id/Worker payload contract; distinguish editions by official timestamp.
-- Requires the base mailing + 20261002 subscription migrations. No historical
-- outbox replay, mail RPC invocation, or sending configuration change occurs.
begin;
set local lock_timeout = '5s';
lock table public.mailing_reports, public.mailing_outbox,
  public.mailing_deliveries in share row exclusive mode;

create table if not exists public.mailing_report_editions (
  report_id text not null references public.mailing_reports(report_id) on delete cascade,
  published_at timestamptz not null,
  source_id text not null,
  title text not null check (length(title) between 1 and 1000),
  summary text not null check (length(summary) <= 600),
  url text not null check (url ~ '^https?://'),
  commodities text[] not null,
  first_seen_at timestamptz not null default now(),
  primary key (report_id,published_at)
);
-- This minimal receipt survives metadata retention/archival; do not delete it
-- when pruning full report payloads. Account deletion still cascades.
create table if not exists public.mailing_report_edition_receipts (
  user_id uuid not null references public.profiles(id) on delete cascade,
  report_id text not null,
  published_at timestamptz not null,
  accepted_at timestamptz not null,
  primary key (user_id,report_id,published_at)
);
alter table public.mailing_report_editions enable row level security;
alter table public.mailing_report_edition_receipts enable row level security;
revoke all on public.mailing_report_editions, public.mailing_report_edition_receipts
  from public,anon,authenticated;
grant select,insert,update on public.mailing_report_editions to service_role;
grant select,insert on public.mailing_report_edition_receipts to service_role;

-- Seed existing metadata and proven provider acceptances only. In particular,
-- do NOT infer the edition of an old report-ID-only legacy receipt.
insert into public.mailing_report_editions
  (report_id,published_at,source_id,title,summary,url,commodities,first_seen_at)
-- archived_at belongs to the first report-ID insert, not necessarily this
-- edition. Record this baseline observation now rather than invent its age.
select report_id,published_at,source_id,title,summary,url,commodities,now()
from public.mailing_reports on conflict do nothing;
insert into public.mailing_report_edition_receipts
  (user_id,report_id,published_at,accepted_at)
select o.user_id,o.item_id,(o.content->>'published_at')::timestamptz,
  min(coalesce(d.accepted_at,d.created_at))
from public.mailing_outbox o join public.mailing_deliveries d using(delivery_id)
where o.kind='commodity' and o.item_kind='commodity' and d.state='sent'
  and nullif(o.content->>'published_at','') is not null
group by o.user_id,o.item_id,(o.content->>'published_at')::timestamptz
on conflict do nothing;

create or replace function public.mail_report_event_key(p_report_id text,p_at timestamptz)
returns text language sql immutable strict set search_path = '' as $$
  select 'report:' || p_report_id || ':' || pg_catalog.md5(extract(epoch from p_at)::text);
$$;

create or replace function public.mail_report_edition_sent(p_user_id uuid,p_report_id text,p_at timestamptz)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.mailing_report_edition_receipts r
    where r.user_id=p_user_id and r.report_id=p_report_id and r.published_at=p_at)
  or (
    -- Before the outbox cutover only report IDs were recorded. If no exact
    -- edition evidence exists, conservatively suppress publications dated at
    -- or before that acceptance. Later releases remain eligible.
    not exists(select 1 from public.mailing_report_edition_receipts r
      where r.user_id=p_user_id and r.report_id=p_report_id)
    and exists(select 1 from public.commodity_report_notifications n
      where n.user_id=p_user_id and n.report_id=p_report_id and n.sent_at>=p_at)
  );
$$;

-- A stale recovery artifact must not roll back the latest report row, even
-- when a concurrent upsert or an older four-hour run finishes later.
create or replace function public.mail_report_keep_latest()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.published_at < old.published_at then return null; end if;
  return new;
end;
$$;
drop trigger if exists mail_report_keep_latest on public.mailing_reports;
create trigger mail_report_keep_latest before update on public.mailing_reports
  for each row execute function public.mail_report_keep_latest();

create or replace function public.mail_capture_report()
returns trigger language plpgsql security definer set search_path = '' as $$
declare event_content jsonb;
begin
  insert into public.mailing_report_editions
    (report_id,published_at,source_id,title,summary,url,commodities)
  values(new.report_id,new.published_at,new.source_id,new.title,new.summary,new.url,new.commodities)
  on conflict(report_id,published_at) do update set source_id=excluded.source_id,
    title=excluded.title,summary=excluded.summary,url=excluded.url,commodities=excluded.commodities;

  event_content := jsonb_build_object('title',left(new.title,1000),'detail',new.summary,
    'url',new.url,'source_id',new.source_id,'commodities',to_jsonb(new.commodities),
    'published_at',new.published_at,'report_id',new.report_id,
    'edition_key',public.mail_report_event_key(new.report_id,new.published_at));
  if tg_op='UPDATE' and new.published_at=old.published_at then
    -- Repair an unclaimed item's text/tags without scheduling a new email.
    -- Never mutate a frozen or already accepted delivery payload.
    update public.mailing_outbox o set content=event_content
    where o.kind='commodity' and o.item_kind='commodity' and o.item_id=new.report_id
      and (o.content->>'published_at')::timestamptz=new.published_at
      and o.delivery_id is null and o.suppressed_at is null;
    return new;
  end if;
  if new.published_at < (select activated_at-interval '8 days' from public.mailing_config where singleton)
    or new.published_at < now()-interval '8 days' then return new; end if;

  insert into public.mailing_outbox(user_id,event_key,kind,item_kind,item_id,content,due_at)
  select distinct f.user_id,public.mail_report_event_key(new.report_id,new.published_at),
    'commodity','commodity',new.report_id,event_content,
    greatest(public.mail_next_due('commodity',new.published_at),public.mail_next_due('commodity',now()))
  from public.user_favorites f
  where f.item_kind='commodity' and f.item_id=any(new.commodities)
    and f.notify_enabled and f.created_at<=new.published_at
    and coalesce((select p.commodity_enabled from public.mailing_preferences p where p.user_id=f.user_id),true)
    and not exists(select 1 from public.commodity_digest_source_prefs p
      where p.user_id=f.user_id and p.source_id=new.source_id)
    and not public.mail_report_edition_sent(f.user_id,new.report_id,new.published_at)
    -- Also recognize events queued with the old report-ID-only key.
    and not exists(select 1 from public.mailing_outbox o where o.user_id=f.user_id
      and o.kind='commodity' and o.item_kind='commodity' and o.item_id=new.report_id
      and (o.content->>'published_at')::timestamptz=new.published_at)
  on conflict(user_id,event_key) do nothing;
  return new;
end;
$$;
drop trigger if exists mail_report_archived on public.mailing_reports;
create trigger mail_report_archived after insert or update on public.mailing_reports
  for each row execute function public.mail_capture_report();

-- Keep mail_complete and its lease/idempotency handling unchanged. Acceptances
-- write their edition receipts atomically in the same completion transaction.
create or replace function public.mail_record_report_edition_receipts()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.state<>'sent' then return new; end if;
  insert into public.mailing_report_edition_receipts(user_id,report_id,published_at,accepted_at)
  select o.user_id,o.item_id,(o.content->>'published_at')::timestamptz,
    coalesce(new.accepted_at,now())
  from public.mailing_outbox o where o.delivery_id=new.delivery_id
    and o.kind='commodity' and o.item_kind='commodity'
    and nullif(o.content->>'published_at','') is not null
  on conflict do nothing;
  return new;
end;
$$;
drop trigger if exists mail_report_edition_accepted on public.mailing_deliveries;
create trigger mail_report_edition_accepted after update of state on public.mailing_deliveries
  for each row when (new.state='sent' and old.state is distinct from new.state)
  execute function public.mail_record_report_edition_receipts();

-- Patch ONLY the legacy report dedup predicate. Preserve the current policy
-- pause/favorite guards and optional policy_idn gateway, including installations
-- where Indonesia has not been installed. Unknown drift aborts the transaction.
do $patch$
declare definition text; patched text;
begin
  definition := pg_get_functiondef('public.mail_item_active(public.mailing_outbox)'::regprocedure);
  patched := regexp_replace(definition,
    'not exists\s*\(\s*select 1 from public\.commodity_report_notifications n\s+where n\.user_id\s*=\s*o\.user_id and n\.report_id\s*=\s*o\.item_id\s*\)',
    'not public.mail_report_edition_sent(o.user_id,o.item_id,(o.content->>''published_at'')::timestamptz)', 'i');
  if patched<>definition then execute patched;
  elsif position('mail_report_edition_sent' in definition)=0 then
    raise exception 'mail_item_active drift: review the commodity dedup predicate before applying';
  end if;
end;
$patch$;

revoke all on function public.mail_report_event_key(text,timestamptz),
  public.mail_report_edition_sent(uuid,text,timestamptz),public.mail_report_keep_latest(),
  public.mail_capture_report(),public.mail_record_report_edition_receipts()
  from public,anon,authenticated;
grant execute on function public.mail_report_event_key(text,timestamptz),
  public.mail_report_edition_sent(uuid,text,timestamptz) to service_role;
commit;
