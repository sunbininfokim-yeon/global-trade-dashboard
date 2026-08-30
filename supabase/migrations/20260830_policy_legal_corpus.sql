-- Phase 2-1 legal corpus extension. Safe for the already-created policy DB.
-- Adds columns/tables only; does not delete, truncate, or archive any rows.

begin;

alter table public.bills
  add column if not exists detail_level text not null default 'index';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.bills'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%detail_level%'
  ) then
    alter table public.bills add constraint bills_detail_level_chk
      check (detail_level in ('index', 'tracked', 'enriched'));
  end if;
end;
$$;

alter table public.public_laws
  add column if not exists source_package_id text,
  add column if not exists statutes_at_large_citation text,
  add column if not exists official_pdf_url text,
  add column if not exists official_text_url text,
  add column if not exists classification_status text not null default 'pending',
  add column if not exists source_updated_at timestamptz,
  add column if not exists last_synced_at timestamptz,
  add column if not exists raw_source jsonb not null default '{}'::jsonb;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.public_laws'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%classification_status%'
  ) then
    alter table public.public_laws add constraint public_laws_classification_status_chk
      check (classification_status in ('pending', 'classified', 'partially_classified', 'not_codified'));
  end if;
end;
$$;

create unique index if not exists public_laws_source_package_uidx
  on public.public_laws (source_package_id)
  where source_package_id is not null;

create table if not exists public.us_code_titles (
  title_number smallint primary key check (title_number between 1 and 54),
  title_name text not null,
  is_reserved boolean not null default false,
  is_positive_law boolean,
  official_url text not null,
  source_release_point text,
  source_updated_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.us_code_sections (
  us_code_section_id text primary key,
  title_number smallint not null references public.us_code_titles(title_number) on delete cascade,
  section_number text not null,
  heading text,
  official_url text not null,
  source_credit text,
  source_release_point text,
  source_updated_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (title_number, section_number)
);

create table if not exists public.public_law_code_impacts (
  public_law_code_impact_id bigint generated always as identity primary key,
  public_law_id text not null references public.public_laws(public_law_id) on delete cascade,
  title_number smallint references public.us_code_titles(title_number) on delete set null,
  us_code_section_id text references public.us_code_sections(us_code_section_id) on delete set null,
  section_citation text,
  impact_type text not null default 'amended'
    check (impact_type in ('added', 'amended', 'repealed', 'note', 'uncodified', 'unknown')),
  classification_status text not null default 'pending'
    check (classification_status in ('pending', 'classified', 'partially_classified', 'not_codified')),
  source_url text,
  source_method text not null default 'official_metadata'
    check (source_method in ('official_metadata', 'official_classification_table', 'verified_manual')),
  created_at timestamptz not null default now()
);

create unique index if not exists public_law_code_impacts_identity_uidx
  on public.public_law_code_impacts (
    public_law_id, coalesce(title_number, 0), coalesce(us_code_section_id, ''),
    coalesce(section_citation, ''), impact_type
  );
create index if not exists us_code_sections_title_idx
  on public.us_code_sections (title_number, section_number);
create index if not exists public_laws_classification_idx
  on public.public_laws (classification_status, enacted_date desc);

create table if not exists public.policy_ingestion_queue (
  queue_id uuid primary key default gen_random_uuid(),
  sync_resource text not null,
  source_key text not null,
  priority smallint not null default 0,
  payload jsonb not null,
  source_updated_at timestamptz,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'succeeded', 'failed', 'skipped')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  claimed_at timestamptz,
  completed_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (sync_resource, source_key)
);
create index if not exists policy_ingestion_queue_ready_idx
  on public.policy_ingestion_queue (sync_resource, status, priority desc, available_at, created_at);

insert into public.us_code_titles (title_number, title_name, is_reserved, official_url, raw_source)
select seed.title_number, seed.title_name, seed.is_reserved,
  format('https://uscode.house.gov/view.xhtml?path=/prelim@title%s', seed.title_number),
  jsonb_build_object('source', 'uscode.house.gov', 'seed', true)
