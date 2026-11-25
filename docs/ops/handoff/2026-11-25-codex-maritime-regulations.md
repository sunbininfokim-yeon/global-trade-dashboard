# CF05 해운 탄소규정 갱신

사용자 2026-11-25 요청으로 공식 자료를 재검토하고, 해운 탄소금융 로컬 도구의 규정 근거와 연도 비교를 보완했다.
이전 구현 #848의 병합 후 최신 `origin/main`인 `48901caf8`에서 `codex/maritime-regulation-update-20261125`로 분기했다.
작업 디렉터리는 `/Users/yeoninair/Documents/해운 데이터/maritime-regulation-update-20261125`다.

## 구현

`tools/shipping_carbon/regulatory_snapshot.json`이 규정 검토 정본이다. 지정 공식 자료의 URL·조항·검증 범위·확인일과
법령·당국 안내·개정안·협상 상태를 함께 기록한다. 이번 검토는 이전 구현에서 빠진 자료의 보완을 포함한다.
최근 신규 발효 법률만을 나열한 자료로 해석하지 않는다.

`/api/regulations`, `/api/market`, `/climate`의 데이터·출처 메뉴와 정적 미리보기가 같은 정본을 읽는다.
계산 응답은 규정 파일 SHA256과 배출연도·제출기한·단계비율·가스를 반환한다.
통합 입력의 연도를 바꾸면 정본의 단계비율을 채우며, 직접 바꾼 비율은 입력대로 계산하고 현행 비율과 차이를 표시한다.
기존 Python 계산 엔진과 운영 JS 간 계약을 유지하도록 루트 계산의 규정 메타데이터는 로컬 API에서 추가한다.

검토한 항목의 세부 내용과 날짜는 정본을 참조한다. FuelEU DB 시행규칙, 노르웨이 적용 지연, ETS·MRV 개정안과
IMO 후속 협상 일정이 추가됐다. 개정안상의 지원금·공제·부속서 변경은 계산에 적용하지 않는다.
노르웨이·아이슬란드 관련 FuelEU 안내는 항로 비중을 검토할 때 표시하며 항구별 자동 판정 기능은 추가하지 않았다.

## 검증

- Python 해운 탄소금융 55개, 시장 JS 5개, 기존 해운·FuelEU JS/Python 대조 40개 통과.
- 기존 설계 산술 16개, 소유권 규칙 16개, `git diff --check` 통과.
- 실제 Chrome에서 규정 8개 항목, 규정 API, 2025→2026 연도 전환, 가스·제출기한, 수동 비율 차이 경고,
  입력 변경 후 저장 무효화, 1100/736/390/320px 및 모든 메뉴 가로 넘침을 확인했다. pageerror 0.
- 정적 미리보기에서도 같은 규정이 표시됨을 확인했다.
- 시세·감사 검증에는 이전 수집본을 git 제외 `source_data/`에서 읽었다. 신규 시세 수집은 수행하지 않았다.

재현은 `python3 tools/shipping_carbon/server.py --port 8786` 후 `http://127.0.0.1:8786/climate`를 연다.
Python 단위 검사는 `python3 -B -m unittest discover -s tools/shipping_carbon -p 'test_*.py'`다.
시장 브라우저 검사는 기존 수집 JSON이 있을 때 `PW_CHANNEL=chrome CARBON_BASE_URL=http://127.0.0.1:8786 node tools/shipping_carbon/market_check.cjs`로 실행한다.

## 확인 한계와 통합

2025/1127 환적항 규칙은 집행위의 공식 소개를 확인했다. EUR-Lex 본문이 자동 접속 검증 화면을 반환해
항구 목록·발효일의 자동 적용은 보류했다. 11월 23일 TRAN 의견 표결 관련 보도의 원문 PDF도 동일한 접근 문제로
확인하지 못했으며 표결 결과를 검증된 법률 변경으로 기록하지 않았다. MRV 개정 절차는 EUR-Lex의 진행 중 표기를 확인했다.

변경 경로는 `tools/shipping_carbon/**`, CF05 TASKS 행과 이 문서다. 운영 UI 연결·배포는 후속 통합 대상이다.
PR 병합 상태와 사이트 배포 상태는 각각 별도 확인한다.
