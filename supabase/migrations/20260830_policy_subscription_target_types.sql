-- Phase 2-1: allow exact bill and Executive Order subscriptions.
-- Safe for the existing policy database; it changes only the CHECK list.

begin;

do $$
declare
  existing_constraint record;
begin
  -- The initial schema used an unnamed CHECK, so PostgreSQL may call it
  -- subscriptions_category_type_check. Remove only that specific predicate;
  -- leave the separate keyword/category required CHECK intact.
  for existing_constraint in
    select conname
    from pg_constraint
    where conrelid = 'public.subscriptions'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%category_type is null%'
  loop
    execute format('alter table public.subscriptions drop constraint %I', existing_constraint.conname);
  end loop;

  alter table public.subscriptions
    add constraint subscriptions_category_type_chk
    check (category_type is null or category_type in (
      'policy_area',
      'legislative_subject',
      'committee',
      'agency',
      'cfr_title',
      'bill',
      'executive_order'
    ));
end;
$$;

commit;
