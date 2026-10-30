# 2026-10-19 — governor context, public discovery, campaign fundraising

Owner Codex. Branch `codex/us-election-context-data-20261019`, base main `b69196c4`. Implements the user's four requests after the design review #631. This is a packet-free backend foundation; OH actual primary reviews and biographies belong to an independent state PR. No UI, Worker, workflow, national generated JSON, main merge, deployment or workflow dispatch changes.

## Delivered contracts

### Governor elections

`config/usa_polls/governor_context_2026.json` records the actual NGA HTML receipt, reviewed incumbent identity, nomination listing and term-limit marker. The 2026 panels match the existing catalog: 50 states, 36 elections, 14 without elections. Status counts on the current state cards are 15 term-limited, 17 reported running, 3 reported retiring (IA/MN/WI), 1 reported primary defeat (RI). The last four notes explicitly retain their secondary 270toWin attribution; they are not legal eligibility rulings. OH's constitutional rule has its own legal source. No universal lifetime/consecutive rule is inferred.

`refresh_governor_context.py` rechecks the publisher and preserves the human review date. A changed incumbent, term marker, nominee listing, year or universe requires review and preserves the last valid input. It participates in the existing finance refresh entrypoint and writes under the already staged `usa_election_finance/2026/` directory. `build_board.py` exposes `ui_ready.state_drilldown.governor_elections` and each state's `governor_election`. Governor candidate rosters are validated and attached beside federal matchups before biography joins. A current-governor identity conflict cannot transfer a predecessor's term limit.

### Candidate biographies

Optional `candidate_profiles` lives inside the existing one-state evidence packet. Fields have value/status/source/review date/locator. Age requires an exact verified birth date; missing race/ethnicity or military service stays null. Race requires explicit self-identification or official biography. Joins require exact current roster name, party, office, state and cycle, and candidate ID if supplied. Unmatched biographies are held. The first real OH packet links four people; this is not national biography coverage. Candidate careers are factual context, not an electoral-fit or performance score. ACS/CVAP demographic ingestion and forecast weighting remain unimplemented.

### Public discovery

The existing daily `discover_poll_sources.py` invocation now also reads the public Race to the WH publisher-linked Infogram table and Still Counting's official RSS. The live chart key is derived from its published viewer manifest; only its normal cached public rendering is used, not its source Drive sheet, editor, private endpoints or credentials. The two display sheets represent the same list and are read once. Unknown aliases, dates, question samples and phases are not guessed. Publisher grades remain labels, never our accuracy grades.

Actual 2026-10-19 discovery CLI: 1,324 discovery items across existing 270toWin plus RTWH, including 1,205 RTWH items (859 resolvable race IDs, 346 unresolved aliases, 13 skipped malformed/blank rows); 8 podcast episodes are separate commentary. These are cumulative discovery items, not 1,324 distinct verified polls, new observations, or accepted leads. RTWH has incomplete rows and source health is partial. The checkpoint is an artifact for review; it does not automatically approve or publish all table rows. Source failure does not erase or block already validated polling data.

RealClearPolling links led to the BGSU release used in the independent OH packet, corroborated by RTWH. Normal direct RCP HTTP returned403, so no working unattended RCP scraper is claimed. NYT access failed; Silver's detailed model remains paid with no verified public API/republication route; Cook governor HTTP403 preserves existing dated ratings. Ballotpedia/538 have no newly verified live adapter here. CBS's public TX original PDF was found but is not admitted: it reports likely-voter results with leaners and weighted question bases, without an unweighted LV sample. The overall 1,492 RV sample must not become the LV question sample. No access-control bypass, betting feed, model probability, audio transcription or synthetic poll is added.

### Campaign fundraising separate from outside spending

`refresh_candidate_fundraising.py` downloads FEC `weball26.zip` plus `cn26.zip`, without an API key. It validates the 30/15-column formats and joins exact FEC IDs, election year, office, party, state and valid district. It writes a separate `candidate_fundraising_v1.json` and failure health file. Missing or older candidate reports preserve their own last valid amounts, report end and source receipt. Unavailable sources preserve last-good file bytes.

