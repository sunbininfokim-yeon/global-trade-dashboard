# P2-B OpenDART document-table adapter

The single-account financial API does not provide a stable, complete source
for order backlog or segment profit.  P2-B introduces a narrow document path:

```text
OpenDART document.xml archive
  -> candidate HTML/XML tables (not financial data)
  -> exact reviewed table mapping manifest
  -> P1 structured_disclosures
  -> P2 industry disclosure status
```

## Safety boundary

- `fetch_dart_document()` reads a caller-provided credential only in memory.
  It does not write a request URL, archive, raw response, or credential.
- Candidate tables are review material only.  They never enter calculation.
- A verified mapping is receipt-specific and must name the exact report ID,
  source table ID, row selector, fiscal year, period end, consolidated scope,
  currency, source scale and report type.
- Numeric cells containing a footnote or other text are rejected rather than
  stripped heuristically.
- The production manifest starts with zero verified mappings.  A mapping may
  be added only after checking the rendered filing and the source archive.

## What it can and cannot do

It can produce P1 `backlog_order_book` and `segment_profit` rows with table
and row provenance once a reviewer approves a mapping.  It cannot infer a
table's meaning from captions or prose, read a scanned image, translate a
note into a number, or fill an unavailable company with an estimate.

## Review and promotion procedure

1. Fetch the intended receipt with a secure runtime `DART_API_KEY`.
2. Record candidate table IDs and independently check table headers, unit,
   CFS/OFS scope, period, and row meaning in the filing.
3. Add an issuer/receipt-specific `verified` entry to
   `config/p2_dart_table_manifest.json`.
4. Add a redacted fixture and regression test proving the exact row, scale,
   provenance, and P1 output.
5. Keep a rejected or unresolved table out of `verified_mappings`.

This adapter is the input boundary only.  A later Worker must call it with a
secret binding and return its P1-compatible output; it must not replicate its
parsing or map candidate tables in JavaScript.
