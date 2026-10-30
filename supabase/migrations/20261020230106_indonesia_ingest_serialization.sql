-- A row lock cannot serialize concurrent first insertions of a new document.
begin;
set local lock_timeout='3s';
create or replace function public.idn_store_document(p_document jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
 perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('policy_idn.source:'||(p_document->>'document_id'),0));
 return policy_idn.store_document(p_document);
end $$;
revoke all on function public.idn_store_document(jsonb) from public,anon,authenticated;
grant execute on function public.idn_store_document(jsonb) to service_role;
commit;
