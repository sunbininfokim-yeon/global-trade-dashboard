-- Signup system, phase 4: let user_favorites hold commodity favorites too.
-- 20260903_user_favorites.sql only allowed 'bill'/'executive_order' (the
-- policy screen's star button). The My Page favorites tab lets a user
-- favorite a commodity block (원유, 가스, ...) directly, independent of any
-- per-commodity screen -- item_id is the same slug app.js already uses for
-- data-target (e.g. 'oil', 'wheat'), so no separate id scheme is needed.
--
-- Not adding 'committee' or a macro-monitor kind yet: committee_members has
-- no real data ingested (see 20260903_policy_legislator_and_committee_roster.sql),
-- and the macro-monitor favorite's purpose isn't decided. Widen this check
-- again once those are real.

begin;

alter table public.user_favorites drop constraint if exists user_favorites_item_kind_check;
alter table public.user_favorites add constraint user_favorites_item_kind_check
  check (item_kind in ('bill', 'executive_order', 'commodity'));

-- Same widening on the notify log (20260904_favorite_notifications.sql),
-- so a commodity favorite doesn't fail its first baseline row once the
-- weekly digest script exists.
alter table public.favorite_notifications drop constraint if exists favorite_notifications_item_kind_check;
alter table public.favorite_notifications add constraint favorite_notifications_item_kind_check
  check (item_kind in ('bill', 'executive_order', 'commodity'));

commit;
