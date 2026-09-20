-- My Page: per-favorite mail notification toggle, alongside the existing
-- account-wide bill_notifications_paused switch (20260919_bill_notification_pause.sql).
-- That one mutes every bill/EO email at once; this lets someone keep a bill
-- favorited (so it still shows progress in My Page) while muting mail for
-- just that one item.

begin;

alter table public.user_favorites
  add column if not exists notify_enabled boolean not null default true;

commit;
