# 미국 주요 선거 여론조사 데이터 인수

## 2026-10-02 자동 수집·경합 선거 감시 확장

이 문서 아래의 2026-09-11 내용은 초기 **수기 검증 자료**의 당시 상태입니다. 별도 최신 출력 `public/data/usa_election_live_polls_v1.json`은 VoteHub 공개 API로 매번 갱신하며, `usa_election_live_polls_status_v1.json`에 성공/실패를 기록합니다. 신규 관측은 `verification=selected_source_aggregator_import`로 표기합니다. 기관·원문 도메인·본선 대진·날짜·모집단·표본 검사 후에만 수용합니다. 현재 7일 기본, 14일 선택입니다. 기관별 최신 한 건을 셉니다. 사용자 2026-10-05 지시로 단일 기관도 `single_poll_lead`로 단일 기관 참고값을 제공하며, 2기관 이상 과반 우세는 `poll_lead`입니다. 공식 인증 결과는 별도 수기 검토 파일을 통해서만 우선합니다.

선거 전에는 `races[race_id].observations[]`에 해당 본선의 채택된 조사를 누적해 보여줄 수 있습니다. 7/14일 우세 집계는 그중 해당 기간의 기관별 최신 조사만 씁니다. 선거일 다음 날(UTC 날짜 기준)부터 `phase=awaiting_certified_result`가 되고 **화면용** `observations[]`는 빈 배열, `windows[7|14].status=election_closed`가 됩니다. 인증된 결과가 들어오면 `phase=certified_result`와 `result`를 표시합니다. 과거 조사 기록은 `public/data/usa_election_poll_history_2026.json`에 감사용으로 남습니다. Git 커밋 이력과 원출처도 존재하므로 전체 저장소에서 조사 흔적을 물리적으로 삭제하는 기능은 아닙니다. API 실패 시에도 선거가 끝난 레이스의 화면용 목록은 닫고 source health를 오류로 표시합니다.

사용자가 제공한 `references/2026-10-01-cursor.md`는 Cook 경합 전망을 설명하는 참고 메모이지 여론조사 원문이 아닙니다. 이 중 공식 Cook 목록과 대조한 55개 경쟁 선거 ID를 `config/usa_polls/watchlist_2026.json`으로 선별했고, 수집 우선순위로만 붙였습니다. 총 24개 주 72개 감시 슬롯 중 60개는 본선 후보 대진이 미검증이라 자동 수치 채택을 보류합니다. Cook 등급을 `poll_lead`나 승자 색으로 바꾸지 마세요. Cook 출처의 변경 감시/자동 라이선스 API 수집은 없습니다. 자세한 출처 경계는 `references/README.md`를 보세요.

초기 수기 자료의 10개 주/22개 슬롯 및 관측 건수는 아래의 역사적 스냅샷이며 현재 자동 수집의 커버리지와 다릅니다. 2026-10-01 UTC 실제 API 갱신은 72개 슬롯에서 채택 관측 13건, 7일 `poll_lead` 0건, 14일 `poll_lead` 2건(MI 상원·주지사)입니다. 이후 숫자는 매일 달라집니다.

GitHub Actions와 배포 워크플로는 `docs/ops/OWNERS.md`상 Claude 소유이고 `codex/` PR에는 ownership guard가 걸립니다. Claude는 `ops/us_election_polls_refresh.yml.example`을 `.github/workflows/us_election_polls_refresh.yml`로 설치하고, `.github/workflows/deploy.yml`의 `workflow_run.workflows`에 `US election polls daily`를 추가해야 합니다. 그 뒤 main의 `workflow_dispatch`를 1회 실행하고 결과 파일·source health·배포 URL을 확인하세요. 이 PR 자체는 백엔드/정본/스냅샷을 전달하며, 활성 일일 실행과 UI 연결은 별도입니다.

2026-09-11 KST / T33 / `codex/us-election-polls`.
UI와 활성 workflow는 변경하지 않았습니다. 이 파일은 Claude가 지도 UI와 원격 갱신을 연결할 때의 계약입니다.

## 제공 범위

