-- Current US legislator roster and a source-backed committee membership model.
-- The initial roster comes from the repository's politics-US data product;
-- committee leadership remains empty until an official House/Senate source is
-- ingested. No guessed chair or subcommittee membership is inserted.

begin;

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
  source_updated_at timestamptz,
  raw_source jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (committee_id, bioguide_id, role, congress_number)
);

create index if not exists committee_members_leadership_idx
  on public.committee_members (committee_id, congress_number, role);

alter table public.us_legislators enable row level security;
alter table public.committee_members enable row level security;

drop trigger if exists set_updated_at on public.us_legislators;
create trigger set_updated_at
before update on public.us_legislators
for each row execute function public.set_updated_at();

drop trigger if exists set_updated_at on public.committee_members;
create trigger set_updated_at
before update on public.committee_members
for each row execute function public.set_updated_at();

commit;
