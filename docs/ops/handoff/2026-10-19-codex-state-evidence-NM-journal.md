# 2026-10-19 Codex — NM House Journal poll admission

State NM only. Checkout `/Users/yeoninair/Documents/해운 데이터/us-poll-NM-source-coverage-20261019`; branch `codex/poll-nm-source-coverage-20261019`. PR base `402f054e` (packet-free national source foundation #616); base main `b408ac68`. No other unmerged state's inputs in the base.

## Actual evidence

New public API request captured 2026-10-18T16:20:04.208175+00:00; six NM provider records saved. Existing NM primary supplement and its 2026-10-09T10:16:59.119404+00:00 capture receipts remain at the original dates; they were not recollected or claimed as newly verified.

Albuquerque Journal commissioner-original report, published October 15, with Research & Polling Inc., was fetched at 2026-10-18T12:10:26.784939+00:00. Original candidate charts were separately fetched and visually inspected. All source URLs, actual check times and SHA-256s are in `NM-journal-20261019.json`.

- NM-01: Melanie Stansbury 53%, Ndidiamaka Okpareke 35%, n=380, reported proportion MOE 5.0pp.
- NM-03: Teresa Leger Fernandez 53%, Martin Zamora 39%, n=362, reported proportion MOE 5.2pp.
- Field October 1–9, live professional calls (97% cellular/3% landline), prior 2022/2024 voters plus new registrants saying likely to vote, stratified by county and weighted. Provider record date October 16 is separate from the original publication date.

Both were blocked by legal-name versus published-name mismatches. Exact aliases bind the same district/party candidate to existing canonical roster names and FEC IDs. No fuzzy matching, canonical-name rewrite, roster certification upgrade, winner or new unopposed status. Existing ballot review dates stay unchanged; alias review has its own current clock.

Each release has exact provider snapshot and normalized fingerprint, source-role admission, primary candidate values, question n and reported precision. Changed provider metadata is held for renewed review. They become single-source DEM numeric leads in the 14-day window at as_of October 18; neither is within seven days. A reported proportion MOE is not used as a candidate-margin significance test or election probability.

## Verification / publication boundary

14 NM regression tests pass (10 existing + 4 new). State packets and projections regenerated only into `/private/tmp/poll-nm-preview/data`. Non-NM races and the VA receipt are identical to their original public inputs. Original NM governor supplemental field end September 30 remains. State-owned release audit, NM packet, NM test and this handoff are the only changes.

Finance was not newly collected. Federal FEC and governor independent expenditure gaps are unchanged. No national generated JSON, shared policy/code, UI, workflow, merge, deployment or production dispatch changed. The national #616 foundation must merge first; this state PR can then be retargeted to main. Other state PRs must branch from that same foundation, not this NM branch. Further tests and PR details are appended after completion.

Final validation: polling 594/594, finance 68, election JS 92, ownership 13 passed; deploy chain 42 workflows, state scope valid. Independent Draft PR #617. Common foundation branch has advanced by documentation only to 23ebc5fa; NM branch point remains 402f054e. Actual PR base must be checked again when retargeting. No merge/deploy.
