# 2026-10-19 Codex — nationwide publisher reference collection

User scope: expand real polling coverage nationwide, including credible unregistered pollster spellings and regional media. Betting markets remain deferred. No merge/deploy/workflow dispatch authorized.

Checkout: `/Users/yeoninair/Documents/해운 데이터/us-poll-national-source-coverage-20261018`; branch `codex/poll-national-source-coverage-20261018`. Started at main `a561fe18`; remote main checked as `b408ac68`. Packet-free foundation; no UI, workflow, national generated JSON or state evidence input changes.

## Behavior

- Existing selected sources and exact-release reviews retain precedence and eligibility. New publisher identity checks add a separate reference-only lane; unknown sources do not approve themselves. Candidate identity, primary/general date, population, percentages, RCV and internal-poll guards remain.
- 22 spellings / 17 publisher groups: BGSU, Saint Anselm, UMass Lowell, UT Austin, UH Hobby, MSU IPPSR, UMBC, Wesleyan, Hendrix/Talk Business, Research & Polling/Albuquerque Journal, SurveyUSA/KSTP, MassINC/Commonwealth Beacon, co/efficient, ActiVote, Targoz/JMI, Glengariff/Detroit Chamber, and one exact YouGov Iowa document.
- University/primary publisher identity evidence includes actual HTTP receipt SHA-256 and original check time. Shared CloudFront/Google/social storage cannot qualify by host alone. The policy does not declare accuracy grades, AAPOR certification or future-release individual verification.
- Current API values from these routes are stored as publisher-identified references. Missing n stays null. Party-sponsored API flags remain explicit references; internal polls still require individual exact primary review. Each individual verified release can override the reference lane; another future release remains reference until separately reviewed.
- Daily refresh already reads this policy via `polls.read`; no manual daily run is required after the foundation is merged and its ordinary publication/deployment completes. This PR is not yet live. Sources missing from the API still require a primary adapter or exact reviewed supplement; this is not a generic all-site scraper.

## Actual same-input comparison

Capture: `2026-10-18T16:20:04.208175+00:00`, as_of `2026-10-18` (UTC); source `https://api.votehub.com/polls?subject=2026&from_date=2025-01-01&to_date=2026-10-18`. 1,511 real provider records. Both runs use the same nationwide target/catalog, existing state overlays and quality reviews. This comparison omits primary supplements in both runs, so it must not be compared directly to the deployed board total.

| Metric | Before | After |
|---|---:|---:|
| Accepted API observations |129|152|
| Eligible API observations |97|97|
| Reference API observations |32|55|
| Newly visible states |—|11: AR, CT, FL, IA, MA, MD, ME, MN, NH, OH, TX|
| New observations by office |—|Senate 11; governor 12|

NM House 01 and 03 additionally fail exact candidate matching because the roster carries full legal names while the poll uses shortened names. Their reviewed aliases and exact-release reviews belong in a separate NM PR, not a common fuzzy-name rule.

## All-state API coverage audit

Numbers are observed races / scheduled targets, followed by recent-14-day observed races in parentheses. References are included in observed counts, never silently counted as leads. Zero here means no accepted observation in this capture, not a zero candidate value. An office with 0 scheduled races is not fabricated. CNU and existing primary supplements are excluded from this table.

