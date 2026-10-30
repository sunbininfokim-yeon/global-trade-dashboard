-- Requires the mailing outbox deployed by PR #321 and the policy evidence collector.
-- Replaces only the capture function; no historical mail or trigger recreation.
-- Vote identity includes action text/type/tally; labels and source URLs are metadata.
-- First canonical snapshot establishes a baseline; no historical backfill mail.
begin;
set local lock_timeout = '3s';
create or replace function public.mail_capture_bill_stage()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  event_id text := 'bill-stage:' || gen_random_uuid()::text;
  before_lifecycle jsonb := old.raw_source->'lifecycle';
  after_lifecycle jsonb := new.raw_source->'lifecycle';
  before_key jsonb;
  after_key jsonb;
begin
  if after_lifecycle->>'version' = '1' then
    if before_lifecycle->>'version' is distinct from '1' then return new; end if;
    before_key := jsonb_build_array(before_lifecycle#>>'{current,step_id}',before_lifecycle#>>'{current,stage}',
      before_lifecycle#>>'{latest_event,kind}',before_lifecycle#>>'{latest_event,chamber}',
      before_lifecycle#>>'{latest_event,date}',before_lifecycle#>>'{latest_event,vote,result}',
      trim(regexp_replace(coalesce(before_lifecycle#>>'{latest_event,text}',''),'\s+',' ','g')),
      before_lifecycle#>>'{latest_event,vote,kind}',before_lifecycle#>>'{latest_event,vote,yea_count}',
      before_lifecycle#>>'{latest_event,vote,nay_count}',before_lifecycle#>>'{latest_event,vote,present_count}',
      before_lifecycle#>>'{latest_event,vote,not_voting_count}');
    after_key := jsonb_build_array(after_lifecycle#>>'{current,step_id}',after_lifecycle#>>'{current,stage}',
      after_lifecycle#>>'{latest_event,kind}',after_lifecycle#>>'{latest_event,chamber}',
      after_lifecycle#>>'{latest_event,date}',after_lifecycle#>>'{latest_event,vote,result}',
      trim(regexp_replace(coalesce(after_lifecycle#>>'{latest_event,text}',''),'\s+',' ','g')),
      after_lifecycle#>>'{latest_event,vote,kind}',after_lifecycle#>>'{latest_event,vote,yea_count}',
      after_lifecycle#>>'{latest_event,vote,nay_count}',after_lifecycle#>>'{latest_event,vote,present_count}',
      after_lifecycle#>>'{latest_event,vote,not_voting_count}');
    if before_key is not distinct from after_key then return new; end if;
  elsif old.current_stage is not distinct from new.current_stage then
    return new;
  end if;
  insert into public.mailing_outbox(user_id,event_key,kind,item_kind,item_id,favorite_created_at,content,due_at)
  select f.user_id,event_id,'policy','bill',new.bill_id,f.created_at,
    jsonb_build_object('title',left(new.title,1000),'from_stage',old.current_stage,'to_stage',new.current_stage,
      'from_lifecycle',before_lifecycle,'lifecycle',after_lifecycle,
      'detail',left(coalesce(new.latest_action_text,''),1000),'source_date',new.status_updated_at,
      'observed_at',now(),'url','https://chokemonitor.com/policy/us'),
    public.mail_next_due('policy',now())
  from public.user_favorites f
  where f.item_kind='bill' and f.item_id=new.bill_id;
  return new;
end;
$$;
commit;
