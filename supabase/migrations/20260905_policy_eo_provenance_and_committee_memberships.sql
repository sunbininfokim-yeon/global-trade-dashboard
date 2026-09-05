-- EO 원문 근거를 보존하는 기관 역할과, 검증된 월간 위원회 roster 적재 계약.
-- 이 마이그레이션은 데이터 관계를 추정하거나 새 행을 자동으로 만들지 않는다.

begin;

alter table public.executive_order_agencies
  drop constraint if exists executive_order_agencies_relationship_type_check;

alter table public.executive_order_agencies
  add constraint executive_order_agencies_relationship_type_check
  check (relationship_type in (
    'issuing_document',
    'implementing_regulation',
    'directed_agency',
    'coordinating_agency',
    'consulted_agency'
  ));

alter table public.executive_order_agencies
  drop constraint if exists executive_order_agencies_relation_origin_check;

alter table public.executive_order_agencies
  add constraint executive_order_agencies_relation_origin_check
  check (relation_origin in (
    'official_document_metadata',
    'official_citation',
    'official_text_citation'
  ));

alter table public.executive_order_agencies
  add column if not exists evidence_excerpt text,
  add column if not exists evidence_section text;

create index if not exists executive_order_agencies_role_idx
  on public.executive_order_agencies (eo_number, relationship_type, agency_id);

alter table public.committee_members
  add column if not exists current boolean not null default true,
  add column if not exists source_name text not null default 'legacy',
  add column if not exists membership_seen_at timestamptz not null default now();

create index if not exists committee_members_current_role_idx
  on public.committee_members (congress_number, current, role, committee_id);

-- 전체 snapshot으로 표시된 역할에 한해, 이번 실행에서 다시 확인되지 않은
-- 과거 행만 비활성화한다. 원본 파일 검증과 모든 upsert 뒤에 호출된다.
create or replace function public.reconcile_committee_membership_snapshot(
  p_congress_number integer,
  p_roles text[],
  p_seen_at timestamptz
)
returns integer
language plpgsql
set search_path = public
as $$
declare
  retired_count integer;
begin
  if p_congress_number is null or p_congress_number < 1 then
    raise exception 'p_congress_number must be a positive integer';
  end if;
  if coalesce(cardinality(p_roles), 0) = 0 then
    raise exception 'p_roles must not be empty';
  end if;
  if p_seen_at is null then
    raise exception 'p_seen_at must not be null';
  end if;

  update public.committee_members
  set current = false
  where congress_number = p_congress_number
    and current = true
    and role = any(p_roles)
    and membership_seen_at < p_seen_at;
  get diagnostics retired_count = row_count;
  return retired_count;
end;
$$;

commit;
