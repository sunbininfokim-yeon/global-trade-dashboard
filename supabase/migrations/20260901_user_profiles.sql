-- Signup system, phase 1: a profile row per auth.users account.
-- auth.users itself is managed by Supabase Auth (email, password hash,
-- session tokens) -- this table only holds the columns the dashboard's own
-- features (policy favorites, commodity subscriptions, risk alerts,
-- portfolio) will each need to join against. Those feature tables come in
-- later migrations; this one only establishes the account <-> profile link
-- so RLS on every future per-user table can reference profiles.id.

begin;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Each user can see and edit only their own row. No public policy: an
-- unauthenticated request gets nothing, matching the rest of this project's
-- RLS posture (see schema.sql).
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select using (auth.uid() = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update using (auth.uid() = id);

-- Supabase Auth writes to auth.users directly on signup; client code has no
-- way to also insert into public.profiles in the same request. This trigger
-- creates the profile row server-side the moment the account exists, so
-- every other feature table can assume profiles.id already exists for any
-- signed-in auth.uid().
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

commit;
