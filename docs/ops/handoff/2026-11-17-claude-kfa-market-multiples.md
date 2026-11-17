# 인수인계 2026-11-17 — claude: 계산기 시장 배수(시가총액 ÷ 공시 분모) + CCC 보강

사용자 지시: "현금전환주기 등 주요 회계 투자지표 만들어봐 / PER은 네이버 금융 시가총액을 끌고 와서
나누는 구조로".

## 구조

| 층 | 파일 | 갱신 |
|---|---|---|
| 분자: 시가총액 | `tools/ops/fetch_kfa_market.py` → `New for anti/public/data/kfa_market_v1.json` | 평일 16:30 KST (`.github/workflows/kfa_market_daily.yml`, deploy.yml workflow_run 등록) |
| 분모: 공시 재무 | `tools/ops/build_kfa_pecr_snapshots.py` `valuation_bases()` → 스냅샷 `valuation_bases` | 엔진 스냅샷 재생성 시 |
| 나눗셈 | `New for anti/calculator-pecr.js` `pecrLive` / `pecrMarketHtml` | 브라우저 |

- 시가총액: Naver `m.stock.naver.com/api/stock/<code>/{basic,integration}` 의 `marketValue`
  (보통주만, 상장주식수 × 종가, 자사주 포함). DART 에 우선주가 있으면 `<code[:-1]>5` 의 시총을 더한다
  (삼성전자우 128조). 우선주 시세가 없으면(삼성중공업) 보통주만, 화면에 표시.
- 분모: FY(사업보고서) + LTM(가장 최근 분기/반기 보고서: FY + 당기 누적 − 전기 동기 누적, 같은 접수본).
  지배주주 순이익·매출·영업이익·자본(지배/전체). EBITDA·순차입금·FCF·CFO 는 엔진 카드(strict 우선).
- 지표: PER(LTM/FY), PBR, PSR, EV/EBITDA, EV/매출, P/FCF. 금융사는 PER·PBR 만(딜 탭 신설).
- Naver 자체 PER/PBR/EPS/BPS 는 `naver_reference` 로 저장, 대조용 표시만. 한화오션(Naver 2026.09 기준)
  PER 7.32 / PBR 1.92 정확히 일치, 현대건설 20.22 vs 20.32(Naver 2026.06).
- 피어 표의 PER·PBR·EV/EBITDA 는 일별 시세가 있으면 같은 날 값으로 계산.

## 엔진 변경 (codex 검토 부탁)

`dart_kfa/xbrl_notes.py`: 시점(instant) 컨텍스트에서 `receivables` / `payables` 잔액을
FY말·전기말 두 시점 모두 추출. 개념은 거래처 전용만
(`ShortTermTradeReceivable`, `CurrentTradeReceivables`; `ShortTermTradePayables`,
`TradeAndOtherCurrentPayablesToTradeSuppliers`, `TradeAndOtherPayablesToTradeSuppliers`).
`TradeAndOther*` 합계는 쓰지 않는다. 기존 규칙(범위 멤버, 합계 멤버 화이트리스트, 값 불일치 시 제외) 동일.
엔진(`pe_cr.read`)은 이미 검토행을 기초잔액·본문 미매핑 시 사용하므로 엔진 코드는 안 바꿨다.
테스트 +2 (이마트 FY2025 실제 컨텍스트), 전체 268 통과.

결과: CCC 대상 9개사 중 5 → 7 (한화오션 83.7일, 이마트 27.4일). 남은 것: 롯데건설(비상장, XBRL 없음),
HD한국조선해양(지주 연결, `requires:confirmed_industry_ccc_scope`).

## 남은 것

- 순차입금은 FY말 값이라 EV 가 최대 3분기 늦은 부채를 쓴다 → 분기 BS 로 순차입금 LTM 화 가능.
- 대상은 스냅샷 22개사(상장 16). 스냅샷을 늘리면 시세 파일도 자동으로 따라 늘어난다.
- Naver 비공식 API 라 응답 형식이 바뀌면 워크플로가 실패로 드러난다(직전 값은 stale 표시로 유지).
