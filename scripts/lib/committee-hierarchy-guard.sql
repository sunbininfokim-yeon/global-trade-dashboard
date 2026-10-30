-- Only explicitly verified hierarchy fields are protected. Ordinary bill metadata
-- remains writable. Repairs use SET LOCAL app.committee_hierarchy_repair = 'on'.
create or replace function public.preserve_verified_committee_hierarchy()
returns trigger language plpgsql set search_path = '' as $$
declare verified jsonb;
begin
  if current_setting('app.committee_hierarchy_repair', true) = 'on' then return new; end if;
  verified := old.raw_source->'_verified_hierarchy';
  if verified is not null then
    new.committee_type := verified->>'committee_type';
    new.parent_committee_id := verified->>'parent_committee_id';
    new.raw_source := coalesce(new.raw_source, '{}'::jsonb)
      || jsonb_build_object('_verified_hierarchy', verified);
  end if;
  return new;
end;
$$;
revoke all on function public.preserve_verified_committee_hierarchy() from public;
drop trigger if exists preserve_verified_committee_hierarchy on public.committees;
create trigger preserve_verified_committee_hierarchy before update on public.committees
for each row execute function public.preserve_verified_committee_hierarchy();
