-- Signup system, phase 6: per-user commodity-digest source filter.
--
-- A row here means that source_id is turned OFF for that user, not on --
-- so a user who never opens this settings screen still gets every source
-- (an unconfigured preference must not silently empty someone's mail), and
-- a source added to the pipeline later reaches everyone by default instead
-- of needing every user to opt in. The My Page source checkboxes should be
-- built from commodity_reports_v1.json's own items[].source_id/agency_ko
-- (already real, already deployed), not a fixed list -- a source in that
-- JSON but missing here is simply "on by default", not "unsupported".
--
-- Browser-writable like user_favorites: the user picks their own sources
-- with the anon key, RLS scopes every row to auth.uid().

begin;

create table if not exists public.commodity_digest_source_prefs (
  user_id uuid not null references public.profiles(id) on delete cascade,
  source_id text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, source_id)
);

alter table public.commodity_digest_source_prefs enable row level security;

drop policy if exists commodity_digest_source_prefs_select_own on public.commodity_digest_source_prefs;
create policy commodity_digest_source_prefs_select_own on public.commodity_digest_source_prefs
  for select using (auth.uid() = user_id);

drop policy if exists commodity_digest_source_prefs_insert_own on public.commodity_digest_source_prefs;
create policy commodity_digest_source_prefs_insert_own on public.commodity_digest_source_prefs
  for insert with check (auth.uid() = user_id);

drop policy if exists commodity_digest_source_prefs_delete_own on public.commodity_digest_source_prefs;
create policy commodity_digest_source_prefs_delete_own on public.commodity_digest_source_prefs
  for delete using (auth.uid() = user_id);

commit;
