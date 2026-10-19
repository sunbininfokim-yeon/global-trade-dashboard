# 2026-10-19 FL wave2 — MDW joint release

Owner Codex; stateFL, checkout `/Users/yeoninair/Documents/해운 데이터/us-poll-FL-source-expansion-20261019`, branch `codex/poll-fl-source-expansion-20261019`. Independent start basef0878e183670c5c7c6f888468c05e303bc9e4883 (#616). FL/MO/GA PRs target packet-free common wave2-route base; KY updates existing independent #622 on #616. No state-on-state dependency. New shared source policy is separate, no source/JS/workflow code in this state diff.

## Verified observation

Original MDW/EDGE release datedOctober14; October4–10 LV2351. Governor Donalds45.9/Jolly43.8; Senate Moody47.6/Nixon42.4. Exact decimals replace API rounding with raw values retained. Senate API800 is corrected to2351 using existing staged answer→metadata reviews: immutable original hash binds answer repair, an exact intermediate-record hash binds sample repair, and final normalized fingerprint binds all values. No common correction guard is relaxed. Reported2.8 precision stays reported disclosure, not automatically inferred question-level probability error. Joint author EDGE is distinct from an undisclosed external funder.

Two exact reviewed questions enter14-day numeric aggregation atOctober18UTC; outside7-day. Future API MDW releases have a bounded reference route through the separate common route PR; new releases do not inherit exact-source lead approval. Five new state tests pass including changed sample/sponsor/value, corrupted intermediate hash and actual prior-vs-new transport clocks.

API actually requested anew2026-10-18T23:03:56.165943+00:00:1511rows and zero row additions/changes against prior capture. New request is not claimed as new poll publication. Provider capture clock is fresh; legacy primary documents/fielddates/receipts are preserved from earlier verified captures, not marked re-fetched. State provider rows and source response hashes are saved in packet. New primary document receipt is in `FL-wave2-20261019.json`; GA additionally distinguishes web review from failed direct HTTP. External spending, candidate roster certification and money dates are not refreshed by this polling work; no missing amount is zero-filled.

## Pipeline and review

Merged input uses existing daily collector and normalization. Exact source review checks the current imported record, not every future statement by an institution. Finite primary documents are automatically rechecked; changed/unavailable documents preserve original dates as references, while candidate/party/question/duplicate conflicts remain held. Requested7/14window contract and latest institutional wave dedup remain.

Temporary combined replay includes prior #617–#624 inputs plus these changes. Current measured total212 cumulative observations/133eligible/79reference in41states (was207/129/78 in40); fresh14-day observed races including references House7/Senate11/governor10. These are not forecast or confirmed seats. Combined validation results are recorded in common wave2 handoff/PR; state source tests listed above passed. No national generated JSON committed. No main merge/deploy/production workflow dispatch or reset click. Next work requires current unassigned-state priority; this PR does not start another state.


Final local integration:polling603 +live30 +election/governor-matchup22, finance68, election JS92, ops16 and deploy-chain42 workflow links. Selected-state replay/projections succeeded without errors; only temporary generated assets were written. PR remote validation remains a separate status. Exact PR base for FL/GA/MO is the packet-free wave2 foundation; KY remains independent on #616. No deployment.
