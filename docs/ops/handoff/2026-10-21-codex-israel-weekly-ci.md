# Israel weekly bars and validation follow-up

Scope: Israel only, PR #653 (`codex/israel-weekly-bars-20261021`). Latest main
96af0fca7 was merged into the isolated worktree without conflicts. US recovery
PRs, primary-source reviews, PR stacks, collection and publication were not edited.

The weekly bars retain the prior desktop/mobile verification at 1100/390/320px.
This follow-up changes tests and validation infrastructure, not the chart logic,
current research inputs, translations, public board/status, or evidence clock.

## Decisions

- Keep `maariv-panel4all-2026-10-15` partial. `pollster` is still null; a named
  institute is required for accepted seat polls. A regression now asserts that
  promoting this historical row fails the existing methodology check. No validator
  relaxation or guessed institute identity was added.
- Add a separate, read-only Israel PR/main validation workflow. Do not add Israel
  to the US `test*poll*.py` publication gate: a broken Israel snapshot must not
  interrupt the repaired daily US publication. There is no capture, translation
  API call, schedule, workflow dispatch, publication, or deployment in this job.
- The ownership exception is the exact current branch and this single new
  workflow. Existing US/deployment ownership restrictions remain; 15 scope tests
  pass.

## Fixed-date audit

The two historical Python suites read current config with a fixed 2026-10-20
clock and exact counts. All four Israel JS suites read mutable public JSON while
asserting historical dates/counts; the service also relied on the real clock.
These regressions now read the immutable `tests/fixtures/israel/2026-10-20/`
fixture. Ten input/publication files were copied byte-for-byte from reviewed main;
input receipts and the paired public hash are intact. The historical service
clock is fixed locally and restored after each test.

`test_israel_current_snapshot.py` separately reads current config/public data,
derives the evidence date from the receipt, checks exact offline reproduction,
and exercises the documented CLI default. The current builder default and
receipt are both 2026-10-20. Future snapshot adoption must update both; the test
fails with an explicit maintenance message if the default is forgotten.

## Local validation

- Israel Python discovery: 27 passed; includes current replay/default checks.
- Israel JS: 32 passed; all election JS: 122 passed.
- Translation --check: 234 cached translations, no API call.
- Builder --check: accepted 8, partial 4, held 2, lists 38, sources 66.
- All ten fixture files match reviewed main bytes; no current input/output edits.
- Independent workflow YAML parsed; read-only PR/main validation only.
- Broader US compatibility run uses existing main fixtures without edits; its
  result is recorded in the PR validation update. Initial sparse-checkout fixture
  omissions were restored from main, not treated as product regressions.

No PR merge, source collection, workflow dispatch, or production deployment was
performed by this follow-up. Remote CI status must be checked separately from
local validation.