`build_superpac_map.py` adds `campaign_fundraising` to existing candidate financial cards, with separate `campaign_fundraising_status`/health. Amounts are integer USD cents. Gross receipts, individual contributions, candidate contributions, candidate/other loans, authorized transfers, cash, disbursements, debts and refunds remain distinct. Receipts are not pure donations; a candidate's personal contribution is not personal wealth. Authorized transfers can double count and are flagged. No total combines campaign money with independent expenditures.

Actual public FEC files: 4,350 summary rows / 8,809 master rows yield 2,822 valid 2026 H/S financial summaries. These include registered/primary candidates and are not 2,822 certified general nominees. Reporting period is FEC's two-year file, not an entire six-year Senate campaign. Exact scope validation links 2,822 existing financial cards and holds 44 conflicting candidate appearances without amounts. All three existing outside-spending totals across 1,118 race assets remain byte-equivalent as parsed values. No candidate is added to an official ballot from FEC registration.

Governor campaign fundraising explicitly remains `state_campaign_fundraising_adapter_not_connected` with null amounts, not FEC money or Super PAC totals. It needs separate official state adapters. This is the principal remaining fundraising coverage gap; no new key is required for the federal bulk route already implemented.

## Cadence and publication

Existing polling workflow is daily06:10KST and already calls discovery. Existing finance workflow runs Monday/Friday in October, weekly otherwise. The new modules use those existing entrypoints, not a new schedule. They start operating in production only after code is merged and the normal authorized workflow publishes assets. This PR neither starts nor proves that production refresh. UI rendering of new fields remains a separate task.

Deploy outputs stay in existing staged directories. `deploy.yml` and all workflows are unchanged. Do not rebase state work on another unmerged state branch: the common foundation is packet-free, and state PRs target this branch or the later merged main. #616 → #627 still governs the previous source-expansion stack; isolated compatibility validation tests both common foundations together before submission. National JSON must be rebuilt by the integrated publisher, never manually merged.

## Measured polling coverage and validation

Fresh API request on 2026-10-19 returned1,511 records, identical in IDs/content to the prior capture. Original reviewed primary receipts/substitutions are retained. With prior independent state packets plus OH, cumulative displayed observations remain212 in41 states:135 eligible /77 reference. OH promotes two existing BGSU records from reference to eligible; it does not create two new surveys. Recent14-day observed races including references: H6/S10/G7; eligible-only H6/S7/G6. Those are coverage counts, not projected seats or winners. The7-day default and14-day option remain unchanged.

The isolated compatibility snapshot `2585cabe` (unpublished temporary checkout only) combines this foundation, #616/#627 and 12 independent state inputs. Polling678 passed, including six OH tests; finance77 passed, election JS92 passed, ops ownership14/deploy3 passed, and `check_deploy_chain.py` confirms42 workflow links. The final clock-safe governor roster regression6 and governor-matchup11 tests also pass. A malformed ZIP is converted to an explicit source failure so the last-good preservation path also handles HTML error responses. The latest finance77 suite includes this case.

The initial combined run found two test assumptions: an unknown BGSU ID may be retained as reference by #616 but cannot inherit primary approval; the state-input test compares tracked catalogs against HEAD, requiring a real isolated compatibility snapshot instead of an uncommitted merge. Neither fix relaxes admission. Full board generation confirms all50 governor contexts and all4 OH biography joins. OH-only replay preserves489 other live races,70 other history races, national collection timestamps and other states' focus rows; `house_poll_focus` is recomputed rather than frozen. Local fixtures restore the tracked committee-jurisdiction JSON omitted by sparse checkout; no unrelated product repair is included. These are local results; remote CI must be checked on each submitted head.

## Information architecture to carry into the UI

Adapt 270toWin's separation of current seats, seats voting this year, and post-election outlook; use race IDs for chip/list/map joins. Keep actual polls, expert ratings and external models separately attributed. A state card should show current officials → this election's candidates → latest support percentages/fieldwork → campaign contributions/cash → candidate support/opposition outside spending → sourced biography. Small source/method text should not obscure the candidate percentages. This foundation supplies governor context and separate campaign finance fields; it does not claim those UI changes are already visible.
