# Israel Knesset research snapshot

This input packet preserves the reviewed 26th Knesset research draft, including
unopened fields and republications. `2026/poll_observations.jsonl` is the numeric
source of truth. No aggregator average is used to fill missing numbers.

Generate the isolated public board and its integrity/status file:

```sh
cd "New for anti/scripts/election_watch"
python3 build_israel_analysis.py
python3 build_israel_analysis.py --check
python3 -m unittest discover -s tests -p test_israel_analysis.py -v
```

The builder validates input receipts, observation identity, cycle, fieldwork
dates, list identities and 120-seat totals before replacing any output. A
failed replay leaves the existing board and status unchanged. The client checks
the serialized board hash against the paired status file, so interrupted or
mixed publication becomes unavailable rather than an empty poll.

Building again changes `built_at`, never `evidence_as_of`, original fieldwork,
publication, collection timestamps or review status. To update the snapshot,
review source inputs, record the actual new evidence date and input byte hashes
in `review_receipts.json`, then regenerate. Do not edit the public JSON by hand.

`accepted` means a reviewed original publisher observation; `partial` includes
republications and missing methodology; `held` is retained without numerical
promotion. Partial polls may be read but cannot drive the selection calculator.
The 61-seat calculator is same-poll arithmetic, not a government-formation model.
An absent list has unknown reported seats, not inferred zero seats.

The current packet has eight accepted seat polls, four partial seat polls and two
held historical records. Its 38 lists are reported by news, not an official
candidate-ranked list. Current Knesset OData, official candidate ranks, law text,
and filed surplus-vote agreements remain held. The broadcaster-hosted judgment
copy is not a court-hosted original or the full reasons. The threshold reported
by news is retained separately from an unverified statutory threshold field.

There is no live scraper, scheduled refresh, polling average, seat-to-vote
inversion, modeled allocation or premiership probability in this implementation.

The existing political country screen lazily loads this board only for Israel:
`/politics/ISR` → **선거 분석**, also directly at
`/politics/ISR/election_analysis`. Existing app.js, global styles, the shared
manifest, other countries' generated files, workflows and deployment are not
changed.

For local integration preview from repository root:

```sh
python3 tools/preview_israel_analysis.py --port 8766       # election module test host
python3 tools/preview_israel_analysis.py --port 8767 --app # existing full app shell
```

Both bind localhost only. The full app preview has no production API; unrelated
macro/shipping widgets can log 404 errors. The test host replaces only the map
adapter; country routing, loader, modal and analysis module are real.


## Korean identities and coalition context (2026-10-15)

`2026/coalition_context.json` is a separately dated, source-linked editorial
context packet. The cooperation view groups reported blocs, an Arab-party electoral agreement,
and unconfirmed/independent alignment. Color does not establish coalition
compatibility. Personal refusals, conditional participation, electoral surplus
agreements and external support remain separate relationship types. Ra’am does
not inherit the Joint List external-support statement; the Netanyahu refusal
is personal rather than a permanent ban on every possible Likud leader.

`2026/ko_translations.json` contains saved translations obtained through the
Google Gemini API. Public labels, leader names, reviewed descriptions and
conditions are translated. Poll numbers and coalition classification are never
supplied by the model. Every entry retains source text, ID, model, timestamp
and review status. Spelling/copy review retains the original `machine_ko`.

```sh
# Only when public source text is added or changed; key stays in the private env file.
python3 translate_israel_ko.py --env-file /path/to/private.env
# Offline validation and publication; no translation API call.
python3 translate_israel_ko.py --check
python3 build_israel_analysis.py
python3 build_israel_analysis.py --check
python3 -m unittest discover -s tests -p 'test_israel*.py' -v
```

Matching translations are reused. Incomplete batches are saved to a temporary
pending cache; failed or uncovered translations cannot replace the public board.
The browser reads pretranslated text and makes no Gemini calls. No API key is
included in generated files. Original research receipts and numeric JSONL stay
unchanged. Coalition context `reviewed_on` is separate from polling
`evidence_as_of`; adding biography sources does not promote official election,
legal or current-seat fields from held.


## Independent grouping axes (2026-10-15)

The party map switches between **연합·협력** and **정치 성향**. Selection,
source poll and coalition constraints persist when the grouping changes.
Cooperation cards distinguish published common principles, reported blocs,
conditional participation and five announced surplus-vote pairs. No current
cabinet membership is inferred from any of these.

`ideology_groups` and each profile's `ideology_group`, `ideology_note` and
`ideology_source_ids` provide a separately sourced editorial taxonomy. The
notes are translated through the same Gemini cache. The IDI party profiles
support the summaries; sources retain review dates and historical limits.
Broad families combine several policy dimensions rather than ranking parties
on an invented numerical scale. Together remains a mixed list; the Joint List
and Ra’am remain distinct. Ra’am's civic transition is an announced aim, not
verified organizational completion. Haredi community identity does not imply
identical conscription policy. Unverified classifications remain unclassified.

Both views partition published observations without altering numbers. Missing
profiled lists appear under an explicitly labeled unpublished-seat disclosure;
no zero is inserted. Source links and per-party explanations are available in
ideology cards. The polling evidence date remains 2026-10-14.

## Snapshot refresh and CI

When adopting a new reviewed snapshot, update both
`review_receipts.json.evidence_as_of` and `build_israel_analysis.py`'s `--as-of`
default. The current-snapshot integration test checks that the documented default
command succeeds and that the public board/status reproduce the reviewed inputs.

Historical Python and JS regressions use the immutable
`tests/fixtures/israel/2026-10-20/` snapshot. Do not replace that fixture when
updating current inputs. Its original input and board hashes remain intact.

`israel_analysis_validation.yml` runs all `test_israel_*.py`, translation/cache
and builder `--check`, and Israel JS contracts on relevant PRs and main pushes.
It is independent of US polling capture/publication and has read-only permissions;
it performs no source collection, translation API call, publication or deployment.

The unnamed Panel4All/Maariv 2026-10-15 poll remains `partial`. A named pollster
is still required for `accepted`; the regression suite enforces this rule.

## Post-election count and government formation (2026-10-31)

`2026/post_election.json` is an optional, independently dated review input. It
preserves #719's `official_results` record byte-for-value, its upstream file hash,
and this review's successful/failed body-access receipts. It is **partial,
media-reported**, not a directly verified CEC table or a government-formation
announcement. No accepted polling rows, old receipt hashes, translations, or
historical fixtures are replaced. A missing optional file retains the earlier UI.

The builder includes this input in `input_digests` and the existing board/status
hash pair. Its result/review dates are separate from polling `evidence_as_of`;
the existing polling replay command remains `--as-of 2026-10-20`.
`israel_results.py` and the browser contract validate counts, null political events,
source receipts and conditional deadlines. A later certified result or mandate
requires a newly reviewed state transition and corresponding validation changes;
do not simply change a null or `partial` flag.

The result and next-step panels precede a closed pre-election disclosure. Dates
for 4 November submission and expected 10 November swearing-in remain attributed
reports, not completed official events. Relative government-formation periods do
not acquire calendar deadlines without a verified mandate. The official statute
was geographically unavailable; the accessible WIPO Hebrew consolidation is from
2016 (its English reference is from 2003), so current official-law verification
remains held. New Korean explanations are source-reviewed editorial summaries;
the preserved Gemini cache still covers only the earlier pre-election material.

Run `python3 -m unittest discover -s tests -p 'test_israel_*.py'` and Israel JS
contracts explicitly. The 2026-10-31 reported-count regression fixture is frozen;
current publication replay is tested separately.
