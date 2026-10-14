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

The current packet has six accepted seat polls, three partial seat polls and two
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
