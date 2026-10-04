-- My Page mailing tab: pause bill/EO notification emails without touching
-- user_favorites, so pausing doesn't lose favorite-change tracking and
-- resuming doesn't dump a backlog of everything missed while paused
-- (notify-favorites.js keeps recording each favorite's last-seen state
-- either way -- it just skips the send for a paused user).

begin;

alter table public.profiles
  add column if not exists bill_notifications_paused boolean not null default false;

commit;
