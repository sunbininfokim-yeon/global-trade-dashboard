# 2026-10-07 — Codex: 고변동 선별·개별주 수급 합계

- 작업: T31 KOSPI universe 실패 보존 계약 보강. 사용자 요청: 정상 skip/일시 오류 구분, 실패 종목만 순차 1회 재시도, krx-month-paste와 삼전·하닉 수급 대조.
- 브랜치: `codex/krx-screen-flow-audit`. 기준 `e4949f01`. 독립 checkout, 기존 원본 WIP 미편집.
- 수정 범위: `New for anti/scripts/market_microstructure/market_microstructure/investor_price_levels.py`, investor 테스트, 감사 MD/JSON, TASKS. UI/Worker/workflow/현재 공개 JSON 변경 없음.
- 정상 제외는 유효한 이력 부족 또는 충분한 기간 전체 거래량 0으로 제한. 빈 응답·NaN·음수 거래량·조회 예외는 제외로 위장하지 않음. 최초 풀 종료 뒤 오류 종목만 시총 순서 순차 재시도 1회(전 1초 간격). 여전히 미해결이면 JSON/보고서 보존 및 exit 1.
- 출력 메타에 제외·재시도 내역. 순위는 제외를 뺀 산출 가능 종목 기준이며 top-N 미달은 실패.
- 원화 금액은 종가 환산 추정값임을 표시. 기존 열 유지. 세 주체 잔여 수급을 0으로 보정하거나 기타법인 값을 역산해 채우지 않음.
- 네이버 2종목 순차 1회씩 조회, 각 60행의 세 주체 수량이 저장값과 일치. KRX 새 대량 조회/전체 선별 실행 없음.
- KRX 12009 commit `7ff60ba991af785bd3595c777d55c88e770021ac`, manifest 및 압축 파일 SHA 일치. 중복 최신 수집 기준 2026-09-01~21 15일×2종목=30건 대조. 세 투자자의 큰 음수는 기타법인·기타외국인 수급으로 대체로 상쇄. 9/21 이후 KRX 자료 없음.
- 별도 원자료 점검: 하이닉스 9/18 저장된 시장 전체 매수−매도 및 5분류 합계 +4.78억원. 값은 보존. 원본 buy/sell SHA는 감사 JSON. 자사주 매입이라는 원인 주장 없음.
- 결과: `New for anti/scripts/market_microstructure/KRX_SCREEN_AND_FLOW_AUDIT_2026-10-07.md`, `audit/stock_investor_balance_2026-10-07.json`.
- 검증: market_microstructure 오프라인 121 테스트 및 UI 데이터 계약 통과. 소스 오류 재시도 경로, 순차 호출·호출 수, 정상 제외, 산출 종목 부족 및 CLI 산출물 보존 포함.
- 작성 시점: 검토 PR 준비. 병합·데이터 재생성·배포는 아직 확인하지 않음. 같은 함수를 사용하는 일일 파이프라인에 병합 후 적용됨.
