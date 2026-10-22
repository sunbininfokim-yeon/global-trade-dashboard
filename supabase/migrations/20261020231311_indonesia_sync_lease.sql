-- One bounded IDN refresh across hosts/stages. No scheduler or mail activation.
begin;
set local lock_timeout='3s';

create table if not exists policy_idn.sync_lease (
 singleton boolean primary key default true check (singleton),
 lease_token uuid not null,
 owner text not null check (owner ~ '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}$'),
 acquired_at timestamptz not null,
 heartbeat_at timestamptz not null,
 expires_at timestamptz not null
);
alter table policy_idn.sync_lease enable row level security;
revoke all on policy_idn.sync_lease from public,anon,authenticated;
grant all on policy_idn.sync_lease to service_role;

create or replace function public.idn_acquire_sync_lease(p_owner text,p_ttl_seconds integer default 900)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_token uuid; v_expires timestamptz;
begin
 if p_owner is null or p_owner !~ '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}$'
    or p_ttl_seconds is null or p_ttl_seconds not between 120 and 1800 then
  raise exception 'invalid IDN lease owner or duration';
 end if;
 insert into policy_idn.sync_lease as l(singleton,lease_token,owner,acquired_at,heartbeat_at,expires_at)
 values(true,pg_catalog.gen_random_uuid(),p_owner,pg_catalog.clock_timestamp(),pg_catalog.clock_timestamp(),
        pg_catalog.clock_timestamp()+pg_catalog.make_interval(secs=>p_ttl_seconds))
 on conflict(singleton) do update set lease_token=excluded.lease_token,owner=excluded.owner,
  acquired_at=pg_catalog.clock_timestamp(),heartbeat_at=pg_catalog.clock_timestamp(),
  expires_at=pg_catalog.clock_timestamp()+pg_catalog.make_interval(secs=>p_ttl_seconds)
 where l.expires_at<=pg_catalog.clock_timestamp()
 returning lease_token,expires_at into v_token,v_expires;
 if v_token is null then
  select expires_at into v_expires from policy_idn.sync_lease where singleton;
  return pg_catalog.jsonb_build_object('acquired',false,'expires_at',v_expires);
 end if;
 return pg_catalog.jsonb_build_object('acquired',true,'lease_token',v_token,'expires_at',v_expires);
end $$;

create or replace function public.idn_renew_sync_lease(p_lease_token uuid,p_ttl_seconds integer default 900)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
 if p_ttl_seconds is null or p_ttl_seconds not between 120 and 1800 then
  raise exception 'invalid IDN lease duration';
 end if;
 update policy_idn.sync_lease set heartbeat_at=pg_catalog.clock_timestamp(),
  expires_at=pg_catalog.clock_timestamp()+pg_catalog.make_interval(secs=>p_ttl_seconds)
 where singleton and lease_token=p_lease_token and expires_at>pg_catalog.clock_timestamp();
 return found;
end $$;

create or replace function public.idn_release_sync_lease(p_lease_token uuid)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
 delete from policy_idn.sync_lease where singleton and lease_token=p_lease_token;
 return found;
end $$;

-- Row lock is held through the source write: takeover waits for this transaction.
-- A token from an expired/replaced runner cannot write via these RPCs.
create or replace function public.idn_sync_store_document(p_document jsonb,p_lease_token uuid)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
 perform 1 from policy_idn.sync_lease where singleton and lease_token=p_lease_token
  and expires_at>pg_catalog.clock_timestamp() for update;
 if not found then raise exception 'IDN sync lease lost'; end if;
 return public.idn_store_document(p_document);
end $$;

create or replace function public.idn_sync_store_source_check(p_check jsonb,p_lease_token uuid)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
 perform 1 from policy_idn.sync_lease where singleton and lease_token=p_lease_token
  and expires_at>pg_catalog.clock_timestamp() for update;
 if not found then raise exception 'IDN sync lease lost'; end if;
 return public.idn_store_source_check(p_check);
end $$;

create or replace function public.idn_sync_status()
returns jsonb language sql security invoker set search_path='' as $$
 select pg_catalog.jsonb_build_object(
  'country','IDN','observed_at',pg_catalog.clock_timestamp(),
  'lease',coalesce((select pg_catalog.jsonb_build_object('active',expires_at>pg_catalog.clock_timestamp(),
   'owner',owner,'expires_at',expires_at,'heartbeat_at',heartbeat_at) from policy_idn.sync_lease where singleton),'{"active":false}'::jsonb),
  'documents',(select count(*) from policy_idn.documents),
  'versions',(select count(*) from policy_idn.versions),
  'latest_source_check',(select max(checked_at) from policy_idn.source_checks),
  'source_checks_24h',coalesce((select pg_catalog.jsonb_object_agg(outcome,n) from
    (select outcome,count(*) n from policy_idn.source_checks where checked_at>pg_catalog.clock_timestamp()-interval '24 hours' group by outcome) c),'{}'::jsonb),
  'pending_mail_reviews',(select count(*) from policy_idn.mail_changes where state='pending'),
  'delivery_enabled',(select delivery_enabled from policy_idn.mail_config limit 1)
 )
$$;

revoke all on function public.idn_acquire_sync_lease(text,integer),public.idn_renew_sync_lease(uuid,integer),
 public.idn_release_sync_lease(uuid),public.idn_sync_store_document(jsonb,uuid),
 public.idn_sync_store_source_check(jsonb,uuid),public.idn_sync_status() from public,anon,authenticated;
grant execute on function public.idn_acquire_sync_lease(text,integer),public.idn_renew_sync_lease(uuid,integer),
 public.idn_release_sync_lease(uuid),public.idn_sync_store_document(jsonb,uuid),
 public.idn_sync_store_source_check(jsonb,uuid),public.idn_sync_status() to service_role;
commit;
