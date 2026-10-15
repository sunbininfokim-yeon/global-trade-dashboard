# Oregon 주별 입력 — 10/14 수집 보존, 10/15 검증 재개

담당 주는 OR(C그룹) 하나다. checkout은 `/Users/yeoninair/Documents/해운 데이터/us-or-evidence-input-20261014`, branch는 `codex/or-evidence-20261014`다. 조사 시작 시 최신 main `57941ec0722940966abfe6c077d4c34db76efd7c`와 packet 없는 공통 기반 `5412a31b`(PR #577)를 사용한다. 10/15 재개 때 main `fa630c37`까지 확인했으며 이 구간의 선거 코드/입력/계약 변경은 없었다. CT/WA의 현행 명부 및 레이스별 게시 기준일 테스트 시계 수정은 #577에만 둔다. 미병합 다른 주 입력 위에 쌓지 않는다. 공통 기반 병합 후 OR PR의 base를 main으로 바꾸고 실제 base SHA로 범위 검사를 다시 수행한다.

## 실제 자료와 기준일

- OR 공개 API 수집 완료는 `2026-10-14T09:37:42.749135+00:00`, 검토 보완 capture는 `2026-10-14T09:55:06.223460+00:00`다. provider 원시 3건과 OPB 원문 보완 1건을 그대로 저장한다. 이번 10/15 재생성은 새 여론조사·FEC 수집이 아니다.
- 공식 2026 본선 유권자 안내 Book4/12/13/16의 각 인쇄 26쪽 후보 목록을 합쳐 하원 6곳 14명, 상원 1곳 4명, 주지사 1곳 3명, 총 8개 선거 21명을 확인했다. 각 PDF URL/지문/추출 페이지와 후보 원문은 `OR-primary-20261014.json`에 보존했다. 단일 county 책을 전국구 명부로 간주하지 않으며 중복 지역구·상원·주지사 명부 일치를 검증한다.
- `*`는 선택적인 후보 공보 미제출 표시다. 사퇴나 무투표 당선으로 바꾸지 않는다. 교차 공천 정당은 원문으로 남기고 사람 수를 중복 계산하지 않는다. 검토한 8개 선거에 무투표 당선 근거는 없다.
- 공식 출처: [Oregon 유권자 안내](https://sos.oregon.gov/elections/Voters-Pamphlet/Pages/Voters-Pamphlet-English.aspx). 연방 후보의 FEC 신원 보조 자료는 [Green Papers OR](https://www.thegreenpapers.com/G26/OR)와 기존 같은 선거의 공시 후보기록을 대조했다. 안내문의 후보 자기소개 내용을 선거관리기관이 검증한 사실로 승격하지 않는다.

## 여론조사와 자동 연결 범위

[OPB/DHM 9/17–27 조사](https://www.opb.org/article/2026/09/30/opb-poll-shows-oregon-governors-race-virtually-deadlocked/)의 실제 정정 PDF Q13 초기 문항을 API 누락 보완으로 추가했다. LV 915명에서 Kotek 44 / Drazan 46 / Brett Smith 3이다. RV 1,000명 결과와 후속 leaner 합산 46/47/3은 별도 항목으로 보존하고 집계에 중복 편입하지 않는다. 후보 호감도 문항이 먼저 제시됐으므로 완전히 비유도·비노출 조사라고 주장하지 않는다. ±3.24%p는 발행처 보고치이며 정확도 등급이나 통계적으로 유의한 승패가 아니다.

9/27 종료 파동은 10/14 기준 최근 7일·14일 범위 밖이다. 누적 이력 1건을 유지하며 현재 우세·전망 정당은 생성하지 않는다. API의 다른 주지사 조사 3건은 각각 경선 전 당파적 가상 대진, 최초 문항·조사기간 미검증, 최신 Oregonian 원문/세부 방법론 접근 미확보로 보류한다. OPB가 보도한 GBAO 후보 캠프 내부 조사도 상세 원문 미공개 상태라 발견 기록만 남겼다. 원문의 일부 수치가 알려졌다는 이유로 검증된 독립 조사로 표시하지 않는다. 하원 6곳과 상원은 이 수집에서 실제 관측 0건이며, 미래에도 조사가 없다는 뜻은 아니다. OR-04/05/06 보완 검색에서 예측·베팅 수치를 실제 조사로 넣지 않았다. 기존 Cook snapshot과 사용자 추가 주의 분류는 바꾸지 않았다.

주별 operation 38개는 기존 `read → state overlay → provider/primary 수집 → 후보·문항·중복/충돌 검증 → poll/history/state projection` 경로에 들어간다. 검증된 기존 기관·출처의 새 API 조사와 실제 본선 후보가 일치하면 다음 정상 수집에서 연결할 수 있다. OR-05 신규 조사 편입과 구 후보 거절을 회귀로 확인했다. 다만 새 기관의 모든 발표나 새 원문 URL이 포괄 승인되는 구조는 아니다. 이번 primary 입력은 검토한 정확한 PDF URL/지문·문항만 재확인한다. 문서 변경·접근 실패·후발 API 수치 충돌 시 보류하거나 원래 날짜의 참고 자료로 남긴다. 같은 파동의 API 후발 중복은 한 번만 센다. 기관 수/AAPOR 참여를 정확도 등급으로 만들지 않는다.

기존 main workflow는 일일 06:10 KST 수집이다. 이 PR은 운영 workflow·UI를 편집하지 않으며, 미병합 OR 입력이 현재 서비스에 반영됐다고 주장하지 않는다.

## 독립지출과 미완료 경계

기존 연방 금융 성공일 `2026-10-12T18:25:08.136419Z`와 지도 생성일 `2026-10-12T18:25:22.502460Z`를 유지했다. 하원 현재 후보 FEC ID 12명과 상원 4명을 명시적으로 연결했다. 기존 O 유형 관측이 연결되는 선거는 OR-04/05/06과 상원 1곳이다. 새 독립지출을 수집한 것이 아니며, 공시의 경선/본선/미확인 선거유형 및 O/U/V/W 범주를 유지한다. Jeff Merkley의 캠프 수입을 외부 지지금액으로 바꾸지 않는다.

Justin Filip 및 Andrea Townsend의 기존 FEC `PG` 정당/이름 표기는 공식 후보와의 완전한 동일성 검토가 끝나지 않아 ID·금액 연결을 보류한다. 신고 ID와 보류 사유는 남긴다. 결측 금액은 null이며 0달러로 채우지 않는다.

주지사는 [공식 ORESTAR 안내](https://sos.oregon.gov/elections/campaign-finance/Pages/search-campaign-finance.aspx)와 공개 검색 경로를 확인했다. 10/14 접근 실패 영수증과 원래 capture를 보존했다. 10/15 자동 수집 환경에서 재시도한 결과도 URLError였다(`06:28:52.907817+00:00`). 반면 웹 읽기 도구로는 공개 이름/거래 검색 화면과 Independent Expenditures·삭제/만료 거래 선택 항목이 열렸다. 이 차이는 audit의 `continuation_source_access_review`에 별도로 기록했다. 사이트가 전면 폐쇄됐거나 API 키가 반드시 필요하다고 판단하지 않는다.

주지사 거래 자동 수집, 수혜 후보·지지/반대·정정/삭제 매핑은 아직 미구현/미확보다. 세 후보 금액은 null이고 상태는 `live_poll_sources_reviewed_finance_blocked`다. 캠프 일반 수입/비용은 독립지출이 아니다. 현재 새 키나 유료 권한을 요청할 근거는 없다. 추후 필요하면 해당 수집만 멈추고 사용자에게 요청한다.

## 검증과 게시 보류

전국 생성 JSON은 `/private/tmp/or-state-evidence-20261015/validation`에서만 다시 만들었다. `publish_state_packets.py --pending` 및 전체 `publish_packet_projections.py`가 성공했다. 금융 68개, 연방 명부 6개, 선거 JS 74개, ops 회귀 13개(소유권 포함)를 통과했다. 금융 지도 대조는 2026 레이스 576 / 후보기록 4,857 / 원공시기록 16,651, 2024 레이스 540 / 후보기록 3 / 원공시기록 11을 확인했다. `check_deploy_chain.py`의 39개 게시 workflow 연결도 통과했다. JS 최초 실행은 sparse 사본에 Israel JSON 2개가 없어 실패했으며, 동일 HEAD의 파일만 사본에 복원한 후 74개가 모두 통과했다. Israel 코드는 수정하지 않았다.

OR만 replay한 보존 검사는 타주 여론조사 레이스 498개, 타주 이력 레이스 65개, 전역 as_of/fetched_at·출처·타주 수집 영수증·타주 coverage/gaps를 그대로 유지했다. `house_poll_focus`를 재계산했으며 타주 항목도 동일하다. 원본 공개 JSON 5,077개를 검증 시작/종료에 해시 대조해 동일함을 확인했다. 원래 OR 수집일·금융일을 현재 처리일로 덮어쓰지 않는다.

최초 통합 polling은 최신 main의 WA 테스트 정책 시계 때문에 480개 실행/오류 1건이었다. 이 공용 오류를 #577에서 수정한 뒤 통합 polling 491개를 모두 통과했다(OR 10개 포함, CT 14개 및 WA 11개도 별도 통과). #579의 기존 head `301acb83`는 GitHub에서도 491개/JS 74개/범위 검사를 통과했다.

OR가 없는 공통 PR #577에서는 NC의 더 최신 레이스 수집 기준일을 fixture가 누락한 오류가 추가로 드러났다. 이 공통 fixture와 새 회귀 3개도 #577에만 반영했고 OR 입력 없는 사본에서 NC 9개/새 회귀 3개를 통과했다. 원래 조사/수집일을 수정하지 않았다. 최종 공통 기반 `5412a31b`로 OR를 다시 맞추며 전체 검사 결과는 각 PR 본문에 기록한다. 실제 base `5412a31b` 대비 `check_state_packet_changes.py --base-ref 5412a31b --head-ref HEAD --branch codex/or-evidence-20261014`, ownership guard, `git diff --check`를 재실행한다. 범위는 OR 소유 파일 6개다.

PR에는 OR packet·OR 원문/접근 감사·OR adapter·OR 전용 테스트·이 인수 문서만 포함한다. 전국 생성물, 공용 목록/테스트, UI, workflow, LETF, TASKS는 포함하지 않는다. 병합·배포·운영 workflow 실행은 하지 않는다. 다음 순서는 기존 계획의 MT → IN → IL → KY이지만 이번 요청에서 시작하지 않는다.
