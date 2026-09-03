-- Signup system, phase 2: per-user favorites (즐겨찾기).
-- 20260901_user_profiles.sql established profiles.id as the anchor every
-- per-user feature table hangs off; this is the first of those tables.
--
-- The browser writes here directly with the anon key, so RLS is the only
-- thing standing between one account's list and another's. The Worker never
-- touches this table -- its service_role key would bypass these policies.

begin;

create table if not exists public.user_favorites (
  user_id uuid not null references public.profiles(id) on delete cascade,
  item_kind text not null check (item_kind in ('bill', 'executive_order')),
  item_id text not null,
  -- Denormalized so the favorites list renders without a join back into
  -- bills/executive_orders. A retention prune (see docs/bill-retention-design.md)
  -- can empty those rows out from under a favorite; the title kept here is what
  -- the user actually saved.
  title text,
  created_at timestamptz not null default now(),
  primary key (user_id, item_kind, item_id)
);

-- The list screen reads one user's rows newest-first; the primary key leads
-- with user_id but cannot order by time.
create index if not exists user_favorites_user_created_idx
  on public.user_favorites (user_id, created_at desc);

alter table public.user_favorites enable row level security;

drop policy if exists user_favorites_select_own on public.user_favorites;
create policy user_favorites_select_own on public.user_favorites
  for select using (auth.uid() = user_id);

-- with check (not using) on insert: the row being written is what must match
-- the caller, and an unauthenticated auth.uid() of null matches nothing.
drop policy if exists user_favorites_insert_own on public.user_favorites;
create policy user_favorites_insert_own on public.user_favorites
  for insert with check (auth.uid() = user_id);

-- upsert on an existing favorite lands on update, so it needs its own policy.
drop policy if exists user_favorites_update_own on public.user_favorites;
create policy user_favorites_update_own on public.user_favorites
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists user_favorites_delete_own on public.user_favorites;
create policy user_favorites_delete_own on public.user_favorites
  for delete using (auth.uid() = user_id);

commit;
