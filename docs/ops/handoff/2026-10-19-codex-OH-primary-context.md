# 2026-10-19 — OH primary polling and candidate context

Owner Codex. Independent branch `codex/poll-oh-primary-context-20261019` targets the packet-free `codex/us-election-context-data-20261019` foundation, not another state's research. Changes are only OH packet/audit/test/handoff. No national generated files, UI, workflow, main merge or deployment.

## Actual source work

RealClearPolling's public listing and Race to the WH corroborate the same Bowling Green release. The [BGSU university page](https://www.bgsu.edu/arts-and-sciences/democracy-and-public-policy-research-network/bgsu-poll.html) was fetched200; actual HTML SHA/time are recorded. It explicitly reports Sept29–Oct9 fieldwork,1,000 likely Ohio voters, online BGSU/YouGov mode, reported3.95-point margin and major-candidate vote preference: Senate Brown48/Husted42; governor Acton50/Ramaswamy44. These are not the separate expected-winner answers (Senate48/48; governor55/43), nor a verified victory forecast.

The exact existing API rows `us-202bow14c3613e` / `gov202bow8bc2f1b8` now receive finite primary reviews. Original university HTML verifies the major toplines and method summary. The full scholarly PDF returned403 and remains marked unavailable; no alternate private path was tried. Minor-candidate answer values remain explicitly provider-only; no Bill→William Redpath nickname or unverified party is invented. Missing full question wording, complete weighting/frame, question sample disclosure and funder detail remain marked. This promotes two existing reference observations, not two newly collected surveys. On Oct19 they are inside14days, outside7days; the default window remains7days.

The public provider API was actually requested again on2026-10-19T08:18:23.120894+00:00:1,511 national rows,53OH rows, same IDs/content as the prior capture. A normalized parsed-JSON digest is labeled accordingly; no original HTTP-body SHA is fabricated. Existing Suffolk primary supplement `primary-suffolk-oh-senate-20261002` retains its2026-10-08 original review and the separate actual PDF recheck receipt. It is not rewritten as today's new poll.

## Candidate context

Four OH current-roster people receive per-field profile entries. Brown's exact DOB and public-service/teaching history come from the official House historian; Husted's official Senate biography supports the listed public-service/economic-development career. Acton's campaign page supports self-reported physician/public-health/professor/cabinet roles. Ramaswamy's own biography transport was unavailable and the career field stays null. Missing ethnicity and military service are null for all4. No inference from photos, names, family occupations or generic campaign praise is used. Brown's age is73 on Oct19, computed against the verified birthday, not a fixed age string.

The full real board builder joins all4 to exact current senator/governor rosters, preserving the other candidates. Current incumbent DeWine's term limit is a separate governor-context record; it does not add him to this ballot.

## Isolation and integration validation

OH-only replay leaves489 other live-race records,70 other history-race records and the national capture clock unchanged. `house_poll_focus` is intentionally recomputed using the integrated collector; other states' focus rows stay identical. Eligible-focus count16→17 reflects the shared commissioned-poll policy already in #616, not a new House poll in this packet. Suffolk's original review stays2026-10-08. Replay is not a new source collection.

Six OH regression tests cover14/7-day eligibility; expected winner vs preference; minor-candidate verification limits; changed raw fields and new IDs; old Suffolk receipt preservation; profile identity/age/nulls. A new provider ID may survive the separately reviewed publisher route as reference-only but cannot inherit this primary review or lead eligibility. Exact existing IDs with changed sample, dates, sponsor or answers are held. State scope guard and combined validation results are recorded on the PR; local checks are not a deployment claim.

Publication order: shared foundation first; OH independently afterward. Previous national source policy #616 / route #627 is tested together in a temporary integration snapshot. Generated national JSON is rebuilt by the integrated publisher, never manually merged. Missing source rights, future waves, complete candidate biographies in other states and state governor campaign-fundraising adapters remain separate work.
