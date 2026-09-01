# Targeted Congress queue recovery

Run this once in Supabase SQL Editor **after** the deduplication fix is
deployed. It requeues only the two Congress.gov bill entries that were
dead-lettered by the former double-encoding bug; it does not reopen unrelated
failed items.

```sql
update public.policy_ingestion_queue
set
  status = 'pending',
  attempts = 0,
  available_at = now(),
  claimed_at = null,
  completed_at = null,
  last_error = null
where sync_resource = 'congress.gov:bills'
  and source_key in ('119-hr-3377', '119-hr-7194')
  and status = 'failed';
```

The result can legitimately report `0 rows` when either record was already
retried, no longer exists, or is not currently in `failed` status. Verify with:

```sql
select source_key, status, attempts, last_error
from public.policy_ingestion_queue
where sync_resource = 'congress.gov:bills'
  and source_key in ('119-hr-3377', '119-hr-7194');
```
