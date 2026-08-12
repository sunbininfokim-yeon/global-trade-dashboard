# Credit data sources (free-only policy)

**Audience:** Cursor (engine)  
**Module:** `dart_kfa/credit.py` + `ma_metrics` coverage cells  
**Rule:** if a single-name field is not free **and** stable, omit it with `status: "omitted"` — never scrape news as a pseudo-feed.

## Included

| Field | Source | Stability |
|-------|--------|-----------|
| Interest coverage (EBIT ≈ OI / interest) | SEC companyfacts / DART map → `INTEREST_EXPENSE` | High when tag present |
| Effective interest rate proxy | interest / interest-bearing debt stock | Medium (accounting avg, not YTM) |
| Debt filing index | SEC `submissions` 424B*, FWP, 8-K 1.01/2.03, S-3* | High (index only) |
| Coupon / principal / maturity text | Optional HTML parse of 424 primary doc | Medium (null if parse fails) |

## Explicitly omitted

| Field | Why |
|-------|-----|
| Agency ratings (S&P/Moody’s/Fitch time series) | No free stable single-name API; document text has high false positives |
| Single-name CDS | Markit-class; news blogs not reliable; do not confuse with **sovereign** CDS in macro monitor |
| Planned future issue size | Only appears if issuer files; no continuous free “pipeline” feed |

## CLI

```bash
cd "New for anti/scripts/dart"
python3 fetch_live.py --ticker AAPL --print
python3 fetch_live.py --ticker MSFT --no-credit-docs --print   # filings index only
python3 fetch_live.py --ticker AAPL --no-credit --print
```

Output lives on `company["credit"]` (`schema: kfa-credit-v1`). UI wiring is Claude’s job.

## Korea (DART)

Coverage ratios work when interest tags map. Filing-index enrichment is US-SEC only until a free DART bond-event API is confirmed.
