# 2026-10-21 미국 여론조사 복구 후속 확인

## 범위와 실제 게시본

미국 여론조사·선거 PR만 담당한다. 사용자 지시로 이스라엘 작업은 제외한다. #641/#652는 별도 진행 세션의 PR이며 편집·검증 완료를 대신 주장하지 않는다. 추가 main 병합·배포·운영 workflow dispatch 없음.

- main `96af0fca70f0e9b598e7d0f909a8205e19426420`. GitHub에서 #651/#654/#655 병합 확인.
- 실제 `https://chokemonitor.com/public/data/usa_election_live_polls_v1.json`은 main 파일과 구조적으로 동일하다. 기준일10/21, source_status=ok, 관측228(전체 과거/참고 포함), 집계 적격136, 참고92. 이것을 최근228개 조사나228개 선거라고 해석하지 않는다.
- AK 상원6관측, 최신 조사 종료10/16. 현재7일 적격 관측이 있는 선거: 하원0·상원2·주지사1.14일은 하원4·상원8·주지사6. 이는 조사 미실시 확인이 아니라 현 수집/검토 범위이다.
- workflow 정기 cron은 `10 21 * * *`(매일06:10KST)이며 다음 실행을 대신 dispatch하지 않았다. 다음 정기 수집 성공 여부는 그 실행 결과로 확인해야 한다.
- 자료 보관/검증 로그: `/private/tmp/poll-postdeploy-20261021` (임시 보관이며 저장소 영구 원문 아카이브 아님).

## 원문 보류 6건 재검토

### MS Data for Progress 한 파동

