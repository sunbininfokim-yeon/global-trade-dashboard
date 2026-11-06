begin;
create or replace function public.lobby_database_bytes()
returns bigint language sql security invoker set search_path=public,pg_temp as $$
  select pg_database_size(current_database());
$$;
create or replace function public.lobby_resolve_policy_links(p_limit integer default 1000)
returns integer language plpgsql security invoker set search_path=public,pg_temp as $$
declare n integer;
begin
  with candidates as (
    select l.record_id,l.reference_key from lobby_policy_links l
    where l.resolution_status='target_not_collected' and (
      (l.target_type='bill' and exists(select 1 from bills b where b.bill_id=l.target_id)) or
      (l.target_type='public_law' and exists(select 1 from public_laws p where p.public_law_id=l.target_id)) or
      (l.target_type='executive_order' and exists(select 1 from executive_orders e where e.eo_number::text=l.target_id)) or
      (l.target_type='regulation' and exists(select 1 from regulations r where r.regulation_id=l.target_id)))
    order by l.record_id,l.reference_key limit least(greatest(p_limit,1),5000)
  ) update lobby_policy_links l set resolution_status='confirmed' from candidates c
    where l.record_id=c.record_id and l.reference_key=c.reference_key;
  get diagnostics n=row_count;
  return n;
end $$;
revoke all on function public.lobby_database_bytes(),public.lobby_resolve_policy_links(integer) from public,anon,authenticated;
grant execute on function public.lobby_database_bytes(),public.lobby_resolve_policy_links(integer) to service_role;
commit;
