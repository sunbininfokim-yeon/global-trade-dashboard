-- Keep privileged Auth implementations outside the Data API's exposed schema.
-- Public wrappers run as the caller; private implementations still require uid.
begin;
set local lock_timeout='3s';
create schema if not exists policy_idn_user;
revoke all on schema policy_idn_user from public,anon,authenticated;
grant usage on schema policy_idn_user to authenticated;
alter default privileges in schema policy_idn_user revoke execute on functions from public;
do $$
declare r record; definition text;
begin
 for r in select p.oid,p.proname,p.prosecdef from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname in ('idn_my_mail_subscriptions','idn_set_my_mail_subscription')
 loop
  if r.prosecdef then
   definition:=replace(pg_get_functiondef(r.oid),'CREATE OR REPLACE FUNCTION public.','CREATE OR REPLACE FUNCTION policy_idn_user.');
   execute definition;
  elsif not exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='policy_idn_user' and p.proname=r.proname and p.prosecdef) then
   raise exception 'Missing private IDN Auth implementation';
  end if;
 end loop;
end $$;
revoke all on function policy_idn_user.idn_my_mail_subscriptions(),policy_idn_user.idn_set_my_mail_subscription(text,text,boolean) from public,anon;
grant execute on function policy_idn_user.idn_my_mail_subscriptions(),policy_idn_user.idn_set_my_mail_subscription(text,text,boolean) to authenticated;
create or replace function public.idn_my_mail_subscriptions()
returns jsonb language sql stable security invoker set search_path='' as $$
 select policy_idn_user.idn_my_mail_subscriptions()
$$;
create or replace function public.idn_set_my_mail_subscription(p_topic text,p_region text,p_enabled boolean)
returns uuid language sql security invoker set search_path='' as $$
 select policy_idn_user.idn_set_my_mail_subscription(p_topic,p_region,p_enabled)
$$;
revoke all on function public.idn_my_mail_subscriptions(),public.idn_set_my_mail_subscription(text,text,boolean) from public,anon;
grant execute on function public.idn_my_mail_subscriptions(),public.idn_set_my_mail_subscription(text,text,boolean) to authenticated;
notify pgrst,'reload schema';
commit;
