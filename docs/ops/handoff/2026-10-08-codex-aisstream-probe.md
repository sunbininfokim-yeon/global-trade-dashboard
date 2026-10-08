# 2026-10-08 — AISStream private reception diagnostic

## Authorized scope

User approved a separate one-off test branch and execution using the existing
GitHub repository secret. No need to resend the key. No main merge, production
deployment, cron, existing workflow changes, public vessel records or shipping
model/UI changes. No PR created; do not merge this diagnostic into production.

- Branch: `codex/aisstream-probe-20261008`
- Test commit: `d566363283c64de68343ca734d993388ebf4492c`
- Base: `7b57a4e215841d0ce16dd302ec863e447c7190bd`
- Run: https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/37724751843
- Conclusion: success; local and runner unit checks: 11 passed.

## Actual reception, not mock data

- Window: 2026-10-08 12:52:29–13:07:30 KST (03:52:29–04:07:30 UTC).
- Actual WebSocket connected time: 898.2 seconds; one attempt, one subscription
  confirmation; no transport error recorded.
- Received 9,504 AIS messages, including 7,506 position-message frames.
- 29 messages rejected by diagnostic validation; 7,481 regional positions accepted.

| Diagnostic rectangle | Position messages | Unique MMSI observed | Checksum-valid IMO available |
|---|---:|---:|---:|
| Persian Gulf inner area | 0 | 0 | 0 |
| Hormuz | 0 | 0 | 0 |
| Gulf of Oman outer area | 0 | 0 | 0 |
| Rotterdam control | 6,837 | 1,706 | 228 |
| Singapore control | 644 | 214 | 67 |

The 1,920 latest-position records have parseable provider timestamps. Rounded
receipt-minus-provider-time lag: median 2 seconds, p95 3 seconds, maximum 7
seconds. This supports feed recency, not independently verified position accuracy.
Valid IMO was available for 295/1,920 positioned identifiers; an IMO checksum
alone does not verify identity. Controls include different AIS vessel classes,
not only the five PortWatch merchant categories. MMSI 200000000 was among the
identifiers, illustrating why valid numeric format is not identity verification.

## Decision and limitations

The secret and streaming connection worked. Focal-region vessel positions were
**not observed in this 15-minute sample**, not proven to be zero vessels or a
permanent absence of AISStream regional coverage. Coverage cause is unresolved.
This sample does not establish reliable Hormuz inventory, individual IDs there,
entrance/exit tracking, inferred gap crossings, or reconstruction of October 4.
Do not enable these as observed features based on this result.

No vessel census, transit count, crude barrels, DWT/TEU or AIS-off intent inferred.
Broad AIS cargo codes cannot separate container from dry-bulk vessels; tanker
codes do not establish crude cargo. Reference:
https://www.navcen.uscg.gov/ais-class-a-reports

Future options require a separate user decision: longer focal sampling,
provider coverage confirmation, or an approved alternate source. Do not start
continuous collection or publish raw data without approval/rights review.

## Private artifacts

`aisstream-private-reception-probe` contains `summary.json` and
`observed_vessels_private.json`. Repository access checks apply; artifact expires
after three days. Files were downloaded to a temporary local directory for
verification, not committed or copied to `public/data`. Key never extracted or
printed. Only this aggregate operational note is committed on the test branch.

The completion-record commit touches docs only, outside probe push path filters;
it does not start a second sample. Leave the existing production workflows,
ownership guards and stopped policy collectors untouched.
