# Daily polling capture / validation recovery — 2026-10-20

User explicitly prioritized fixing broken collection/validation, with manual source research delegated to Cursor as an acceptable input route. This PR is a packet-free fix on main1888e017c, independent of unmerged #644/#649/#647. Branch codex/poll-capture-validation-recovery-20261020; workspace reused sequentially at us-ne-research-integration-20261020. Prior branches/commits remain saved and pushed. No state inputs/reviews/national JSON/UI/workflow/ownership exception are changed. Main merge, deployment and production workflow dispatch remain held.

## Confirmed root causes

Actions39346678472 on main34defb24: capture fetched1511 API records and saved their checkpoint, then failed `primary_and_provider_wave_conflict`. The exact MS Data for Progress Aug5–15 wave has provider1018LV, two candidates47/41, DEM/Way to Lead PAC, while the reviewed primary is three candidates44/38/7 with different commissioning metadata. No evidence permits treating these as the same ordinary question or choosing one as correct. Previously that one conflict aborted the entire nationwide supplement merge.

Validation ran678 cases with2 failures: Iowa finance-route work_status and Suffolk7/14-day tie were asserted against mutable published national JSON. The actual fixed reviewed survey audits still normalize correctly. New collection replaces state receipts and changes the set of observations, so these historical expectations need explicit reviewed fixtures rather than whatever the current live asset happens to contain.

Saved failed-run inputs: /private/tmp/poll-recovery-39346678472 (downloaded original GitHub artifact), log /private/tmp/poll-failure-20261020.log. These are audit/replay inputs, not newly collected or published data.

## Fix and safeguards

Production refresh opts into supplement-conflict isolation. Default strict callers still raise; no wholesale weakening of record validation. An isolated conflicting wave stores both exact provider record(s) and reviewed primary values in the receipt, removes the duplicate provider wave from normal input, and admits the primary observation only as `primary_provider_conflict_reference_only` with explicit exclusion reason. Neither conflicting version counts as a vote signal. Other healthy races continue. Original field/review/capture dates and primary values remain unchanged. This does not resolve or silently correct the MS questionnaire/commissioner discrepancy.

The two Iowa tests now normalize their existing original reviewed audit rows with a fixed historical date and an explicit source-review receipt. All prior tie/count/precision/missing-money assertions are retained. No live percentage or party rating is altered to make a test pass.

Focused recovery/primary/normalization49, Iowa15, finance33, election JS114, ownership14 pass; deploy-chain42 workflows pass. Added regressions demonstrate strict default conflict failure, production isolation with retained opposing versions and an unaffected healthy race, and unchanged exact-wave deduplication. Full offline polling suite and local non-publishing real capture are being run; exact final results must be read from PR/logs, not inferred from these focused results.

Actual local live capture runs `--capture-only` to /private/tmp/poll-recovery-live-20261020/capture.json, never into public/data. No new API key is needed. A validated checkpoint may be replayed locally with --retry-capture and a temporary output directory. Publication is not authorized by local success. Cursor research inputs can continue to use state packets; source research, collector health, data review and deployed freshness remain separate statuses.

## Actual non-publishing recovery result

Real capture-only succeeded: captured_at2026-10-20T12:12:22.801429+00:00, API1511 records,1545 with supplements. The sole primary/API conflict is MS and its complete opposing provider snapshot is retained in the receipt. Replaying that exact checkpoint with --retry-capture into a temporary directory succeeded without new requests or advanced timestamps:86 races /212 observations,134 eligible historical observations and78 reference observations. Recent7-day comparison covers2 races and14-day18 races. The deployed165→local212 increase is pending reviewed input backfill, not47 newly released polls. The captured_at equality and MS conflict's explicit ineligibility were asserted. Production public assets and workflows remain unchanged.

Full suite is still running at this checkpoint; final result will be recorded separately. No requirement to merge earlier unmerged election expansions before this recovery: its base is current main and its diff contains no state packets.