from (values
  (1::smallint, 'General Provisions', false), (2::smallint, 'The Congress', false),
  (3::smallint, 'The President', false), (4::smallint, 'Flag and Seal, Seat of Government, and the States', false),
  (5::smallint, 'Government Organization and Employees', false), (6::smallint, 'Domestic Security', false),
  (7::smallint, 'Agriculture', false), (8::smallint, 'Aliens and Nationality', false),
  (9::smallint, 'Arbitration', false), (10::smallint, 'Armed Forces', false),
  (11::smallint, 'Bankruptcy', false), (12::smallint, 'Banks and Banking', false),
  (13::smallint, 'Census', false), (14::smallint, 'Coast Guard', false),
  (15::smallint, 'Commerce and Trade', false), (16::smallint, 'Conservation', false),
  (17::smallint, 'Copyrights', false), (18::smallint, 'Crimes and Criminal Procedure', false),
  (19::smallint, 'Customs Duties', false), (20::smallint, 'Education', false),
  (21::smallint, 'Food and Drugs', false), (22::smallint, 'Foreign Relations and Intercourse', false),
  (23::smallint, 'Highways', false), (24::smallint, 'Hospitals and Asylums', false),
  (25::smallint, 'Indians', false), (26::smallint, 'Internal Revenue Code', false),
  (27::smallint, 'Intoxicating Liquors', false), (28::smallint, 'Judiciary and Judicial Procedure', false),
  (29::smallint, 'Labor', false), (30::smallint, 'Mineral Lands and Mining', false),
  (31::smallint, 'Money and Finance', false), (32::smallint, 'National Guard', false),
  (33::smallint, 'Navigation and Navigable Waters', false), (34::smallint, 'Crime Control and Law Enforcement', false),
  (35::smallint, 'Patents', false), (36::smallint, 'Patriotic and National Observances, Ceremonies, and Organizations', false),
  (37::smallint, 'Pay and Allowances of the Uniformed Services', false), (38::smallint, 'Veterans'' Benefits', false),
  (39::smallint, 'Postal Service', false), (40::smallint, 'Public Buildings, Property, and Works', false),
  (41::smallint, 'Public Contracts', false), (42::smallint, 'The Public Health and Welfare', false),
  (43::smallint, 'Public Lands', false), (44::smallint, 'Public Printing and Documents', false),
  (45::smallint, 'Railroads', false), (46::smallint, 'Shipping', false),
  (47::smallint, 'Telecommunications', false), (48::smallint, 'Territories and Insular Possessions', false),
  (49::smallint, 'Transportation', false), (50::smallint, 'War and National Defense', false),
  (51::smallint, 'National and Commercial Space Programs', false), (52::smallint, 'Voting and Elections', false),
  (53::smallint, '[Reserved]', true), (54::smallint, 'National Park Service and Related Programs', false)
) as seed(title_number, title_name, is_reserved)
on conflict (title_number) do update set
  title_name = excluded.title_name, is_reserved = excluded.is_reserved,
  official_url = excluded.official_url, raw_source = excluded.raw_source, updated_at = now();

create or replace function public.set_updated_at()
returns trigger language plpgsql set search_path = public as $$
begin new.updated_at = now(); return new; end;
$$;

do $$
declare table_name text;
begin
  foreach table_name in array array['us_code_titles', 'us_code_sections', 'policy_ingestion_queue'] loop
    execute format('drop trigger if exists set_updated_at on public.%I', table_name);
    execute format('create trigger set_updated_at before update on public.%I for each row execute function public.set_updated_at()', table_name);
    execute format('alter table public.%I enable row level security', table_name);
  end loop;
  alter table public.public_law_code_impacts enable row level security;
end;
$$;

commit;
