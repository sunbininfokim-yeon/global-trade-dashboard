-- EO relationship provenance and official-citation support.
-- Existing EOP links are retained as issuing-document links. This migration
-- creates no new EO/agency, authority, or regulation relationship by itself.

begin;

alter table public.executive_order_agencies
  add column if not exists relationship_type text not null default 'issuing_document'
    check (relationship_type in ('issuing_document', 'implementing_regulation')),
  add column if not exists relation_origin text not null default 'official_document_metadata'
    check (relation_origin in ('official_document_metadata', 'official_citation')),
  add column if not exists source_url text;

-- One agency can be both the document issuer and an implementation agency for
-- the same EO. Keep both provenances instead of overwriting one with the other.
alter table public.executive_order_agencies
  drop constraint if exists executive_order_agencies_pkey;

alter table public.executive_order_agencies
  add constraint executive_order_agencies_pkey
  primary key (eo_number, agency_id, relationship_type, relation_origin);

alter table public.legal_authorities
  drop constraint if exists legal_authorities_extraction_method_check;

alter table public.legal_authorities
  add constraint legal_authorities_extraction_method_check
  check (extraction_method in ('official_metadata', 'official_text_citation', 'verified_manual'));

create index if not exists executive_order_agencies_relationship_idx
  on public.executive_order_agencies (agency_id, relationship_type, eo_number);

commit;
