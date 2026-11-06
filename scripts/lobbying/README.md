# Lobbying and policy pipeline

This collector ingests **all available countries, clients, industries and history**.
Country/industry choices in the UI are query filters, never intake allowlists.
Official filing existence, extracted text, structured activity, reviewed cases and
confirmed policy links have separate completeness states.

## Sources and sink

- FARA daily bulk: Registrants, ForeignPrincipals, ShortForms, RegistrantDocs.
- LDA official filings REST API: unfiltered pagination plus a separate listing refresh.
- Supabase `lobby_records`: official metadata/raw JSON, current text and source identities.
- `lobby_record_versions`: immutable observed metadata and PDF text revisions.
- `lobby_activities`: LDA issue blocks, not individual meetings.
- `lobby_policy_links`: explicit references, with unresolved Congress kept ambiguous.
- `lobby_sync_state`: durable per-stream cursor, lease, expected inventory and failures.
- All tables/functions are service-role-only; the Worker exposes bounded read routes.
- There are no inserts/triggers on existing policy/mail tables and no notification sends.

Migration: `supabase/migrations/20261105122419_lobbying_pipeline.sql`.
Runtime guards: `supabase/migrations/20261106015110_lobbying_runtime_guards.sql`.
Newly collected policy IDs are rechecked against unresolved explicit references.
The DB-wide default ingestion budget is 6 GiB; reaching it preserves cursors and
holds new ingestion instead of silently expanding storage indefinitely.

## Scheduled collection

`.github/workflows/lobbying_policy_refresh.yml` runs every four hours on main.
Separate FARA inventory, LDA and PDF jobs continue from DB state. Batch/page/PDF
limits bound a run; the next run resumes. Finishing one source traversal records
a completed pass; it does not certify text extraction or reviewed content complete.

FARA identity is based on the official PDF URL, registration identity or relation
identity. Exact duplicate rows collapse, conflicting observations remain together,
and malformed CSV rows are preserved with a review marker. Office-only documents
retain their source sentinel and are never given a fabricated PDF URL. FARA dates
outside a plausible source year remain null with their original value preserved.

Source access failures hold the cursor and keep prior rows. LDA next links and
source redirects are restricted to official hosts before credentials are sent.
LDA payload/schema/auth must be verified live; fixture tests are not source success.
All original LDA amendments are preserved. No cross-filing spend aggregation is
provided because effective revision and in-house/vendor overlap need review.

FARA unknown-principal documents show **registration-scope related countries**,
which must not be read as that document's actual beneficiary. Priority country
aliases are normalized; other source countries remain in `country_raw`. All remain
in the unfiltered inventory. The initial country shortcuts are KR/JP/CN/TW/HK/US.

PDF job uses Poppler, with a pypdf fallback for local extraction. Image-only PDFs
are `ocr_required` and remain incomplete. Full contact tables are not reconstructed
from arbitrary PDF layouts. PDF pages and raw-file hash support source review.

Raw ZIP/PDF receipts are retained outside git and uploaded as Actions artifacts
for 30 days. DB versions preserve observed metadata/text beyond that period.
This is not permanent raw-binary archival; durable object storage can be connected
before a requirement to retain every historical original binary indefinitely.

## Secrets and manual execution

Use existing `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` repo secrets.
`LDA_API_KEY` is optional for anonymous access but recommended for sustained
collection. It is a separate key from Congress/data.gov. Set it through GitHub
Secrets or the local environment; do not add it to source files.

```sh
python3 -m unittest discover -s scripts/lobbying/tests -v
node --test scripts/lobbying/tests/api.test.mjs
python3 scripts/lobbying/sync.py --source all --cache-dir /private/tmp/lobbying-source
```

Local collection requires the operator to supply sink secrets explicitly.
Actions branch executions are blocked from production writes by job and script.
No source/cache file is committed. A re-run can replay completed batches safely.

## Product routes

- UI: `/policy/us/lobbying`, `/policy/us/lobbying/<record-id>`.
- Reviewed case: `/policy/us/lobbying/case:coupang-korea-data-and-trade`.
- Read API: `/api/us/lobbying/{records,coverage,cases}` and record/case details.
- Existing bill and EO detail screens show confirmed lobbying references.
- Policy → case and automatic semantic case matching remain separate from explicit
  identifier links; curated case receipts do not imply lobbying causation.

## Remaining evidence boundaries

Full metadata intake is implemented. Historical passes take multiple scheduled
runs. Text/OCR and reviewed activity coverage are reported independently. No
complete-history, full-text, policy-effect or case-specific spend claim follows
from a successful bounded run. The case register is reviewed and static; its
review date is displayed, and source changes need a fresh case review.
