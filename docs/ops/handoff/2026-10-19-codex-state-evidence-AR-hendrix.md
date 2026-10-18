# 2026-10-19 Codex — AR Hendrix/Talk Business Senate release

AR only. Checkout `/Users/yeoninair/Documents/해운 데이터/us-poll-AR-source-coverage-20261019`; branch `codex/poll-ar-source-coverage-20261019`. Same packet-free base `402f054e`, dependency #616. Does not stack on NM #617. Starting main b408ac68.

New public API capture 2026-10-18T16:20:04.208175+00:00 contains five AR rows. Original Talk Business & Politics commissioner report fetched 2026-10-18T12:10:26.682121+00:00; SHA and URL retained in the state audit. Field 10/8–13, LV n=709, SMS/live calls, weighted ethnicity/education/gender/geography, reported proportion MOE 5pp. Article publication 10/15 is distinct from API registration 10/16.

Original primary candidate values: Cotton 50%, Shoffner 41%, Wadlin 4.5%; undecided 4.5%. API rounds Wadlin to 5%. Exact provider snapshot correction preserves the raw 5 and displays the original 4.5 only for this reviewed question. Any provider metadata change requires review. 7/14-day summaries at as_of 10/18 are REP single-poll numeric leads. No significance/winner/probability/accuracy grade is claimed.

The publication discloses both a Republican consultant and a Democratic-party-active academic in question design/analysis. Their affiliations remain in sponsor_review. Detailed weighting tables/response rate/full sampling frame remain missing; this is not an impartiality or methodological certification. Full official ballot not obtained; third candidate party remains null until roster review, despite the original L label being disclosed in the review. Existing roster coverage is not upgraded and no race becomes unopposed or confirmed.

## New finding outside the API

The same primary publisher has a governor release (Sanders 51 / Love 32 / Shelby 11, n=709, field 10/8–13) absent from the saved API response. Public web reading finds the real article, but direct pipeline HTTP returns 403 and publication metadata/document fingerprint could not be captured. It is explicitly recorded as `primary_report_discovered_automated_fetch_403`, not an eligible poll or successful collection. URL and observed values are in the audit. No access challenge was bypassed and no date was invented. This is a remaining source transport problem, not absence of a published poll.

## Validation and handoff

Five AR regressions pass: raw preservation, exact-value correction, metadata conflicts held, later releases stay references, partial roster preserved. Temporary packet rebuild `/private/tmp/poll-ar-preview/data` admitted the release; all non-AR races remain identical. Finance not recollected. Only AR packet/audit/test/handoff change. No national generated files, common policy/code, UI/workflow, merge/deploy/production dispatch. Further full-suite results appended when complete. Merge foundation #616 first; retarget independent NM and AR PRs to main afterward in either order.

Final validation: polling 595/595, finance 68, election JS 92, ownership 13 passed; deploy chain 42 workflows. State scope valid. Independent Draft PR #618. Common #616 documentation advanced to 23ebc5fa; original branch point remains 402f054e. Current head/base and CI must be rechecked on retarget; no merge or deployment.
