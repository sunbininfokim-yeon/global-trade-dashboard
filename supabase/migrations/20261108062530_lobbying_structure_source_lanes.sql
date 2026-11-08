begin;

-- Keep the two-argument RPC compatible with an in-flight prior runner.
create function public.lobby_claim_structure(p_owner uuid,p_profile text,p_source text)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare chosen record; result jsonb;
begin
  if p_source is not null and p_source not in ('fara','lda') then raise exception 'Invalid source'; end if;
  select r.record_id,r.payload_hash||':'||coalesce(r.body_sha256,'') as version into chosen
  from lobby_records r left join lobby_structure_jobs j on j.record_id=r.record_id
    and j.source_version=r.payload_hash||':'||coalesce(r.body_sha256,'') and j.profile=p_profile
  where r.kind='document' and r.text_state='extracted'
    and (p_source is null or r.source=p_source)
    and (j.record_id is null or (j.status in ('pending','partial','error','running')
      and coalesce(j.lease_until,'-infinity')<now()
      and (j.status<>'error' or j.last_attempt_at<now()-interval '1 hour')))
  order by j.last_attempt_at nulls first,r.source_date desc nulls last,r.record_id
  limit 1 for update of r skip locked;
  if not found then return null; end if;
  insert into lobby_structure_jobs(record_id,source_version,profile,status,lease_owner,lease_until,last_attempt_at)
    values(chosen.record_id,chosen.version,p_profile,'running',p_owner,now()+interval '10 minutes',now())
  on conflict(record_id,source_version,profile) do update
    set status='running',lease_owner=p_owner,lease_until=now()+interval '10 minutes',last_attempt_at=now(),last_error=null
  returning jsonb_build_object('record_id',record_id,'source_version',source_version,'next_ordinal',next_ordinal) into result;
  return result;
end $$;

revoke all on function public.lobby_claim_structure(uuid,text,text) from public,anon,authenticated;
grant execute on function public.lobby_claim_structure(uuid,text,text) to service_role;

commit;
