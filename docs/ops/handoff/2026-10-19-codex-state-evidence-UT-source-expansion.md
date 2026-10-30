# UT — official commissioner images and exact RV correction

UT only; checkout `/Users/yeoninair/Documents/해운 데이터/us-poll-UT-source-coverage-20261019`, branch `codex/poll-ut-source-coverage-20261019`, common base 52546e0a (#616). Independent state PR, not based on another state.

Replayed actual provider capture 2026-10-18T16:20:04.208175+00:00. Newly fetched and visually inspected Utah Debate Commission original CD2 results and methodology JPEGs (source URLs/SHA/timestamps in audit). Footer identifies Lighthouse Research. CD2 n=515, field September 10–24, publication September 29, reported proportion MOE 4.32pp. Exact values: Moore 39, Crosby 34, Bowen 4.1, Cottam 4.9, Moesinger 4.9. Question names current CD2 and the full candidate field.

Registered-voter-list random sample with contact matching, CATI and emailed online interviews, registration/residency verified, no weighting and no likely-voter screen disclosed. API LV is therefore corrected to RV, preserving original LV in an exact provider-bound correction. The source's Blake D. Moore is explicitly aliased to the existing canonical Blake David Moore; no fuzzy matching or legal-name/FEC identity rewrite.

Observation enters cumulative verified history. September 24 remains outside both 7/14-day windows at as_of October 18, so no current lead or fresh date is fabricated. Other-party identities not already in the reviewed roster remain unknown. No official ballot-certification upgrade, unopposed status, winner or finance collection claimed.

Changes only UT packet, UT-specific audit/test/handoff. Primary source images are manual review evidence for this API record, not a generic future-image OCR collector. Future matching API records use the common reference lane until individually reviewed. No common code, national output, UI/workflow, merge/deploy/dispatch. State regression and shared integration results appended after validation. #616 first, then independently retarget this state PR to main.
