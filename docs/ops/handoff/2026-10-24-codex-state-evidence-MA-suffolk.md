# MA Suffolk 주지사 조사 · 2026-10-24 Codex 인수

## 담당과 범위

- 한 주 MA / worktree `/Users/yeoninair/Documents/해운 데이터/us-MA-suffolk-20261024` / branch `codex/ma-suffolk-review-20261024`.
- 시작 main/base SHA `9cbbf2893deac81a3f91b2b91947d846e929de65`. 독립 main 기반이며 다른 주 미병합 PR에 의존하지 않는다.
- 인수 대기열의 MA `gov202suf418414b7`부터 처리했다. 다른 주·UI #700·#657/#661·Supabase·workflow·공용 코드·전국 생성 JSON은 수정하지 않았다.

## 실제 원문 검토

- 공식 후보 명부: https://www.sec.state.ma.us/divisions/elections/research-and-statistics/2026-state-election-candidates.htm
  Governor & Lieutenant Governor 절에서 Healey/Driscoll(D), Minogue/Oliver(R), James/Kittredge(Independent) 세 티켓을 확인했다. 주지사 이름 전체는 기존 NGA 신원과 Suffolk의 인증 3후보 Q8로 교차 확인했다. 부지사는 주지사 후보로 넣지 않는다.
- 공식 페이지는 웹 읽기로 확인했다. 직접 HTTP 요청은 실패했으므로 raw HTML SHA를 만들어 넣지 않았다. 명부 역할/접근 방식은 MA audit에 명시한다.
- Suffolk 원문은 Claude가 실제 확보한 `source-fetch/a-src4-20261023-39893658088`의 두 PDF를 git에서 읽어 검토했다. 별도 PDF 페이지 렌더링으로 주 전체 Q8 및 방법론을 대조했다. 10/23 원래 수집일·해시를 보존하며 10/24 새 PDF 다운로드로 주장하지 않는다.
- Marginals: https://www.suffolk.edu/-/media/suffolk/documents/academics/research-at-suffolk/suprc/polls/massachusetts2/2026/10_20_2026_massachusetts_statewide_marginals.pdf
  SHA256 `4271767be62ae85d86f5d10fda5a4806f8c3c653c8368df402bfd686e4f7e462`.
- Release/methods: https://www.suffolk.edu/-/media/suffolk/documents/academics/research-at-suffolk/suprc/polls/massachusetts2/2026/10_20_2026_massachusetts_press_release.pdf
  SHA256 `a3cb18143ebb21868f67aae6a2266fb29374cca4516aa69dcb062421e259cc90`.
- 주 전체 LV500, 10/14~18, 발표10/20, Q8 Healey58.6/Minogue36/James2, 미정3.4. vote/lean을 한 문항에서 함께 묻는 형식으로 표시한다. Quincy300·상원Q7은 사용하지 않는다. 보고된 표본오차±4.4이며 정확도 등급·당선확률은 만들지 않는다.

## 변경과 출처 계약

- Andrea James(IND)를 MA 공식 3티켓 명부와 주지사 대진에 추가한다. `Maura Healy` 오타는 정확한 후보 별칭으로만 연결하며 공식 이름은 Maura Healey를 유지한다.
- 원래 API 응답59/36/2·종료10/17은 그대로 보존한다. 기존 answer correction 후 metadata correction 순서에 맞춘 각 단계 지문으로 원문58.6·종료10/18만 교정한다. 최상위 지문은 원래 응답 전체에 묶이고 값/기간/표본/의뢰자 변경은 기존 승인으로 통과하지 않는다. 공용 수집기 코드를 바꾸지 않았다.
- 실제 공개 API를 10/24 다시 요청했다: `https://api.votehub.com/polls?subject=2026&from_date=2025-01-01&to_date=2026-10-24`, 수집시각 `2026-10-24T01:51:30.530999+00:00`, 전국1630행 중 MA42행. 기존 MA42개 ID를 모두 보존했다. 신규 API 조사 발견을 주장하지 않으며 기존 보류 발표의 검토 편입이다.
- 영수증 덮어쓰기를 피하려고 오프라인 `refresh_state_polls.py --packet`을 실행하지 않았다. 기존 MA `primary_records`와 `primary_supplement_receipts`를 그대로 보존하고 이전 receipt를 별도 보관했다. 실제 새 API 수집과 과거 PDF 검토 시각을 구분한다. 공용 오프라인 영수증 덮어쓰기 동작 자체를 수정한 것은 아니다.

## 비게시 재생 결과

- base 게시본 as_of10/23: 채택290→292, 집계 대상166→167. MA 주지사0→2 관측.
- Suffolk1건은 원문 검토·명부 대조 후 집계 대상. 별칭으로 다시 연결된 과거 MassINC1건은 `publisher_identified_release_review_pending` 참고 전용을 유지한다. 기관 전체나 향후 발표를 일괄 승인하지 않는다.
- MA 상원 기존4건은 유지. MA 하원9곳은 이 작업에서 새 조사를 확보하지 않았다. 타주495선거·타주 누적 기록·전국 원래 as_of/fetched_at·하원 house_poll_focus 보존 및 재생 반복 일치를 검사한다.
- 새 후보 모금/독립지출은 수집하지 않았다. finance 결측·참고·미지원 상태를0으로 채우지 않는다.

## 검증 및 배포

- MA 집중7개 통과. 원문 수치/종료일 교정, 원래 API 불변, 공식3후보, 7/14일 창, 변경/미래 검토 거부, 영수증/42ID 보존, 타주/이력/날짜/focus/참고 상태 보존과 멱등성 포함.
- finance79·election JS130·소유권15 통과, deploy-chain44 확인. JS 첫 실행은 sparse checkout에 CHN 공개 fixture가 없어 실패했으며 기존 파일만 materialize한 뒤 같은 검사130개 통과. 코드/기대값 변경 없음.
- 전체 polling771개 통과(406.039초). 최신 origin/main76ce5c16a 기준 state scope 통과. 해당 main 갱신에는 election_watch 코드/입력 및 live 여론조사 JSON 변경이 없음을 확인했다. 원격 최종 head CI는 PR 생성 후 별도 확인한다.
- 병합·배포·운영 workflow dispatch는 하지 않았다. Claude가 최종 head CI와 state scope를 확인하고 병합한 뒤 기존 polling 발행 경로로 재생성한다. 수집 성공·게시·실제 사이트 반영을 각각 확인한다.
- 다음 대상은 최신 대기열/담당 상태를 다시 확인하고 결정한다. 이 PR 위에 다음 주를 쌓지 않는다. 브라우저 전용 출처·나머지 MA/다른 주·B/C 검토는 완료 처리하지 않는다.
