-- Terminal bill retention and Congress rollover cleanup.
--
-- These routines do not run automatically. sync-congress calls the terminal
-- prune only after notification matching, and rollover deletion requires both
-- a dry-run review and an explicit confirmation argument from a gated script.

begin;

create or replace function public.prune_terminal_bill_details(
  p_bill_id text
)
returns table (
  outcome text,
  detail_rows_removed integer
)
language plpgsql
set search_path = public
as $$
declare
  target_stage text;
  removed integer := 0;
  changed integer := 0;
begin
  -- Lock the parent row first so an overlapping sync cannot repopulate child
  -- detail rows in the middle of this transaction.
  select current_stage
  into target_stage
  from public.bills
  where bill_id = p_bill_id
  for update;

  if not found then
    return query select 'not_found'::text, 0;
    return;
  end if;

  if target_stage not in ('failed', 'vetoed') then
    return query select 'not_terminal'::text, 0;
    return;
  end if;

  -- A Public Law link wins over an accidentally stale bill stage. Never
  -- discard the linked bill detail merely because current_stage is wrong.
  if exists (select 1 from public.public_laws where bill_id = p_bill_id) then
    return query select 'protected_public_law'::text, 0;
    return;
  end if;

  delete from public.bill_vote_members
  where vote_id in (select vote_id from public.bill_votes where bill_id = p_bill_id);
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_votes where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_summaries where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_text_versions where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_actions where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_status_history where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_committees where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_subjects where bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  delete from public.bill_relations
  where source_bill_id = p_bill_id or target_bill_id = p_bill_id;
  get diagnostics changed = row_count;
  removed := removed + changed;

  update public.bills
  set
    detail_level = 'index',
    storage_tier = 'cold',
    tier_changed_at = now(),
    summary = null,
    summary_source = null,
    summary_updated_at = null,
    embedding = null,
    embedding_model = null,
    embedded_at = null,
    policy_area_id = null,
    sponsor_bioguide_id = null,
    introduced_date = null,
    latest_action_text = null,
    law_type = null,
    law_number = null,
    raw_source = jsonb_build_object(
      'source', coalesce(raw_source ->> 'source', 'congress.gov'),
      'retention', 'terminal_minimal',
      'pruned_at', now()
    )
  where bill_id = p_bill_id;

  return query select 'pruned'::text, removed;
end;
$$;

create or replace function public.preview_congress_rollover_purge(
  p_previous_congress integer,
  p_result_limit integer default 100
)
returns table (
  bill_id text,
  title text,
  current_stage text,
  latest_action_date date
)
language sql
stable
set search_path = public
as $$
  select
    bill.bill_id,
    bill.title,
    bill.current_stage,
    bill.latest_action_date
  from public.bills bill
  where bill.congress_number = p_previous_congress
    and bill.current_stage <> 'enacted'
    and not exists (
      select 1
      from public.public_laws public_law
      where public_law.bill_id = bill.bill_id
    )
  order by bill.latest_action_date desc nulls last, bill.bill_id
  limit least(greatest(coalesce(p_result_limit, 100), 1), 1000);
$$;

create or replace function public.purge_congress_rollover(
  p_previous_congress integer,
  p_max_bills integer default 1000,
  p_confirm boolean default false
)
returns table (
  deleted_bill_count integer,
  deleted_queue_count integer
)
language plpgsql
set search_path = public
as $$
declare
  target_bill_ids text[];
  target_count integer;
  queue_count integer := 0;
  bill_count integer := 0;
begin
  if not p_confirm then
    raise exception 'rollover purge requires p_confirm = true; run preview_congress_rollover_purge first';
  end if;

  if p_previous_congress is null or p_previous_congress < 1 then
    raise exception 'a valid previous Congress number is required';
  end if;

  if p_max_bills is null or p_max_bills < 1 or p_max_bills > 10000 then
    raise exception 'p_max_bills must be between 1 and 10000';
  end if;

  select coalesce(array_agg(candidate.bill_id order by candidate.bill_id), '{}'::text[])
  into target_bill_ids
  from (
    select bill.bill_id
    from public.bills bill
    where bill.congress_number = p_previous_congress
      and bill.current_stage <> 'enacted'
      and not exists (
        select 1
        from public.public_laws public_law
        where public_law.bill_id = bill.bill_id
      )
    order by bill.bill_id
    limit p_max_bills + 1
  ) candidate;

  target_count := cardinality(target_bill_ids);
  if target_count > p_max_bills then
    raise exception 'rollover candidate count % exceeds the approved maximum %', target_count, p_max_bills;
  end if;

  if target_count = 0 then
    return query select 0, 0;
    return;
  end if;

  -- The queue has no foreign key, so delete its rows explicitly before the
  -- corresponding bills disappear. This is intentionally scoped to the exact
  -- official Congress bill queue keys only.
  delete from public.policy_ingestion_queue
  where sync_resource = 'congress.gov:bills'
    and source_key = any(target_bill_ids)
    and exists (
      select 1
      from public.bills bill
      where bill.bill_id = policy_ingestion_queue.source_key
        and bill.congress_number = p_previous_congress
        and bill.current_stage <> 'enacted'
        and not exists (
          select 1
          from public.public_laws public_law
          where public_law.bill_id = bill.bill_id
        )
    );
  get diagnostics queue_count = row_count;

  -- Re-apply the Public Law check in the delete itself, so a concurrent link
  -- created after the candidate list was assembled remains protected.
  delete from public.bills bill
  where bill.bill_id = any(target_bill_ids)
    and bill.congress_number = p_previous_congress
    and bill.current_stage <> 'enacted'
    and not exists (
      select 1
      from public.public_laws public_law
      where public_law.bill_id = bill.bill_id
    );
  get diagnostics bill_count = row_count;

  return query select bill_count, queue_count;
end;
$$;

commit;
