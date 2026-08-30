-- Phase 2-1: United States federal policy data
-- Sources: Congress.gov API, Federal Register API
-- PostgreSQL 17 / Supabase / pgvector
-- Canonical fresh-install schema. Run this file once after resetting an existing
-- project database; do not layer old migration files on top of it.
--
-- Design rules:
--   * Normalize fields required for filtering, navigation, and relationships.
--   * Preserve selected source payloads in JSONB for traceability.
--   * Never store legislative or regulatory full text; store official links only.
--   * Keep official and semantic relationships distinguishable.
--   * service_role is server-only. RLS is enabled without browser policies.

begin;

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Shared reference data
-- ---------------------------------------------------------------------------

create table if not exists public.agencies (
  agency_id text primary key,
  name text not null,
  short_name text,
  federal_register_id integer,
  parent_agency_id text references public.agencies(agency_id) on delete set null,
  agency_url text,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists agencies_federal_register_id_uidx
  on public.agencies (federal_register_id)
  where federal_register_id is not null;

create table if not exists public.policy_areas (
  policy_area_id text primary key,
  name text not null unique,
  source text not null default 'congress.gov'
    check (source in ('congress.gov', 'manual')),
  source_url text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.legislative_subjects (
  subject_id text primary key,
  name text not null unique,
  source_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.cfr_titles (
  title_number smallint primary key check (title_number between 1 and 50),
  title_name text not null,
  reserved boolean not null default false,
  latest_amended_on date,
  latest_issue_date date,
  source_url text not null,
  raw_source jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now()
);

-- Fixed reference seed for the UI's CFR Title 1–50 navigation. This is not an
-- eCFR API synchronization job; Federal Register documents supply the actual
-- regulation-to-title/part relationships.
insert into public.cfr_titles (
  title_number, title_name, reserved, source_url, raw_source, synced_at
)
select
  seed.title_number,
  seed.title_name,
  seed.reserved,
  format('https://www.ecfr.gov/current/title-%s', seed.title_number),
  jsonb_build_object('seed', 'static', 'source', 'eCFR title directory'),
  now()
from (
  values
    (1::smallint, 'General Provisions', false),
    (2::smallint, 'Federal Financial Assistance', false),
    (3::smallint, 'The President', false),
    (4::smallint, 'Accounts', false),
    (5::smallint, 'Administrative Personnel', false),
    (6::smallint, 'Domestic Security', false),
    (7::smallint, 'Agriculture', false),
    (8::smallint, 'Aliens and Nationality', false),
    (9::smallint, 'Animals and Animal Products', false),
    (10::smallint, 'Energy', false),
    (11::smallint, 'Federal Elections', false),
    (12::smallint, 'Banks and Banking', false),
    (13::smallint, 'Business Credit and Assistance', false),
    (14::smallint, 'Aeronautics and Space', false),
    (15::smallint, 'Commerce and Foreign Trade', false),
    (16::smallint, 'Commercial Practices', false),
    (17::smallint, 'Commodity and Securities Exchanges', false),
    (18::smallint, 'Conservation of Power and Water Resources', false),
    (19::smallint, 'Customs Duties', false),
    (20::smallint, 'Employees'' Benefits', false),
    (21::smallint, 'Food and Drugs', false),
    (22::smallint, 'Foreign Relations', false),
    (23::smallint, 'Highways', false),
    (24::smallint, 'Housing and Urban Development', false),
    (25::smallint, 'Indians', false),
    (26::smallint, 'Internal Revenue', false),
    (27::smallint, 'Alcohol, Tobacco Products and Firearms', false),
    (28::smallint, 'Judicial Administration', false),
    (29::smallint, 'Labor', false),
    (30::smallint, 'Mineral Resources', false),
    (31::smallint, 'Money and Finance: Treasury', false),
    (32::smallint, 'National Defense', false),
    (33::smallint, 'Navigation and Navigable Waters', false),
    (34::smallint, 'Education', false),
    (35::smallint, 'Reserved', true),
    (36::smallint, 'Parks, Forests, and Public Property', false),
    (37::smallint, 'Patents, Trademarks, and Copyrights', false),
    (38::smallint, 'Pensions, Bonuses, and Veterans'' Relief', false),
    (39::smallint, 'Postal Service', false),
    (40::smallint, 'Protection of Environment', false),
    (41::smallint, 'Public Contracts and Property Management', false),
    (42::smallint, 'Public Health', false),
    (43::smallint, 'Public Lands: Interior', false),
    (44::smallint, 'Emergency Management and Assistance', false),
    (45::smallint, 'Public Welfare', false),
    (46::smallint, 'Shipping', false),
    (47::smallint, 'Telecommunication', false),
    (48::smallint, 'Federal Acquisition Regulations System', false),
    (49::smallint, 'Transportation', false),
    (50::smallint, 'Wildlife and Fisheries', false)
) as seed(title_number, title_name, reserved)
on conflict (title_number) do update
set
  title_name = excluded.title_name,
  reserved = excluded.reserved,
  source_url = excluded.source_url,
  raw_source = excluded.raw_source,
  synced_at = excluded.synced_at;

-- Persistent cursors make incremental polling recoverable after a failed run.
create table if not exists public.data_sync_state (
  sync_resource text primary key,
  cursor jsonb not null default '{}'::jsonb,
  last_successful_at timestamptz,
  last_attempt_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.data_sync_runs (
  sync_run_id uuid primary key default gen_random_uuid(),
  sync_resource text not null,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null default 'running'
    check (status in ('running', 'succeeded', 'failed', 'partial')),
  records_read integer not null default 0,
  records_written integer not null default 0,
  error_summary text,
  metadata jsonb not null default '{}'::jsonb
);

-- Discovery and processing are separate so a large source delta is never lost
-- merely because one GitHub Actions run reaches its time or storage budget.
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

-- ---------------------------------------------------------------------------
-- Congress
-- ---------------------------------------------------------------------------

create table if not exists public.committees (
  committee_id text primary key,
  congress_number integer,
  committee_code text not null,
  chamber text not null
    check (chamber in ('house', 'senate', 'joint')),
  committee_type text,
  name text not null,
  parent_committee_id text references public.committees(committee_id) on delete set null,
  jurisdiction_summary text,
  counterpart_group text,
  display_order integer,
  official_url text,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists committees_source_identity_uidx
  on public.committees (
    coalesce(congress_number, 0),
    chamber,
    committee_code
  );

create table if not exists public.committee_agency_jurisdictions (
  committee_id text not null references public.committees(committee_id) on delete cascade,
  agency_id text not null references public.agencies(agency_id) on delete cascade,
  relationship_type text not null default 'oversight'
    check (relationship_type in ('oversight', 'authorization', 'appropriations', 'related')),
  mapping_source text not null
    check (mapping_source in ('official', 'verified_manual')),
  source_url text,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  primary key (committee_id, agency_id, relationship_type)
);

create table if not exists public.bills (
  bill_id text primary key,
  congress_number integer not null,
  bill_type text not null,
  bill_number integer not null,
  origin_chamber text
    check (origin_chamber in ('house', 'senate')),
  current_chamber text
    check (current_chamber in ('house', 'senate', 'conference', 'executive')),
  title text not null,
  sponsor text,
  sponsor_bioguide_id text,
  introduced_date date,
  current_status text,
  current_stage text not null default 'introduced'
    check (current_stage in (
      'introduced',
      'referred',
      'subcommittee',
      'committee_consideration',
      'reported',
      'passed_origin_chamber',
      'second_chamber',
      'resolving_differences',
      'passed_both_chambers',
      'presented_to_president',
      'enacted',
      'vetoed',
      'failed',
      'other'
    )),
  status_updated_at timestamptz,
  latest_action_date date,
  latest_action_text text,
  policy_area_id text references public.policy_areas(policy_area_id) on delete set null,
  summary text,
  summary_source text,
  summary_updated_at timestamptz,
  law_type text check (law_type is null or law_type in ('public', 'private')),
  law_number text,
  congress_url text not null,
  source_updated_at timestamptz,
  last_synced_at timestamptz,
  embedding extensions.vector(1536),
  embedding_model text,
  embedded_at timestamptz,
  detail_level text not null default 'index',
  raw_source jsonb not null default '{}'::jsonb,
  storage_tier text not null default 'hot',
  tier_changed_at timestamptz not null default now(),
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint bills_storage_tier_chk
    check (storage_tier in ('hot', 'warm', 'cold')),
  constraint bills_detail_level_chk
    check (detail_level in ('index', 'tracked', 'enriched')),
  unique (congress_number, bill_type, bill_number)
);

create table if not exists public.bill_summaries (
  bill_summary_id bigint generated always as identity primary key,
  bill_id text not null references public.bills(bill_id) on delete cascade,
  action_date date,
  action_description text,
  version_code text,
  summary_text text not null,
  source_updated_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.public_laws (
  public_law_id text primary key,
  congress_number integer not null,
  law_number integer not null,
  law_title text,
  enacted_date date,
  bill_id text unique references public.bills(bill_id) on delete set null,
  congress_url text,
  govinfo_url text,
  source_package_id text,
  statutes_at_large_citation text,
  official_pdf_url text,
  official_text_url text,
  classification_status text not null default 'pending',
  source_updated_at timestamptz,
  last_synced_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint public_laws_classification_status_chk
    check (classification_status in ('pending', 'classified', 'partially_classified', 'not_codified')),
  unique (congress_number, law_number)
);

-- The U.S. Code is a navigational map of current general/permanent law.
-- We store citations and official links, never statutory body text or PDFs.
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

-- Official classification only: one Public Law may affect many Code sections,
-- and some valid laws remain uncodified or appear as statutory notes.
create table if not exists public.public_law_code_impacts (
  public_law_code_impact_id bigint generated always as identity primary key,
  public_law_id text not null references public.public_laws(public_law_id) on delete cascade,
  title_number smallint references public.us_code_titles(title_number) on delete set null,
  us_code_section_id text references public.us_code_sections(us_code_section_id) on delete set null,
  section_citation text,
  impact_type text not null default 'amended',
  classification_status text not null default 'pending',
  source_url text,
  source_method text not null default 'official_metadata',
  created_at timestamptz not null default now(),
  constraint public_law_code_impacts_type_chk
    check (impact_type in ('added', 'amended', 'repealed', 'note', 'uncodified', 'unknown')),
  constraint public_law_code_impacts_classification_chk
    check (classification_status in ('pending', 'classified', 'partially_classified', 'not_codified')),
  constraint public_law_code_impacts_source_method_chk
    check (source_method in ('official_metadata', 'official_classification_table', 'verified_manual'))
);

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
  title_name = excluded.title_name,
  is_reserved = excluded.is_reserved,
  official_url = excluded.official_url,
  raw_source = excluded.raw_source,
  updated_at = now();

create unique index if not exists bill_summaries_source_identity_uidx
  on public.bill_summaries (
    bill_id,
    coalesce(action_date, '-infinity'::date),
    coalesce(version_code, ''),
    md5(summary_text)
  );

-- Link metadata only. No HTML, XML, PDF, or plain-text body is downloaded.
create table if not exists public.bill_text_versions (
  bill_text_version_id bigint generated always as identity primary key,
  bill_id text not null references public.bills(bill_id) on delete cascade,
  version_code text,
  version_name text,
  issued_on date,
  html_url text,
  pdf_url text,
  xml_url text,
  formatted_text_url text,
  source_url text,
  fetched_at timestamptz not null default now(),
  raw_source jsonb not null default '{}'::jsonb,
  check (num_nonnulls(html_url, pdf_url, xml_url, formatted_text_url, source_url) >= 1)
);

create unique index if not exists bill_text_versions_source_identity_uidx
  on public.bill_text_versions (
    bill_id,
    coalesce(version_code, ''),
    coalesce(issued_on, '-infinity'::date)
  );

create table if not exists public.bill_subjects (
  bill_id text not null references public.bills(bill_id) on delete cascade,
  subject_id text not null references public.legislative_subjects(subject_id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (bill_id, subject_id)
);

create table if not exists public.bill_committees (
  bill_id text not null references public.bills(bill_id) on delete cascade,
  committee_id text not null references public.committees(committee_id) on delete cascade,
  activity_names text[] not null default '{}'::text[],
  first_referred_at timestamptz,
  last_activity_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (bill_id, committee_id)
);

create table if not exists public.bill_actions (
  bill_action_id text primary key,
  bill_id text not null references public.bills(bill_id) on delete cascade,
  action_date timestamptz not null,
  action_code text,
  action_type text,
  chamber text check (chamber is null or chamber in ('house', 'senate', 'joint', 'executive')),
  committee_id text references public.committees(committee_id) on delete set null,
  action_text text not null,
  normalized_stage text
    check (normalized_stage is null or normalized_stage in (
      'introduced',
      'referred',
      'subcommittee',
      'committee_consideration',
      'reported',
      'passed_origin_chamber',
      'second_chamber',
      'resolving_differences',
      'passed_both_chambers',
      'presented_to_president',
      'enacted',
      'vetoed',
      'failed',
      'other'
    )),
  source_url text,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.bill_status_history (
  bill_status_history_id bigint generated always as identity primary key,
  bill_id text not null references public.bills(bill_id) on delete cascade,
  status text not null,
  normalized_stage text,
  changed_at timestamptz not null,
  source_action_id text references public.bill_actions(bill_action_id) on delete set null,
  detected_at timestamptz not null default now()
);

create unique index if not exists bill_status_history_event_uidx
  on public.bill_status_history (
    bill_id,
    status,
    changed_at
  );

create table if not exists public.bill_votes (
  vote_id text primary key,
  bill_id text not null references public.bills(bill_id) on delete cascade,
  chamber text not null check (chamber in ('house', 'senate')),
  congress_number integer not null,
  session_number integer,
  roll_number integer,
  vote_date timestamptz not null,
  question text,
  result text,
  yea_count integer check (yea_count is null or yea_count >= 0),
  nay_count integer check (nay_count is null or nay_count >= 0),
  present_count integer check (present_count is null or present_count >= 0),
  not_voting_count integer check (not_voting_count is null or not_voting_count >= 0),
  vote_method text,
  source_url text not null,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists bill_votes_roll_uidx
  on public.bill_votes (
    congress_number,
    chamber,
    coalesce(session_number, 0),
    coalesce(roll_number, 0),
    vote_date
  );

create table if not exists public.bill_vote_members (
  vote_id text not null references public.bill_votes(vote_id) on delete cascade,
  bioguide_id text not null,
  member_name text not null,
  party text,
  state text,
  vote_position text not null,
  created_at timestamptz not null default now(),
  primary key (vote_id, bioguide_id)
);

create table if not exists public.bill_relations (
  bill_relation_id bigint generated always as identity primary key,
  source_bill_id text not null references public.bills(bill_id) on delete cascade,
  target_bill_id text references public.bills(bill_id) on delete cascade,
  target_congress_number integer,
  target_bill_type text,
  target_bill_number integer,
  relation_type text not null,
  relation_origin text not null
    check (relation_origin in ('official', 'semantic', 'verified_manual')),
  identified_by text,
  similarity_score double precision
    check (similarity_score is null or similarity_score between 0 and 1),
  source_url text,
  created_at timestamptz not null default now(),
  check (
    target_bill_id is not null
    or num_nonnulls(target_congress_number, target_bill_type, target_bill_number) = 3
  ),
  check (
    (relation_origin = 'semantic' and similarity_score is not null)
    or (relation_origin <> 'semantic' and similarity_score is null)
  ),
  check (target_bill_id is null or target_bill_id <> source_bill_id)
);

create unique index if not exists bill_relations_identity_uidx
  on public.bill_relations (
    source_bill_id,
    coalesce(target_bill_id, ''),
    coalesce(target_congress_number, 0),
    coalesce(target_bill_type, ''),
    coalesce(target_bill_number, 0),
    relation_type,
    relation_origin
  );

-- ---------------------------------------------------------------------------
-- Executive branch / Federal Register
-- ---------------------------------------------------------------------------

create table if not exists public.executive_orders (
  eo_number integer primary key,
  document_number text not null unique,
  title text not null,
  president_name text,
  signed_date date,
  publication_date date,
  citation text,
  federal_register_url text not null,
  pdf_url text,
  executive_order_url text,
  summary text,
  summary_source text,
  embedding extensions.vector(1536),
  embedding_model text,
  embedded_at timestamptz,
  source_updated_at timestamptz,
  last_synced_at timestamptz,
  storage_tier text not null default 'hot',
  tier_changed_at timestamptz not null default now(),
  archived_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint executive_orders_storage_tier_chk
    check (storage_tier in ('hot', 'warm', 'cold'))
);

create table if not exists public.executive_order_agencies (
  eo_number integer not null references public.executive_orders(eo_number) on delete cascade,
  agency_id text not null references public.agencies(agency_id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (eo_number, agency_id)
);

create table if not exists public.legal_authorities (
  legal_authority_id bigint generated always as identity primary key,
  authority_type text not null
    check (authority_type in (
      'constitution',
      'usc',
      'public_law',
      'statutes_at_large',
      'executive_order',
      'regulation',
      'other'
    )),
  citation text not null,
  title text,
  official_url text,
  linked_bill_id text references public.bills(bill_id) on delete set null,
  verification_status text not null default 'verified'
    check (verification_status in ('verified', 'unverified')),
  extraction_method text not null
    check (extraction_method in ('official_metadata', 'verified_manual')),
  verified_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index if not exists legal_authorities_identity_uidx
  on public.legal_authorities (
    authority_type,
    citation,
    coalesce(official_url, '')
  );

create table if not exists public.executive_order_authorities (
  eo_number integer not null references public.executive_orders(eo_number) on delete cascade,
  legal_authority_id bigint not null references public.legal_authorities(legal_authority_id) on delete cascade,
  source_url text,
  created_at timestamptz not null default now(),
  primary key (eo_number, legal_authority_id)
);

create table if not exists public.regulations (
  regulation_id text primary key,
  document_number text not null unique,
  document_type text not null
    check (document_type in ('RULE', 'PRORULE', 'NOTICE', 'OTHER')),
  title text not null,
  abstract text,
  action_text text,
  publication_date date,
  effective_on date,
  comments_close_on date,
  federal_register_url text not null,
  pdf_url text,
  docket_ids text[] not null default '{}'::text[],
  rin text,
  citation text,
  embedding extensions.vector(1536),
  embedding_model text,
  embedded_at timestamptz,
  source_updated_at timestamptz,
  last_synced_at timestamptz,
  storage_tier text not null default 'hot',
  tier_changed_at timestamptz not null default now(),
  archived_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint regulations_storage_tier_chk
    check (storage_tier in ('hot', 'warm', 'cold'))
);

create table if not exists public.regulation_agencies (
  regulation_id text not null references public.regulations(regulation_id) on delete cascade,
  agency_id text not null references public.agencies(agency_id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (regulation_id, agency_id)
);

create table if not exists public.regulation_cfr_references (
  regulation_cfr_reference_id bigint generated always as identity primary key,
  regulation_id text not null references public.regulations(regulation_id) on delete cascade,
  title_number smallint not null references public.cfr_titles(title_number) on delete cascade,
  part_number text,
  created_at timestamptz not null default now()
);

create unique index if not exists regulation_cfr_references_identity_uidx
  on public.regulation_cfr_references (
    regulation_id,
    title_number,
    coalesce(part_number, '')
  );

create table if not exists public.executive_order_regulations (
  eo_number integer not null references public.executive_orders(eo_number) on delete cascade,
  regulation_id text not null references public.regulations(regulation_id) on delete cascade,
  relation_type text not null,
  relation_origin text not null
    check (relation_origin in ('official_citation', 'semantic', 'verified_manual')),
  similarity_score double precision
    check (similarity_score is null or similarity_score between 0 and 1),
  source_url text,
  created_at timestamptz not null default now(),
  primary key (eo_number, regulation_id, relation_type, relation_origin),
  check (
    (relation_origin = 'semantic' and similarity_score is not null)
    or (relation_origin <> 'semantic' and similarity_score is null)
  )
);

-- ---------------------------------------------------------------------------
-- Phase 2-2 placeholders and notifications
-- ---------------------------------------------------------------------------

create table if not exists public.reports (
  report_id text primary key,
  agency_id text references public.agencies(agency_id) on delete set null,
  agency text not null,
  title text not null,
  url text not null,
  published_date date,
  keywords text[] not null default '{}'::text[],
  summary text,
  embedding extensions.vector(1536),
  embedding_model text,
  embedded_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
  subscription_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  keyword text,
  category_type text
    check (category_type is null or category_type in (
      'policy_area',
      'legislative_subject',
      'committee',
      'agency',
      'cfr_title'
    )),
  category_id text,
  filter_config jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (keyword is not null or (category_type is not null and category_id is not null))
);

create table if not exists public.notifications_queued (
  notification_id bigint generated always as identity primary key,
  subscription_id uuid not null references public.subscriptions(subscription_id) on delete cascade,
  bill_id text references public.bills(bill_id) on delete cascade,
  eo_number integer references public.executive_orders(eo_number) on delete cascade,
  regulation_id text references public.regulations(regulation_id) on delete cascade,
  report_id text references public.reports(report_id) on delete cascade,
  created_at timestamptz not null default now(),
  sent boolean not null default false,
  sent_at timestamptz,
  error_message text,
  check (num_nonnulls(bill_id, eo_number, regulation_id, report_id) = 1),
  check ((sent = false and sent_at is null) or sent = true)
);

create unique index if not exists notifications_queued_bill_uidx
  on public.notifications_queued (subscription_id, bill_id)
  where bill_id is not null;

create unique index if not exists notifications_queued_eo_uidx
  on public.notifications_queued (subscription_id, eo_number)
  where eo_number is not null;

create unique index if not exists notifications_queued_regulation_uidx
  on public.notifications_queued (subscription_id, regulation_id)
  where regulation_id is not null;

create unique index if not exists notifications_queued_report_uidx
  on public.notifications_queued (subscription_id, report_id)
  where report_id is not null;

-- ---------------------------------------------------------------------------
-- Operational indexes
-- ---------------------------------------------------------------------------

create index if not exists bills_stage_date_idx
  on public.bills (current_stage, latest_action_date desc);
create index if not exists bills_policy_area_date_idx
  on public.bills (policy_area_id, latest_action_date desc);
create index if not exists bills_source_updated_idx
  on public.bills (source_updated_at desc);
create index if not exists public_laws_enacted_date_idx
  on public.public_laws (enacted_date desc);
create index if not exists public_laws_classification_idx
  on public.public_laws (classification_status, enacted_date desc);
create unique index if not exists public_law_code_impacts_identity_uidx
  on public.public_law_code_impacts (
    public_law_id,
    coalesce(title_number, 0),
    coalesce(us_code_section_id, ''),
    coalesce(section_citation, ''),
    impact_type
  );
create index if not exists us_code_sections_title_idx
  on public.us_code_sections (title_number, section_number);
create index if not exists policy_ingestion_queue_ready_idx
  on public.policy_ingestion_queue (sync_resource, status, priority desc, available_at, created_at);
create index if not exists data_sync_runs_resource_started_idx
  on public.data_sync_runs (sync_resource, started_at desc);
create index if not exists bills_storage_tier_idx
  on public.bills (storage_tier, tier_changed_at);
create index if not exists bills_tier_sync_idx
  on public.bills (storage_tier, last_synced_at);
create index if not exists bill_actions_bill_date_idx
  on public.bill_actions (bill_id, action_date desc);
create index if not exists bill_committees_committee_idx
  on public.bill_committees (committee_id, last_activity_at desc);
create index if not exists bill_subjects_subject_idx
  on public.bill_subjects (subject_id, bill_id);
create index if not exists bill_votes_bill_date_idx
  on public.bill_votes (bill_id, vote_date desc);
create index if not exists bill_relations_source_origin_idx
  on public.bill_relations (source_bill_id, relation_origin);
create index if not exists executive_orders_date_idx
  on public.executive_orders (signed_date desc);
create index if not exists executive_orders_storage_tier_idx
  on public.executive_orders (storage_tier, tier_changed_at);
create index if not exists executive_orders_tier_sync_idx
  on public.executive_orders (storage_tier, last_synced_at);
create index if not exists executive_order_agencies_agency_idx
  on public.executive_order_agencies (agency_id, eo_number);
create index if not exists regulations_date_idx
  on public.regulations (publication_date desc);
create index if not exists regulations_storage_tier_idx
  on public.regulations (storage_tier, tier_changed_at);
create index if not exists regulations_tier_sync_idx
  on public.regulations (storage_tier, last_synced_at);
create index if not exists regulation_agencies_agency_idx
  on public.regulation_agencies (agency_id, regulation_id);
create index if not exists regulation_cfr_title_idx
  on public.regulation_cfr_references (title_number, regulation_id);
create index if not exists notifications_unsent_idx
  on public.notifications_queued (created_at)
  where sent = false;

-- HNSW is appropriate for the expected low-to-mid six-figure corpus because it
-- supports good recall without an IVFFLAT training step. Revisit memory/build
-- cost when the corpus grows into the multi-million-vector range.
create index if not exists bills_embedding_hnsw_idx
  on public.bills using hnsw (embedding vector_cosine_ops)
  where embedding is not null;
create index if not exists executive_orders_embedding_hnsw_idx
  on public.executive_orders using hnsw (embedding vector_cosine_ops)
  where embedding is not null;
create index if not exists regulations_embedding_hnsw_idx
  on public.regulations using hnsw (embedding vector_cosine_ops)
  where embedding is not null;
create index if not exists reports_embedding_hnsw_idx
  on public.reports using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

-- Lifecycle tier is a sync/retention policy, not a claim that source full text
-- is stored locally. The sync job calls this after each successful run.
create or replace function public.refresh_policy_lifecycle_tiers(
  active_congress_number integer,
  reference_date date default current_date
)
returns void
language plpgsql
set search_path = public
as $$
begin
  with desired as (
    select
      bill_id,
      case
        when current_stage not in ('enacted', 'vetoed', 'failed')
          or coalesce(latest_action_date, introduced_date) >= reference_date - 30
          then 'hot'
        when congress_number >= active_congress_number - 3
          then 'warm'
        else 'cold'
      end as next_tier
    from public.bills
  )
  update public.bills b
  set
    storage_tier = d.next_tier,
    tier_changed_at = now()
  from desired d
  where b.bill_id = d.bill_id
    and b.storage_tier is distinct from d.next_tier;

  with desired as (
    select
      eo_number,
      case
        when coalesce(source_updated_at::date, publication_date, signed_date)
          >= reference_date - 30 then 'hot'
        when coalesce(source_updated_at::date, publication_date, signed_date)
          >= reference_date - interval '8 years' then 'warm'
        else 'cold'
      end as next_tier
    from public.executive_orders
  )
  update public.executive_orders eo
  set
    storage_tier = d.next_tier,
    tier_changed_at = now()
  from desired d
  where eo.eo_number = d.eo_number
    and eo.storage_tier is distinct from d.next_tier;

  with desired as (
    select
      regulation_id,
      case
        when coalesce(source_updated_at::date, publication_date, effective_on)
          >= reference_date - 30 then 'hot'
        when coalesce(source_updated_at::date, publication_date, effective_on)
          >= reference_date - interval '8 years' then 'warm'
        else 'cold'
      end as next_tier
    from public.regulations
  )
  update public.regulations r
  set
    storage_tier = d.next_tier,
    tier_changed_at = now()
  from desired d
  where r.regulation_id = d.regulation_id
    and r.storage_tier is distinct from d.next_tier;
end;
$$;

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'agencies',
    'policy_areas',
    'legislative_subjects',
    'committees',
    'bills',
    'public_laws',
    'us_code_titles',
    'us_code_sections',
    'policy_ingestion_queue',
    'bill_committees',
    'bill_votes',
    'executive_orders',
    'regulations',
    'reports',
    'subscriptions',
    'data_sync_state'
  ]
  loop
    execute format('drop trigger if exists set_updated_at on public.%I', table_name);
    execute format(
      'create trigger set_updated_at before update on public.%I for each row execute function public.set_updated_at()',
      table_name
    );
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- Security
-- ---------------------------------------------------------------------------

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'agencies',
    'policy_areas',
    'legislative_subjects',
    'cfr_titles',
    'data_sync_state',
    'data_sync_runs',
    'policy_ingestion_queue',
    'committees',
    'committee_agency_jurisdictions',
    'bills',
    'public_laws',
    'us_code_titles',
    'us_code_sections',
    'public_law_code_impacts',
    'bill_summaries',
    'bill_text_versions',
    'bill_subjects',
    'bill_committees',
    'bill_actions',
    'bill_status_history',
    'bill_votes',
    'bill_vote_members',
    'bill_relations',
    'executive_orders',
    'executive_order_agencies',
    'legal_authorities',
    'executive_order_authorities',
    'regulations',
    'regulation_agencies',
    'regulation_cfr_references',
    'executive_order_regulations',
    'reports',
    'subscriptions',
    'notifications_queued'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
  end loop;
end;
$$;

commit;