|State|House|Senate|Governor|
|---|---:|---:|---:|
|AK|1/1 (0)|1/1 (0)|1/1 (0)|
|AL|0/7 (0)|0/1 (0)|0/1 (0)|
|AR|0/4 (0)|1/1 (1)|0/1 (0)|
|AZ|0/9 (0)|0/0 (0)|1/1 (0)|
|CA|3/52 (1)|0/0 (0)|1/1 (0)|
|CO|0/8 (0)|0/1 (0)|0/1 (0)|
|CT|0/5 (0)|0/0 (0)|1/1 (1)|
|DE|0/1 (0)|0/1 (0)|0/0 (0)|
|FL|3/28 (0)|1/1 (0)|1/1 (1)|
|GA|0/14 (0)|1/1 (0)|1/1 (0)|
|HI|0/2 (0)|0/0 (0)|0/1 (0)|
|IA|0/4 (0)|1/1 (1)|1/1 (1)|
|ID|0/2 (0)|0/1 (0)|0/1 (0)|
|IL|0/17 (0)|0/1 (0)|0/1 (0)|
|IN|0/9 (0)|0/0 (0)|0/0 (0)|
|KS|0/4 (0)|1/1 (1)|1/1 (0)|
|KY|0/6 (0)|0/1 (0)|0/0 (0)|
|LA|0/6 (0)|0/1 (0)|0/0 (0)|
|MA|0/9 (0)|1/1 (0)|0/1 (0)|
|MD|0/8 (0)|0/0 (0)|1/1 (0)|
|ME|0/2 (0)|1/1 (0)|1/1 (0)|
|MI|0/13 (0)|1/1 (0)|1/1 (0)|
|MN|1/8 (1)|1/1 (1)|1/1 (1)|
|MO|0/8 (0)|0/0 (0)|0/0 (0)|
|MS|0/4 (0)|0/1 (0)|0/0 (0)|
|MT|1/2 (0)|0/1 (0)|0/0 (0)|
|NC|0/14 (0)|1/1 (1)|0/0 (0)|
|ND|0/1 (0)|0/0 (0)|0/0 (0)|
|NE|1/3 (0)|0/1 (0)|0/1 (0)|
|NH|1/2 (0)|1/1 (0)|1/1 (0)|
|NJ|0/12 (0)|0/1 (0)|0/0 (0)|
|NM|1/3 (0)|1/1 (0)|0/1 (0)|
|NV|0/4 (0)|0/0 (0)|1/1 (0)|
|NY|2/26 (1)|0/0 (0)|1/1 (1)|
|OH|1/15 (0)|1/1 (1)|1/1 (1)|
|OK|0/5 (0)|0/1 (0)|0/1 (0)|
|OR|0/6 (0)|0/1 (0)|0/1 (0)|
|PA|2/17 (0)|0/0 (0)|1/1 (0)|
|RI|0/2 (0)|1/1 (0)|0/1 (0)|
|SC|0/7 (0)|1/1 (0)|0/1 (0)|
|SD|0/1 (0)|0/1 (0)|0/1 (0)|
|TN|1/9 (0)|1/1 (0)|1/1 (0)|
|TX|0/38 (0)|1/1 (1)|1/1 (1)|
|UT|0/4 (0)|0/0 (0)|0/0 (0)|
|VA|2/11 (0)|0/1 (0)|0/0 (0)|
|VT|0/1 (0)|0/0 (0)|1/1 (0)|
|WA|1/10 (0)|0/0 (0)|0/0 (0)|
|WI|0/8 (0)|0/0 (0)|1/1 (0)|
|WV|0/2 (0)|0/1 (0)|0/0 (0)|
|WY|0/1 (0)|0/1 (0)|0/1 (0)|

## Remaining gaps

- Institution registration is only one cause: primary/general timing, pollster-provided social links, unverified original methods, missing official aliases, RCV/final-pair questions, and missing recent published polls remain separately held.
- HTTP failures remain failures: UT Tyler certificate verification, Florida Politics/AARP 403, Washington Post timeout, and invalid guessed YouGov/GMU/UNH URLs were not counted as verified primary releases or bypassed.
- API does not contain every fresh local poll. PA-10 Susquehanna fielded Oct 5–11 appears in the RCP table while this API snapshot stops at the prior F&M wave. Exact questionnaire/method and primary origin remain needed before lead admission; a headline/topline list is not a complete review.
- The 1,511 provider records include generic ballots, primary/hypothetical and older polls; that total is not the number of recent district surveys.

## Validation

New source-lane regression tests: 11 passed. Finance 68, election JS 92, ownership rules 13 passed. `check_deploy_chain.py`: all 42 committing workflows chained, no deploy.yml edits. Full polling after committing the intended policy: all 590 passed. The pre-commit HEAD/catalog comparison required a committed catalog; no test assertion was relaxed. No generated JSON is committed.

## Full unpublished collection