- NY·TN·GA·FL·PA·MI·WI·AZ·NV·NC의 주별 상원·주지사 감시 슬롯과 NY-10·NC-01 하원: 22개.
- 검증한 7개 조사에서 13개 문항/모집단 결과, 8개 선거에 관측값.
- 자료가 있는 선거: NY 주지사·NY-10, WI 주지사, FL 주지사·상원, GA 상원, NC-01, NV 주지사.
- 이 초기 선정은 기업 입지 지도나 경합도 계산 결과가 아닙니다. 두 하원 지역구는 지역 방송이 다룬 주요 경선의 초기 표본입니다. 중요 하원 전체를 선정한 상태가 아닙니다.
- TN·PA·MI·AZ에는 아직 편입한 후보 선택 조사가 없습니다. PA Siena 8/25 조사는 존재하지만 연결된 NYT 세부 표를 이번 환경에서 열지 못했습니다. 전국/10개 주 전체 조사 수집 완료로 표시하지 마세요.
- GA 주지사 경선 표는 확보했지만 하위 표본·가중 설계 검토 대기입니다. Vanderbilt의 경제·직무평가 조사를 TN 후보 선택 조사로 바꾸지 않습니다.

## UI 읽기 계약

모든 경로는 `public/data/` 기준 상대 경로입니다.

1. `usa_election_polls_index_v1.json` → `cycles["2026"].path`
2. 전국 파일 `states["NY"].path`
3. 주 파일 `races["USA:NY:house:10"].path`
4. 선거 파일 `observations[]`

선거자금의 `race_id`와 동일합니다. 상원 `USA:GA:senate`, 주지사 `USA:NY:governor`, 하원 `USA:NC:house:01`.
금액 데이터의 존재 여부와 관계없이 여론조사를 읽으세요. 주지사 자금이 unsupported여도 여론조사는 있을 수 있습니다.
`race_id`는 선거구/직위 조인 키이며 개별 상원 의석·보궐/정기·후보 확정 식별자가 아닙니다. `seat_class`, `election_kind`를 확인하지 못한 곳은 null/미확인입니다.
현행 도형 문자열 조인은 가능하지만 조사 당시 선거구 경계와 120대 경계가 같다는 검증은 별도입니다.

선거 파일의 주요 항목:

| 필드 | 표시/의미 |
|---|---|
| `status` | `observed_partial` 또는 `no_verified_poll`. 후자는 검증 자료 미편입이며 지지율 0이 아님 |
| `election_schedule_status` | 이 데이터셋은 선거 개최 일정의 정본이 아님. 빈 상원 슬롯을 2026 선거 예정으로 표시하면 안 됨 |
| `headline_observation_ids` | 최근·본선·LV·출처 변경 미감지인 결과의 후보 목록. 승률이나 대표 평균이 아님 |
| `independent_survey_count` | 같은 조사의 질문/모집단을 중복 세지 않음 |
| `poll_average_pct`, `win_probability` | 항상 null. UI에서 임의 계산 금지 |

각 관측의 `answers[]`는 후보뿐 아니라 미정·기타·투표 안 함·모름/거절을 구분합니다. 값은 0~100의 퍼센트로, `49`는 49%입니다.
`candidate_id`는 null입니다. 이름만으로 FEC 후보 카드에 자동 합치지 말고 선거 수준의 여론조사 목록으로 표시하세요.
정당은 원문 보고값이며 원문 NPP를 다른 정당으로 강제 치환하지 않습니다.

필수 화면 정보: 조사기관·후원자·조사 시작/종료일·발표일·모집단·문항 표본·조사 방식·원문 링크.
`question_summary_ko`는 원문 질문의 요약이며 직접 인용이 아닙니다. `question_locator`로 표/PDF 위치를 확인할 수 있습니다.
`sample_n`은 전체 표본, `question_n`은 해당 문항/모집단의 보고된 표본입니다. 가중 빈도를 실제 응답자 수로 역산하지 않습니다.
`uncertainty.type`의 credibility interval을 전통적인 표본오차로 바꾸지 마세요. `scope=survey`이면 해당 문항 자체의 오차로 그리지 마세요.

### 반드시 분리할 보기

