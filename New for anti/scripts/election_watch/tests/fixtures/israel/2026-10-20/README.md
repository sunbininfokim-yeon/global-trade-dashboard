# Reviewed Israel snapshot: 2026-10-20

Immutable regression fixture copied byte-for-byte from the reviewed inputs and
published board/status on main 96af0fca7 (Israel data from merged PR #650).
It contains eight input files and the paired public board/status. Existing input
byte hashes remain in review_receipts.json; the public body hash remains in the
status file. No evidence, numbers, translations or review statuses were edited.

Historical Python and JS assertions read this fixture, not the mutable public
JSON or current config. Do not overwrite it when refreshing the research snapshot.
Add a separately dated fixture when a new historical case is needed.

Current production input/publication consistency and the CLI default evidence date
are checked separately in test_israel_current_snapshot.py. Update the builder's
--as-of default and current receipt date together when adopting a new snapshot.

The dedicated Israel validation workflow discovers test_israel_*.py and runs the
Israel JS tests. It has no capture, publication, schedule, or deployment steps;
its failures cannot block the daily US polling publication workflow.
