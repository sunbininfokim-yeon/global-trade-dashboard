# P1 source validation and bridge

`dart_kfa.p1_source_adapter` is the only input bridge for the separately
reported components used by strict P1 EBITDA:

`OPERATING_INCOME + PPE_DEPRECIATION + INTANGIBLE_AMORTIZATION`

It does not modify `accounts.map.json`.  The ordinary account map remains
available for P0 metrics; it cannot make a P1 depreciation/amortisation
component available.  The bridge builds a small canonical fragment from raw
OpenDART `fnlttSinglAcntAll` rows or SEC companyfacts and then merges it into
the normal canonical facts object.  Existing P1 facts are never overwritten.

## Executable manifest contract

The versioned file is `config/p1_source_validation_manifest.json` and must
have `schema_version: kfa-p1-source-validation/1`.  Its report order is a
contract, not a runtime guess:

| Provider | Order |
| --- | --- |
| OpenDART | `11014` (Q3), `11012` (H1/Q2), `11013` (Q1), `11011` (FY) |
| SEC | Q3, Q2, Q1, FY |

Only records in `verified_mappings` can produce observations.  Each verified
mapping requires the following acceptance record fields:

- `mapping_id`, `provider` (`DART` or `SEC`), `status: verified`, and `kind`
- `acceptance_record.reviewed_at`, `.reviewer`, `.evidence_ids`, and
  `.acceptance_basis`
- account mappings: `canonical_account_id`, exact `source_concept`,
  `statement`, and `separate_component: true`
- structured-row mappings: `disclosure_type`, exact `source_table_id`, and
  exact `source_row_type`

The only executable account IDs are `PPE_DEPRECIATION` and
`INTANGIBLE_AMORTIZATION`.  No `DEPRECIATION`, `D&A`, or combined component
is accepted as a substitute.  Candidate mappings must use `status:
candidate`; they are intentionally excluded from the executable specification
even if their labels look plausible.

## Raw evidence retained

Account observations preserve provider, source concept/account, filing ID,
report code/type, dates, CFS/OFS, currency/unit, source table ID, and source
row ID in canonical provenance.  Structured segment-profit and backlog rows
also retain provider, table/row IDs, mapping ID, and report provenance.

The structured adapter only accepts records explicitly marked `structure:
table` or `xbrl_table`, whose provider/table/row type exactly match a verified
mapping.  It never reads `note_text`, labels, keywords, or LLM output.

## Live-validation procedure

1. Check for `DART_API_KEY` (or the deployment binding) without printing it.
   Never recover a key from chat, files, logs, or history.
2. With a securely supplied key, run
   `python3 tools/validate_p1_live_dart.py --year 2025` (or call only
   OpenDART `https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json`) for the
   minimum evidence sample: Samsung Electronics (`005930`) and one
   non-Samsung industrial issuer selected from the local corp-code index.
   The program queries FY first, then Q3/H1/Q1 for the selected year, and
   falls back only when the FY endpoint has no data.  Record non-secret
   response metadata, receipt number, report code, exact account ID,
   statement, requested CFS/OFS scope, returned row scope, period, unit, and
   table/row identifier if the source supplies one.  Some OpenDART rows omit
   `fs_div`; retain that fact and the request scope rather than inferring a
   row-level scope.
3. For SEC, retrieve only official `data.sec.gov/api/xbrl/companyfacts/CIK…`
   data (with an identifying User-Agent), and record the accession, form,
   fiscal period, exact concept, unit, start/end, and any supplied row/table
   identifier.
4. Confirm that each component is separately reported, is a flow, has the
   same selected period/scope/currency/unit as operating income, and is not a
   combined D&A tag.  A generic `감가상각비` is combined/ambiguous evidence,
   not PPE depreciation.  Confirm structured rows come from a reported table.
5. Add an immutable evidence ID to the acceptance record and only then change
   `status` to `verified`.  Otherwise leave it `candidate` and out of the
   compute path.

`docs/P1_LIVE_VALIDATION_EVIDENCE.md` records this branch's non-secret live
validation status.  It is not evidence sufficient to promote a mapping.
