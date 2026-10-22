-- Review completion is the release boundary; do not require a second manual job.
begin;
set local lock_timeout='3s';
create or replace function policy_idn.enqueue_reviewed_mail_change()
returns trigger language plpgsql security definer set search_path='' as $$
begin
 if new.state='reviewed' and old.state<>'reviewed' and exists(
  select 1 from policy_idn.mail_config where singleton and delivery_enabled and activated_at<=new.seen_at
 ) then
  perform public.idn_enqueue_mail_change(new.change_id,true);
 end if;
 return new;
end $$;
revoke all on function policy_idn.enqueue_reviewed_mail_change() from public,anon,authenticated;
drop trigger if exists idn_enqueue_reviewed_mail on policy_idn.mail_changes;
create trigger idn_enqueue_reviewed_mail after update of state on policy_idn.mail_changes
 for each row execute function policy_idn.enqueue_reviewed_mail_change();
commit;