- `display_group=general`: 원문에 보고된 본선 후보 조합. 최종 투표용지 독립 검증 상태와 구분.
- `primary`: 경선 자료. NY-10·NC-01은 과거 경선으로 현재 본선 카드와 분리.
- `hypothetical`: 조사 당시 가상 상대 조합. GA의 세 가지 상원 조합은 같은 조사 한 건.
- WI의 등록 유권자(RV)·투표 가능 유권자(LV)는 같은 조사 하위 표본. 서로 다른 기관 조사로 세지 않음.

최근 여부는 조사 종료일 후 45일이라는 운영 기준이며 정확도 등급이 아닙니다. `as_of`는 UTC 날짜입니다.
정적 파일이 며칠간 갱신되지 않았다면 UI는 실제 날짜와 `field_end`를 다시 비교하거나 오래된 스냅샷임을 표시해야 합니다.
현재 선거가 종료되었다면 별도 선거 일정 정본에 따라 역사 자료로 보내세요. 이 파이프라인은 선거 종료 여부를 추정하지 않습니다.

## 출처 정책과 감사 자료

정본 입력: `config/usa_polls/2026.json`. 손으로 검증한 문항 전사이며 fixture/예측 자료가 아닙니다.
각 기관의 `selection_reason_ko`, 결과·방법론 URL, 질문 위치, 검토 날짜, 오차 종류를 보존합니다.
`review.human_reviewed=false`: Codex가 원문을 대조했으며 사람이 별도 승인한 것으로 표시하지 않습니다.
기관의 지역성·공개 방법론은 선정 이유입니다. 무오류/무편향 보증이나 임의 품질 등급이 아닙니다.
내부 캠페인 조사·유료 자료·표본 불명 온라인 투표를 이 기본 목록에 자동 편입하지 않습니다.

전사상 중요한 사례:

- FL의 전체 n=786과 문항 n=776/773/772/768을 분리. 상원 한 조합의 반올림 합계 101%를 100%로 재조정하지 않음.
- NC-01 세부 표에 있는 Ashley-Nicole Russell 0.5%를 보도자료 생략을 이유로 제거하지 않음.
- NV의 Danielle Ford도 세부 표에 따라 포함. 후보 두 명의 비율만 100%로 재계산하지 않음.
- NY-07은 제목과 본문의 선거구 번호가 달라 격리. NY-10 결과에 섞지 않음.
- GA 가중 변수 상세, NV 방법론 두 문단의 인종 가중 기재 차이는 limitations에 보존.

## 갱신 절차

런타임은 Python 3.9+ 표준 라이브러리만 사용합니다. FEC 키나 새 API 키가 필요하지 않습니다.

```bash
cd "New for anti/scripts/election_watch"
python3 -m unittest discover -s tests -p 'test_election_polls.py' -v
python3 monitor_election_polls.py --report /tmp/poll-monitor.json
python3 build_election_polls.py --monitor-report /tmp/poll-monitor.json
```

`monitor`는 공개 문서/목록의 변경만 감지합니다. 신규 퍼센트를 자동 추출하거나 입력을 승인하지 않습니다.
검증 기준 fingerprint는 입력 정본에 고정돼 있습니다. 변경된 문서는 다음 실행에도 changed로 남습니다.
HTML은 본문/링크, XLSX는 셀/수식/문자열의 의미 내용을 비교합니다. WI는 무작위 추천 글을 제외한 entry-content 본문만 비교합니다.
PDF는 바이트를 비교하므로 메타데이터만 바뀌어도 검토 대상으로 잡힐 수 있습니다.
목록 감시는 새 조사 존재를 놓치지 않기 위한 보조 수단이며 모든 기관·유료 DB의 완전한 발견을 보장하지 않습니다.

새 자료 편입: 원문 문항·표본·전체 답변·조사 방식·후원·선거/경계를 확인 → 정본 JSON의 observations와 출처 baseline 갱신 → 검증 → 재생성 → 데이터 PR.
통신 실패는 보고서에 남고 monitor 종료 코드 1입니다. 기존 관측 입력을 지우지 않습니다. 보고서를 넘겨 빌드하면 영향받은 출처를 표시하고 대표 표시 대상에서 제외합니다.
유효하지 않은 전사는 전체 빌드를 중단하며 기존 인덱스를 보존합니다. 의존 파일은 내용 해시 경로로 먼저 쓰고 인덱스를 마지막에 교체합니다.
새 회기는 새 JSON을 만들어 `--input config/usa_polls/2028.json`으로 실행하세요. 기존 회기 인덱스는 보존합니다. 2026 조사를 2028 조사로 자동 재표기하지 않습니다.

