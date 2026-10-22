-- Operational recovery of the partial 20261021 install. This filename uses
-- the already-recorded production migration version, not a new application.
-- The main edition migration ends with these same restricted grants.
begin;
set local lock_timeout='3s';
set local statement_timeout='15s';
revoke all on function public.mail_report_event_key(text,timestamptz),
  public.mail_report_edition_sent(uuid,text,timestamptz),public.mail_report_keep_latest()
  from public,anon,authenticated;
grant execute on function public.mail_report_event_key(text,timestamptz),
  public.mail_report_edition_sent(uuid,text,timestamptz) to service_role;
commit;
