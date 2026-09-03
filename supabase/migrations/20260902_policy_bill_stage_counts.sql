-- Exact bill-stage counts for the policy UI.
-- Read-only and independent of PostgREST's optional aggregate setting.

begin;

create or replace function public.policy_bill_stage_counts(
  p_committee_id text default null,
  p_policy_area_id text default null,
  p_congress_number integer default null
)
returns table (
  current_stage text,
  bill_count bigint
)
language sql
stable
set search_path = public
as $$
  select
    bill.current_stage,
    count(*)::bigint as bill_count
  from public.bills bill
  where (p_policy_area_id is null or bill.policy_area_id = p_policy_area_id)
    and (p_congress_number is null or bill.congress_number = p_congress_number)
    and (
      p_committee_id is null
      or exists (
        select 1
        from public.bill_committees bill_committee
        where bill_committee.bill_id = bill.bill_id
          and bill_committee.committee_id = p_committee_id
      )
    )
  group by bill.current_stage
  order by bill.current_stage;
$$;

commit;