## Claude 설치 단계

활성 GitHub Actions는 Claude 소유입니다. `ops/us_election_polls_refresh.yml.example`은 아직 설치되지 않은 검토용 템플릿입니다.
권장: 매일 21:00 UTC(다음 날 06:00 KST), 또는 주 1회. 감시·노후화 갱신을 자동 실행하고 결과 JSON을 데이터 PR로 제출합니다.
목록/문서 변경이 있으면 담당자가 검토 후 정본을 갱신해야 새로운 수치가 표시됩니다. **완전 무인 수치 수집은 구현하지 않았습니다.**
원격 스케줄 설치·머지·배포·운영 페이지 확인은 이번 데이터 PR의 완료 증거에 포함하지 않습니다.
배포 대상에 `usa_election_polls_index_v1.json` 및 `usa_election_polls/**`를 포함하고, 전국→주→선거 경로의 HTTP 200/해시 및 실제 화면의 source/stale 표시를 검증하세요.

## 남은 수집 큐

정본 `review_queue`가 기계 판독 목록입니다. 우선 TN 후보 선택 원문, PA 원문 접근, MI·AZ의 주요 지역 조사, GA 주지사, 중요 하원 목록과 현행 경계 검증을 이어가세요.
유료 DB/API가 필요해지는 경우 사용자에게 접근 권한을 요청하고 멈춥니다. 재설정 기능은 사용자가 직접 실행합니다.

## 이번 검증 결과

- 11개 계약/회귀 테스트 통과. 누락·중복·미래 날짜·잘못된 분모·NaN·추정 후보 ID·출처 변경·실패 보존·재생성 재현성을 확인.
- 공개 원문 7개와 발견용 목록 5개 실제 요청 성공. 최종 보고서 error_count=0, needs_review=false.
- 인덱스 포함 34개 공개 JSON의 모든 참조를 확인. 22개 race_id 전부 기존 선거자금 국가/주 인덱스에 존재.
- 선택된 하원 두 지역구의 코드가 현재 저장소 도형에 존재함을 확인. 조사 당시 경계와 동일함까지 확인한 것은 아님.
- 이번 UTC 스냅샷 기준 최근 본선 LV 대표 표시 대상: NY·WI·NV 주지사 3건. 나머지는 RV·과거 경선·오래된 가상 대결로 분리.
- 활성 스케줄·운영 배포·실제 화면 검증은 미실행.

## 전국 의석 조건부 집계 (2026-10-05)

`seat_scenarios.py`가 `usa_midterms_forecast_v1.json`을 함께 산출합니다.
비선거 상원·주지사는 기존 명부의 정당별 잔여 의석을 계산하며 무소속은 별도입니다.
하원과 개선 상원은 검토한 Cook Solid/Likely 등급의 유지 가정만 기초 집계에 넣습니다.
Lean/Toss-up·미확보는 미정으로 남기고, 검증된 최근 조사 우세나 인증 결과가 있으면
해당 선거만 대체합니다. 7일 기본과 14일 대안은 따로 계산합니다.

이는 통계적 당선 예측이 아닙니다. `seats`와 `win_prob`는 발행하지 않으며,
`scenario_counts`·`unresolved_seats`·`buckets`·`conditional_bounds`에 전제와 미정을 담습니다.
기존 UI는 `margin_note_ko`로 숫자와 전제를 표시할 수 있습니다.
평가 등급은 자동 수집하지 않으며 21일 뒤 제외합니다. 2026-10-05 열린 Cook 원문에서
주지사 36곳의 10월 1일 등급도 확인했습니다. Solid/Likely 유지 가정과 비선거 14곳을
기초 집계에 넣고 Lean/Toss-up 12곳은 조사 우세·인증 결과 또는 미정으로 남깁니다.
Cook API 접근·라이선스는 별도 문의 대상이며 자동 API 연결은 구현하지 않았습니다.
선거 다음 날부터 조사 신호·등급 가정을 제외하고 인증 결과를 우선합니다.
명부/정책 검증 실패 시 집계는 hold로 바꾸되 정상 수집한 여론조사는 보존합니다.

