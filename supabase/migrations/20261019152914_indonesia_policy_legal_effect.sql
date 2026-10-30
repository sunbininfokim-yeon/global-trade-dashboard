-- Reviewed operative clauses, not an inference from age or search absence.
begin;
set local lock_timeout='3s';
create table if not exists policy_idn.legal_effect_findings (
 finding_id text primary key check(finding_id ~ '^idn-effect-[a-f0-9]{64}$'),
 subject_id text not null check(subject_id ~ '^idn-[a-z0-9-]{1,160}$'),
 source_document_id text not null,
 source_hash text not null,
 source_url text not null check(source_url ~ '^https://[^/]+\.go\.id/'),
 finding_type text not null check(finding_type in ('commencement','amendment','full_repeal','partial_repeal','expiry','transition')),
 article text not null check(length(article) between 1 and 160),
 quote text not null check(length(quote) between 30 and 12000),
 effective_on date,
 date_quote text,
 date_basis text not null default 'unverified' check(date_basis in ('unverified','promulgation','explicit_date','reviewed_pdf')),
 reviewed_pdf_sha256 text check(reviewed_pdf_sha256 ~ '^[a-f0-9]{64}$'),
 scope_note_ko text not null check(length(scope_note_ko) between 10 and 2000),
 reviewed_at timestamptz not null default now(),
 foreign key(source_document_id,source_hash) references policy_idn.versions(document_id,content_hash) on delete restrict,
 check((effective_on is null and date_quote is null and date_basis='unverified') or
       (effective_on is not null and date_quote is not null and length(date_quote) between 20 and 4000 and date_basis<>'unverified')),
 check(finding_type<>'commencement' or subject_id=source_document_id)
);
create index if not exists idn_effect_subject_idx on policy_idn.legal_effect_findings(subject_id);
create index if not exists idn_effect_source_idx on policy_idn.legal_effect_findings(source_document_id,source_hash);
alter table policy_idn.legal_effect_findings enable row level security;
revoke all on policy_idn.legal_effect_findings from public,anon,authenticated;
grant select,insert on policy_idn.legal_effect_findings to service_role;
create or replace function policy_idn.guard_legal_effect()
 returns trigger language plpgsql security invoker set search_path='' as $$
declare v policy_idn.versions; t text;
begin
 if not exists(select 1 from policy_idn.documents where document_id=new.subject_id)
 and not exists(select 1 from policy_idn.coverage_items where document_id=new.subject_id)
 then raise exception 'Unknown legal-effect subject'; end if;
 select * into v from policy_idn.versions where document_id=new.source_document_id and content_hash=new.source_hash;
 t=regexp_replace(v.text_content,'\s+',' ','g');
 if not found or v.content_kind<>'official_text'
 or new.source_url<>coalesce(v.provenance->>'text_source_url',v.source_url)
 or position(regexp_replace(new.quote,'\s+',' ','g') in t)=0
 or (new.date_quote is not null and position(regexp_replace(new.date_quote,'\s+',' ','g') in t)=0)
 then raise exception 'Legal effect requires literal official text and date evidence'; end if;
 if not exists(select 1 from policy_idn.embedding_corpus c where c.document_id=new.source_document_id and c.content_hash=new.source_hash)
 then raise exception 'Legal-effect source is no longer current'; end if;
 if new.date_basis='reviewed_pdf' and (new.reviewed_pdf_sha256 is null or new.reviewed_pdf_sha256 is distinct from coalesce(v.provenance->>'raw_text_sha256',v.provenance->>'raw_sha256'))
 then raise exception 'Visual date review requires the identified source PDF hash'; end if;
 if new.finding_type in ('full_repeal','partial_repeal') and lower(new.quote) not like '%tidak berlaku%'
 then raise exception 'Missing operative repeal wording'; end if;
 return new;
end $$;
drop trigger if exists idn_legal_effect_guard on policy_idn.legal_effect_findings;
create trigger idn_legal_effect_guard before insert on policy_idn.legal_effect_findings for each row execute function policy_idn.guard_legal_effect();
create or replace function public.idn_store_legal_effect(p_record jsonb)
 returns boolean language plpgsql security invoker set search_path='' as $$
