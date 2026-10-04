begin;
set local lock_timeout='3s';
set local statement_timeout='30s';
create table if not exists public.committee_identity_aliases (
 alias_committee_id text primary key references public.committees(committee_id) on delete restrict,
 canonical_committee_id text not null references public.committees(committee_id) on delete restrict,
 source_url text not null,
 evidence jsonb not null default '{}'::jsonb,
 verified_at timestamptz not null default now(),
 check (alias_committee_id <> canonical_committee_id),
 check (split_part(alias_committee_id,'-',1)=split_part(canonical_committee_id,'-',1)),
 check (split_part(alias_committee_id,'-',2)=split_part(canonical_committee_id,'-',2))
);
alter table public.committee_identity_aliases enable row level security;
revoke all on public.committee_identity_aliases from public, anon, authenticated;
grant select, insert, update, delete on public.committee_identity_aliases to service_role;
create or replace function public.validate_committee_identity_alias()
returns trigger language plpgsql set search_path='' as $$
begin
 perform pg_advisory_xact_lock(119,20260921);
 if exists(select 1 from public.committee_identity_aliases a where a.alias_committee_id=new.canonical_committee_id or a.canonical_committee_id=new.alias_committee_id) then
  raise exception 'Committee aliases must resolve in one hop; chains and cycles are forbidden';
 end if;
 return new;
end $$;
revoke all on function public.validate_committee_identity_alias() from public;
drop trigger if exists validate_committee_identity_alias on public.committee_identity_aliases;
create trigger validate_committee_identity_alias before insert or update on public.committee_identity_aliases
for each row execute function public.validate_committee_identity_alias();

create or replace view public.committee_identity with (security_invoker=true) as
select c.committee_id as source_committee_id,
 coalesce(a.canonical_committee_id,c.committee_id) as canonical_committee_id,
 c.congress_number,c.chamber
from public.committees c left join public.committee_identity_aliases a on a.alias_committee_id=c.committee_id;

create or replace view public.committee_directory with (security_invoker=true) as
select c.*, coalesce(pa.canonical_committee_id,c.parent_committee_id) as canonical_parent_committee_id, array(select i.source_committee_id from public.committee_identity i
 where i.canonical_committee_id=c.committee_id order by i.source_committee_id) as source_committee_ids,
 (select count(distinct b.bill_id) from public.bill_committees b join public.committee_identity i
 on i.source_committee_id=b.committee_id where i.canonical_committee_id=c.committee_id) as canonical_bill_count
from public.committees c left join public.committee_identity_aliases pa on pa.alias_committee_id=c.parent_committee_id where not exists(select 1 from public.committee_identity_aliases a where a.alias_committee_id=c.committee_id);

create or replace view public.committee_canonical_bill_links with (security_invoker=true) as
select i.canonical_committee_id as committee_id,b.bill_id,
 array_agg(distinct b.committee_id order by b.committee_id) as source_committee_ids
from public.bill_committees b join public.committee_identity i on i.source_committee_id=b.committee_id
group by i.canonical_committee_id,b.bill_id;
revoke all on public.committee_identity,public.committee_directory,public.committee_canonical_bill_links from public,anon,authenticated;
grant select on public.committee_identity,public.committee_directory,public.committee_canonical_bill_links to service_role;

-- Site canonical identity, not a claim that Congress.gov retired the other codes.
insert into public.committee_identity_aliases(alias_committee_id,canonical_committee_id,source_url,evidence)
values
('119-joint-jhje00','119-joint-jjec00','https://www.jec.senate.gov/public/index.cfm/about','{"basis":"same official name; 1946 founding; House/Senate representation; source codes retained","source_api":"https://api.congress.gov/v3/committee/joint/jhje00"}'),
('119-joint-jsec00','119-joint-jjec00','https://www.jec.senate.gov/public/index.cfm/about','{"basis":"same official name, website and 1946 history; source codes retained","source_api":"https://api.congress.gov/v3/committee/joint/jsec00"}')
on conflict(alias_committee_id) do nothing;
do $$ begin
 if (select count(*) from public.committee_identity_aliases where alias_committee_id in ('119-joint-jhje00','119-joint-jsec00') and canonical_committee_id='119-joint-jjec00')<>2 then raise exception 'Conflicting JEC alias mapping'; end if;
end $$;
insert into public.policy_areas(policy_area_id,name,source,source_url,active)
select trim(both '-' from regexp_replace(lower(name),'[^a-z0-9]+','-','g')),name,'congress.gov','https://www.congress.gov/help/field-values/policy-area',true
from (values
('Agriculture and Food'),
('Animals'),
('Armed Forces and National Security'),
('Arts, Culture, Religion'),
('Civil Rights and Liberties, Minority Issues'),
('Commerce'),
('Congress'),
('Crime and Law Enforcement'),
('Economics and Public Finance'),
('Education'),
('Emergency Management'),
('Energy'),
('Environmental Protection'),
('Families'),
('Finance and Financial Sector'),
('Foreign Trade and International Finance'),
('Government Operations and Politics'),
('Health'),
('Housing and Community Development'),
('Immigration'),
('International Affairs'),
('Labor and Employment'),
('Law'),
('Native Americans'),
('Public Lands and Natural Resources'),
('Science, Technology, Communications'),
('Social Sciences and History'),
('Social Welfare'),
('Sports and Recreation'),
('Taxation'),
('Transportation and Public Works'),
('Water Resources Development')) as areas(name)
on conflict(name) do nothing;

select (select count(*) from public.policy_areas where active) as active_policy_areas, (select count(*) from public.committee_directory where congress_number=119 and name='Joint Economic Committee') as canonical_jec_rows;
notify pgrst, 'reload schema';
commit;
