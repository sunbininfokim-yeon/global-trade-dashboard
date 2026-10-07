# P1 live validation evidence

Date: 2026-08-27

No live DART credential was used by this branch.  The implementation checks
for a secure runtime credential without printing it; no key is read from chat,
repository history, source files, or test fixtures.

Status: **blocked pending securely supplied `DART_API_KEY` or deployment
binding**.

Consequently, `config/p1_source_validation_manifest.json` contains zero
verified production mappings and zero promoted candidate findings.  Offline
fixtures use a dedicated test-only verified manifest; they are contract tests,
not real-filing validation evidence.

No SEC concept is promoted here either.  A future live SEC check must use only
official `data.sec.gov` companyfacts metadata and satisfy the acceptance
record fields in `P1_SOURCE_VALIDATION.md` before any manifest update.