- [공개 의뢰자 발표](https://chartingthewayforward.substack.com/p/research-release-fresh-polling-from),8/28 게시,8/24 메모. 의뢰자는 Way to Lead PAC·Democracy Alliance·Democracy Strategy Partners. PDF만 보고 의뢰자 미공개로 둔 기존 판단은 보완할 근거를 확보했다.
- [원문 PDF](https://www.filesforprogress.org/datasets/2026/8/dfp_ms_ge26_aug2026_crosstabs.pdf),7쪽,8/5–15·1,018LV·SMS/live caller/web panel·English·±3pp. 원문 SHA `7c7e34816f6dd351f014cdcfcc1e6170caec5187e1e7ac670fcf431097eab649`, 기존 검토와 일치.
- p4 Q3 초기3자: Hyde-Smith44·Colom38·Pinkins7. p5 Q4 초기양자: Hyde-Smith47·Colom41. API는 Q4이며 원문 수기 보완은 Q3다. 조사 파동 자체의 수치 모순으로 단정하면 안 된다. 정보 제공 후 Q7/Q8 및 동원 시나리오는 별도다.
- **현재 코드/입력 상태는 변경하지 않았다.** 기존 동일 파동 예외는 개별 검토된 ranked-choice 문항 전용이다. MS에 이 이유를 거짓 적용하지 않는다. 후속 공용 계약에서 정확한 API fingerprint·원문 Q3/Q4·양자/다자 문항·의뢰자를 묶는 개별 승인 검증을 추가한 후 MS 한 주 PR로 편입해야 한다. 의뢰자·게시일을 고치더라도8월 조사가 최신7/14일 우세로 바뀌지 않는다. 같은파동2문항을2개 독립조사로 세지 않는다.

### CA PPIC 두 문서

- [9월 보고서](https://www.ppic.org/pdf/ppic-statewide-survey-californians-and-their-government-september-2026.pdf): Q13·조사9/4–10·1,103LV/전체1,745adults·60/38·LV ±3.8pp. 새 PDF SHA `6880d260c1cbdbd9b760e6f92cba5453961af3b5f163775939b112246d85f325`.
- [7월 보고서](https://www.ppic.org/pdf/ppic-statewide-survey-californians-and-the-environment-july-2026.pdf): Q48·조사6/29–7/6·1,003LV/전체1,578adults·61/36. 새 SHA `b3825270822e196657d23e80c58b49033d53caf716910e7bfe99bf63af20f5d5`.
- 두 보고서의 해당 후보 수치·표본·기간·방법론을 대조했고 기존 수치와 일치한다. 기존 LV 교차표의 SHA도 각각 `73f48a89c4085558f1fb6ceaae6bf8ce2bf77b57fce7fd605033918613a42ae0`, `753484cc0fd5e78f681f9abee8a6c84c0916852b15e4f5c4a471adcbb40b1f62`로 동일하다. 전체 문서 바이트가 같다는 뜻은 아니다.
- **새 지문 승인은 아직 운영 입력에 반영하지 않았다.** CA 독립 packet에서 원래 검토일/수집일과 기존 원문 지문을 이력으로 보존하고, 이번 재검토 영수증과 정확한 새 문서만 갱신해야 한다. 현재7/14일 밖 조사이며 최신 조사로 되살리지 않는다.

### CA IVC/IVP 한 문서

- [발표 기사](https://ivn.us/new-ca-poll-voter-id-measure-leads-today-its-undecided-voters-point-the-other-way/) 본문과 연결된 실제 지지도 표 확인: Becerra48·Hilton38, N2,906,9/23–10/2,10/4 발표. 본문의 모형 기반 양자 추정치를 실측 지지도로 섞지 않는다. 연결된 실제 지지도 표 이미지 SHA `d3f19a02266a74430db4f8e9852a5c50bb99da8c5e109407bd3b76d572005612`.
- 실제 새 HTML의 기존 정규화 함수 지문은 `d7273edcce7efa8e7ca0c70e547471aec726e8f46072b0f5bee506aa0d127510`으로 배포본 변경 탐지값과 같다. 기존 승인 지문은 `c9e64952330c2b086ddf3b4c3ad260a9423dca39cf7dd4ee7801362790321b23`.
- 방법론에는L2선거인명부·투표 이력 기반 LV·문자 초대 온라인·영어/스페인어·가중을 공개한다. 전체 정확한 문항/leaner 분리 검증은 완료됐다고 주장하지 않는다. 새 지문을 검토 반영해도 **참고 전용 유지**, 기관 전체의 미래 발표 승인이 아니다.

### AL RMG/Napolitan 두 문항

- [Alabama Policy Action PDF](https://alabamapolicy.org/wp-content/uploads/2026/10/0926-SURVEY-DATA.pdf), 기존SHA `70127c089206f51e4b299f77d71dfa6772844340696bb411f3ad75731f62e547` 재확인. p1주지사50/37, p3상원54/33·800RV·9/21–25·게시된 정밀도±3.5pp. 보고된 오차를 독립 검증한 값으로 바꾸지 않는다.
- 재검토 시 운영 `merge_primary_supplements`의 실제 요청·응답·해시 검사를 그대로 사용해 두 건 모두 `primary_documents_rechecked`. 배포 수집 때의 unavailable은 당시 실패였으며 현재 영구 미지원으로 단정하지 않는다.
- 별도 수치/코드 수정 필요 없음. 다음 정상 정기 수집에서 재확인 가능하다. 방법/모집/가중 미공개에 따른 참고 전용은 유지하며 여론조사 우세로 승격하지 않는다.

## PR와 날짜 회귀

- #644 최신main 합본, 관련35개 및 GitHub polling/ownership 성공 확인.
- #649 TASKS의 co/efficient 행과 복구 행을 모두 보존. 새 HTML 합본52개 통과. 가상 문서 수집시각만10/20으로 고정했고 실제 운영 미래 검증은 유지했다.
- #656은18개 공용 검사의 명부 검증 시각을 기존SNAPSHOT_DAY로 분리한 기반이다. 과거 조사normalize/summarize의DAY와 수치·원래 날짜는 변경하지 않는다. synthetic/local future-boundary fixture는 그대로 검사한다.
- #647은 NE주별12파일만 #649기반으로 유지한다. #649가 미병합인데 base를main으로 바꾸면 공용 코드/테스트/TASKS가 주별diff에 들어와 범위 검사가 거부한다. 따라서 최신main 내용은 모두 합쳤지만 base는 #649를 유지하고, 기반들이main에 들어간 뒤 retarget한다. 예외로 우회하지 않는다.
- 권장 반영: #656 → #644 → #649 → #647. #644와#656은 독립 공용 기반이므로 서로 순서교환 가능하다. 주별 생성JSON 수동병합 없음.
- 최종 고정 checkout 검사 결과와 원격 head는 아래 완료 절에 추가한다.

## 최종 합본 로컬 검증

2026-10-21, 최신 main96af0fca와 #644/#649/#656/NE#647의 코드·입력을 한 고정 checkout에서 검증했다.

- `unittest discover -s tests -p 'test*poll*.py'`: 743개,337.866초,통과.
- discover 패턴 밖의co/efficient10·발표일 미확인3과NE5를 명시 실행:18개 통과(NE5는743개에도 포함;합산해 중복된 수를 제시하지 않는다).
- 선거자금77·선거JS114·소유권14 통과,check_deploy_chain42workflow 확인.
- NE 재생의 타주501races·타주history·state_captures·root as_of/fetched_at 일치. 하원focus104개ID 및 타주focus 값 동일. 동일 입력 재생 board/history 완전 동일.
- NE원래수집시각 `2026-10-20T08:44:51.616945+00:00` 유지. 새 금융 수집/전국JSON게시 없음.
- 주별 범위 검사: #649의 실제 코드 tree를 기반으로 #647 NE주별12파일만 허용됨을 확인. 최신main 재fetch 후 SHA동일 확인.
- 전체 로그의 의도적인 실패/last-good/seat-forecast-held 출력은 실패 경로 단위 테스트의 출력이다. 최종 unittest 종료코드0과743개OK를 기준으로 판정했다.

원격 CI는 최종 head별 상태를 별도로 확인한다. 로컬 통과만으로 병합·배포 완료를 주장하지 않는다.
