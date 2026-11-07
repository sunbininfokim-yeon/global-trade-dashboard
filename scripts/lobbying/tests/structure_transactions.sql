-- Execute inside the migration's rollback transaction before production apply.
do $$
declare
  owner uuid:=gen_random_uuid();
  passage jsonb;
  units jsonb;
  result jsonb;
begin
  insert into lobby_records(record_id,source,kind,source_url,raw_payload,payload_hash,text_state)
    values('fixture:structure','fara','document','https://example.test','{}','version-a','extracted');
  insert into lobby_structure_jobs(record_id,source_version,profile,status,lease_owner,lease_until)
    values('fixture:structure','version-a:','lobby-evidence-v1','running',owner,now()+interval '5 minutes');
  passage=jsonb_build_object('passage_id','fixture:passage','ordinal',0,'content','We emailed Senator Smith about steel tariffs.',
    'locator',jsonb_build_object('page',3),'extraction_model','fixture','extraction','{}'::jsonb,
    'embedding',to_jsonb(array_fill(0.01::float8,array[1536])));
  units='[{"grain":"contact","date":null,"quote":"We emailed Senator Smith about steel tariffs.","principal":null,"recipients":[{"name":"Smith","branch":"legislative"}],"review_status":"machine_extracted"}]';
  begin
    perform lobby_commit_structure(gen_random_uuid(),'fixture:structure','version-a:','lobby-evidence-v1',passage,units);
    raise exception 'Unexpected foreign lease write';
  exception when others then
    if sqlerrm <> 'Structure lease lost' then raise; end if;
  end;
  begin
    perform lobby_commit_structure(owner,'fixture:structure','version-a:','lobby-evidence-v1',passage,
      jsonb_set(units,'{0,quote}','"An invented contact"'));
    raise exception 'Unexpected unsupported quote write';
  exception when others then
    if sqlerrm <> 'Quote not in passage' then raise; end if;
  end;
  if exists(select 1 from lobby_passages where passage_id='fixture:passage') then raise exception 'Partial insert survived rollback'; end if;
  perform lobby_commit_structure(owner,'fixture:structure','version-a:','lobby-evidence-v1',passage,units);
  if (select next_ordinal from lobby_structure_jobs where record_id='fixture:structure')<>1 then raise exception 'Cursor failed'; end if;
  result=lobby_explore('{"record_id":"fixture:structure"}',null);
  if jsonb_array_length(result->'items')<>1 then raise exception 'Current unit missing'; end if;
  update lobby_records set payload_hash='version-b' where record_id='fixture:structure';
  result=lobby_explore('{"record_id":"fixture:structure"}',null);
  if jsonb_array_length(result->'items')<>0 then raise exception 'Stale evidence leaked into current search'; end if;
  if has_table_privilege('anon','lobby_passages','SELECT') then raise exception 'Public raw embedding access'; end if;
  if has_function_privilege('anon','lobby_explore(jsonb,extensions.vector)','EXECUTE') then raise exception 'Public direct RPC'; end if;
end $$;