declare r policy_idn.legal_effect_findings; old_record policy_idn.legal_effect_findings;
begin
 if octet_length(p_record::text)>65000 then raise exception 'Effect payload too large'; end if;
 select * into r from jsonb_populate_record(null::policy_idn.legal_effect_findings,
 jsonb_build_object('date_basis','unverified')||p_record);
 select * into old_record from policy_idn.legal_effect_findings where finding_id=r.finding_id;
 if found then
  if (to_jsonb(old_record)-'reviewed_at') is distinct from (to_jsonb(r)-'reviewed_at') then raise exception 'Effect IDs are immutable'; end if;
  return false;
 end if;
 r.reviewed_at=now();insert into policy_idn.legal_effect_findings select r.*;return true;
end $$;
create or replace function public.idn_legal_effect(p_document_ids text[],p_as_of date default current_date)
 returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
 if p_document_ids is null or cardinality(p_document_ids) not between 1 and 50 or p_as_of is null
 or exists(select 1 from unnest(p_document_ids) x where x is null or x !~ '^idn-[a-z0-9-]{1,160}$')
 then raise exception 'Invalid legal-effect scope'; end if;
 return (with ids as (select distinct unnest(p_document_ids) document_id), evidence as (
 select f.*,c.content_hash=f.source_hash source_current,c.content_observed_at source_observed_at
 from policy_idn.legal_effect_findings f join policy_idn.embedding_corpus c on c.document_id=f.source_document_id
 where f.subject_id=any(p_document_ids)
 ), assessments as (
 select i.document_id,
 exists(select 1 from policy_idn.documents d where d.document_id=i.document_id) document_stored,
 count(*) filter(where e.source_current and e.effective_on<=p_as_of and e.finding_type='full_repeal') full_repeals,
 count(*) filter(where e.source_current and e.effective_on<=p_as_of and e.finding_type='partial_repeal') partial_repeals,
 count(*) filter(where e.source_current and e.effective_on<=p_as_of and e.finding_type='amendment') amendments,
 count(*) filter(where e.source_current and e.effective_on<=p_as_of and e.finding_type='expiry') expiries,
 count(*) filter(where e.source_current and e.effective_on<=p_as_of and e.finding_type='commencement') commencements,
 count(*) filter(where e.source_current and e.effective_on>p_as_of and e.finding_type='commencement') future_commencements,
 max(e.effective_on) filter(where e.source_current and e.effective_on<=p_as_of and e.finding_type='full_repeal') last_repeal,
 max(e.effective_on) filter(where e.source_current and e.finding_type='commencement') last_commencement,
 count(*) filter(where e.source_current and e.effective_on is null and e.finding_type in ('full_repeal','partial_repeal','expiry','amendment','commencement')) undated,
 count(*) filter(where not e.source_current) stale_evidence_count,
 bool_or(e.source_current and e.finding_type='transition' and (e.effective_on is null or e.effective_on<=p_as_of)) transition_review_required,
 max(e.reviewed_at) filter(where e.source_current) reviewed_at,
 coalesce(jsonb_agg(to_jsonb(e) order by e.effective_on,e.finding_id) filter(where e.source_current),'[]'::jsonb) findings
 from ids i left join evidence e on e.subject_id=i.document_id group by i.document_id
 ) select jsonb_build_object('country','IDN','as_of',p_as_of,'exhaustive',false,'items',coalesce(jsonb_agg(
 jsonb_build_object('document_id',document_id,'document_stored',document_stored,
 'status',case when full_repeals>0 and last_commencement>=last_repeal then 'conflicting_evidence'
 when full_repeals>0 then 'fully_repealed' when expiries>0 then 'expired'
 when future_commencements>0 and commencements=0 then 'not_yet_effective'
 when partial_repeals>0 then 'partially_repealed' when amendments>0 then 'amended'
 when undated>0 then 'effective_date_unverified' when commencements>0 then 'commenced_review_needed' else 'unverified' end,
 'current_validity_confirmed',false,'stale_evidence_count',stale_evidence_count,
 'transition_review_required',coalesce(transition_review_required,false),'reviewed_at',reviewed_at,'findings',findings
 ) order by document_id),'[]'::jsonb)) from assessments);
end $$;
revoke all on function policy_idn.guard_legal_effect(),public.idn_store_legal_effect(jsonb),public.idn_legal_effect(text[],date) from public,anon,authenticated;
grant execute on function policy_idn.guard_legal_effect(),public.idn_store_legal_effect(jsonb),public.idn_legal_effect(text[],date) to service_role;
notify pgrst,'reload schema';
commit;