자동 발행 시 Actions의 git add와 artifact 경로에 이 전망 JSON도 포함해야 합니다.
공용 배포 및 UI 코드는 해당 데이터 변경 PR에서 수정하지 않습니다.

### Toss-up / Lean 판단 계약 (사용자 2026-10-05 확정)

Cook의 등급 방향을 결론으로 사용하지 않습니다. 대상은 하원 43곳·상원 9곳·주지사
12곳, 총 64곳이며 `windows[7|14].competitive_conclusions`에서 각 선거의 결론을
읽습니다. `conclusion_ko`는 조사상 우세 또는 판정 보류이고, `basis`, `poll_status`,
`included_poll_ids`로 근거를 추적합니다. 7일 기본·14일 선택, 기관별 최신 조사 1건,
단일 기관 수치상 앞섬은 참고값, 복수 기관은 과반 우세이며 LV/RV는 분리합니다.
조사 없음·동률·미검증 대진은 보류합니다. Solid/Likely는 별도의 기초 유지 가정이며
이 결론 목록에 포함하지 않습니다. 인증 결과는 모든 등급보다 우선합니다.

Marist 공개 방법론과 OH 원문, Emerson NY-17, Siena TX·IA 주지사 원문, NGA AZ·GA·TN
대진을 검토해 편입했습니다. 2026 비선거 슬롯 6곳은 제외했습니다. 감시 목록은
26개 주 71개 슬롯이며 실제 자료가 있는 수와 구분해야 합니다.

2026-10-05 09:41 UTC 실제 공개 API 수집 성공: 23관측·14개 선거에 자료 있음·71개 감시
슬롯·26개 주. 감시 대상 수와 실제 조사가 있는 수는 다릅니다. 7일에는 단일 기관 우세
4곳, 복수 기관 우세 0곳입니다. 14일에는 단일 기관 우세 8곳, 복수 기관 우세 1곳입니다.
자동화 PR의 병합과 최초 Actions→배포 검증은 아직 남았습니다.

### 조사 출처와 판단 근거 (2026-10-05 보강)

이전의 1기관 하·2기관 중·3기관 75% 일치 상 기준은 철회했습니다. 조사 수와
일치도만으로 품질·정확도를 평가할 수 없습니다. `evidence_quality.grade`는 null,
`level=unrated`이며 기관 수·집계 방향 비율과 단일/복수 기관 여부를 사실값으로 제공합니다.

`observations[].source_quality`는 집계값의 검증 상태입니다. 원문을 아직 대조하지
못한 자동 수집은 `verification_level=partial`, `methodological_quality=unrated`입니다.
선정 기관과 원문 도메인·대진·날짜·표본을 확인했지만 정확도 등급을 자동 부여하지 않습니다.
원문 숫자를 대조한 경우 `primary_toplines_checked`, 검토일·출처·공개 항목과 미확인
항목을 붙입니다. 원문 검토는 정확도 인증이 아니며, 미래 조사에도 동일 평가를 상속하지 않습니다.

`config/usa_polls/quality_reviews_2026.json`에 5개 관측의 원문 검토 기록을 담았습니다.
NY-17은 결과표·방법론, Ohio Suffolk는 원문 PDF·방법론을 확인했습니다. Siena의 TX·OH·IA는
발표 수치만 대조했으며 상세 방법론 링크에 접근하지 못한 한계를 남겼습니다. 검토 레코드는
기관·모집단·시기·표본·응답값 fingerprint에 연결합니다. 그 값이 바뀌면 검토를 재사용하지
않고 관측을 검토 대기열로 보냅니다.

