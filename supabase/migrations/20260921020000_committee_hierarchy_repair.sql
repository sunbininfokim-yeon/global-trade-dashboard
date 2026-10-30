begin;
set local lock_timeout = '3s';
set local statement_timeout = '30s';
set local app.committee_hierarchy_repair = 'on';
lock table public.committees in share row exclusive mode;
-- Only explicitly verified hierarchy fields are protected. Ordinary bill metadata
-- remains writable. Repairs use SET LOCAL app.committee_hierarchy_repair = 'on'.
create or replace function public.preserve_verified_committee_hierarchy()
returns trigger language plpgsql set search_path = '' as $$
declare verified jsonb;
begin
  if current_setting('app.committee_hierarchy_repair', true) = 'on' then return new; end if;
  verified := old.raw_source->'_verified_hierarchy';
  if verified is not null then
    new.committee_type := verified->>'committee_type';
    new.parent_committee_id := verified->>'parent_committee_id';
    new.raw_source := coalesce(new.raw_source, '{}'::jsonb)
      || jsonb_build_object('_verified_hierarchy', verified);
  end if;
  return new;
end;
$$;
revoke all on function public.preserve_verified_committee_hierarchy() from public;
drop trigger if exists preserve_verified_committee_hierarchy on public.committees;
create trigger preserve_verified_committee_hierarchy before update on public.committees
for each row execute function public.preserve_verified_committee_hierarchy();

create temporary table committee_repair_plan(committee_id text,committee_type text,parent_committee_id text,old_type text default 'standing',old_parent text,source_url text) on commit drop;
insert into committee_repair_plan(committee_id,committee_type,parent_committee_id) values
('119-senate-slet00','select',null),
('119-joint-jcuc00','commission_or_caucus',null),
('119-joint-jjec00','joint',null),
('119-joint-jhje00','joint',null),
('119-joint-jcpk00','commission_or_caucus',null),
('119-senate-ssju22','subcommittee','119-senate-ssju00'),
('119-senate-ssju21','subcommittee','119-senate-ssju00'),
('119-senate-ssju01','subcommittee','119-senate-ssju00'),
('119-senate-sshr12','subcommittee','119-senate-sshr00'),
('119-senate-sshr11','subcommittee','119-senate-sshr00'),
('119-senate-sshr09','subcommittee','119-senate-sshr00'),
('119-senate-ssju04','subcommittee','119-senate-ssju00'),
('119-senate-ssju28','subcommittee','119-senate-ssju00'),
('119-senate-ssju26','subcommittee','119-senate-ssju00'),
('119-senate-ssju25','subcommittee','119-senate-ssju00'),
('119-senate-ssfr07','subcommittee','119-senate-ssfr00'),
('119-senate-ssfi02','subcommittee','119-senate-ssfi00'),
('119-senate-ssfi10','subcommittee','119-senate-ssfi00'),
('119-senate-ssfr15','subcommittee','119-senate-ssfr00'),
('119-senate-ssfr14','subcommittee','119-senate-ssfr00'),
('119-senate-ssfr06','subcommittee','119-senate-ssfr00'),
('119-senate-ssfi13','subcommittee','119-senate-ssfi00'),
('119-senate-ssfi14','subcommittee','119-senate-ssfi00'),
('119-senate-ssfi11','subcommittee','119-senate-ssfi00'),
('119-senate-ssfi12','subcommittee','119-senate-ssfi00'),
('119-senate-ssfr01','subcommittee','119-senate-ssfr00'),
('119-senate-ssfr02','subcommittee','119-senate-ssfr00'),
('119-senate-ssfr09','subcommittee','119-senate-ssfr00'),
('119-senate-ssev15','subcommittee','119-senate-ssev00'),
('119-senate-ssev10','subcommittee','119-senate-ssev00'),
('119-senate-ssev09','subcommittee','119-senate-ssev00'),
('119-senate-sseg07','subcommittee','119-senate-sseg00'),
('119-senate-sseg04','subcommittee','119-senate-sseg00'),
('119-senate-sseg03','subcommittee','119-senate-sseg00'),
('119-senate-sseg01','subcommittee','119-senate-sseg00'),
('119-senate-sscm33','subcommittee','119-senate-sscm00'),
('119-senate-sscm34','subcommittee','119-senate-sscm00'),
('119-senate-ssbk09','subcommittee','119-senate-ssbk00'),
('119-senate-ssbk08','subcommittee','119-senate-ssbk00'),
('119-senate-ssas21','subcommittee','119-senate-ssas00'),
('119-senate-ssaf13','subcommittee','119-senate-ssaf00'),
('119-senate-spag00','special',null),
('119-senate-slin00','select',null),
('119-joint-jstx00','joint',null),
('119-senate-slia00','select',null),
('119-senate-scnc00','caucus',null),
('119-joint-jslc00','joint',null),
('119-joint-jspr00','joint',null),
('119-joint-jcse00','commission_or_caucus',null),
('119-joint-jsec00','joint',null),
('119-house-hlzs00','select',null),
('119-house-hotl00','commission_or_caucus',null),
('119-house-hlig00','select',null);
update committee_repair_plan set source_url='https://api.congress.gov/v3/committee/'||split_part(committee_id,'-',2)||'/'||split_part(committee_id,'-',3);

do $$ begin
 if exists(select 1 from committee_repair_plan p left join public.committees c using(committee_id) where c.committee_id is null or not ((c.committee_type is not distinct from p.old_type and c.parent_committee_id is not distinct from p.old_parent) or (c.committee_type is not distinct from p.committee_type and c.parent_committee_id is not distinct from p.parent_committee_id))) then raise exception 'Committee changed since audit'; end if;
 if exists(select 1 from committee_repair_plan p left join public.committees c on c.committee_id=p.parent_committee_id where p.parent_committee_id is not null and (c.committee_id is null or c.committee_id=p.committee_id or c.congress_number<>119)) then raise exception 'Invalid parent'; end if;
end $$;
update public.committees c set committee_type=p.committee_type,parent_committee_id=p.parent_committee_id,
 raw_source=coalesce(c.raw_source,'{}'::jsonb)||jsonb_build_object('_verified_hierarchy',jsonb_build_object('committee_type',p.committee_type,'parent_committee_id',p.parent_committee_id,'source_url',p.source_url,'verified_at','2026-09-21','revision','20260921'))
from committee_repair_plan p where c.committee_id=p.committee_id and (c.committee_type is distinct from p.committee_type or c.parent_committee_id is distinct from p.parent_committee_id or c.raw_source->'_verified_hierarchy'->>'revision' is distinct from '20260921');
do $$ begin
 if exists(select 1 from committee_repair_plan p join public.committees c using(committee_id) where c.committee_type is distinct from p.committee_type or c.parent_committee_id is distinct from p.parent_committee_id) then raise exception 'Verification failed'; end if;
end $$;
select count(*) as verified_rows from committee_repair_plan p join public.committees c using(committee_id) where c.committee_type=p.committee_type and c.parent_committee_id is not distinct from p.parent_committee_id;
commit;
