-- Phase 2-1: United States federal policy data
-- Sources: Congress.gov API, Federal Register API
-- PostgreSQL 17 / Supabase / pgvector
-- Canonical POLICY fresh-install schema. Run once after resetting the policy DB;
-- do not replay older policy migrations on top of it.
-- Auth/favorites/mailing are separate application modules: this file does NOT
-- install profiles or user_favorites. After their 20260904 migrations, install
-- supabase/migrations/20260911010000_mailing_outbox.sql, then its lifecycle and
-- 20261002 event/subscription migrations in order (see mailing README).
-- See services/mailing/README.md for the existing-production cutover order.
--
-- Design rules:
--   * Normalize fields required for filtering, navigation, and relationships.
--   * Preserve selected source payloads in JSONB for traceability.
--   * Base policy tables store official links. The search sidecar stores bounded, source-attributed text.
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
  agency_type text check (agency_type in ('eop', 'department', 'independent', 'sub')),
  agency_url text,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists agencies_federal_register_id_uidx
  on public.agencies (federal_register_id)
  where federal_register_id is not null;

create index if not exists agencies_type_parent_name_idx
  on public.agencies (agency_type, parent_agency_id, name);

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

create table if not exists public.us_legislators (
  bioguide_id text primary key,
  full_name text not null,
  party text,
  party_abbr text,
  state text,
  district integer,
  chamber text not null check (chamber in ('house', 'senate')),
  current_member boolean not null default true,
  source_name text not null,
  source_updated_at timestamptz,
  roster_seen_at timestamptz not null default now(),
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists us_legislators_chamber_party_idx
  on public.us_legislators (chamber, party_abbr, state);

create table if not exists public.committee_members (
  committee_id text not null references public.committees(committee_id) on delete cascade,
  bioguide_id text not null references public.us_legislators(bioguide_id) on delete cascade,
  role text not null default 'member'
    check (role in ('member', 'chair', 'vice_chair', 'ranking_member', 'ex_officio')),
  congress_number integer not null,
  source_url text not null,
  source_name text not null default 'legacy',
  source_updated_at timestamptz,
  current boolean not null default true,
  membership_seen_at timestamptz not null default now(),
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (committee_id, bioguide_id, role, congress_number)
);

create index if not exists committee_members_leadership_idx
  on public.committee_members (committee_id, congress_number, role);
create index if not exists committee_members_current_role_idx
  on public.committee_members (congress_number, current, role, committee_id);

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
  relationship_type text not null
    check (relationship_type in (
      'issuing_document',
      'implementing_regulation',
      'directed_agency',
      'coordinating_agency',
      'consulted_agency'
    )),
  relation_origin text not null
    check (relation_origin in ('official_document_metadata', 'official_citation', 'official_text_citation')),
  source_url text,
  evidence_excerpt text,
  evidence_section text,
  created_at timestamptz not null default now(),
  primary key (eo_number, agency_id, relationship_type, relation_origin)
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
    check (extraction_method in ('official_metadata', 'official_text_citation', 'verified_manual')),
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
      'cfr_title',
      'bill',
      'executive_order'
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
create index if not exists executive_order_agencies_role_idx
  on public.executive_order_agencies (eo_number, relationship_type, agency_id);
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

-- Semantic relations are directional. Each newly embedded bill gets up to five
-- same-model neighbours; the function replaces only its prior semantic rows.
-- Official and verified-manual bill relations are never changed here.
create or replace function public.refresh_bill_semantic_relations(
  p_source_bill_id text,
  p_source_embedding extensions.vector(1536),
  p_embedding_model text,
  p_similarity_threshold double precision default 0.80,
  p_result_limit integer default 5
)
returns integer
language plpgsql
set search_path = public, extensions
as $$
declare
  inserted_count integer;
begin
  if p_source_bill_id is null or p_source_embedding is null or nullif(trim(p_embedding_model), '') is null then
    raise exception 'source bill, embedding, and embedding model are required';
  end if;
  if p_similarity_threshold < 0 or p_similarity_threshold > 1 then
    raise exception 'similarity threshold must be between 0 and 1';
  end if;

  delete from public.bill_relations
  where source_bill_id = p_source_bill_id
    and relation_origin = 'semantic';

  with nearest as (
    select
      candidate.bill_id as target_bill_id,
      1 - (candidate.embedding <=> p_source_embedding) as similarity_score
    from public.bills candidate
    where candidate.bill_id <> p_source_bill_id
      and candidate.embedding is not null
      and candidate.embedding_model = p_embedding_model
    order by candidate.embedding <=> p_source_embedding
    limit least(greatest(p_result_limit, 1), 5)
  )
  insert into public.bill_relations (
    source_bill_id,
    target_bill_id,
    relation_type,
    relation_origin,
    identified_by,
    similarity_score
  )
  select
    p_source_bill_id,
    nearest.target_bill_id,
    'semantic_similarity',
    'semantic',
    p_embedding_model || ' cosine',
    nearest.similarity_score
  from nearest
  where nearest.similarity_score >= p_similarity_threshold;

  get diagnostics inserted_count = row_count;
  return inserted_count;
end;
$$;

-- Terminal bill retention is explicit rather than trigger-driven. The sync
-- worker calls this only after it has matched subscriptions for a terminal
-- status, so a title/summary is still available to notification matching.
create or replace function public.prune_terminal_bill_details(
  p_bill_id text
)
returns table (outcome text, detail_rows_removed integer)
language plpgsql
set search_path = public
as $$
declare
  target_stage text;
  removed integer := 0;
  changed integer := 0;
begin
  select current_stage into target_stage
  from public.bills
  where bill_id = p_bill_id
  for update;

  if not found then return query select 'not_found'::text, 0; return; end if;
  if target_stage not in ('failed', 'vetoed') then return query select 'not_terminal'::text, 0; return; end if;
  -- Preserve a bill if a Public Law already links to it, even when its stage
  -- was accidentally classified as terminal.
  if exists (select 1 from public.public_laws where bill_id = p_bill_id) then
    return query select 'protected_public_law'::text, 0;
    return;
  end if;

  delete from public.bill_vote_members where vote_id in (select vote_id from public.bill_votes where bill_id = p_bill_id);
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_votes where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_summaries where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_text_versions where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_actions where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_status_history where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_committees where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_subjects where bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;
  delete from public.bill_relations where source_bill_id = p_bill_id or target_bill_id = p_bill_id;
  get diagnostics changed = row_count; removed := removed + changed;

  update public.bills
  set
    detail_level = 'index', storage_tier = 'cold', tier_changed_at = now(),
    summary = null, summary_source = null, summary_updated_at = null,
    embedding = null, embedding_model = null, embedded_at = null,
    policy_area_id = null, sponsor_bioguide_id = null, introduced_date = null,
    latest_action_text = null, law_type = null, law_number = null,
    raw_source = jsonb_build_object(
      'source', coalesce(raw_source ->> 'source', 'congress.gov'),
      'retention', 'terminal_minimal', 'pruned_at', now()
    )
  where bill_id = p_bill_id;

  return query select 'pruned'::text, removed;
end;
$$;

-- A read-only inspection function. It is the required first step before any
-- rollover deletion and also excludes bills that have a Public Law link.
create or replace function public.preview_congress_rollover_purge(
  p_previous_congress integer,
  p_result_limit integer default 100
)
returns table (bill_id text, title text, current_stage text, latest_action_date date, total_candidate_count integer)
language sql
stable
set search_path = public
as $$
  select bill.bill_id, bill.title, bill.current_stage, bill.latest_action_date,
    count(*) over ()::integer as total_candidate_count
  from public.bills bill
  where bill.congress_number = p_previous_congress
    and bill.current_stage <> 'enacted'
    and not exists (select 1 from public.public_laws public_law where public_law.bill_id = bill.bill_id)
  order by bill.latest_action_date desc nulls last, bill.bill_id
  limit least(greatest(coalesce(p_result_limit, 100), 1), 1000);
$$;

-- Actual rollover removal has an explicit confirmation argument. The local
-- runner requires ALLOW_CONGRESS_ROLLOVER_PURGE=true before it can pass this.
create or replace function public.purge_congress_rollover(
  p_previous_congress integer,
  p_max_bills integer default 1000,
  p_confirm boolean default false
)
returns table (deleted_bill_count integer, deleted_queue_count integer)
language plpgsql
set search_path = public
as $$
declare
  target_bill_ids text[];
  target_count integer;
  queue_count integer := 0;
  bill_count integer := 0;
begin
  if not p_confirm then raise exception 'rollover purge requires p_confirm = true; run preview_congress_rollover_purge first'; end if;
  if p_previous_congress is null or p_previous_congress < 1 then raise exception 'a valid previous Congress number is required'; end if;
  if p_max_bills is null or p_max_bills < 1 or p_max_bills > 10000 then raise exception 'p_max_bills must be between 1 and 10000'; end if;

  select coalesce(array_agg(candidate.bill_id order by candidate.bill_id), '{}'::text[])
  into target_bill_ids
  from (
    select bill.bill_id
    from public.bills bill
    where bill.congress_number = p_previous_congress
      and bill.current_stage <> 'enacted'
      and not exists (select 1 from public.public_laws public_law where public_law.bill_id = bill.bill_id)
    order by bill.bill_id
    limit p_max_bills + 1
  ) candidate;
  target_count := cardinality(target_bill_ids);
  if target_count > p_max_bills then raise exception 'rollover candidate count % exceeds the approved maximum %', target_count, p_max_bills; end if;
  if target_count = 0 then return query select 0, 0; return; end if;

  delete from public.policy_ingestion_queue
  where sync_resource = 'congress.gov:bills'
    and source_key = any(target_bill_ids)
    and exists (
      select 1 from public.bills bill
      where bill.bill_id = policy_ingestion_queue.source_key
        and bill.congress_number = p_previous_congress
        and bill.current_stage <> 'enacted'
        and not exists (select 1 from public.public_laws public_law where public_law.bill_id = bill.bill_id)
    );
  get diagnostics queue_count = row_count;

  -- Re-check against a concurrently-created Public Law relation immediately
  -- before deleting the bill itself.
  delete from public.bills bill
  where bill.bill_id = any(target_bill_ids)
    and bill.congress_number = p_previous_congress
    and bill.current_stage <> 'enacted'
    and not exists (select 1 from public.public_laws public_law where public_law.bill_id = bill.bill_id);
  get diagnostics bill_count = row_count;
  return query select bill_count, queue_count;
end;
$$;

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

-- 완전한 공식 위원회 스냅샷은 자신이 포함한 역할 범위의 행만 비활성화할 수
-- 있다. 적재기는 원본을 검증하고 모든 입력 행을 쓴 뒤에 이 함수를 호출한다.
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
    'us_legislators',
    'committee_members',
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
    'us_legislators',
    'committee_members',
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

-- Verified committee hierarchy preservation (20260921).
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

-- Canonical committee read models; original identities are retained.
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

-- Complete official CRS policy-area dictionary.
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


-- Search sidecar (matches 20261005010000_policy_search_documents.sql).
-- Independent search snapshots: never mutate bill lifecycle or send mail.
begin;
set local lock_timeout='2s';
create table if not exists public.policy_search_documents (
  document_id text primary key,
  source_type text not null check (source_type in ('bill','public_law','executive_order','regulation')),
  source_id text not null,
  title text not null,
  document_date date,
  source_url text not null,
  search_text text not null,
  search_vector tsvector generated always as (to_tsvector('simple'::regconfig,search_text)) stored,
  evidence_parts jsonb not null default '[]',
  references_json jsonb not null default '[]',
  coverage jsonb not null default '{}',
  input_hash text not null,
  refreshed_at timestamptz not null default now(),
  unique(source_type,source_id)
);
create index if not exists policy_search_documents_text_idx on public.policy_search_documents using gin(search_vector);
create table if not exists public.policy_search_passages (
  document_id text not null references public.policy_search_documents on delete cascade,
  passage_index integer not null check (passage_index between 0 and 23),
  field text not null,
  text_content text not null,
  source_url text not null,
  target_type text, target_id text,
  input_hash text not null,
  embedding extensions.vector(1536),
  embedding_model text,
  embedded_at timestamptz,
  primary key(document_id,passage_index)
);
create index if not exists policy_search_passages_embedding_idx on public.policy_search_passages
  using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null;
create table if not exists public.policy_search_jobs (
  document_id text primary key,
  source_type text not null, source_id text not null,
  revision bigint not null default 1, claimed_revision bigint,
  status text not null default 'queued' check (status in ('queued','processing','done','failed')),
  claim_token uuid, lease_until timestamptz,
  attempts integer not null default 0,
  retry_at timestamptz not null default now(), last_error text,
  priority integer not null default 0,
  updated_at timestamptz not null default now()
);
alter table public.policy_search_jobs add column if not exists priority integer not null default 0;
create index if not exists policy_search_jobs_pending_idx on public.policy_search_jobs(status,retry_at,updated_at);

create or replace function public.enqueue_policy_search_document(p_type text,p_id text) returns void
language sql security definer set search_path=public,extensions as $$
  insert into policy_search_jobs(document_id,source_type,source_id,priority) values(p_type||':'||p_id,p_type,p_id,20)
  on conflict(document_id) do update set revision=policy_search_jobs.revision+1,
    status=case when policy_search_jobs.status='processing' then 'processing' else 'queued' end,
    attempts=case when policy_search_jobs.status='processing' then policy_search_jobs.attempts else 0 end,
    priority=20,retry_at=now(), updated_at=now(),last_error=null;
$$;
-- Idempotent historical backfill: live changes outrank newest-session bootstrap.
create or replace function public.seed_policy_search_jobs(p_limit int default 1000) returns integer
language plpgsql security definer set search_path=public,extensions as $$
declare inserted integer;
begin
  with active as (select max(congress_number) n from bills), sources as (
    select 'bill' kind,bill_id id,latest_action_date dated,case when congress_number=(select n from active) then 10 else 0 end priority from bills
    union all select 'public_law',public_law_id,enacted_date,case when congress_number=(select n from active) then 10 else 0 end from public_laws
    union all select 'executive_order',eo_number::text,coalesce(signed_date,publication_date),case when coalesce(signed_date,publication_date)>=current_date-interval '2 years' then 10 else 0 end from executive_orders
    union all select 'regulation',regulation_id,publication_date,10 from regulations
  ) insert into policy_search_jobs(document_id,source_type,source_id,priority)
    select kind||':'||id,kind,id,priority from sources s
    where not exists(select 1 from policy_search_jobs j where j.document_id=s.kind||':'||s.id)
    order by priority desc,dated desc nulls last,kind,id limit least(greatest(p_limit,1),1000)
    on conflict(document_id) do nothing;
  get diagnostics inserted=row_count;
  return inserted;
end; $$;
create or replace function public.policy_search_source_changed() returns trigger
language plpgsql security definer set search_path=public,extensions as $$
declare src text:=tg_argv[0]; ident text; r record;
begin
  if tg_op='UPDATE' and
    (to_jsonb(new)->'title',to_jsonb(new)->'law_title',to_jsonb(new)->'summary',to_jsonb(new)->'abstract',to_jsonb(new)->'official_text_url',to_jsonb(new)->'source_updated_at',to_jsonb(new)->'bill_id',to_jsonb(new)->'latest_action_date',to_jsonb(new)->'enacted_date',to_jsonb(new)->'signed_date',to_jsonb(new)->'publication_date')
    is not distinct from
    (to_jsonb(old)->'title',to_jsonb(old)->'law_title',to_jsonb(old)->'summary',to_jsonb(old)->'abstract',to_jsonb(old)->'official_text_url',to_jsonb(old)->'source_updated_at',to_jsonb(old)->'bill_id',to_jsonb(old)->'latest_action_date',to_jsonb(old)->'enacted_date',to_jsonb(old)->'signed_date',to_jsonb(old)->'publication_date') then return new; end if;
  ident:=coalesce(to_jsonb(new),to_jsonb(old))->>tg_argv[1];
  if tg_op='DELETE' then
    delete from policy_search_documents where document_id=src||':'||ident;
    delete from policy_search_jobs where document_id=src||':'||ident;
  else
    perform enqueue_policy_search_document(src,ident);
  end if;
  -- A public law may carry the official summary of its originating bill.
  if src='bill' then
    for r in select public_law_id from public_laws where bill_id=ident
    loop perform enqueue_policy_search_document('public_law',r.public_law_id); end loop;
  end if;
  -- One-hop dependencies only; a cited document changing refreshes its citers.
  for r in select distinct d.source_type,d.source_id from policy_search_documents d,
    jsonb_array_elements(d.references_json) ref
    where ref->>'target_type'=src and ref->>'target_id'=ident
  loop perform enqueue_policy_search_document(r.source_type,r.source_id); end loop;
  return coalesce(new,old);
end; $$;
drop trigger if exists policy_search_bill_changed on public.bills;
create trigger policy_search_bill_changed after insert or delete or update of title,summary,source_updated_at,latest_action_date
  on public.bills for each row execute function public.policy_search_source_changed('bill','bill_id');
drop trigger if exists policy_search_eo_changed on public.executive_orders;
create trigger policy_search_eo_changed after insert or delete or update of title,summary,source_updated_at,signed_date,publication_date
  on public.executive_orders for each row execute function public.policy_search_source_changed('executive_order','eo_number');
drop trigger if exists policy_search_law_changed on public.public_laws;
create trigger policy_search_law_changed after insert or delete or update of law_title,official_text_url,source_updated_at,bill_id,enacted_date
  on public.public_laws for each row execute function public.policy_search_source_changed('public_law','public_law_id');
drop trigger if exists policy_search_reg_changed on public.regulations;
create trigger policy_search_reg_changed after insert or delete or update of title,abstract,source_updated_at,publication_date
  on public.regulations for each row execute function public.policy_search_source_changed('regulation','regulation_id');
create or replace function public.policy_search_bill_detail_changed() returns trigger
language plpgsql security definer set search_path=public,extensions as $$
begin
  perform enqueue_policy_search_document('bill',coalesce(to_jsonb(new),to_jsonb(old))->>'bill_id');
  if tg_op='UPDATE' and old.bill_id is distinct from new.bill_id then
    perform enqueue_policy_search_document('bill',old.bill_id);
  end if;
  return coalesce(new,old);
end; $$;
drop trigger if exists policy_search_bill_text_changed on public.bill_text_versions;
create trigger policy_search_bill_text_changed after insert or delete or update
  on public.bill_text_versions for each row execute function public.policy_search_bill_detail_changed();
drop trigger if exists policy_search_bill_subject_changed on public.bill_subjects;
create trigger policy_search_bill_subject_changed after insert or delete or update
  on public.bill_subjects for each row execute function public.policy_search_bill_detail_changed();

create or replace function public.claim_policy_search_job() returns setof public.policy_search_jobs
language sql security definer set search_path=public,extensions as $$
  update policy_search_jobs j set status='processing',claim_token=gen_random_uuid(),
    lease_until=now()+interval '15 minutes',claimed_revision=revision,attempts=attempts+1
  where j.document_id=(select document_id from policy_search_jobs
    where (status in ('queued','failed') and retry_at<=now() and attempts<8)
       or (status='processing' and lease_until<now())
    order by priority desc,updated_at,document_id for update skip locked limit 1)
  returning j.*;
$$;
create or replace function public.finish_policy_search_job(p_id text,p_token uuid,p_error text default null) returns boolean
language plpgsql security definer set search_path=public,extensions as $$
begin
  update policy_search_jobs set status=case when revision<>claimed_revision then 'queued'
    when p_error is null then 'done' else 'failed' end,
    last_error=left(p_error,240),retry_at=now()+case when revision<>claimed_revision or p_error is null then interval '0'
      else interval '5 minutes'*least(attempts,12) end,claim_token=null,lease_until=null,
    attempts=case when revision<>claimed_revision or p_error is null then 0 else attempts end
    where document_id=p_id and claim_token=p_token;
  return found;
end; $$;

create or replace function public.save_policy_search_document(p_document jsonb,p_passages jsonb,p_token uuid)
returns boolean language plpgsql security definer set search_path=public,extensions as $$
declare ident text:=p_document->>'document_id'; item jsonb; job policy_search_jobs;
begin
  select * into job from policy_search_jobs where document_id=ident for update;
  if not found or p_token is null or job.claim_token is distinct from p_token or job.status<>'processing' or job.lease_until<now() then
    raise exception 'search job lease is no longer owned';
  end if;
  if job.revision<>job.claimed_revision then return false; end if;
  if ident<>job.source_type||':'||job.source_id or p_document->>'source_type'<>job.source_type
    or p_document->>'source_id'<>job.source_id then raise exception 'search document identity mismatch'; end if;
  if jsonb_array_length(p_passages)>24 then raise exception 'passage cap exceeded'; end if;
  insert into policy_search_documents(document_id,source_type,source_id,title,document_date,source_url,
    search_text,evidence_parts,references_json,coverage,input_hash)
  values(ident,job.source_type,job.source_id,p_document->>'title',(p_document->>'document_date')::date,
    p_document->>'source_url',p_document->>'search_text',p_document->'evidence_parts',p_document->'references',
    jsonb_build_object('text_status',p_document->>'text_status','embedding_coverage',p_document->>'embedding_coverage',
      'available_passages',p_document->'available_passages','body_characters',p_document->'body_characters',
      'retained_body_characters',p_document->'retained_body_characters','resolved_references',p_document->'resolved_references',
      'reference_count',p_document->'reference_count','version',p_document->>'version'),p_document->>'input_hash')
  on conflict(document_id) do update set title=excluded.title,document_date=excluded.document_date,
    source_url=excluded.source_url,search_text=excluded.search_text,evidence_parts=excluded.evidence_parts,
    references_json=excluded.references_json,coverage=excluded.coverage,input_hash=excluded.input_hash,refreshed_at=now();
  for item in select value from jsonb_array_elements(p_passages) loop
    insert into policy_search_passages(document_id,passage_index,field,text_content,source_url,target_type,target_id,
      input_hash,embedding,embedding_model,embedded_at)
    values(ident,(item->>'passage_index')::int,item->>'field',item->>'text',item->>'source_url',
      item->>'target_type',item->>'target_id',item->>'input_hash',
      case when item->'embedding' is not null and item->'embedding'<>'null'::jsonb then (item->'embedding')::text::extensions.vector(1536) else null end,
      item->>'embedding_model',case when item->'embedding' is not null and item->'embedding'<>'null'::jsonb then now() end)
    on conflict(document_id,passage_index) do update set field=excluded.field,text_content=excluded.text_content,
      source_url=excluded.source_url,target_type=excluded.target_type,target_id=excluded.target_id,input_hash=excluded.input_hash,
      embedding=case when excluded.embedding is not null then excluded.embedding
        when policy_search_passages.input_hash=excluded.input_hash then policy_search_passages.embedding end,
      embedding_model=case when excluded.embedding is not null then excluded.embedding_model
        when policy_search_passages.input_hash=excluded.input_hash then policy_search_passages.embedding_model end,
      embedded_at=case when excluded.embedding is not null then now()
        when policy_search_passages.input_hash=excluded.input_hash then policy_search_passages.embedded_at end;
  end loop;
  delete from policy_search_passages where document_id=ident and passage_index>=jsonb_array_length(p_passages);
  return true;
end; $$;

create or replace function public.search_policy_document_vectors(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_result_limit int default 50)
returns table(source_type text,source_id text,title text,similarity_score double precision)
language sql stable set search_path=public,extensions as $$
  with nearest as (
    select p.document_id,p.embedding<=>p_query_embedding distance
    from policy_search_passages p where p.embedding is not null and p.embedding_model=p_embedding_model
    order by p.embedding<=>p_query_embedding limit least(greatest(p_result_limit,1),100)*24
  )
  select d.source_type,d.source_id,d.title,(1-n.distance)::double precision
  from (select document_id,min(distance) distance from nearest group by document_id) n
  join policy_search_documents d using(document_id)
  order by 4 desc,d.document_id limit least(greatest(p_result_limit,1),100);
$$;
-- No full text crosses the public request boundary. Return only bounded proof
-- windows; JS applies word-boundary verification before claiming N/N matches.
create or replace function public.search_policy_document_terms(p_terms jsonb,p_limit int default 60)
returns table(source_type text,source_id text,title text,source_url text,document_date date,
  evidence_parts jsonb,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  with matches as (
    select d.document_id,term->>'key' term_key,
      (part-'text')||jsonb_build_object('text',substring(part->>'text'
        from greatest(1,pos.value-100) for 360)) evidence,
      row_number() over(partition by d.document_id,term->>'key' order by
        case part->>'field' when 'title' then 0 when 'summary' then 1 when 'subjects' then 2 when 'body' then 3 else 4 end,
        length(alias) desc,part->>'source_url',pos.value) ordinal
    from policy_search_documents d,jsonb_array_elements(d.evidence_parts) part,
      jsonb_array_elements(p_terms) term,jsonb_array_elements_text(term->'aliases') alias,
      lateral (select regexp_instr(lower(part->>'text'),
        case when alias~'^[a-z0-9]' then '(^|[^a-z0-9])' else '' end
        ||replace(alias,' ','[[:space:]-]+')||case when alias~'[a-z0-9]$' then '([^a-z0-9]|$)' else '' end) value) pos
    where d.search_vector @@ (select string_agg('('||plainto_tsquery('simple',a)::text||')',' | ')::tsquery
      from jsonb_array_elements(p_terms) t,jsonb_array_elements_text(t->'aliases') a)
      and pos.value>0
  ), proof as (
    select document_id,count(distinct term_key) hits,jsonb_agg(evidence order by term_key,ordinal) parts
    from matches where ordinal<=3 group by document_id
  ) select d.source_type,d.source_id,d.title,d.source_url,d.document_date,
    (select jsonb_agg(value) from (select value from jsonb_array_elements(proof.parts) limit 30) t),
    d.coverage,coalesce(j.status<>'done',false)
  from proof join policy_search_documents d using(document_id) left join policy_search_jobs j using(document_id)
  order by proof.hits desc,d.document_date desc nulls last,d.document_id
  limit least(greatest(p_limit,1),100);
$$;
create or replace function public.policy_search_status() returns jsonb
language sql stable set search_path=public,extensions as $$
  select jsonb_build_object('database_bytes',pg_database_size(current_database()),
    'documents',(select count(*) from policy_search_documents),
    'passages',(select count(*) from policy_search_passages),'embedded_passages',(select count(*) from policy_search_passages where embedding is not null),
    'partial_vector_documents',(select count(*) from policy_search_documents where coverage->>'embedding_coverage'='partial'),
    'without_body',(select count(*) from policy_search_documents where coverage->>'text_status'='unavailable'),
    'pending',(select count(*) from policy_search_jobs where status in ('queued','processing')),
    'failed',(select count(*) from policy_search_jobs where status='failed'),
    'last_refreshed_at',(select max(refreshed_at) from policy_search_documents));
$$;

alter table policy_search_documents enable row level security;
alter table policy_search_passages enable row level security;
alter table policy_search_jobs enable row level security;
revoke all on policy_search_documents,policy_search_passages,policy_search_jobs from public,anon,authenticated;
grant all on policy_search_documents,policy_search_passages,policy_search_jobs to service_role;
revoke all on function enqueue_policy_search_document(text,text),seed_policy_search_jobs(integer),policy_search_source_changed(),policy_search_bill_detail_changed(),claim_policy_search_job(),
  finish_policy_search_job(text,uuid,text),save_policy_search_document(jsonb,jsonb,uuid),
  search_policy_document_vectors(extensions.vector,text,integer),search_policy_document_terms(jsonb,integer),policy_search_status() from public,anon,authenticated;
grant execute on function enqueue_policy_search_document(text,text),seed_policy_search_jobs(integer),claim_policy_search_job(),finish_policy_search_job(text,uuid,text),
  save_policy_search_document(jsonb,jsonb,uuid),search_policy_document_vectors(extensions.vector,text,integer),
  search_policy_document_terms(jsonb,integer),policy_search_status() to service_role;
notify pgrst,'reload schema';
commit;

-- Policy search quality (20261006010000_policy_search_quality.sql)
-- Additive search RPCs; collection and notification triggers stay unchanged.
-- Load vector GUCs before validating function SET options on a fresh connection.
select extensions.vector_dims('[1,0]'::extensions.vector);
begin;
set local lock_timeout='2s';
create or replace function public.search_policy_legacy_vectors_for_type(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_source_type text,p_result_limit int default 25)
returns table(source_type text,source_id text,title text,similarity_score double precision)
language plpgsql stable set search_path=public,extensions set hnsw.ef_search='80' as $$
declare tbl text; ident text; heading text;
begin
  case p_source_type
    when 'bill' then tbl:='bills';ident:='bill_id';heading:='title';
    when 'public_law' then tbl:='public_laws';ident:='public_law_id';heading:='law_title';
    when 'executive_order' then tbl:='executive_orders';ident:='eo_number';heading:='title';
    when 'regulation' then tbl:='regulations';ident:='regulation_id';heading:='title';
    else return;
  end case;
  -- Some fresh/older installations have no legacy vector on a source table.
  if (select count(*) from information_schema.columns where table_schema='public' and table_name=tbl
      and column_name in ('embedding','embedding_model'))<>2 then return; end if;
  return query execute format('select $3::text,%I::text,%I::text,(1-(embedding<=>$1))::double precision
    from public.%I where embedding is not null and embedding_model=$2
    order by embedding<=>$1 limit $4',ident,heading,tbl)
    using p_query_embedding,p_embedding_model,p_source_type,least(greatest(p_result_limit,1),50);
end; $$;
create or replace function public.search_policy_vectors_for_type(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_source_type text,p_per_type_limit int default 25)
returns table(source_type text,source_id text,title text,similarity_score double precision,coverage jsonb,refresh_pending boolean)
language plpgsql stable set search_path=public,extensions set hnsw.ef_search='200' as $$
declare kind text:=p_source_type; budget int:=least(greatest(p_per_type_limit,1),50);
begin
  if p_query_embedding is null or kind not in ('bill','public_law','executive_order','regulation') then return; end if;
    return query execute format($query$
    with nearest as materialized (
      select p.document_id,p.embedding<=>$1 distance from public.policy_search_passages p
      where p.embedding is not null and p.embedding_model=$2 and p.document_id like %L
      order by p.embedding<=>$1 limit $3*24
    ), fresh as (
      select d.source_type,d.source_id,d.title,(1-min(n.distance))::double precision similarity_score
      from nearest n join public.policy_search_documents d using(document_id)
      where d.source_type=$4 group by d.source_type,d.source_id,d.title
      order by 4 desc,d.source_id limit $3
    ), combined as (
      select * from fresh union all
      select l.* from public.search_policy_legacy_vectors_for_type($1,$2,$4,$3*2) l
      where not exists(select 1 from public.policy_search_documents d join public.policy_search_passages p using(document_id)
        where d.source_type=$4 and d.source_id=l.source_id and p.embedding is not null and p.embedding_model=$2)
    ) select c.source_type,c.source_id,c.title,c.similarity_score,d.coverage,coalesce(j.status<>'done',false)
      from combined c left join public.policy_search_documents d on d.source_type=c.source_type and d.source_id=c.source_id
      left join public.policy_search_jobs j on j.document_id=d.document_id
      order by c.similarity_score desc,c.source_id limit $3
    $query$,kind||':%') using p_query_embedding,p_embedding_model,budget,kind;
end; $$;
-- Compatibility aggregate. The Worker calls typed RPCs concurrently so the
-- HTTP statement timeout applies to each lane rather than their cumulative work.
create or replace function public.search_policy_balanced_vectors(p_query_embedding extensions.vector(1536),
  p_embedding_model text,p_per_type_limit int default 25)
returns table(source_type text,source_id text,title text,similarity_score double precision,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  select hit.* from unnest(array['bill','public_law','executive_order','regulation']) kind
    cross join lateral search_policy_vectors_for_type(p_query_embedding,p_embedding_model,kind,p_per_type_limit) hit;
$$;
create or replace function public.search_policy_document_terms_for_type(p_terms jsonb,p_source_type text,p_limit int default 25)
returns table(source_type text,source_id text,title text,source_url text,document_date date,
  evidence_parts jsonb,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  with terms as materialized (
    select term->>'key' key,term->'aliases' aliases,
      (select string_agg('('||plainto_tsquery('simple',a)::text||')',' | ')::tsquery
        from jsonb_array_elements_text(term->'aliases') a) query
    from jsonb_array_elements(p_terms) term
  ), query as materialized (select string_agg('('||query::text||')',' | ')::tsquery value from terms),
  pool as materialized (
    select d.* from policy_search_documents d cross join query q
    where d.source_type=p_source_type and d.search_vector@@q.value
    order by (select count(*) from terms t where d.search_vector@@t.query) desc,
      (to_tsvector('simple',d.title)@@q.value) desc,ts_rank_cd(d.search_vector,q.value,32) desc,
      d.document_date desc nulls last,d.document_id
    -- Bounded proof extraction; candidate-limited is disclosed by the Worker.
    limit greatest(50,least(p_limit*2,200))
  ), matches as (
    select d.document_id,term->>'key' term_key,
      (part-'text')||jsonb_build_object('text',substring(part->>'text'
        from greatest(1,pos.value-100) for 360)) evidence,
      row_number() over(partition by d.document_id,term->>'key' order by
        case part->>'field' when 'title' then 0 when 'summary' then 1 when 'subjects' then 2 when 'body' then 3 else 4 end,
        length(alias) desc,part->>'source_url',pos.value) ordinal
    from pool d,jsonb_array_elements(d.evidence_parts) part,
      jsonb_array_elements(p_terms) term,jsonb_array_elements_text(term->'aliases') alias,
      lateral (select regexp_instr(lower(part->>'text'),
        case when alias~'^[a-z0-9]' then '(^|[^a-z0-9])' else '' end
        ||replace(alias,' ','[[:space:]-]+')||case when alias~'[a-z0-9]$' then '([^a-z0-9]|$)' else '' end) value) pos
    where pos.value>0
  ), proof as (
    select document_id,count(distinct term_key) hits,jsonb_agg(evidence order by term_key,ordinal) parts
    from matches where ordinal<=3 group by document_id
  ) select d.source_type,d.source_id,d.title,d.source_url,d.document_date,
    (select jsonb_agg(value) from (select value from jsonb_array_elements(proof.parts) limit 30) t),
    d.coverage,coalesce(j.status<>'done',false)
  from proof join policy_search_documents d using(document_id) left join policy_search_jobs j using(document_id)
  order by proof.hits desc,(to_tsvector('simple',d.title)@@(select value from query)) desc,
    ts_rank_cd(d.search_vector,(select value from query),32) desc,d.document_date desc nulls last,d.document_id
  limit least(greatest(p_limit,1),100);
$$;
create or replace function public.search_policy_balanced_terms(p_terms jsonb,p_per_type_limit int default 25)
returns table(source_type text,source_id text,title text,source_url text,document_date date,
  evidence_parts jsonb,coverage jsonb,refresh_pending boolean)
language sql stable set search_path=public,extensions as $$
  select hit.* from unnest(array['bill','public_law','executive_order','regulation']) kind
    cross join lateral search_policy_document_terms_for_type(p_terms,kind,least(greatest(p_per_type_limit,1),50)) hit;
$$;
revoke all on function search_policy_legacy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_balanced_vectors(extensions.vector,text,integer),search_policy_document_terms_for_type(jsonb,text,integer),
  search_policy_balanced_terms(jsonb,integer) from public,anon,authenticated;
grant execute on function search_policy_legacy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_vectors_for_type(extensions.vector,text,text,integer),
  search_policy_balanced_vectors(extensions.vector,text,integer),search_policy_document_terms_for_type(jsonb,text,integer),
  search_policy_balanced_terms(jsonb,integer) to service_role;
notify pgrst,'reload schema';
commit;

-- The dominant bill lane reuses the global HNSW index; isolate minority lanes.
-- Independent commits preserve completed indexes if the editor times out.
begin;
set local lock_timeout='2s';
set local max_parallel_maintenance_workers=0;
set local maintenance_work_mem='64MB';
create index if not exists policy_search_passages_regulation_ann on public.policy_search_passages using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null and document_id like 'regulation:%';
commit;
begin;
set local lock_timeout='2s';
set local max_parallel_maintenance_workers=0;
set local maintenance_work_mem='64MB';
create index if not exists policy_search_passages_public_law_ann on public.policy_search_passages using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null and document_id like 'public_law:%';
commit;
begin;
set local lock_timeout='2s';
set local max_parallel_maintenance_workers=0;
set local maintenance_work_mem='64MB';
create index if not exists policy_search_passages_executive_order_ann on public.policy_search_passages using hnsw (embedding extensions.vector_cosine_ops) where embedding is not null and document_id like 'executive_order:%';
commit;
