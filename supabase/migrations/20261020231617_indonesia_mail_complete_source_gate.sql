-- Metadata/site layout changes are evidence to retain, not mail-ready rules.
begin;
set local lock_timeout='3s';
alter table policy_idn.mail_changes add column if not exists hold_reason text;
alter table policy_idn.mail_changes add column if not exists held_at timestamptz;

create or replace function policy_idn.guard_mail_source()
returns trigger language plpgsql security invoker set search_path='' as $$
declare complete_source boolean;
begin
 select content_kind='official_text' and not text_truncated into complete_source
 from policy_idn.versions where document_id=new.document_id and content_hash=new.content_hash;
 if new.state='reviewed' and not coalesce(complete_source,false) then
  raise exception 'complete official text required for IDN mail review';
 end if;
 if new.state='pending' and not coalesce(complete_source,false) then
  new.state:='held';new.hold_reason:='incomplete_official_text';new.held_at:=pg_catalog.clock_timestamp();
 elsif new.state='held' then
  if tg_op='INSERT' then
   new.held_at:=pg_catalog.clock_timestamp();new.hold_reason:=coalesce(new.hold_reason,'manual_review_hold');
  elsif old.state<>'held' then
   new.held_at:=pg_catalog.clock_timestamp();new.hold_reason:=coalesce(new.hold_reason,'manual_review_hold');
  end if;
 end if;
 return new;
end $$;
revoke all on function policy_idn.guard_mail_source() from public,anon,authenticated;
grant execute on function policy_idn.guard_mail_source() to service_role;
drop trigger if exists idn_guard_mail_source on policy_idn.mail_changes;
create trigger idn_guard_mail_source before insert or update on policy_idn.mail_changes
 for each row execute function policy_idn.guard_mail_source();

-- Include previously captured incomplete candidates, preserving versions/history.
update policy_idn.mail_changes c set state='held',hold_reason='incomplete_official_text'
 from policy_idn.versions v where c.document_id=v.document_id and c.content_hash=v.content_hash
 and c.state in ('pending','reviewed') and (v.content_kind<>'official_text' or v.text_truncated);

create or replace function public.idn_mail_review_queue(p_limit integer default 20)
returns jsonb language sql stable security invoker set search_path='' as $$
 select pg_catalog.jsonb_build_object('country','IDN',
 'delivery_enabled',(select delivery_enabled from policy_idn.mail_config where singleton),
 'states',(select coalesce(pg_catalog.jsonb_object_agg(state,n),'{}'::jsonb) from
   (select state,count(*) n from policy_idn.mail_changes group by state) s),
 'pending',coalesce((select pg_catalog.jsonb_agg(to_jsonb(r)) from
   (select c.change_id,c.document_id,c.content_hash,c.previous_hash,c.candidate_kind,c.seen_at,
    d.title_ko,d.issuer_level,d.jurisdiction,v.source_url,v.content_kind,v.text_truncated
    from policy_idn.mail_changes c join policy_idn.documents d using(document_id)
    join policy_idn.versions v using(document_id,content_hash) where c.state='pending'
    order by c.seen_at,c.change_id limit least(50,greatest(1,coalesce(p_limit,20)))) r),'[]'::jsonb),
 'held',coalesce((select pg_catalog.jsonb_agg(to_jsonb(r)) from
   (select c.change_id,c.document_id,c.hold_reason,c.held_at,v.content_kind,v.text_truncated,v.source_url
    from policy_idn.mail_changes c join policy_idn.versions v using(document_id,content_hash)
    where c.state='held' order by c.held_at desc nulls last,c.change_id
    limit least(50,greatest(1,coalesce(p_limit,20)))) r),'[]'::jsonb))
$$;
revoke all on function public.idn_mail_review_queue(integer) from public,anon,authenticated;
grant execute on function public.idn_mail_review_queue(integer) to service_role;
commit;
