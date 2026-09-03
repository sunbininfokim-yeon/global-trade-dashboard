# Policy corpus embedding backfill

Use this local script after a metadata backfill that intentionally skipped
Gemini embeddings. It does **not** download Congress.gov or Federal Register
data again. It only finds existing `bills`, `executive_orders`, and
`regulations` rows where `embedding is null`, then fills `embedding`,
`embedding_model`, and `embedded_at`.

It is safe to stop and run again: successfully updated rows no longer satisfy
the `embedding is null` selection. It does not alter titles, summaries,
authorities, stage data, or source records.

## Cost and quota

Every processed row is a real Gemini Embeddings API request. This uses Google
AI Studio/Gemini input-token quota and, when billing is enabled for the key,
may incur Gemini API cost. It does **not** use ChatGPT or Codex token allowance.

Start with a 100-row batch to confirm access and cost expectations. A Gemini
quota or billing error leaves the remaining rows unchanged and ends the run as
`partial`; rerun after quota is available again.

## Prerequisites

From the repository checkout, export the existing local credentials. Do not
paste values into a shell history, commit, or chat.

```bash
export SUPABASE_URL='...'
export SUPABASE_SERVICE_ROLE_KEY='...'
export GEMINI_API_KEY='...'
```

## Inspect before spending quota

This checks only the next batch and makes no Gemini call or database write.

```bash
export EMBEDDING_BACKFILL_DRY_RUN=true
node scripts/backfill-policy-embeddings.js
unset EMBEDDING_BACKFILL_DRY_RUN
```

## Safe first run

The default selects EO first, then regulations, then bills. It embeds at most
100 rows in 25-row Gemini batches, waiting 1.5 seconds between batches.

```bash
node scripts/backfill-policy-embeddings.js
```

## Keep a local Mac running

After a successful small run, the following processes every remaining selected
row until the Gemini account reports quota/billing exhaustion or the process is
stopped. It is intentionally for a local Mac, not GitHub Actions.

```bash
export EMBEDDING_BACKFILL_LIMIT=0
export EMBEDDING_BACKFILL_BATCH_SIZE=25
export EMBEDDING_BACKFILL_BATCH_INTERVAL_MS=1500
node scripts/backfill-policy-embeddings.js
```

To prioritize only historical EO search, use:

```bash
export EMBEDDING_BACKFILL_TARGETS=executive_orders
node scripts/backfill-policy-embeddings.js
```

To omit optional bill-to-bill similar-law relations while filling bill search
embeddings, set `REFRESH_BILL_SEMANTIC_RELATIONS=false`.

## Verify progress

Run in Supabase SQL Editor:

```sql
select 'bills' as source, count(*) filter (where embedding is not null) as embedded,
       count(*) filter (where embedding is null) as remaining
from public.bills
union all
select 'executive_orders', count(*) filter (where embedding is not null),
       count(*) filter (where embedding is null)
from public.executive_orders
union all
select 'regulations', count(*) filter (where embedding is not null),
       count(*) filter (where embedding is null)
from public.regulations;
```

The run history is recorded in `data_sync_runs` as
`sync_resource = 'policy:embedding-backfill'` (except dry runs).
