# P1 live validation evidence

Date: 2026-08-27

## Outcome

Status: **validated no-promotion**.  The production manifest remains at zero
verified mappings.  There is no strict-EBITDA value from this source endpoint;
the engine must continue returning `null` with the missing-components reason.

The only live source called was OpenDART's official
`fnlttSinglAcntAll.json` endpoint.  The validation program read its credential
only from the process environment.  It neither writes a raw payload/request
URL nor prints, stores, or includes the credential in the generated evidence.

The committed, redacted evidence is
`tests/fixtures/p1_live_dart_2025_evidence.json`; it retains public receipt,
account, period, scope-request, statement, and currency metadata only.  It is
also asserted by `tests/test_p1_live_validation.py` without making a network
request.

## 2025 CFS evidence

The company set came directly from `config/universe_seed.json`: Samsung
Electronics (`005930` / `00126380`) and the non-Samsung industrial issuer HD
Korea Shipbuilding & Offshore Engineering (`009540` / `00164742`).  For each,
the annual report was queried first and succeeded, followed by the available
Q3, H1/Q2, and Q1 endpoints.  Therefore no older-year fallback was used.

| Issuer | 11011 FY receipt | 11014 Q3 receipt | 11012 H1 receipt | 11013 Q1 receipt | Result |
| --- | --- | --- | --- | --- | --- |
| Samsung Electronics | `20260310002820` | `20251114002447` | `20250814003156` | `20250515001922` | Operating income: `dart_OperatingIncomeLoss` / `영업이익` (IS, KRW); no D&A candidate row |
| HD Korea Shipbuilding & Offshore Engineering | `20260318001394` | `20251114002658` | `20250814003906` | `20250515001159` | Operating income: `dart_OperatingIncomeLoss` / `영업이익` (IS, KRW); no D&A candidate row |

Every successful request specified `fs_div=CFS`.  OpenDART's returned rows
had `fs_div: null` (preserved in the fixture), so the request scope is recorded
separately as `requested_fs_div: CFS`; a blank row field is **not** silently
treated as an OFS row.  This nuance does not relax the production adapter: no
account mapping was promoted, so no endpoint row can enter the strict formula.

At every matching endpoint, operating income was present but neither an
explicit `유형자산…감가…` PPE component nor an explicit
`무형자산…상각…` intangible component was reported.  There were no combined
D&A rows to consider as a substitute.  Thus each evidence ID
(`dart-2025-{issuer}-{report_code}`) has:

```text
strict_formula_available_at_endpoint = false
reason = missing:separately_reported_ppe_depreciation_or_intangible_amortization
```

## Mapping decision

No DART account ID/name was promoted.  Specifically, no global or
issuer-specific mapping for `PPE_DEPRECIATION` or
`INTANGIBLE_AMORTIZATION` is justified by these filings.  The production
manifest intentionally continues to contain:

```json
{"verified_mappings": [], "candidate_mappings": []}
```

The test-only verified manifest remains a contract fixture, not live evidence.
A later promotion requires a source that reports both components separately
with the same endpoint, requested scope, currency/unit, and period as the
operating-income fact.  If it is issuer/extension specific, it must carry an
explicit issuer restriction in the executable adapter before promotion.
