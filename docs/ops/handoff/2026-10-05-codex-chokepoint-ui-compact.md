# 초크포인트 UI 정리 — 2026-10-05

## 상태와 범위

- 사용자 승인: 공식/AIS 물량 구분, 현재 규모·선종 비중순 표시, 전주·전월·전년 비교, 긴 분석은 세부보기로 이동. 기존 PR **#454** 보강.
- 브랜치: `codex/chokepoint-ui-compact`, 기준 `origin/main`의 `9f200b29`.
- 별도 worktree: `/Users/yeoninair/Documents/해운 데이터/chokepoint-ui-compact`.
- **이번 요청은 커밋·푸시까지만. 병합·배포는 하지 않으며, 2026-10-07 수요일 Claude 통합·배포용으로 인계. 이전 배포 요청보다 이 후속 지시가 우선.**
- 변경: `New for anti/shipping.js`, traffic_summary 계산·artifact 생성기·스키마·테스트, 일치하는 해운 JSON 4종, 전용 문서와 본인 TASKS 행.
- 미변경: 항로/봉쇄/환경 모델 수식과 기존 계산 결과, app.js, style.css, index.html, Worker, workflow. ACP·파나마 기후 모델 제외.
- 공유 체크아웃의 Claude 및 다른 산업 변경을 가져오거나 수정하지 않음.

## 사용자가 보게 되는 구조

1. 수에즈 등 통로 카드: **전체 선종 최근 7일 추정 톤/일 → 중량 비중순 선종 3개와 막대 → 작은 전주/전월/전년 변화율**. 수에즈 석유 배럴 값은 하단의 `SUMED 포함` 별도 참고값.
2. 호르무즈는 공식 석유 발표 물량·기관·대상 기간을 주값으로 유지하고 전체 AIS 추정 톤/일·포착 선종 구성·미포착 경고를 분리. 변화율은 공식 석유 감소율·실제 봉쇄율이 아님.
3. 카드 클릭: 기존 국가명이 있는 지도 + `공식 물량 / AIS 통항 / 통항 여건 / 시뮬레이션` 네 탭.
4. 공식 물량: 석유 전체·원유+콘덴세이트·석유제품·LNG 중 자료가 있는 품목만 토글. 발표 기간별 절대 물량 그래프.
5. 연구용 표·미포착 추정·우회로·원자료는 닫힌 `자료·방법 자세히`에서만 표시.
6. 전체 통로 AIS 비교 그래프도 별도 닫힌 보조지표로 이동.

## 데이터 계약

- 새 `chokepoints_live[id].traffic_summary`는 `shipping_capacity/traffic_summary.py`에서 계산하고 화면은 그대로 읽음. 현재 규모·선종 순위/중량 비중·비교율을 브라우저에서 재계산하지 않음.
- 최근 7일 평균을 전주 7일, **전월 같은 시점에 끝나는 7일**, 52주 전 같은 요일 7일과 비교. 전월은 직전 28일이나 달 전체 평균이 아님. 말일은 해당 월 말일로 조정.
- 날짜가 연속된 7일 모두 있을 때만 산출. 결측·충돌 중복·음수·NaN은 보간하지 않으며 결측 비교/0 기준선은 null. 비중 분모는 전체 선종 중량이며 상위 3종으로 재정규화하지 않음.
- 선종별 중량은 실제 품목별 물동량·TEU·원유 배럴이 아님. 무료 원자료에 없는 TEU/배럴은 임의 환산하지 않음. 출처는 IMF PortWatch.
- 저장된 730일 일별 관측자료를 재사용해 새 요약 계약만 추가했음. 신규 수집·API 키·AI 호출·ML 재학습 없음. 현재 AIS 기준일 **2026-09-27**, generated_at **2026-10-04T21:53:23.152413+00:00**는 그대로 유지.
- 해운 JSON 4종 bundle_id **`c8a992190852a97d9b95`** 일치. bundle_id와 새 traffic_summary 외 기존 환경·항로·시뮬레이터·공식 발표·백테스트 값은 구조 비교로 동일함을 확인.
- 기존 자동 파이프라인의 `build_artifact_bundle()`이 전체 일별 자료에서 이 계약을 매번 계산한 뒤 화면 이력을 180일로 줄임. 연간 비교는 줄이기 전에 계산하므로 누락되지 않음.
- 기존 `point.officialCargo`의 `reported_series`, `reference_cards`, `supplementary_reference_cards`만 사용. 새 API 키·AI 계산 호출 없음.
- EIA 분기 평균과 IEA 월 평균을 서로 다른 계열로 표시. 단일 IEA 월 발표는 독립된 점이며 EIA와 이어 붙이지 않음.
- 톤을 배럴로 환산하지 않음. 일별 공식 관측값을 생성하거나 보간하지 않음. 미보고 값은 null 유지.
- 호르무즈 공식 카드의 760만 배럴/일은 **저장된 IEA 2026-08 기간 평균**이며 오늘의 실측이 아님. EIA 2026년 2분기 490만 배럴/일은 별도 계열.
- 수에즈 공식 석유 계열은 **SUMED 포함**을 명시. AIS 전체 선종과 집계 범위가 다름.
- 호르무즈 AIS 탭의 초기 선종은 기존 헤드라인 기준인 탱커로 맞춤.
- 실제 통항 성공확률·보험 가용성은 관측 근거 없이 새로 산출하지 않음.
- 시뮬레이터는 탭을 열 때 기존 격자를 불러오며 선택 행의 엔진 결과만 표시.
- 발견한 기존 UI 불일치 정정: 수에즈 50% 기준 시나리오가 80%로 시작하던 값을 기준 시나리오 메타데이터에 맞춤. 100% 시나리오 선택 시에도 100%·28일로 맞춤. 수식 변경 없음.

