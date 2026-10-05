# 초크포인트 UI 정리 — 2026-10-05

## 상태와 범위

- 사용자 승인: 공식 물량 우선 표시, AIS 감소율 표현 정정, 긴 분석은 세부보기로 이동.
- 브랜치: `codex/chokepoint-ui-compact`, 기준 `origin/main`의 `9f200b29`.
- 별도 worktree: `/Users/yeoninair/Documents/해운 데이터/chokepoint-ui-compact`.
- **로컬 구현·검증 완료. 사용자 후속 요청에 따라 커밋·푸시·PR 절차 진행. 배포 완료를 의미하지 않음.**
- 변경: `New for anti/shipping.js`, UI 회귀 테스트·로컬 검증 HTML, 이 문서와 본인 TASKS 행.
- 미변경: 모델 엔진, public JSON, app.js, style.css, index.html, Worker, workflow. ACP·파나마 기후 모델 제외.
- 공유 체크아웃의 Claude 및 다른 산업 변경을 가져오거나 수정하지 않음.

## 사용자가 보게 되는 구조

1. 통로 카드: 공식 발표가 있으면 물량·기관·대상 기간을 먼저 표시. 없으면 AIS 추정 톤/일 표시.
2. AIS 전년 대비 감소율은 작은 보조 행에 표시. 실제 석유 감소율이나 봉쇄율로 해석하지 않는다는 안내 유지.
3. 카드 클릭: 기존 국가명이 있는 지도 + `공식 물량 / AIS 통항 / 통항 여건 / 시뮬레이션` 네 탭.
4. 공식 물량: 석유 전체·원유+콘덴세이트·석유제품·LNG 중 자료가 있는 품목만 토글. 발표 기간별 절대 물량 그래프.
5. 연구용 표·미포착 추정·우회로·원자료는 닫힌 `자료·방법 자세히`에서만 표시.
6. 전체 통로 AIS 비교 그래프도 별도 닫힌 보조지표로 이동.

## 데이터 계약

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

`New for anti/scripts/shipping_capacity`에서:

```sh
python3 -m unittest discover -s tests -p test_ui_contract.py
```

- Node 11개, Python UI 계약 11개 통과.
- 테스트의 합성 입력은 미보고·서로 다른 집계 범위 처리 회귀 검사에만 사용. 공개 JSON이나 실제 UI 물량으로 저장하지 않음.
- 로컬 HTML은 실제 shipping.js·style.css·커밋된 public JSON을 사용하며 mock 응답 없음.
- 브라우저 확인: 공식 품목 전환, 탱커 AIS, 통항 여건, 시뮬레이터, 연구자료 접기, 5/9개 통로 전환, 보조 그래프.
- 수에즈 100%·28일 희망봉 우회 결과의 추가 흡수 필요 선복량 5.23M DWT 표시 확인. 모델 결과이며 실제 AIS 통항량이 아님.
- 호르무즈 기본 상세 약 736px. 펼친 연구 자료까지 포함한 전체 길이가 아니라 기본 닫힌 상태의 측정값.
- 360px 뷰포트: 페이지 가로 넘침 없음. 콘솔 오류 없음.

로컬 미리보기는 자산 루트를 HTTP 서버로 제공한 뒤 다음 경로를 열면 됨:

`/scripts/shipping_capacity/tests/chokepoint-ui-preview.html`

## Claude 통합 시

- 사용자 2026-10-05 후속 요청은 커밋과 배포까지 포함함. 그러나 기존 `ownership_guard.yml`은 `codex/` 브랜치의 shipping.js 변경을 차단하므로 자동 검사를 임의로 우회하지 않음. 담당자의 UI 소유권 정리에 따라 병합·배포를 이어가야 함.
- 이 브랜치의 **해운 UI 범위만** 반영하고 기존 Claude 공용 UI 변경은 유지.
- 배포 전 최신 main의 shipping.js 변경과 차이를 확인하고 회귀 테스트 재실행.
- index.html의 shipping.js 캐시 버전은 현재 `v=22`. 이 작업에서는 파일 소유권 충돌을 피하려고 수정하지 않았으므로, 배포 담당자가 최신 main 기준으로 캐시 버전을 갱신해야 함.
- 모델 재계산·public JSON 재생성은 이 UI 정리의 필수 단계가 아님. 기존 자동 수집 스냅샷을 그대로 읽음.
- 이 문서의 로컬 검증은 실제 main 병합·공개 사이트 배포 검증을 의미하지 않음.
