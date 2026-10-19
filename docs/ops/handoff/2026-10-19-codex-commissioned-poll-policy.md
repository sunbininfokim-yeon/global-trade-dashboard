# Reviewed commissioned polls — common foundation #616

User on 2026-10-19 KST explicitly requested party/candidate-commissioned polls in our aggregate. Policy effective review date is 2026-10-18 UTC. Earlier historical replay behavior remains unchanged.

`commissioned_poll_aggregation.enabled` permits an exact-reviewed named voting-intention question to count when the only exclusions concern sponsorship. It requires matching raw/supplement fingerprint, primary-release admission, exact sponsor/party binding, sample/population/field dates and identified commissioner. Named voting intention as reported in a primary memo can qualify even without a full questionnaire; missing mode/frame/weighting remain disclosed, not imputed. An explicit existing methodological/RCV/leaner/historical exclusion is not cleared. Publisher-only fallback references, unknown commissioners and changed snapshots do not inherit approval.

Commissioning stays on every observation and `poll_details`. Summaries expose `commissioned_poll_count` after the existing latest-wave-per-institution deduplication, LV/RV split and conflicting-wave checks. `independent_pollster_count` retains its legacy field for compatibility; `count_basis` explicitly means distinct institution groups, not nonpartisan sponsors. No adjustment factor, accuracy grade or win probability is invented.

Publication failure/changed document still appends `primary_source_unavailable_or_changed`, so the last valid original observation remains reference-only. No UI, workflow, deployment or generated national data is edited. Existing automatic daily collection will use this policy after authorized merge; no production workflow was dispatched.

Validation: seven targeted policy tests cover internal DCCC admission, policy-off/earlier date, changed sponsor/sample/wave, substantive exclusions and same-wave deduplication. Full regression is rerun on committed common inputs because the state-scope invariant deliberately compares shared catalogs to HEAD. Results in follow-up handoff.

Final integration635 passed; latest policy/source-outage/sponsor metadata7 targeted checks passed. Primary commissioner is exposed through the existing commissioning.sponsors contract with provider_sponsors preserved. Live rules_ko and effective policy metadata agree with aggregate behavior. Source-unavailable observations use a reference label and remain excluded.
