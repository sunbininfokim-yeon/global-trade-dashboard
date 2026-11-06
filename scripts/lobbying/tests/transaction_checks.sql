-- Run after schema creation inside a transaction that is rolled back.
do $$
declare owner uuid := '11111111-1111-1111-1111-111111111111'; n int; state jsonb;
begin
  if has_table_privilege('anon','public.lobby_records','SELECT') then raise exception 'anon table exposed'; end if;
  if has_function_privilege('anon','public.lobby_commit_batch(text,uuid,jsonb,jsonb,bigint,boolean)','EXECUTE') then raise exception 'anon writer exposed'; end if;
  state := lobby_claim_stream('fara:document',owner);
  if state is null then raise exception 'claim failed'; end if;
  if lobby_claim_stream('fara:document','22222222-2222-2222-2222-222222222222') is not null then raise exception 'parallel claim admitted'; end if;
  n := lobby_commit_batch('fara:document',owner,'[{"record_id":"fara:document:transaction-fixture","source":"fara","kind":"document","source_url":"https://efile.fara.gov/docs/fixture.pdf","raw_payload":{},"payload_hash":"fixture-v1","text_state":"pending","country_codes":[],"related_countries":[],"topics":[]}]','{"after":"a"}',1,false);
  n := lobby_commit_batch('fara:document',owner,'[{"record_id":"fara:document:transaction-fixture","source":"fara","kind":"document","source_url":"https://efile.fara.gov/docs/fixture.pdf","raw_payload":{},"payload_hash":"fixture-v1","text_state":"pending","country_codes":[],"related_countries":[],"topics":[]}]','{"after":"a"}',1,false);
  if (select count(*) from lobby_records where record_id='fara:document:transaction-fixture')<>1 then raise exception 'replay duplicated record'; end if;
  if (select count(*) from lobby_record_versions where record_id='fara:document:transaction-fixture')<>1 then raise exception 'replay duplicated revision'; end if;
  begin
    n:=lobby_commit_batch('fara:document',owner,'[{"record_id":"fara:document:must-rollback","source":"fara","kind":"document","source_url":"https://efile.fara.gov/docs/fixture.pdf","raw_payload":{},"payload_hash":"fixture-v2","text_state":"pending"},{"record_id":"bad","source":"lda"}]','{"after":"b"}',1,false);
    raise exception 'invalid batch accepted';
  exception when others then
    if SQLERRM='invalid batch accepted' then raise; end if;
  end;
  if exists(select 1 from lobby_records where record_id='fara:document:must-rollback') then raise exception 'partial batch committed'; end if;
  if (select cursor->>'after' from lobby_sync_state where stream='fara:document')<>'a' then raise exception 'failed cursor advanced'; end if;
  perform lobby_finish_stream('fara:document',owner,'source HTTP 403');
  if (select status from lobby_sync_state where stream='fara:document')<>'source_unavailable' then raise exception 'failure status lost'; end if;
end $$;
