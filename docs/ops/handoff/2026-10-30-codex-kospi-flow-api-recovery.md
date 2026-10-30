# KOSPI stock-market investor flow recovery — 2026-10-30

Branch: `codex/kospi-flow-api-recovery-20261030`. Codex data-code repair;
Claude owns UI, workflows, merge and deployment.

## Verified failure and repair

The production asset at
`https://global-trade-dashboard.sunbin-info-kim.workers.dev/public/data/investor_price_levels_v1.json`
still serves 157 KOSPI index-flow days ending 2026-09-16, all carried forward.
The legacy Naver `investorDealTrendDay.naver` page returns HTTP 410.
The strict KRX stock-only loader remains valid, but its required dataset is
`krx_12008_kospi_stock_investor`; an ETF-inclusive export must not be renamed
or substituted just to satisfy that path.

Replaced the failed HTML fallback with:

```text
https://m.stock.naver.com/api/index/KOSPI/trend?bizdate=YYYYMMDD
personalValue -> retail_net_eok
foreignValue -> foreign_net_eok
institutionalValue -> institution_net_eok
```

These values are already 억원. The public-extras adapter converts them to KRW
with ×100,000,000 and uses the same loader; it no longer calls the dead page.
This Naver path does not need `KRX_MONTH_PASTE_TOKEN`.

The API echoes holiday/future dates with zero amounts. The repair queries only
actual, finite, positive KS11-close dates, verifies the echoed date, and joins
those same closes without a second price request. Missing/malformed responses
are not replaced with zero; previous same-scope observations survive failures.
Three consecutive failed API requests stop the scan and record unavailable
dates. A valid zero on an actual trading date is preserved. `fetched_at` records
retrieval time separately from the last observation date.

## Backfill included

- Index snapshot: 180 dates, 2026-02-03 through 2026-10-30.
- Newly restored gap: 28 trading dates, 2026-09-17 through 2026-10-30.
- No holiday observations; no carried-forward days in this recovered snapshot.
- Compared with the prior snapshot: 152 overlapping dates, 150 exact matches
  for all three investor amounts; two dates have a one-억원 difference in one
  actor (2026-02-20 retail and 2026-07-09 institution). Current source values
  are retained without forcing them to match the older rendering.
- The rolling 180-day window drops the five oldest dates from the prior
  157-date block. This UI asset is a rolling snapshot, not the source archive.
- All other top-level JSON fields, all 19 ticker blocks, and their timestamps
  remain unchanged. `INVESTOR_PRICE_LEVELS.md` was regenerated from that report.

The default existing builder uses the repaired loader. For an independent
index-only recovery, bypassing the stock-universe screen:

```bash
cd "New for anti/scripts/market_microstructure"
python build_investor_price_levels.py --live --index-only --page-size 180
```

This requires an existing ticker report, updates only `kospi_index_levels`,
and does not bump ticker/report-wide timestamps. No fresh observations means
nonzero exit with both existing JSON and markdown left unchanged.

## Validation

- `test_kospi_market_flow_krx.py`: 15 tests passed, including the real API
  shape, sign/unit mapping, date validation, holiday exclusion, null handling,
  carry-forward, bounded outage and index-only write preservation.
- `test_investor_universe_failure.py`: 17 tests passed.
- `validate_ui_contracts.py`: passed against current main assets plus the
  recovered index snapshot.
- Unrelated JSON fields equal the prior report; investor bin sums equal the
  corresponding daily observations; `git diff --check` passed.
- No UI, Worker or workflow files changed. Browser rendering after production
  deployment remains a Claude verification step.

## Claude deployment handoff — PR #739 also needs repair

PR #739 is OPEN. Its guard fails at **Every data collector is chained to
deploy**, run `41022914642`, with this exact error:

```text
'Investor price levels daily' commits to main but is not in deploy.yml workflow_run.workflows -- its data never ships
```

Add the exact workflow name `Investor price levels daily` to
`.github/workflows/deploy.yml` -> `on.workflow_run.workflows` in the Claude PR,
then rerun the deploy-chain check. Merely splitting the schedule does not
establish automatic deployment.

After both PRs merge, dispatch `investor_price_levels_daily.yml`, confirm the
data commit and subsequent deployment, and read back the public asset's
`kospi_index_levels.date_end`, `n_days`, `source`, and `carried_forward_days`.
Check the KOSPI index view in the browser. Index data should reach 2026-10-30
or the latest successfully observed day rather than remain at 2026-09-16.

The private-repository checkout is already `continue-on-error`; a failed PAT
does not prevent this Naver fallback from collecting. However, the workflow's
final reporting step may still turn the run red after a successful commit.
PAT repair remains necessary for the separate KRX private-repository inputs.
The UI's last-observation notice remains Claude's separate task.
