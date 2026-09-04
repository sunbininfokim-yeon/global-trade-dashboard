-- Signup system, phase 3: dedup log for the favorites email digest.
-- notify-favorites.js (run after the daily policy sync) compares each
-- favorited bill/EO's current state against the last state this row saw --
-- only a change past that baseline goes into the digest. Without this log,
-- every run would re-notify for the same unchanged status forever.
--
-- Server-only: the notify script authenticates with the service_role key,
-- same as the sync scripts, so no RLS policy here needs to allow browser
-- access -- there is none.

begin;

create table if not exists public.favorite_notifications (
  user_id uuid not null references public.profiles(id) on delete cascade,
  item_kind text not null check (item_kind in ('bill', 'executive_order')),
  item_id text not null,
  -- The favorited item's own updated_at/status_updated_at at the point this
  -- row last looked at it. A later run sees a newer value here as "changed".
  last_seen_updated_at timestamptz not null,
  -- Null until the first real change fires an email; distinguishes the
  -- baseline row written the moment someone favorites something (nothing to
  -- report yet) from a row that has actually triggered a digest.
  last_notified_at timestamptz,
  primary key (user_id, item_kind, item_id)
);

alter table public.favorite_notifications enable row level security;

commit;
