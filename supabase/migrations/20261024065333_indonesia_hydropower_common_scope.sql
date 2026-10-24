-- Curated retrieval relevance only; no legal-effect or project-applicability finding.
begin;
set local lock_timeout='3s';
create or replace function policy_idn.preserve_hydropower_common_scope()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if new.country_code='IDN' and new.document_id in
 ('idn-uu-32-2009','idn-pp-22-2021','idn-uu-25-2007','idn-uu-40-2007','idn-pp-28-2025') then
  new.topics:=array(select distinct t from unnest(new.topics||array['hydropower']) t order by t);
 end if;
 return new;
end $$;
revoke all on function policy_idn.preserve_hydropower_common_scope() from public,anon,authenticated;
drop trigger if exists idn_hydropower_common_scope on policy_idn.documents;
create trigger idn_hydropower_common_scope before insert or update of topics on policy_idn.documents
 for each row execute function policy_idn.preserve_hydropower_common_scope();
update policy_idn.documents set topics=topics||array['hydropower']
 where document_id in ('idn-uu-32-2009','idn-pp-22-2021','idn-uu-25-2007','idn-uu-40-2007','idn-pp-28-2025')
 and not 'hydropower'=any(topics);
commit;
