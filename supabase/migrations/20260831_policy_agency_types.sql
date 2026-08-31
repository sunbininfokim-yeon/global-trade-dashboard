-- Phase 2-1 agency taxonomy. Safe for the existing policy database.
-- Adds a display classification and backfills only Federal Register agencies.
-- It never deletes agencies or EO/regulation relationships.

begin;

alter table public.agencies
  add column if not exists agency_type text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.agencies'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%agency_type%'
  ) then
    alter table public.agencies add constraint agencies_agency_type_chk
      check (agency_type is null or agency_type in ('eop', 'department', 'independent', 'sub'));
  end if;
end;
$$;

create index if not exists agencies_type_parent_name_idx
  on public.agencies (agency_type, parent_agency_id, name);

-- Resolve a child agency's stored Federal Register parent_id to the stable
-- local agency_id. If a parent has not been encountered yet, retain any
-- existing parent relationship and classify the child as sub in the meantime.
create or replace function public.refresh_federal_register_agency_classification()
returns integer
language plpgsql
set search_path = public
as $$
declare
  refreshed integer;
begin
  with source_rows as (
    select
      child.agency_id,
      trim(regexp_replace(lower(coalesce(
        nullif(child.raw_source ->> 'raw_name', ''),
        nullif(child.raw_source ->> 'name', ''),
        child.name,
        child.short_name,
        ''
      )), '[^a-z0-9]+', ' ', 'g')) as normalized_name,
      case
        when coalesce(child.raw_source ->> 'parent_id', '') ~ '^[0-9]+$'
          then (child.raw_source ->> 'parent_id')::integer
        else null
      end as parent_federal_register_id
    from public.agencies child
    where child.agency_id like 'fr-%'
  ), classified as (
    select
      source_rows.agency_id,
      parent.agency_id as resolved_parent_agency_id,
      case
        when source_rows.parent_federal_register_id is not null then 'sub'
        when source_rows.normalized_name in (
          'executive office of the president',
          'office of management and budget',
          'office of the united states trade representative',
          'office of united states trade representative',
          'office of science and technology policy',
          'council of economic advisers',
          'national security council',
          'office of national drug control policy'
        ) then 'eop'
        when source_rows.normalized_name in (
          'department of state', 'state department',
          'department of the treasury', 'treasury department',
          'department of defense', 'defense department',
          'department of justice', 'justice department',
          'department of the interior', 'interior department',
          'department of agriculture', 'agriculture department',
          'department of commerce', 'commerce department',
          'department of labor', 'labor department',
          'department of health and human services', 'health and human services department',
          'department of housing and urban development', 'housing and urban development department',
          'department of transportation', 'transportation department',
          'department of energy', 'energy department',
          'department of education', 'education department',
          'department of veterans affairs', 'veterans affairs department',
          'department of homeland security', 'homeland security department'
        ) then 'department'
        else 'independent'
      end as agency_type
    from source_rows
    left join public.agencies parent
      on parent.federal_register_id = source_rows.parent_federal_register_id
  )
  update public.agencies target
  set
    agency_type = classified.agency_type,
    parent_agency_id = coalesce(classified.resolved_parent_agency_id, target.parent_agency_id)
  from classified
  where target.agency_id = classified.agency_id
    and (
      target.agency_type is distinct from classified.agency_type
      or (
        classified.resolved_parent_agency_id is not null
        and target.parent_agency_id is distinct from classified.resolved_parent_agency_id
      )
    );

  get diagnostics refreshed = row_count;
  return refreshed;
end;
$$;

select public.refresh_federal_register_agency_classification();

commit;