`windows[7|14].poll_details`와 전국 경쟁 선거 결론의 `poll_details`에 기관별 출처 검토,
발표 오차범위/신뢰구간과 수치상 격차를 제공합니다. 비확률 조사 신뢰구간을 확률표본의
표본오차로 바꾸지 않으며, 전체 표본 오차를 후보 간 격차 오차로 간주하지 않습니다.
`significance=not_evaluated`이고 당선확률도 발행하지 않습니다.
검토 항목은 [AAPOR 공개 기준](https://aapor.org/standards-and-ethics/disclosure-standards/)과
[조사 모범 사례](https://aapor.org/standards-and-ethics/best-practices/)를 참고했습니다.

조건부 집계는 단일 기관 참고값을 `buckets.single_poll_lead`에 분리합니다.
`single_poll_lead_counts`, `scenario_counts_without_single_polls`,
`unresolved_without_single_polls`로 단일 조사를 제외한 비교도 가능합니다.

UI에서는 `single_poll_lead`를 단일 조사 참고값으로, 기관 수·출처 검증·수치상 격차와
발표 오차범위를 함께 표시해야 합니다. 이 PR은 UI를 수정하지 않으며 기존 지도는
새 상태를 처리하기 전까지 단일 기관 색상을 표시하지 않을 수 있습니다.

### 미등록 기관·개별 원문 편입 (2026-10-06 KST)

기관 등록은 필요조건이 아닙니다. 기존 기관/호스트 경로와 별도로
`quality_reviews_2026.json.reviews[id].admission`의 개별 발표 검토 경로를 추가했습니다.
정확한 기관명·provider URL·원문 수치·방법 공개 항목·정규화 fingerprint가 모두
일치해야 합니다. 공유 Google/Drive 호스트 전체를 허용하지 않으며, 링크만 있는
미검토 레코드는 채택하지 않습니다. 새 발표는 원문 대조 또는 검토한 기관 경로로
편입합니다. URL/값/모집단/표본 변경은 재검토 대상입니다.

- `source_admission`: `registered_pollster` 또는 `reviewed_release`.
- `aggregation_eligibility`: `eligible`, 제외 사유 `reasons`.
- `display_group`: 본선 자료 `general` 또는 과거 대진 참고
  `historical_matchup_reference`. 기관 미등록을 저품질 등급으로 바꾸지 않습니다.
- `windows[7|14].reference_ids/reference_details/reference_poll_count`:
  최근 기간에 있는 참고 전용 자료. `included_ids`와 기관별 우세 횟수에는 넣지 않습니다.
  참고만 있으면 `status_note_ko`가 집계 가능한 조사 없음과 자료 자체의 부재를 구분합니다.
- 검토 대기열에도 원문 URL·기간·모집단·표본·의뢰자·제외 사유를 남깁니다.
  `verification=not_accepted_not_verified`이며 조사 없음/저품질 확정이 아닙니다.

추가 원문 대조 8건: 조지아 Big Data Poll 상원·주지사 2건, 플로리다 Stetson
상원·주지사 2건, Change Research 상원·주지사 2건, 테네시 Beacon/Targoz
상원·주지사 2건. Stetson과 Targoz의 검토한 원문 호스트는 향후 자동 발견 경로에도
등록했습니다. Big Data Poll의 미정층 재질문 후 두 후보 합계 100% 값은 참고만 보관합니다.
Change Research는 원문 내 LV 표본 수가 1063/1107로 상충하고 의뢰자 성격이
미확인이라 참고 전용입니다. 원문 값을 다른 수치로 임의 보정하지 않습니다.
Targoz 원문 RV 문항 표본은 주지사 1149/상원 1157로 확인했고 전체 RV 1200 및
LV 결과와 구분했습니다. 8월 자료를 최신 조사로 표시하지 않습니다.

실수집(2026-10-06 UTC): 31관측·20선거·12개 주에 누적 자료가 있습니다.
그 중 집계 적격 25건, 참고 전용 6건입니다. GA·FL·TN에 자료가 추가됐지만
이 세 주에 현재 7일/14일 우세 신호가 생긴 것은 아닙니다. GA는 참고 전용,
FL의 적격 Stetson은 9월21일로 기간 밖, TN은 8월 자료입니다.
기관 확대 테스트 포함 65개 polling 테스트 통과. UI·Actions·LETF 편집 없음.
