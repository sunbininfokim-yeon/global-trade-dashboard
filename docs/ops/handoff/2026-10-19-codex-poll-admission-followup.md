# 2026-10-19 polling follow-up — primary admission and commissioned aggregation

Common PR #616, independent state PRs #617 NM, #618 AR, #619 IA, #620 UT, #621 MI and new KY/MS/ID PRs. All state branches incorporate packet-free common commitceba6edf; no state-on-state stack. Initial main4ba56f69; submission recheck ec41fe85 changes only unrelated data/config, no election files. No main merge/deployment/production workflow dispatch.

## Actual coverage

Provider capture remains October18 16:20:04UTC / full provider-plus-prior-supplements capture16:22:20UTC, as_ofOctober18. No new provider request is claimed. New original documents were requested and their SHA/time recorded; API-omitted MS/ID primary rows were added using their own actual primary receipts, not the provider capture clock.

|Stage|Cumulative observations|Eligible|Reference|States with any observation|
|---|---:|---:|---:|---:|
|Original input comparison|165|118|47|—|
|Previous common+NM/AR|190|121|69|—|
|Expanded routes+IA/UT/MI, before latest user change|204|124|80|37|
|Latest combined inputs and commissioned policy|207|129|78|40|

Latest additions fill three previously empty states: KY House6 primary memo; MS Senate old primary supplement; ID governor old primary supplement. IA YouGov governor changes from reference to eligible after primary Q8 sample correction2245→2244; the original API sample is preserved. Commissioned policy promotes four exact-reviewed observations: KY Change Research, CA DCCC, NC co/efficient and WI DCCC. Older sources stay outside current7/14; no historical observation is a new lead.

AtOctober18 UTC, recent14 observed races including references: House7/Senate10/governor9. These are observed races, not all eligible leads or projected seats. Original165→latest207 is42 more observations. No poll, sample size, source accuracy or missing spending was invented.

## Aggregation policy

Latest user explicitly requested inclusion of party/candidate commissioning. Exact primary named-question reviews can count when sponsorship is the only exclusion. Identified commissioner, exact raw/supplement fingerprint, date/population/sample and source admission are required. Source/method gaps remain visible. Other explicit methodological/forced-choice/RCV/historical exclusions remain. Publisher-only references are still not lead evidence. Commissioning stays in observations/poll_details and commissioned_poll_count; count is after latest-wave-per-institution dedup and LV/RV split. No invented house-effect correction, quality grade or probability.

## Fifty-state coverage

Cumulative observation counts by office. Zero below is a count of admitted observations, not candidate support or evidence that no real poll exists. Election scope is435 House/35 scheduled Senate/36 governor contests.

|State|House|Senate|Governor|Eligible|Reference|
|---|---:|---:|---:|---:|---:|
|AK|1|3|2|0|6|
|AL|1|2|2|0|5|
|AR|0|1|0|1|0|
|AZ|1|0|2|1|2|
|CA|4|0|6|7|3|
|CO|2|0|0|0|2|
|CT|0|0|5|3|2|
|DE|0|0|0|0|0|
|FL|3|5|6|2|12|
|GA|0|3|3|4|2|
|HI|0|0|0|0|0|
|IA|0|8|9|14|3|
|ID|0|0|1|0|1|
|IL|0|1|1|0|2|
|IN|0|0|0|0|0|
|KS|0|2|2|3|1|
|KY|1|0|0|1|0|
|LA|0|0|0|0|0|
|MA|0|2|0|1|1|
|MD|0|0|1|0|1|
|ME|0|1|4|3|2|
|MI|0|9|5|10|4|
|MN|1|1|1|1|2|
|MO|0|0|0|0|0|
|MS|0|1|0|0|1|
|MT|3|2|0|3|2|
|NC|1|11|0|11|1|
|ND|0|0|0|0|0|
|NE|1|0|0|0|1|
|NH|1|4|4|7|2|
|NJ|1|0|0|0|1|
|NM|3|1|1|5|0|
|NV|0|0|3|3|0|
|NY|4|0|3|5|2|
|OH|1|6|6|8|5|
|OK|0|0|0|0|0|
|OR|0|0|1|1|0|
|PA|2|0|3|4|1|
|RI|0|1|0|1|0|
|SC|0|2|0|2|0|
|SD|0|0|0|0|0|
|TN|1|1|2|0|4|
|TX|3|11|9|19|4|
|UT|1|0|0|1|0|
|VA|3|0|0|3|0|
|VT|0|0|1|1|0|
|WA|1|0|0|1|0|
|WI|1|0|5|3|3|
|WV|0|0|0|0|0|
|WY|0|0|0|0|0|

Remaining no-admitted-observation states in this input: DE, HI, IN, LA, MO, ND, OK, SD, WV, WY. Limited discovery audit is in `2026-10-19-codex-poll-unobserved-state-audit.md`; none is falsely marked fully reviewed. NE remains paused; existing data retained.

## Preserved boundaries

IA preserves two Suffolk original supplements and October4 field dates. UT RV correction preserves API LV; outside current windows. MI exact Trafalgar decimals/Tyson waves stay reference where commissioner or methodology exclusions remain; literal0 for<1% stays held. NM/AR earlier original reviews remain. MS forced pair41/47 is not merged into initial38/44/7. ID Senate remains held because old required David Roth differs from primary Achilles/Risch field; official current nominee review is required before changing it.

Primary supplements recheck only finite reviewed documents, not all future releases. Changed/source-unavailable documents retain original field dates and reference-only status. Newly published API rows must still pass candidate/date/source checks; bounded publisher routes may first display them as references. Unregistered source is not itself a quality failure.

## Validation / delivery

Common baseline592 passed before commissioned policy. Common commissioned regression597 exercised596passed; only failure was shared-catalog-vs-HEAD invariant while policy was uncommitted. Policy is now committed and that module is rerun in final integration. Previous integrated614 had one missing-JS-directory environment error; copied unchanged JS dependency and affected module9passed. These were validation setup issues, not waived product assertions. Final combined full-run result appended below. Finance68/JS92/ownership13/deploy-chain42 passed after policy change; state scope valid independently for all eight branches againstceba6edf. New targeted KY4/MS5/ID5/IA6 passed before combined run.

Common first, then independent state PRs may be retargeted to current main and rechecked. Normal existing daily06:10KST polling publication applies authorized merged input. This work did not dispatch it, merge main or deploy. National generated JSON remains temporary, not committed.


Final combined full polling635 passed (269.318s), after the four shared test catalog clocks were separated from fixed historical observation dates. Latest original-provider-sponsor preservation and outage display metadata additionally passed7 targeted policy tests. Finance68, electionJS92, ownership13 and deploy-chain42 passed. Real generated server/client comparison1012 windows (506races ×7/14) matched party/status/count/includedIDs/leadcounts. Eight-state packet replay and projection generation exited0; all unselected-state races and national as_of/fetched_at stayed identical, and both IA Suffolk original October4 observations remained. New common rules/metadata describe commissioned inclusion; primary sponsor is displayed through existing commissioning.sponsors while provider_sponsors preserves the empty original API field. No UI file edited.

Final common source includes ceba6edf commissioning logic,5557d1b8 published-policy/catalog-clock compatibility,60e92842 primary-commissioner preservation, plus latest outage-label test/metadata. Common review status is ready; GitHub checks for latest commits may still be running. Local validation is not deployment evidence.
