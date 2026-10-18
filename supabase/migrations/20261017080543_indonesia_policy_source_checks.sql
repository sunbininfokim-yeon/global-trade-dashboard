begin;
set local lock_timeout = '3s';
create table if not exists public.idn_policy_source_checks (
  document_id text not null,
  checked_at timestamptz not null,
  source_url text not null check (source_url ~ '^https://[^/]+\.go\.id/'),
  outcome text not null check (outcome in ('collected','failed')),
  detail text not null check (length(detail)<=1000),
  primary key(document_id,checked_at)
);
alter table public.idn_policy_source_checks enable row level security;
revoke all on public.idn_policy_source_checks from public,anon,authenticated;
grant select,insert,update on public.idn_policy_source_checks to service_role;
comment on table public.idn_policy_source_checks is '인도네시아 수집 성공·차단·시간 초과 기록. 실패 후보는 법령 목록과 분리.';
commit;
