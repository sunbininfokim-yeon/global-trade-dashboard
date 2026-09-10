-- Signup system, phase 7: My Page account fields.
-- 20260901_user_profiles.sql already ran on the live database, so this adds
-- columns rather than editing that file in place -- `create table if not
-- exists` there would silently no-op on a re-run and these columns would
-- never actually appear.

begin;

alter table public.profiles
  -- Assigned in signup order; shown in My Page instead of a real name,
  -- since this project deliberately does not collect one. A plain integer
  -- sequence, backfilled for existing rows by the identity column's own
  -- rule (order of physical row, not created_at -- fine, there are no
  -- profiles yet with this migration's timing).
  add column if not exists member_no bigint generated always as identity,
  -- Null until the user sets one in My Page; the UI should show
  -- "닉네임 미설정" rather than default to the email or a guessed name.
  add column if not exists nickname text,
  -- Captured from auth.users.raw_user_meta_data at signup (see
  -- handle_new_user() below), not a separate client update call right
  -- after signUp() -- a signup that requires email confirmation has no
  -- authenticated session yet for that second call to run under.
  add column if not exists terms_agreed_at timestamptz;

-- Re-create to also populate terms_agreed_at from the signup form's consent
-- checkbox timestamp (see auth.js signUp, which now sends it in
-- options.data). Existing accounts created before this migration keep
-- terms_agreed_at null; nothing here retroactively assumes consent.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, terms_agreed_at)
  values (new.id, new.email, (new.raw_user_meta_data ->> 'terms_agreed_at')::timestamptz);
  return new;
end;
$$;

commit;
