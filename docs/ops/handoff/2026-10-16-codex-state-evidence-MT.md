# MT first pass — official nominees and actual API transport

State MT, checkout `/Users/yeoninair/Documents/해운 데이터/us-mt-evidence-input-20261016`, branch `codex/mt-evidence-20261016`, base main `0f01e465788fc1786cdbef9fccf823e5571b5bcd`. No unmerged state dependency. Next IN is not started.

Actual public VoteHub collection on 2026-10-16 saved 27 MT provider records with original capture receipt; no national generated files changed. Official Montana general list election 450002987 was fetched and fingerprinted. The three federal contests contain 11 printed nominees and one separately declared Senate write-in. Senate had only DEM/REP in the old listing; Kyle Austin LIB and Seth Bodnar IND are now included. House has 3/4 nominees. No 2026 governor contest is generated. FEC IDs not verified for new nominees remain null; campaign money is never substituted for independent expenditure.

Six state-owned operations overlay federal and ballot catalogs; raw shared catalogs were restored by freeze_state_inputs. Existing daily polling ingestion reads the packet after merge, and retains source/candidate/question admission rules. No new institution or future release has blanket approval.

This is partial evidence work: MTFP/Eagleton September Senate and MT-01 releases were discovered, but detailed spreadsheet, methodology and district subsample reconciliation remain pending. Secondary aggregators disagree on Alme/Bodnar values; no new numbers were guessed or imported. No claim of complete polling or fresh FEC collection. Governor is non-election, not missing money. New API key was not needed for the public poll collection.

Dedicated tests verify all four Senate parties, separated write-in, House universe/non-election governor, and replay preservation of all other states/history/global clocks. Overall validation result is recorded in the PR. Do not merge/deploy/dispatch production. Complete original-document and federal finance identity reviews before calling MT fully reviewed.