Actual `refresh_live_polls.py --capture-only --capture-output /private/tmp/poll-national-sources-20261018/full-capture.json` succeeded. Original capture start 2026-10-18T16:22:20.155706+00:00; API 1,511 rows plus 31 supplemental rows = 1,542 source rows. 36 primary receipts: 35 rechecked, CA IVC changed-document reference carried at its original review date (not claimed as fresh verification). Same full capture before/after: observations 165 -> 188, eligible 118 -> 118, reference 47 -> 70. Recent-14-day observed races house 4 -> 4, senate 7 -> 9, governor 8 -> 9. These are observed races including references, not projected seats or wins. All 506 scheduled targets remain.

The all-state table above uses API-only rows by design. Full comparison is in the temporary `full-comparison.json`; no national generated files were edited or committed. Exact NM and AR releases are being isolated into their respective state inputs, not included in this foundation's 23 references.

Final validation: polling 590 passed; finance 68, JS 92, ownership 13, scope valid, deploy chain 42. Foundation PR #616. NM exact-release PR #617 branches independently from this foundation; AR exact-release PR is separate. Merge/deployment remain unperformed.

## Combined independent-input rehearsal

Temporary source copy `/private/tmp/poll-source-integration-20261019` includes only the separately reviewed NM and AR packets atop the same foundation; no branch or generated JSON merge. Replayed the identical unpublished full capture: baseline foundation-before-changes 165 observations / 118 eligible / 47 references; combined #616 + #617 + #618 yields 190 observations / 121 eligible / 69 references. Net +25 observations across 12 states (the 11 reference-lane states plus NM); three exact releases newly eligible, 22 net references added. Recent 14-day observed-race counts, including references: House 4 -> 6, Senate 7 -> 9, Governor 8 -> 9. These are neither poll question totals nor projected/confirmed seats. Rehearsal output `/private/tmp/poll-source-integrated-report/full-comparison.json`.

PR order: #616 packet-free foundation first; #617 NM and #618 AR are independent on that common foundation and may follow in either order after retargeting to main and scope verification against the actual PR base. Do not merge state PRs into each other or text-merge generated data. No merge or deployment was performed. Existing daily main polling workflow will use these inputs after approved merging; no separate daily user click is required. API omissions and new unreviewed original sources still require source work.

## Follow-up admission request, 2026-10-19 KST

User explicitly requested admission of remaining source-gated observations. Reviewed 23 actually linked public pages, plus official Emerson Iowa release, original Trafalgar/Tyson PDFs and Utah Debate Commission candidate/method images. HTTP 403/429/timeouts remain unavailable; no challenge bypass. New source routes identify actual reporting separately from original publication, with all new routes reference-only until exact individual review.

Registry expands from 22 aliases/17 groups to 32 aliases/27 groups. Added Mitchell/WWMT, Tyson/Breitbart, PPP/Chicago News Weekly, RMG/Yellowhammer, Bravo newsletter, TPOR/Slingshot, American Pulse/NonStop Local, the exact university-linked Emerson Iowa sheet, Change Research/Carolina Forward, Lighthouse/Utah Debate Commission and an alternate co/efficient/NYPost reporting route. Reporting routes explicitly leave original poll document and pollster-name correspondence unverified; they cannot create leads or accuracy grades. Primary source routes retain their distinct roles. Shared Mailchimp paths, like Google/cloud storage, require exact/bounded publisher paths.

Same saved full source capture now produces 200 observations / 118 eligible / 82 reference versus the prior foundation 188 / 118 / 70. New observed-reference states include MI, IL, NC, PA and NY. The original 78 recent-30-day held API records are NOT 78 independent missing polls: e.g. AL RMG records are already replaced by reviewed primary supplements in the full capture. Full-capture deduplication is retained, not inflated by counting them twice.

Original images exposed Utah RV/LV metadata and candidate spelling issues; these are handled in an independent UT packet, not a fuzzy national correction. Emerson's official page links the API's same sheet and supplies exact question/sample/method; IA admission is independent. Michigan Enjoyer '<1%' answers were encoded by the provider as zero; these records remain held, not presented as verified zero. Checked Trafalgar PDF discloses finite decimal minor-candidate values, suitable for an exact state-bound correction; party reference remains excluded from leads. GA timeouts, Florida Politics/AARP 403 and Minnesota newspaper 429 remain source constraints. API omission or HTTP failure is never zero.

New source-route regressions: 13 passed. Subsequent committed full-suite validation and independent PRs are recorded after completion. No UI, workflow, national output or state packet is changed by this common foundation.
