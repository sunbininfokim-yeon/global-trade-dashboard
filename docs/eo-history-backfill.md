# Executive Order historical backfill

Use this **only for the initial local history load**. It is deliberately
separate from the normal Federal Register incremental sync, uses a separate
`data_sync_state` resource, and only requests Presidential Documents whose
official Federal Register type is `executive_order`.

It stores EO metadata, official URLs, selected Federal Register summary
metadata, agency relations, and official structured authority metadata. It does
not download or store full EO text, PDFs, or eCFR content.

## Initial 1994+ load

From a local checkout that includes this change and has the existing Supabase
credentials exported, run:

```bash
export EO_BACKFILL=true
export EO_BACKFILL_FROM_DATE=1994-01-01
export EO_BACKFILL_TO_DATE="$(date +%F)"
export MAX_FR_DOCUMENTS=100
export SKIP_EMBEDDINGS=true
node scripts/sync-federal-register.js
```

Repeat the same command until the log says `history complete`. A stopped or
failed local run resumes from the saved page and document numbers; it does not
restart from 1994. `SKIP_EMBEDDINGS=true` is recommended for this metadata
backfill and is also the default when `EO_BACKFILL=true`. Set
`EO_BACKFILL_EMBEDDINGS=true` only in a later, explicitly funded embedding pass.

## Routine sync after history is complete

Unset `EO_BACKFILL` and use the normal incremental command. Its state is
separate, so it starts from the ordinary recent window and keeps monitoring new
EOs and Federal Register regulations without replaying the historical range.

```bash
unset EO_BACKFILL EO_BACKFILL_FROM_DATE EO_BACKFILL_TO_DATE EO_BACKFILL_EMBEDDINGS
node scripts/sync-federal-register.js
```

## Verification

Run in Supabase SQL Editor after a batch:

```sql
select
  count(*) as eo_count,
  min(publication_date) as earliest_publication_date,
  max(publication_date) as latest_publication_date
from public.executive_orders;

select sync_resource, status, started_at, completed_at, records_written, metadata
from public.data_sync_runs
where sync_resource = 'federalregister.gov:executive-orders:bootstrap'
order by started_at desc
limit 10;
```