## 검증

저장소 루트:

```sh
node --test 'New for anti/scripts/shipping_capacity/tests/chokepoint-ui.test.cjs'
node --check 'New for anti/shipping.js'
git -c core.fsmonitor=false diff --check
```

의존성이 설치된 Python으로 `New for anti/scripts/shipping_capacity`에서:

```sh
python3 -m unittest discover -s tests
```

- Node 14개, Python 전체 150개 통과. 스키마 4종 및 screen/diagnostics golden contract 통과.
- 캐시 재생성 시 기존 백테스트 기록 보존, bundle_id 불일치 시 파일을 바꾸지 않고 중단하는 회귀 검사 포함.
- 테스트의 합성 입력은 미보고·서로 다른 집계 범위 처리 회귀 검사에만 사용. 공개 JSON이나 실제 UI 물량으로 저장하지 않음.
- 로컬 HTML은 실제 shipping.js·style.css·커밋된 public JSON을 사용하며 mock 응답 없음.
- 브라우저 확인: 공식 품목 전환, 탱커 AIS, 통항 여건, 시뮬레이터, 연구자료 접기, 5/9개 통로 전환, 보조 그래프.
- 수에즈 100%·28일 희망봉 우회 결과의 추가 흡수 필요 선복량 5.23M DWT 표시 확인. 모델 결과이며 실제 AIS 통항량이 아님.
- 호르무즈 기본 상세 약 736px. 펼친 연구 자료까지 포함한 전체 길이가 아니라 기본 닫힌 상태의 측정값.
- 이번 보강의 수에즈 전체/컨테이너 비교율 확인. 360px 뷰포트 재배치 완료 후 본문·문서 너비 동일, 가로 넘침 없음. 콘솔 오류 없음.

로컬 미리보기는 자산 루트를 HTTP 서버로 제공한 뒤 다음 경로를 열면 됨:

`/scripts/shipping_capacity/tests/chokepoint-ui-preview.html`

## Claude 통합 시

- **10/7 수요일에 PR #454를 검토·통합한 뒤 배포. 지금 자동 배포를 실행하지 말 것.**
- 기존 `ownership_guard.yml`은 `codex/` 브랜치의 shipping.js 변경을 차단함. 검사 자체를 변경·우회하거나 실패한 채 강제 병합하지 않았음. Claude가 정식 UI 소유권 절차로 통합하고 검사를 다시 확인해야 함.
- 이 브랜치의 **해운 UI와 traffic_summary 계약 범위만** 반영하고 기존 Claude 공용 UI·다른 산업 변경은 유지. 현재 원격 main `6f67d5e0`까지 겹치는 shipping.js/엔진 변경은 없었음.
- 배포 전 최신 main의 shipping.js 변경과 차이를 확인하고 회귀 테스트 재실행.
- index.html의 shipping.js 캐시 버전은 현재 `v=22`. 이 작업에서는 파일 소유권 충돌을 피하려고 수정하지 않았으므로, 배포 담당자가 최신 main 기준으로 캐시 버전을 갱신해야 함.
- **shipping.js만 가져오지 말고** 엔진·스키마와 동일 bundle_id의 JSON 4종을 함께 반영. 추가 모델링이나 별도 AI 계산은 필요 없음.
- 수요일 main 데이터가 이 PR보다 최신이면 오래된 JSON으로 덮어쓰지 말고 최신 관측자료 기준으로 기존 일일 빌드를 실행하거나 아래 요약 재생성 도구 사용. 관측일은 수집하지 않은 오늘 날짜로 바꾸지 말 것.
- 네 파일의 bundle_id가 이미 일치하고 diagnostics에 전체 이력이 있는 경우, 모델 재계산 없이 요약만 갱신 가능:

```sh
python3 'New for anti/scripts/shipping_capacity/refresh_traffic_summary.py'
python3 'New for anti/scripts/shipping_capacity/validate_schema.py'
```

- 미리보기용 HTML은 새 UI와 실제 public JSON을 읽으며 API/mock 응답을 대체하지 않음.
- 이 문서의 로컬 검증은 실제 main 병합·공개 사이트 배포 검증을 의미하지 않음.
