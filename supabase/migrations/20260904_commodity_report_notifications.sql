-- Signup system, phase 5: weekly commodity report digest sent-log.
--
-- Shaped differently from favorite_notifications (bills/EOs): a bill is one
-- row whose status changes in place, so one baseline+diff row per favorite
-- is enough. A commodity report is a new, immutable item every time one is
-- published -- there can be many per commodity per week -- so this instead
-- tracks which individual report ids a user has already been sent, append-only.
--
-- Server-only, same as favorite_notifications: the digest script authenticates
-- with the service_role key, so no browser RLS policy is needed.

begin;

create table if not exists public.commodity_report_notifications (
  user_id uuid not null references public.profiles(id) on delete cascade,
  report_id text not null,
  sent_at timestamptz not null default now(),
  primary key (user_id, report_id)
);

alter table public.commodity_report_notifications enable row level security;

commit;
