-- Requires PR #321 mailing tables and existing favorite notification preference columns.
-- Preserve the verified production opt-out guards when replaying older mailing migrations.
begin;
set local lock_timeout = '3s';
CREATE OR REPLACE FUNCTION public.mail_item_active(o mailing_outbox)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
select case when o.kind='policy' then
coalesce((select p.policy_enabled from public.mailing_preferences p where p.user_id=o.user_id),true)
and not coalesce((select p.bill_notifications_paused from public.profiles p where p.id=o.user_id),false)
and exists(select 1 from public.user_favorites f where f.user_id=o.user_id and f.item_kind=o.item_kind and f.item_id=o.item_id and f.created_at=o.favorite_created_at and f.notify_enabled)
else coalesce((select p.commodity_enabled from public.mailing_preferences p where p.user_id=o.user_id),true)
and not exists(select 1 from public.commodity_report_notifications n where n.user_id=o.user_id and n.report_id=o.item_id)
and exists(select 1 from public.user_favorites f where f.user_id=o.user_id and f.item_kind='commodity' and f.notify_enabled and (o.content->'commodities') ? f.item_id and f.created_at<=(o.content->>'published_at')::timestamptz)
and not exists(select 1 from public.commodity_digest_source_prefs p where p.user_id=o.user_id and p.source_id=o.content->>'source_id') end;
$function$
;
commit;
