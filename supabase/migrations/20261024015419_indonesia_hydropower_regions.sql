begin;
set local lock_timeout='3s';
alter table policy_idn.documents drop constraint if exists idn_policy_documents_primary_stage_check;
alter table policy_idn.documents add constraint idn_policy_documents_primary_stage_check check(primary_stage in ('coal','nickel_mining','palm_oil','biofuel','mineral_mining','hydropower'));
alter table policy_idn.mail_subscriptions drop constraint if exists mail_subscriptions_topic_check;
alter table policy_idn.mail_subscriptions add constraint mail_subscriptions_topic_check check(topic in ('coal','nickel_mining','palm_oil','biofuel','bauxite','copper','tin','cobalt','manganese','iron_steel','silica','gold_silver','rare_earths','hydropower'));
-- Preserve deployed function bodies/ACL/security modes; extend only explicit topic budgets.
do $migration$
declare f record; body text;
begin
 for f in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where (n.nspname='policy_idn' and p.proname in ('search_documents','search_documents_v2'))
 or (n.nspname='policy_idn_user' and p.proname='idn_set_my_mail_subscriptions')
 or (n.nspname='public' and p.proname='idn_review_mail_change') loop
  body:=pg_get_functiondef(f.oid);
  if strpos(body,'''hydropower''')=0 then body:=replace(body,'''rare_earths''','''rare_earths'',''hydropower'''); end if;
  body:=replace(body,'1 and 13','1 and 14');
  execute body;
 end loop;
end $migration$;
notify pgrst,'reload schema';
commit;
