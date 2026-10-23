# 미국 선거 여론조사 원문 검토 대기열 · 작업 절차 (2026-10-23)

작성: Claude Code. 대상: Codex(주별 PR 담당). 이 문서 하나로 같은 분석·같은 절차를 재현할 수 있게 적었다.

## Codex에 줄 시작 문구

```text
docs/ops/US_POLL_SOURCE_QUEUE_20261023.md 를 먼저 읽고 같은 절차로 진행하세요.
- 한 주·한 worktree·한 PR. packet(config/state_evidence/2026/XX.json)과 그 주 원문/검토 자료만 담습니다.
- 5절 대기열에서 A등급부터: 원문을 열어 수치·표본·기간·모집단·의뢰자를 대조하고 3절 1~7단계로 packet을 만듭니다.
- 원문을 못 열면(Cloudflare 등) 추가하지 말고 사유만 남깁니다. 평균·역산·추정 금지.
- C등급(당파·의뢰)은 메모 원문을 찾은 경우에만 참고용으로 넣습니다.
- 전국 생성 JSON 손편집 금지, 공용 코드·UI·workflow는 수정하지 않습니다. 병합·배포는 Claude가 검사 후 진행합니다.
```

## 0. 현황 요약

- 9/1 이후 조사 중 `review_queue`에 남은 주지사·상원·하원 조사 **171건 / 37개 주** (공개 데이터 `usa_election_live_polls_v1.json`, 게시 6b7a7148 이후 main).
- 완료 2건(SD, PR #684) · A 비당파 103건 · B 추가 확인 27건 · C 당파·의뢰 39건.
- 이번 세션 반영: #678(FEC 캠프 총수입 리디렉트·재무 테스트 고정), #679(MI-07 FEC 신고명 변형), #680(Cook 경과일 표시·상원 차트), #681(AK 순위선택 결선 짝짓기), #682(원문 수집 workflow), #684(SD Mason-Dixon).

### 주별 상태

| 주 | 대기 | 완료 | 비고 |
|---|---|---|---|
| AK | 5 | 0 | DFP 순위선택 충돌은 #681로 해소. 나머지는 기관 미선정 |
| AL | 3 | 0 |  |
| AR | 2 | 0 |  |
| AZ | 4 | 0 |  |
| CA | 5 | 0 | CA-11 USC 원문 확보(source-fetch/house-polls). 기존 CA packet이 커서 9/1 이전 원자료까지 다시 받아 capture 교체 필요 |
| CO | 1 | 0 |  |
| CT | 2 | 0 |  |
| FL | 11 | 0 |  |
| GA | 6 | 0 |  |
| IA | 11 | 0 |  |
| IN | 1 | 0 |  |
| KS | 2 | 0 |  |
| KY | 3 | 0 |  |
| MA | 5 | 0 |  |
| ME | 14 | 0 |  |
| MI | 11 | 0 |  |
| MN | 9 | 0 |  |
| MO | 3 | 0 |  |
| MS | 1 | 0 |  |
| MT | 5 | 0 |  |
| NC | 8 | 0 |  |
| NE | 3 | 0 |  |
| NH | 1 | 0 | NH-01 UNH: VoteHub 후보 철자(Stephany↔Stefany) 별칭 검토 필요. 원문 확보 |
| NV | 1 | 0 |  |
| NY | 3 | 0 |  |
| OH | 13 | 0 |  |
| OR | 2 | 0 |  |
| PA | 2 | 0 |  |
| RI | 5 | 0 | Embold(Salve Regina Pell Center) 목록 페이지만 확보 → 개별 발표문 필요 |
| SC | 1 | 0 |  |
| SD | 2 | 2 | House·Senate Mason-Dixon 완료(#684). Senate Emerson(KELO)·Quantus 남음 |
| TN | 1 | 0 |  |
| TX | 16 | 0 |  |
| UT | 3 | 0 | Lighthouse(Utah Debate Commission) 원문 확보. UT-03/04 대진 검토 선행 |
| VT | 1 | 0 | UNH 1006 원문 확보. VT-00 대진 검토 선행 |
| WA | 1 | 0 |  |
| WI | 2 | 0 |  |

## 1. 우선순위 기준

- **A 비당파·원문 검토 후보**: 대학·언론 의뢰 또는 비당파 기관. 원문에서 수치·표본·기간·모집단·의뢰자를 대조하면 `signal_eligible: true` 후보.
- **B 추가 확인**: 문항 형식(순위선택·강제양자·리너), 모집단·지리·표본 불일치, 원문 접근 장애 등. 문항별로 판단.
- **C 당파·의뢰**: House Majority PAC·DCCC·후보/정당 계열 의뢰. `allow_partisan_reference`·`reviewed_partisan`로 **참고용** 표시만(일반 우세 집계 제외). X/Bluesky 게시물은 원문이 아니므로 메모 PDF·보도자료를 찾아야 함.

## 2. 원문 접근 — `source_fetch.yml` (#682)

클라우드 에이전트는 대부분의 발표 사이트·VoteHub API에 접근하지 못한다. Actions 러너에서 받아 `source-fetch/<label>-<run_id>` 브랜치에 저장한다(main 미변경).

```text
Actions → "Source fetch for manual review" → Run workflow
  urls : 공백 구분 https URL 목록
  label: a-z0-9- (예: ca11-20261023)
결과 : source_fetch/<label>/{NN-*.raw.html|.raw.pdf, NN-*.rendered.html, NN-*.txt, receipts.json}
```

- `receipts.json`의 `raw_sha256`·`fetched_at`·`final_url`을 packet `capture.receipt.provider_fetch`와 리뷰 `disclosure_review.source_fetch_receipt`에 인용한다.
- Cloudflare 봇 차단으로 **cookpolitical.com, *.substack.com(Poll Vault)** 은 러너에서도 403. 이 둘은 맥 브라우저로 직접 검토해야 한다.
- 이미 받은 브랜치: `source-fetch/house-polls-20261023-39877776048`(SD House, CA-11, Utah, UNH 1005/1006, Salve 목록), `source-fetch/sd-senate-20261023-*`, `source-fetch/votehub-20261023-39878722044`(VoteHub API 9/1~10/23 원본 362건).

## 3. 주별 packet 절차 (SD #684에서 실제로 쓴 순서)

1. VoteHub 원본에서 대상 레코드(id)를 찾는다. `answer_correction_fingerprint(raw)` → `provider_record_sha256`.
2. 원문을 읽고 `config/usa_polls/quality_reviews_2026.json`에 **임시로** 리뷰를 넣는다. 형식은 CA packet의 `us-202sur70c7e750`(SurveyUSA) 또는 SD packet 참고: `sources`, `primary_toplines`(VoteHub 후보명 그대로), `question_sample_n`, `disclosure_review`(population·sample_n·field_dates·sponsors·sampling·weighting·question), `reported_precision`, `sponsor_review`, `admission`{pollster, provider_url(=VoteHub url), group, methodology_url, source_role, signal_eligible}, `missing_fields`, `limitations_ko`.
3. 후보명이 공식 명부와 다르면(`unreviewed_matchup`) `ballot_reviews_2026.json` 해당 race 후보에 `poll_name_aliases`와 `poll_alias_basis: existing_reviewed_identity_and_exact_source_name_or_quoted_nickname`를 임시로 추가한다(SD: "Nikki Gronli").
4. `snapshot_sha256 = review_fingerprint(row)`(정규화된 관측 행). 먼저 snapshot 없이 한 번 돌려 값을 얻거나, `poll_quality.review_fingerprint`로 계산한다.
5. `refresh_state_polls.py --state XX --as-of YYYY-MM-DD --packet` — VoteHub 접근이 안 되면 `fetch_polls`를 source-fetch로 받은 JSON으로 대체한다(SD에서 사용, packet receipt에 출처 기록).
6. `freeze_state_inputs.py --state XX` → 임시 catalog 편집이 packet operation으로 이동하고 공용 catalog는 복원된다.
7. 검증: `check_state_packet_changes.py --base-ref origin/main --head-ref HEAD`, `refresh_state_evidence.py --all`(공개 데이터 사본), polling 전체 unittest.
8. 기존 packet이 있는 주(CA 등)는 `--packet`이 capture를 **통째로 교체**한다. VoteHub를 9/1 이후만 받으면 기존 리뷰가 가리키는 이전 레코드가 빠질 수 있으니 기존 capture 범위(`from_date=2025-01-01`)로 다시 받는다.

## 4. 주의한 규칙

- 평균·역산 금지. 화면의 상원 차트도 기관 방향 수만 센다.
- 순위선택(AK·ME): 1순위·결선 모의 문항은 별도 참고. VoteHub 결선 사본은 원문 결선 문항으로 `reviewed_provider_replacements`, 1순위 문항에는 `same_wave_separate_question_reviews`(AK #681 참고).
- 재무 테스트는 `PINNED_FINANCE_NATIONAL`(10/19 게시본)로 고정됨. 새 FEC 신고명 변형은 주별 packet의 `state_finance_identities` 연산으로 반영(MI #679).
- Cook 등급: 검토본은 하원 9/25·주지사 10/1·상원 10/6. 화면은 45일까지 경과일 표시로 사용(#680). 최신 등급은 브라우저 원문 재검토로 `usa_election_ratings_review_v1.json` 갱신 필요.

## 5. 전체 대기열 (9/1 이후, 주별)

### AK

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Alaska Survey Research | 2026-10-18 | 1568 | `pollster_not_selected` | - | https://x.com/The_Real_ASR/status/2112415183226429942 |  |
| B 원문·문항 추가 확인 필요 | governor | The New York Times/Siena University | 2026-10-01 | 431 | `ranked_choice_question_not_reviewed` | - | https://sri.siena.edu/2026/10/04/nytimes-siena-poll-of-likely-voters-gubernatorial-races-2/ |  |
| B 원문·문항 추가 확인 필요 | senate | co/efficient | 2026-09-17 | 799 | `ranked_choice_question_not_reviewed` | - | https://battlegrounds.coefficient.org/ak/ |  |
| C 당파·의뢰(참고용) | house:00 | The Bullfinch Group | 2026-09-06 | 820 | `pollster_not_selected` | Independent Leadership Council | https://cdn.prod.website-files.com/68d1c32ec01e1d1f6a86e801/6abd40f2f3810a4e535a8aa6_Alaska_Topline-Independent_Leadership_Council.pdf |  |
| C 당파·의뢰(참고용) | senate | Public Policy Polling | 2026-10-15 | 578 | `pollster_not_selected` | - / DEM | https://x.com/AndrewSolender/status/2110867168892014803 |  |

### AL

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | The Alabama Poll | 2026-10-16 | 600 | `pollster_not_selected` | - | https://www.al.com/politics/2026/10/gop-faces-election-downturn-but-theres-no-blue-wave-for-alabama-democrats-poll-shows.html |  |
| A 비당파·원문 검토 후보 | senate | The Alabama Poll | 2026-10-16 | 600 | `pollster_not_selected` | - | https://www.al.com/politics/2026/10/gop-faces-election-downturn-but-theres-no-blue-wave-for-alabama-democrats-poll-shows.html |  |
| A 비당파·원문 검토 후보 | senate | Cygnal | 2026-10-17 | 500 | `pollster_not_selected` | Gray Television, Alabama Daily News | https://aldailynews.com/poll-barry-moore-leads-everett-wess-in-u-s-senate-race/ |  |

### AR

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:02 | Emerson College | 2026-10-14 | 383 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | Grayhouse | 2026-10-04 | 550 | `pollster_not_selected` | - | https://x.com/LandonWall_/status/2108601370580332749 |  |

### AZ

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Equis Research | 2026-10-09 | 1214 | `pollster_not_selected` | - | https://www.weareequis.us/research/memo-arizona-voter-research---sept-2026 |  |
| A 비당파·원문 검토 후보 | house:02 | Emerson College | 2026-10-14 | 345 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| B 원문·문항 추가 확인 필요 | governor | BSP Research | 2026-09-04 |  | `primary_population_sample_mapping_required` | Arizona State University Center for Latina/os and American Politics Research, Arizona State University Hispanic Research Center | https://linktr.ee/hrc_asu |  |
| B 원문·문항 추가 확인 필요 | house:01 | FirstStrategic | 2026-10-01 | 400 | `primary_provider_population_conflict` | - | https://s3.documentcloud.org/documents/28722214/shahfeeley-poll-release.pdf |  |

### CA

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | University of California Berkeley Jack Citrin Center for Public Opinion Research/Verasight/TrueDot | 2026-09-16 | 1983 | `pollster_not_selected` | Politico | https://www.politico.com/newsletters/california-playbook/2026/09/25/xavier-becerras-dispassionate-supporters-01092984 |  |
| A 비당파·원문 검토 후보 | governor | University of California Berkeley Jack Citrin Center for Public Opinion Research/Verasight/TrueDot | 2026-10-14 | 909 | `pollster_not_selected` | Politico | https://www.politico.com/newsletters/california-playbook/2026/10/21/ramans-apology-and-polling-on-newsom-01128744 |  |
| A 비당파·원문 검토 후보 | house:11 | University of Southern California Democracy and Fair Elections Lab | 2026-10-19 | 454 | `pollster_not_selected` | - | https://www.thedemocracylab.com/ca11 | house-polls-20261023 |
| C 당파·의뢰(참고용) | house:11 | Tavern Research | 2026-09-17 | 658 | `pollster_not_selected` | Jobs and Democracy PAC / DEM | https://www.politico.com/newsletters/california-playbook/2026/10/02/carl-demaio-is-the-establishment-now-01104622 |  |
| C 당파·의뢰(참고용) | house:40 | Grassroots Targeting | 2026-09-09 | 800 | `pollster_not_selected` | California First Fund / REP | https://www.politico.com/newsletters/california-playbook/2026/09/17/paramounts-nashville-overture-01081617 |  |

### CO

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | house:04 | Impact Research | 2026-09-24 | 403 | `pollster_not_selected` | Invest In Tomorrow Coalition | https://www.the-downballot.com/p/morning-digest-why-democrats-think-561 |  |

### CT

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | GreatBlue Research | 2026-10-12 | 1000 | `pollster_not_selected` | CT Insider, Sacred Heart University Institute for Public Policy and Civic Engagement | https://s3.documentcloud.org/documents/28821730/shu-ct-gubernatorial-race-poll-3-of-3.pdf |  |
| B 원문·문항 추가 확인 필요 | governor | University of New Hampshire | 2026-09-21 | 540 | `primary_pdf_access_blocked_toplines_and_methods_not_rechecked` | - | https://scholars.unh.edu/survey_center_polls/1010/ |  |

### FL

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | St. Pete Polls | 2026-09-17 | 913 | `pollster_not_selected` | Florida Politics | https://floridapolitics.com/archives/820638-poll-byron-donalds-44-david-jolly-43-in-dead-heat-race-for-florida-governor/ |  |
| A 비당파·원문 검토 후보 | governor | St. Pete Polls | 2026-10-07 | 836 | `pollster_not_selected` | Florida Politics | https://floridapolitics.com/archives/823921-new-st-pete-polls-survey-has-ashley-moody-at-47-angie-nixon-at-45-and-the-senate-race-still-inside-the-margin-of-error/ |  |
| A 비당파·원문 검토 후보 | governor | YouGov | 2026-10-15 | 825 | `pollster_not_selected` | N+ Univision | https://www.univision.com/noticias/politica/republicans-lead-florida-as-most-latino-voters-say-immigration-enforcement-has-gone-too-far |  |
| A 비당파·원문 검토 후보 | house:14 | Emerson College | 2026-10-14 | 315 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-09-10 | 733 | `pollster_not_selected` | - | https://quantusinsights.org/f/new-quantus-polls-moody-leads-in-florida-flanagan-in-minnesota |  |
| A 비당파·원문 검토 후보 | senate | St. Pete Polls | 2026-09-17 | 913 | `pollster_not_selected` | Florida Politics | https://floridapolitics.com/archives/820638-poll-byron-donalds-44-david-jolly-43-in-dead-heat-race-for-florida-governor/ |  |
| A 비당파·원문 검토 후보 | senate | St. Pete Polls | 2026-10-07 | 836 | `pollster_not_selected` | Florida Politics | https://floridapolitics.com/archives/823921-new-st-pete-polls-survey-has-ashley-moody-at-47-angie-nixon-at-45-and-the-senate-race-still-inside-the-margin-of-error/ |  |
| B 원문·문항 추가 확인 필요 | senate | InsiderAdvantage | 2026-09-21 | 600 | `provider_third_candidate_attribution_unverified` | - | https://insideradvantage.com/insideradvantage-florida-u-s-senate-survey-moody-leads-nixon-by-7/?utm_source=rss&utm_medium=rss&utm_campaign=insideradvantage-florida-u-s-senate-survey-moody-leads-nixon-by-7 |  |
| C 당파·의뢰(참고용) | house:07 | DCCC Targeting and Analytics Department | 2026-10-19 | 414 | `pollster_not_selected` | - / DEM | https://dccc.org/%f0%9f%9a%a8-breaking-new-dccc-poll-shows-a-tied-race-in-fl-07/ |  |
| C 당파·의뢰(참고용) | house:13 | Public Policy Polling | 2026-10-15 | 603 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |
| C 당파·의뢰(참고용) | house:27 | Tulchin Research | 2026-09-13 | 600 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2100648029678170342 |  |

### GA

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | GBAO Strategies | 2026-10-15 | 2000 | `pollster_not_selected` | The Atlanta Journal-Constitution | https://www.ajc.com/politics/2026/10/rick-jackson-has-outspent-keisha-lance-bottoms-but-democratic-enthusiasm-has-the-race-knotted/ |  |
| A 비당파·원문 검토 후보 | governor | Quantus Insights | 2026-10-17 | 755 | `pollster_not_selected` | - | https://quantusinsights.org/polling/f/georgia-two-weeks-out-ossoff-ahead-down-ballot-near-even |  |
| A 비당파·원문 검토 후보 | senate | University of Georgia School of Public and International Affairs | 2026-10-15 | 1000 | `pollster_not_selected` | The Atlanta Journal-Constitution | https://www.ajc.com/politics/2026/10/ajc-poll-ossoff-leads-collins-in-georgias-us-senate-race/ |  |
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-10-17 | 755 | `pollster_not_selected` | - | https://quantusinsights.org/polling/f/georgia-two-weeks-out-ossoff-ahead-down-ballot-near-even |  |
| B 원문·문항 추가 확인 필요 | governor | Wedgewood Polls | 2026-10-03 | 600 | `publisher_identity_unverified` | - | https://drive.google.com/file/d/1ztqd_FYClBh1OknXwKOqi6zJXxECcqDK/view?usp=sharing |  |
| B 원문·문항 추가 확인 필요 | senate | Wedgewood Polls | 2026-10-03 | 600 | `publisher_identity_unverified` | - | https://drive.google.com/file/d/1ztqd_FYClBh1OknXwKOqi6zJXxECcqDK/view?usp=sharing |  |

### IA

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Emerson College | 2026-09-01 | 750 | `outside_reviewed_general_period` | Nexstar Media | https://emersoncollegepolling.com/iowa-2026-poll-hinson-leads-turek/ |  |
| A 비당파·원문 검토 후보 | governor | YouGov | 2026-09-08 | 2041 | `pollster_not_selected` | - | https://d3nkl3psvxxpe9.cloudfront.net/documents/iowa_election_20260903.pdf |  |
| A 비당파·원문 검토 후보 | governor | YouGov | 2026-09-08 | 2167 | `pollster_not_selected` | - | https://d3nkl3psvxxpe9.cloudfront.net/documents/iowa_election_20260903.pdf |  |
| A 비당파·원문 검토 후보 | governor | National Public Affairs | 2026-10-12 | 678 | `pollster_not_selected` | - | https://backend.natpublicaffairs.com/media/Iowa_General_Election_Memo_101526.3.pdf |  |
| A 비당파·원문 검토 후보 | governor | New River | 2026-10-13 | 602 | `pollster_not_selected` | The Cook Political Report | https://www.cookpolitical.com/analysis/survey-research/battleground-district-project/senate-battleground-district-project-october?utm_medium=email_action&utm_source=customer.io |  |
| A 비당파·원문 검토 후보 | house:02 | Emerson College | 2026-10-14 | 344 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | Emerson College | 2026-09-01 | 750 | `outside_reviewed_general_period` | Nexstar Media | https://emersoncollegepolling.com/iowa-2026-poll-hinson-leads-turek/ |  |
| A 비당파·원문 검토 후보 | senate | YouGov | 2026-09-08 | 2166 | `pollster_not_selected` | - | https://d3nkl3psvxxpe9.cloudfront.net/documents/iowa_election_20260903.pdf |  |
| A 비당파·원문 검토 후보 | senate | YouGov | 2026-09-08 | 2041 | `pollster_not_selected` | - | https://d3nkl3psvxxpe9.cloudfront.net/documents/iowa_election_20260903.pdf |  |
| A 비당파·원문 검토 후보 | senate | National Public Affairs | 2026-10-12 | 678 | `pollster_not_selected` | - | https://backend.natpublicaffairs.com/media/Iowa_General_Election_Memo_101526.3.pdf |  |
| A 비당파·원문 검토 후보 | senate | New River Strategies/GS Strategy Group | 2026-10-13 | 602 | `pollster_not_selected` | The Cook Political Report | https://www.cookpolitical.com/analysis/survey-research/battleground-district-project/senate-battleground-district-project-october?utm_medium=email_action&utm_source=customer.io |  |

### IN

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | house:05 | Expedition Strategies | 2026-10-04 | 600 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### KS

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Wedgewood Polls | 2026-09-24 | 500 | `pollster_not_selected` | - | https://drive.google.com/drive/u/0/folders/1VKLmawSn60cr7L9HCx9mtZDvATC20N5u |  |
| A 비당파·원문 검토 후보 | senate | Wedgewood Polls | 2026-09-24 | 500 | `pollster_not_selected` | - | https://drive.google.com/drive/u/0/folders/1VKLmawSn60cr7L9HCx9mtZDvATC20N5u |  |

### KY

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | house:06 | Lake Research Partners | 2026-10-04 | 400 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2108282466733818029 |  |
| C 당파·의뢰(참고용) | house:06 | Lake Research Partners | 2026-10-04 | 400 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2108282466733818029 |  |
| C 당파·의뢰(참고용) | house:06 | Public Policy Polling | 2026-10-20 | 572 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### MA

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | University of New Hampshire | 2026-09-21 | 564 | `unreviewed_matchup` | - | https://scholars.unh.edu/survey_center_polls/1008/ |  |
| A 비당파·원문 검토 후보 | governor | MassINC Polling Group | 2026-09-22 | 800 | `unreviewed_matchup` | CommonWealth Beacon | https://commonwealthbeacon.org/wp-content/uploads/2026/09/Topline-2026-09-CWB-Ballot-Questions-TUES-RELEASE.pdf |  |
| A 비당파·원문 검토 후보 | governor | University of Massachusetts Department of Political Science/YouGov | 2026-10-12 | 800 | `pollster_not_selected` | WCVB-TV | https://www.umass.edu/poll/about/reports/2026-10-massachusetts-public-opinion-poll |  |
| A 비당파·원문 검토 후보 | governor | Suffolk University | 2026-10-17 | 500 | `unreviewed_matchup` | The Boston Globe | https://www.suffolk.edu/academics/research-at-suffolk/political-research-center/polls/massachusetts#collapse-October-20-2026-Massachusetts-Governor-and-US-Senate-Statewide-and-Bellwether-with-The-Boston-Globe |  |
| A 비당파·원문 검토 후보 | senate | University of Massachusetts Department of Political Science/YouGov | 2026-10-12 | 800 | `pollster_not_selected` | WCVB-TV | https://www.umass.edu/poll/about/reports/2026-10-massachusetts-public-opinion-poll |  |

### ME

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | YouGov | 2026-09-08 | 1334 | `pollster_not_selected` | - | https://d3nkl3psvxxpe9.cloudfront.net/documents/ttw_me_20260902.pdf |  |
| A 비당파·원문 검토 후보 | governor | University of Massachusetts Lowell Center for Public Opinion/YouGov | 2026-09-14 | 650 | `outside_reviewed_general_period` | - | https://www.uml.edu/news/press-releases/2026/09242026-maine-poll.aspx |  |
| A 비당파·원문 검토 후보 | governor | Fabrizio, Lee & Associates/Impact Research | 2026-09-22 | 982 | `pollster_not_selected` | AARP | https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-maine/ |  |
| A 비당파·원문 검토 후보 | governor | The Washington Post/George Mason University School of Policy and Government | 2026-10-05 | 800 | `pollster_not_selected` | - | https://www.washingtonpost.com/tablet/2026/10/09/sept-30-oct-5-2026-washington-post-schar-school-poll-maine-voters |  |
| A 비당파·원문 검토 후보 | senate | YouGov | 2026-09-08 | 1335 | `pollster_not_selected` | - | https://d3nkl3psvxxpe9.cloudfront.net/documents/ttw_me_20260902.pdf |  |
| A 비당파·원문 검토 후보 | senate | University of Massachusetts Lowell Center for Public Opinion/YouGov | 2026-09-14 | 650 | `outside_reviewed_general_period` | - | https://www.uml.edu/news/press-releases/2026/09242026-maine-poll.aspx |  |
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-09-15 | 621 | `pollster_not_selected` | - | https://quantusinsights.org/f/quantus-survey-collins-and-jackson-even-in-maine-senate-race |  |
| A 비당파·원문 검토 후보 | senate | Fabrizio, Lee & Associates/Impact Research | 2026-09-22 | 982 | `pollster_not_selected` | AARP | https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-maine/ |  |
| A 비당파·원문 검토 후보 | senate | Wedgewood Polls | 2026-10-01 | 400 | `pollster_not_selected` | - | https://drive.google.com/file/d/1sycfLKEWvUxaW7oNYTdih5DzlXlcmtXC/view |  |
| A 비당파·원문 검토 후보 | senate | The Washington Post/George Mason University School of Policy and Government | 2026-10-05 | 800 | `pollster_not_selected` | - | https://www.washingtonpost.com/tablet/2026/10/09/sept-30-oct-5-2026-washington-post-schar-school-poll-maine-voters |  |
| B 원문·문항 추가 확인 필요 | senate | University of New Hampshire | 2026-09-21 | 1312 | `ranked_choice_question_not_reviewed` | - | https://scholars.unh.edu/survey_center_polls/1007/ |  |
| B 원문·문항 추가 확인 필요 | senate | The New York Times/Siena University | 2026-09-22 | 619 | `ranked_choice_question_not_reviewed` | Portland Press Herald | https://www.nytimes.com/2026/09/24/us/politics/democrats-show-strength-in-michigan-senate-race-but-trail-in-maine-polls-find.html |  |
| B 원문·문항 추가 확인 필요 | senate | co/efficient | 2026-09-30 | 1240 | `ranked_choice_question_not_reviewed` | - | https://battlegrounds.coefficient.org/me/ |  |
| B 원문·문항 추가 확인 필요 | senate | InsiderAdvantage | 2026-10-14 | 1200 | `ranked_choice_question_not_reviewed` | - | https://insideradvantage.com/insideradvantage-senate-surveys-texas-paxton-49-talarico-48-kansas-marshall-48-hamilton-47-maine-jackson-49-collins-47/ |  |

### MI

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | The Washington Post/George Mason University School of Policy and Government | 2026-09-14 | 803 | `pollster_not_selected` | - | https://www.washingtonpost.com/documents/08fa9b5e-43ac-456c-a706-4c33ec6506dc.pdf |  |
| A 비당파·원문 검토 후보 | house:07 | Emerson College | 2026-10-14 | 314 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | The Washington Post/George Mason University School of Policy and Government | 2026-09-14 | 803 | `pollster_not_selected` | - | https://www.washingtonpost.com/documents/08fa9b5e-43ac-456c-a706-4c33ec6506dc.pdf |  |
| A 비당파·원문 검토 후보 | senate | Guidant Polling and Strategy | 2026-09-27 | 800 | `pollster_not_selected` | Public First Action | https://x.com/burgessev/status/2107923538392776875?s=20 |  |
| B 원문·문항 추가 확인 필요 | governor | Cygnal/Beacon Research | 2026-09-21 | 600 | `primary_censored_less_than_one_percent_cannot_be_zero` | Michigan Enjoyer | https://enjoyer.com/michigan-poll-fall-2026/ |  |
| B 원문·문항 추가 확인 필요 | governor | Marist University | 2026-10-18 |  | `missing_sample_size` | - | https://maristpoll.marist.edu/polls/midterm-elections-in-michigan-october-2026/ |  |
| B 원문·문항 추가 확인 필요 | senate | Cygnal/Beacon Research | 2026-09-21 | 600 | `primary_censored_less_than_one_percent_cannot_be_zero` | Michigan Enjoyer | https://enjoyer.com/michigan-poll-fall-2026/ |  |
| B 원문·문항 추가 확인 필요 | senate | Marist University | 2026-10-18 |  | `missing_sample_size` | - | https://maristpoll.marist.edu/polls/midterm-elections-in-michigan-october-2026/ |  |
| C 당파·의뢰(참고용) | governor | Z to A Research | 2026-10-01 | 483 | `pollster_not_selected` | Rust Belt Rising / DEM | https://x.com/rbrtraining/status/2108302504446337272 |  |
| C 당파·의뢰(참고용) | senate | Trafalgar Group | 2026-09-09 | 1079 | `pollster_not_selected` | - / REP | https://www.thetrafalgargroup.org/news/mi-sen-general-0910/ |  |
| C 당파·의뢰(참고용) | senate | Z to A Research | 2026-10-01 | 483 | `pollster_not_selected` | Rust Belt Rising / DEM | https://x.com/rbrtraining/status/2108302504446337272 |  |

### MN

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | SurveyUSA | 2026-09-14 | 654 | `unregistered_primary_host` | KSTP-TV (St. Paul), KAAL-TV (Austin), WDIO-DT (Duluth) | https://kstp.com/kstp-news/top-news/kstp-surveyusa-poll-governor-senate-races-tightening-days-before-early-voting-starts-in-minnesota/ |  |
| A 비당파·원문 검토 후보 | governor | Mason-Dixon | 2026-10-07 | 800 | `pollster_not_selected` | StarTribune, KARE | https://www.startribune.com/minnesota-poll-klobuchar-demuth-governor/601887444 |  |
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-09-10 | 720 | `pollster_not_selected` | - | https://quantusinsights.org/f/new-quantus-polls-moody-leads-in-florida-flanagan-in-minnesota |  |
| A 비당파·원문 검토 후보 | senate | SurveyUSA | 2026-09-14 | 654 | `unregistered_primary_host` | KSTP-TV (St. Paul), KAAL-TV (Austin), WDIO-DT (Duluth) | https://kstp.com/kstp-news/top-news/kstp-surveyusa-poll-governor-senate-races-tightening-days-before-early-voting-starts-in-minnesota/ |  |
| A 비당파·원문 검토 후보 | senate | Big Data Poll | 2026-09-30 | 622 | `pollster_not_selected` | Public Polling Project | https://www.bigdatapoll.com/blog/lone-star-state-poll-peggy-flanagan-holds-slight-lead-over-michele-tafoya-for-us-senate-in-minnesota/ |  |
| C 당파·의뢰(참고용) | governor | GQR | 2026-10-04 | 800 | `pollster_not_selected` | Senate Majority PAC / DEM | https://x.com/DrewSav/status/2108502733045334207 |  |
| C 당파·의뢰(참고용) | house:01 | GBAO Strategies | 2026-09-21 | 500 | `pollster_not_selected` | House Majority PAC / DEM | https://bsky.app/profile/the-downballot.com/post/3mwbqbuzrn22f |  |
| C 당파·의뢰(참고용) | house:01 | Public Policy Polling | 2026-10-14 | 588 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |
| C 당파·의뢰(참고용) | senate | GQR | 2026-10-04 | 800 | `pollster_not_selected` | Senate Majority PAC / DEM | https://x.com/DrewSav/status/2108502733045334207 |  |

### MO

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:02 | Remington Research Group | 2026-09-15 | 565 | `pollster_not_selected` | - | https://x.com/MarkMaxwellTV/status/2103501820840534440?s=20 |  |
| A 비당파·원문 검토 후보 | house:02 | Emerson College | 2026-10-14 | 401 | `unregistered_primary_host` | Poll Vault | us-202eme08dc10c3 |  |
| C 당파·의뢰(참고용) | house:02 | Public Policy Polling | 2026-10-20 | 631 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/MarkMaxwellTV/status/2112721483617464784 |  |

### MS

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | senate | Wedgewood Polls | 2026-10-14 | 511 | `pollster_not_selected` | - | https://drive.google.com/file/d/16nLOQEszQimue_N2O6G42brKUXopDLcu/view |  |

### MT

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:01 | Emerson College | 2026-10-14 | 329 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-09-15 | 625 | `pollster_not_selected` | - | https://quantusinsights.org/f/latest-survey-alme-leads-as-montana%E2%80%99s-senate-opposition-splits |  |
| A 비당파·원문 검토 후보 | senate | American Pulse Research & Polling | 2026-09-24 | 604 | `unreviewed_matchup` | KULR-TV | https://www.montanarightnow.com/elections/montana-senate-race-kurt-alme-tops-bodnar-and-bankhead-in-new-poll-findings/article_cd8401fb-0470-492c-a53a-c7dfe39552ff.html |  |
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-10-18 | 686 | `pollster_not_selected` | - | https://quantusinsights.org/polling/f/montana-senate-alme-leads-by-16-as-bodnar-consolidates |  |
| C 당파·의뢰(참고용) | house:01 | Public Policy Polling | 2026-10-14 | 541 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### NC

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:11 | Emerson College | 2026-10-14 | 388 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | Elon University/YouGov | 2026-10-08 | 561 | `pollster_not_selected` | - | https://eloncdn.blob.core.windows.net/eu3/sites/819/2026/10/Elon-Poll-news-release-10-20-26.pdf |  |
| A 비당파·원문 검토 후보 | senate | Harper Polling | 2026-10-20 | 600 | `pollster_not_selected` | Carolina Journal | https://www.carolinajournal.com/polls/october-2026-coopers-lead-over-whatley-narrows-to-10-points-in-nc-senate-race/ |  |
| B 원문·문항 추가 확인 필요 | house:01 | Neighborhood Research and Media | 2026-10-06 | 303 | `primary_methodology_not_obtained` | - | https://x.com/Shaftan/status/2107772933322277266 |  |
| B 원문·문항 추가 확인 필요 | senate | East Carolina University | 2026-09-03 | 675 | `forced_choice_question_not_comparable` | - | https://surveyresearch-ecu.reportablenews.com/pr/ecu-poll-cooper-leads-whatley-by-7-points |  |
| B 원문·문항 추가 확인 필요 | senate | InsiderAdvantage | 2026-09-17 | 1200 | `primary_release_not_accessed` | - | https://insideradvantage.com/nc-top-line-tabs |  |
| B 원문·문항 추가 확인 필요 | senate | Big Data Poll | 2026-09-29 | 642 | `primary_provider_candidate_values_conflict` | Public Polling Project | https://www.bigdatapoll.com/blog/tar-heel-state-poll-roy-cooper-holds-solid-lead-over-michael-whatley-for-us-senate-in-north-carolina/ |  |
| C 당파·의뢰(참고용) | house:09 | Public Policy Polling | 2026-10-20 | 526 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### NE

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | house:01 | Global Strategy Group | 2026-09-03 | 600 | `pollster_not_selected` | Fight for Nebraska / DEM | https://s3.documentcloud.org/documents/28652094/ne-01-global-strategy-group-for-retire-career-politicians-sept-2026.pdf |  |
| C 당파·의뢰(참고용) | house:01 | Public Policy Polling | 2026-10-20 | 536 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |
| C 당파·의뢰(참고용) | senate | GBAO Strategies | 2026-09-08 | 800 | `pollster_not_selected` | Working Class Majority PAC / DEM | https://www.washingtonsun.com/newsletters/panic-week |  |

### NH

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:01 | University of New Hampshire | 2026-09-21 | 711 | `NH01_provider_Stephany_name_typo_full_primary_PDF_access_blocked_exact_record_review_required` | - | https://scholars.unh.edu/survey_center_polls/1005/ | house-polls-20261023 |

### NV

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | house:02 | Public Policy Polling | 2026-10-13 | 560 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### NY

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Beacon Research | 2026-10-06 | 820 | `pollster_not_selected` | Secure AI Project | https://www.politico.com/newsletters/new-york-playbook/2026/10/15/mamdanis-mia-from-gop-attack-ads-01119739 |  |
| A 비당파·원문 검토 후보 | governor | Quinnipiac University | 2026-10-19 | 1167 | `unregistered_primary_host` | - | https://www.nytimes.com/2026/10/21/nyregion/poll-hochul-blakeman-governor.html |  |
| C 당파·의뢰(참고용) | house:21 | Public Policy Polling | 2026-10-13 | 613 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### OH

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | New River Strategies/GS Strategy Group | 2026-10-13 | 959 | `pollster_not_selected` | The Cook Political Report | https://www.cookpolitical.com/analysis/survey-research/battleground-district-project/senate-battleground-district-project-october?utm_medium=email_action&utm_source=customer.io |  |
| A 비당파·원문 검토 후보 | governor | VoteHub/Verasight | 2026-10-20 | 531 | `pollster_not_selected` | VoteHub | https://cdn.votehub.com/pdfs/VoteHub_Verasight_Oct_2026_Ohio_Report_D1CB7735.pdf |  |
| A 비당파·원문 검토 후보 | senate | New River Strategies/GS Strategy Group | 2026-10-13 | 959 | `pollster_not_selected` | The Cook Political Report | https://www.cookpolitical.com/analysis/survey-research/battleground-district-project/senate-battleground-district-project-october?utm_medium=email_action&utm_source=customer.io |  |
| A 비당파·원문 검토 후보 | senate | VoteHub/Verasight | 2026-10-20 | 531 | `pollster_not_selected` | VoteHub | https://cdn.votehub.com/pdfs/VoteHub_Verasight_Oct_2026_Ohio_Report_D1CB7735.pdf |  |
| B 원문·문항 추가 확인 필요 | governor | Big Data Poll | 2026-09-27 | 680 | `primary_geography_and_candidate_table_not_verified` | Public Polling Project | https://www.bigdatapoll.com/blog/buckeye-state-poll-sherrod-brown-leads-jon-husted-for-us-senate-in-ohio/ |  |
| B 원문·문항 추가 확인 필요 | senate | InsiderAdvantage | 2026-09-09 | 1200 | `primary_release_not_accessed` | - | https://insideradvantage.com/top-line-tabs-ohio/ |  |
| B 원문·문항 추가 확인 필요 | senate | Quantus Insights | 2026-09-23 | 695 | `primary_question_and_methods_not_obtained` | - | https://quantusinsights.org/polling/f/brown-and-husted-deadlocked-in-ohio-senate-race |  |
| B 원문·문항 추가 확인 필요 | senate | Big Data Poll | 2026-09-27 | 680 | `primary_geography_methodology_conflict` | Public Polling Project | https://www.bigdatapoll.com/blog/buckeye-state-poll-sherrod-brown-leads-jon-husted-for-us-senate-in-ohio/ |  |
| B 원문·문항 추가 확인 필요 | senate | InsiderAdvantage | 2026-09-29 | 1200 | `primary_release_not_accessed` | - | https://insideradvantage.com/insideradvantage-ohio-senate-race-narrows-to-brown-up-by-one |  |
| C 당파·의뢰(참고용) | house:10 | DCCC Targeting and Analytics Department | 2026-10-13 | 535 | `pollster_not_selected` | - / DEM | https://dccc.org/dccc-polling-memo-knickerbocker-leads-turner-by-3-in-oh-10/ |  |
| C 당파·의뢰(참고용) | house:15 | Hart Research Associates | 2026-09-24 | 500 | `primary_methodology_not_obtained` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2104619061556457603 |  |
| C 당파·의뢰(참고용) | house:15 | Hart Research Associates | 2026-10-12 | 503 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |
| C 당파·의뢰(참고용) | senate | Trafalgar Group | 2026-09-16 | 1085 | `pollster_not_selected` | - / REP | https://www.thetrafalgargroup.org/wp-content/uploads/2026/09/OH-Midterms-Full-Report-0917.pdf |  |

### OR

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| B 원문·문항 추가 확인 필요 | governor | DHM Research | 2026-09-11 | 600 | `primary_question_and_field_period_not_verified` | Grow Oregon | https://www.oregonjournalismproject.org/new-poll-shows-drazan-with-slight-lead-in-governors-race |  |
| B 원문·문항 추가 확인 필요 | governor | DHM Research | 2026-10-01 | 549 | `original_source_access_and_detailed_question_methodology_unavailable` | The Oregonian/Oregon/Live | https://www.oregonlive.com/politics/2026/10/oregon-governors-race-may-be-shifting-new-poll-shows.html |  |

### PA

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Z to A Research | 2026-10-01 | 630 | `pollster_not_selected` | - | https://x.com/rbrtraining/status/2108302504446337272 |  |
| A 비당파·원문 검토 후보 | house:08 | Emerson College | 2026-10-14 | 396 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |

### RI

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | University of New Hampshire | 2026-09-21 | 598 | `unreviewed_matchup` | - | https://scholars.unh.edu/survey_center_polls/1009/ |  |
| A 비당파·원문 검토 후보 | governor | Embold Research | 2026-10-08 | 815 | `pollster_not_selected` | Salve Regina University Pell Center for International Relations and Public Policy | https://salve.edu/news/news-listing/pell-center-survey-foulkes-leads-governors-race-11-points-lieutenant-governor-contest-deadlocked |  |
| A 비당파·원문 검토 후보 | house:01 | Embold Research | 2026-10-08 | 363 | `pollster_not_selected` | Salve Regina University Pell Center for International Relations and Public Policy | https://salve.edu/news/news-listing/pell-center-survey-foulkes-leads-governors-race-11-points-lieutenant-governor-contest-deadlocked |  |
| A 비당파·원문 검토 후보 | house:02 | Embold Research | 2026-10-08 | 417 | `pollster_not_selected` | Salve Regina University Pell Center for International Relations and Public Policy | https://salve.edu/news/news-listing/pell-center-survey-foulkes-leads-governors-race-11-points-lieutenant-governor-contest-deadlocked |  |
| A 비당파·원문 검토 후보 | senate | Embold Research | 2026-10-08 | 815 | `pollster_not_selected` | Salve Regina University Pell Center for International Relations and Public Policy | https://salve.edu/news/news-listing/pell-center-survey-foulkes-leads-governors-race-11-points-lieutenant-governor-contest-deadlocked |  |

### SC

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | governor | Trafalgar Group | 2026-10-18 | 1095 | `pollster_not_selected` | - / REP | https://www.thetrafalgargroup.org/news/sc-statewide-gen-1020/ |  |

### SD

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | senate | Quantus Insights | 2026-10-19 | 657 | `pollster_not_selected` | - | https://www.semafor.com/article/10/21/2026/poll-shows-big-lead-for-south-dakota-republican-rounds |  |
| A 비당파·원문 검토 후보 | senate | Emerson College | 2026-10-20 | 803 | `unregistered_primary_host` | KELO-TV | https://www.keloland.com/keloland-com-original/keloland-poll-rounds-leads-bengs-at-8-trump-approval-down/amp/ |  |
| 완료 | house:00 | Mason-Dixon | 2026-10-14 | 500 | `pollster_not_selected` | South Dakota News Watch, Chiesman Center for Democracy at the University of South Dakota | https://www.sdnewswatch.org/south-dakota-poll-us-house-jackley-gronli/ | house-polls-20261023 |
| 완료 | senate | Mason-Dixon | 2026-10-14 | 500 | `pollster_not_selected` | South Dakota News Watch, Chiesman Center for Democracy at the University of South Dakota | https://www.sdnewswatch.org/south-dakota-poll-us-senate-rounds-bengs | sd-senate-20261023 |

### TN

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Spry Strategies | 2026-10-16 | 635 | `pollster_not_selected` | - | https://www.spryresearch.com/post/tennessee-statewide-survey-october-2026 |  |

### TX

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | governor | Fabrizio Ward/Impact Research | 2026-09-01 | 895 | `pollster_not_selected` | - | https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-texas |  |
| A 비당파·원문 검토 후보 | governor | YouGov | 2026-09-04 | 1000 | `pollster_not_selected` | Univision | https://www.univision.com/noticias/politica/poll-univision-texas-2026 |  |
| A 비당파·원문 검토 후보 | governor | Guidant Polling and Strategy | 2026-09-28 | 800 | `pollster_not_selected` | Public First Action | https://x.com/burgessev/status/2107923538392776875?s=20 |  |
| A 비당파·원문 검토 후보 | governor | New River Strategies/GS Strategy Group | 2026-10-13 | 934 | `pollster_not_selected` | The Cook Political Report | https://www.cookpolitical.com/analysis/survey-research/battleground-district-project/senate-battleground-district-project-october?utm_medium=email_action&utm_source=customer.io |  |
| A 비당파·원문 검토 후보 | governor | Pollfinity | 2026-10-18 | 278 | `pollster_not_selected` | - | https://www.pollfinity.com/polls/tx-governor-senate-2026-oct |  |
| A 비당파·원문 검토 후보 | house:15 | Texas Southern University Barbara Jordan Public Policy Research and Survey Center | 2026-10-16 |  | `pollster_not_selected` | San Antonio Express-News, El País, Puente News Collaborative | https://www.expressnews.com/politics/article/bobby-pulido-monica-de-la-cruz-poll-donald-trump-22483930.php |  |
| A 비당파·원문 검토 후보 | house:35 | Emerson College | 2026-10-14 | 417 | `unregistered_primary_host` | Poll Vault | https://pollvault.substack.com/p/levee-math |  |
| A 비당파·원문 검토 후보 | senate | Fabrizio Ward/Impact Research | 2026-09-01 | 895 | `pollster_not_selected` | - | https://www.aarp.org/pri/topics/voter-research/politics/2026-midterm-election-poll-texas |  |
| A 비당파·원문 검토 후보 | senate | YouGov | 2026-09-04 | 1000 | `pollster_not_selected` | Univision | https://www.univision.com/noticias/politica/poll-univision-texas-2026 |  |
| A 비당파·원문 검토 후보 | senate | Guidant Polling and Strategy | 2026-09-28 | 800 | `pollster_not_selected` | Public First Action | https://x.com/burgessev/status/2107923538392776875?s=20 |  |
| A 비당파·원문 검토 후보 | senate | New River Strategies/GS Strategy Group | 2026-10-13 | 934 | `pollster_not_selected` | The Cook Political Report | https://www.cookpolitical.com/analysis/survey-research/battleground-district-project/senate-battleground-district-project-october?utm_medium=email_action&utm_source=customer.io |  |
| A 비당파·원문 검토 후보 | senate | Pollfinity | 2026-10-18 | 278 | `pollster_not_selected` | - | https://www.pollfinity.com/polls/tx-governor-senate-2026-oct |  |
| C 당파·의뢰(참고용) | house:15 | Normington, Petts & Associates | 2026-09-28 | 400 | `commissioner_primary_methodology_not_obtained` | House Majority PAC / DEM | https://x.com/PatrickSvitek/status/2105651406627561762?s=20 |  |
| C 당파·의뢰(참고용) | house:23 | Normington, Petts & Associates | 2026-10-07 | 400 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |
| C 당파·의뢰(참고용) | house:28 | DCCC Targeting and Analytics Department | 2026-10-13 | 563 | `pollster_not_selected` | - / DEM | https://dccc.org/%f0%9f%9a%a8-breaking-new-dccc-poll-explains-why-republicans-abandoned-tano-tijerina/ |  |
| C 당파·의뢰(참고용) | house:35 | Normington, Petts & Associates | 2026-10-14 | 400 | `pollster_not_selected` | House Majority PAC / DEM | https://x.com/cjwarnke/status/2112877284684341727 |  |

### UT

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:01 | Lighthouse Research | 2026-09-10 | 515 | `outside_reviewed_general_period` | Utah Debate Commission | https://utahdebatecommission.org/2026-polling/ | house-polls-20261023 |
| A 비당파·원문 검토 후보 | house:03 | Lighthouse Research | 2026-09-15 | 508 | `unreviewed_matchup` | Utah Debate Commission | https://utahdebatecommission.org/2026-polling/ | house-polls-20261023 |
| A 비당파·원문 검토 후보 | house:04 | Lighthouse Research | 2026-09-17 | 513 | `unreviewed_matchup` | Utah Debate Commission | https://utahdebatecommission.org/2026-polling/ | house-polls-20261023 |

### VT

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| A 비당파·원문 검토 후보 | house:00 | University of New Hampshire | 2026-09-21 | 835 | `unreviewed_matchup` | - | https://scholars.unh.edu/survey_center_polls/1006/ | house-polls-20261023 |

### WA

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | house:03 | Change Research | 2026-10-21 | 551 | `pollster_not_selected` | Northwest Progressive Institute / DEM | https://www.nwprogressive.org/weblog/2026/10/theyre-tied-again-in-wa-03-npis-autumn-civic-heartbeat-polling-finds-marie-gluesenkamp-perez-at-45-john-braun-at-44.html |  |

### WI

| 등급 | 선거 | 기관 | 기간 끝 | n | 사유 | 의뢰·당파 | 원문 | 받은 원문 |
|---|---|---|---|---|---|---|---|---|
| C 당파·의뢰(참고용) | governor | Z to A Research | 2026-10-01 | 662 | `pollster_not_selected` | Rust Belt Rising / DEM | https://x.com/rbrtraining/status/2108302504446337272 |  |
| C 당파·의뢰(참고용) | house:01 | Impact Research | 2026-10-01 | 500 | `commissioner_primary_methodology_not_obtained` | House Majority PAC / DEM | https://bsky.app/profile/the-downballot.com/post/3mwyouhbwg22k |  |

