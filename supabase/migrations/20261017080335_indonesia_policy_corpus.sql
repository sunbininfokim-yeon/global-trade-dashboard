-- Narrow IDN pilot: separate from US bill lifecycle, search jobs and mail.
begin;
set local lock_timeout = '3s';
create table if not exists public.idn_policy_documents (
  document_id text primary key check (document_id ~ '^idn-[a-z0-9-]+$'),
  country_code text not null default 'IDN' check (country_code='IDN'),
  title text not null check (length(title) between 1 and 2000),
  title_ko text not null,
  issuer_name text not null,
  issuer_level text not null check (issuer_level in ('national','provincial','regency','city')),
  jurisdiction text not null,
  document_type text not null,
  document_number text not null,
  document_year integer not null check (document_year between 1900 and 2200),
  topics text[] not null check (cardinality(topics)>0),
  primary_stage text not null check (primary_stage in ('coal','nickel_mining','palm_oil')),
  scope_note text not null,
  source_url text not null check (source_url ~ '^https://[^/]+\.go\.id/'),
  legal_status text not null default 'unverified' check (legal_status='unverified'),
  status_note text not null,
  first_observed_at timestamptz not null default now(),
  last_observed_at timestamptz not null,
  unique(issuer_name,jurisdiction,document_type,document_number,document_year)
);
create table if not exists public.idn_policy_versions (
  document_id text not null references public.idn_policy_documents on delete restrict,
  content_hash text not null check (content_hash ~ '^[a-f0-9]{64}$'),
  content_kind text not null check (content_kind in ('official_metadata','official_text','abstract')),
  text_content text not null check (length(text_content) between 150 and 300000),
  text_truncated boolean not null,
  source_url text not null check (source_url ~ '^https://[^/]+\.go\.id/'),
  observed_at timestamptz not null,
  provenance jsonb not null check (jsonb_typeof(provenance)='object'),
  primary key(document_id,content_hash)
);
create index if not exists idn_policy_versions_observed_idx on public.idn_policy_versions(document_id,observed_at desc);
create index if not exists idn_policy_documents_region_idx on public.idn_policy_documents(issuer_level,jurisdiction);
alter table public.idn_policy_documents enable row level security;
alter table public.idn_policy_versions enable row level security;
revoke all on public.idn_policy_documents,public.idn_policy_versions from public,anon,authenticated;
grant select,insert,update on public.idn_policy_documents to service_role;
grant select,insert on public.idn_policy_versions to service_role;

create or replace function public.store_idn_policy_document(p_document jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
declare d public.idn_policy_documents; inserted integer;
begin
  if p_document->>'legal_status' is distinct from 'unverified' or
     p_document->>'country_code' is distinct from 'IDN' then
    raise exception 'Invalid pilot status/country';
  end if;
  if octet_length(p_document::text)>2500000 then raise exception 'Document exceeds pilot budget'; end if;
  select * into d from jsonb_populate_record(null::public.idn_policy_documents,p_document);
  insert into public.idn_policy_documents(document_id,country_code,title,title_ko,issuer_name,issuer_level,
    jurisdiction,document_type,document_number,document_year,topics,primary_stage,scope_note,source_url,
    legal_status,status_note,last_observed_at)
  values(d.document_id,d.country_code,d.title,d.title_ko,d.issuer_name,d.issuer_level,d.jurisdiction,
    d.document_type,d.document_number,d.document_year,d.topics,d.primary_stage,d.scope_note,d.source_url,
    d.legal_status,d.status_note,(p_document->>'observed_at')::timestamptz)
  on conflict(document_id) do update set title=excluded.title,title_ko=excluded.title_ko,
    scope_note=excluded.scope_note,source_url=excluded.source_url,
    last_observed_at=excluded.last_observed_at,topics=excluded.topics
    where public.idn_policy_documents.last_observed_at<=excluded.last_observed_at;
  insert into public.idn_policy_versions(document_id,content_hash,content_kind,text_content,text_truncated,
    source_url,observed_at,provenance)
  values(d.document_id,p_document->>'content_hash',p_document->>'content_kind',p_document->>'text_content',
    (p_document->>'text_truncated')::boolean,p_document->>'source_url',(p_document->>'observed_at')::timestamptz,
    p_document-'text_content')
  on conflict(document_id,content_hash) do nothing;
  get diagnostics inserted=row_count;
  return inserted=1;
end $$;
revoke all on function public.store_idn_policy_document(jsonb) from public,anon,authenticated;
grant execute on function public.store_idn_policy_document(jsonb) to service_role;
comment on table public.idn_policy_documents is '인도네시아 석탄→니켈·광산→팜유 공식문서 시범 목록. 법적 효력·완전성 미확인.';
comment on table public.idn_policy_versions is '인도네시아 공식 메타데이터·원문 관측 버전. 내용 해시로 중복 방지, 과거 관측 보존.';
commit;
