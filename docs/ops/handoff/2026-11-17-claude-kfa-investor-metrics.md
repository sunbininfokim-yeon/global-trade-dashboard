# 인수인계 2026-11-17 — claude: 계산기 투자지표(성장·ROIC·Z/F·주주환원·희석·조정 EV)

사용자 지시: "PBR·CCC 말고 투자·PE 인수 때 보는 주요 회계 지표" 조사 → 1·2·3번 묶음 구현.

## 구조

| 층 | 파일 |
|---|---|
| 엔진(순수 함수, 신규) | `New for anti/scripts/dart/dart_kfa/investor_metrics.py` + `tests/test_investor_metrics.py` (18개) |
| 수집·연결 | `tools/ops/build_kfa_pecr_snapshots.py` `investor_packet()` → 스냅샷 `investor_metrics`, `investor_input` |
| 화면 | `calculator-pecr.js` (`inv*` 함수), `calculator.js` 새 탭 `metrics`("투자지표") |

추가 API 호출(회사당): `alotMatter`, `tesstkAcqsDspsSttus`, `stockTotqySttus`(FY), 그리고 정기보고서
본문(document.xml) 최대 몇 건. 모두 무료·OpenDART.

## 지표와 규칙

1. **재무제표 (5개년)** — FY·FY-1·FY-2 사업보고서의 당기·전기·전전기를 이어 FY-4..FY. 같은 연도가 두 보고서에
   있으면 최신 보고서(재작성) 값. 계정은 엔진 `config/pe_cr_inputs.json` 정확 ID를 재사용하고, EPS·이익잉여금·
   충당부채·확정급여·배당·자사주·리스상환만 모듈 `EXTRA` 에 둠(현금흐름·충당부채는 이름 대체 허용).
   - 성장: 매출·영업이익·지배순이익·EPS 전년비, 3년 CAGR(양 끝 양수일 때만, 흑자전환은 `turnaround`).
   - ROIC = 영업이익 × (1 − 유효세율) ÷ 평균(자본총계 + 차입금·사채·리스 − 현금·단기금융상품).
     유효세율이 0~50% 밖이면 3년 합산, 그래도 안 되면 **법정 최고세율 26.4% 가정**(`tax_basis` 로 표시). 세전 ROIC 병기.
   - 듀퐁 ROE, 발생액 비율, CFO/순이익, 매출채권·재고 증가율 − 매출 증가율(%p).
     매출채권이 본문에 없으면 XBRL 주석 거래처 잔액(`xbrl_notes` receivables)으로 채움.
   - Altman Z''(장부가, 연도별) + 원조 Z 입력값(시가총액은 브라우저가 일별 시세로), Piotroski F(9개 중 7개 이상 있을 때).
2. **주주환원·희석**
   - 배당: alotMatter DPS·총액·배당성향·공시 수익률 3년. 총주주환원율 = (당해 결산 현금배당 총액 + CF 자기주식 취득) ÷ 지배순이익.
     연결 CF 배당금 지급은 종속회사 비지배 배당이 섞여(두산에너빌리티 127%로 나왔음) 공시 배당총액을 우선하고, 배당 절이 전부 "-" 면 0.
   - 자기주식: tesstk '총계' 행 기초·취득·처분·소각·기말, 발행주식 대비.
   - 희석: 정기보고서 본문 "미상환 전환사채 / 신주인수권부사채 등 / 전환형 조건부자본증권 발행현황" 표의
     합계 행 마지막 두 숫자(미상환 권면, 전환가능주식수). 발행결정(cvbdIsDecsn)은 조기상환·리픽싱 미반영이라 쓰지 않음
     (이연제약: 결정 6.09백만주 → 보고서 7.17백만주). Q1·Q3는 대형사가 자본금 절을 생략하므로 H1→FY 로 거슬러 감.
     판정: `reported` / `none_declared`(명시) / `not_in_capital_section`(자본금 절은 있는데 항목 없음 → 0) / `undetermined`.
3. **조정 EV 브릿지(딜 탭)** — EV + 순확정급여부채(적립 초과면 가산 안 함) + 재무상태표 미표시 리스부채(XBRL;
   엔진 `net_debt_reported` 입력에 lease_* 가 없을 때만) − 관계기업·공동기업 투자. 보수적 EV는 충당부채까지 가산.
   리스 장부금액 태그가 없으면 `GrossLeaseLiabilities`(할인 전) 를 "상한"으로 표시(삼성전자).
   XBRL 리스는 금융부채 범주 멤버를 합계로 보지 않음(NAVER: 상각후원가 0 / IFRS7 범위 밖 1.19조).
   FCCR = (EBITDA − 설비투자) ÷ (이자 지급 + 리스부채 상환), PE 탭.

금융회사: 성장(순이익·EPS), 주주환원, 희석만. 매출·이익의 질·Z/F·EV 는 `not_applicable:financial`.

## 결과 (FY2025, 11/16 종가)

| 기업 | ROIC | Z'' | F | 총환원 | 희석 |
|---|---|---|---|---|---|
| 삼성전자 | 13.0% | 7.97 안전 | 6/9 | 43.6% | 없음 |
| SK하이닉스 | 39.9% | 7.25 안전 | 9/9 | 4.9% | 없음 |
| 한화오션 | 8.2% (법정세율 가정) | 1.39 회색 | 7/9 | 0% | CB 2.33조 → 5,781만주(18.9%) |
| 현대건설 | 6.8% | 3.19 안전 | 6/9 | 24.1% | CB 5,000억 → 332만주(3.0%) |
| 이마트 | 1.0% | 0.50 부실 | 7/9 | 49.5% | 없음 · 조정 EV/EBITDA 7.7배, FCCR 0.5배 |
| HMM | 4.5% | 8.02 안전 | 3/9 | 149% (2025 공개매수 자사주) | 없음 |

## Codex 검토 부탁

- `investor_metrics.py` 는 `regulatory_capital.report_tables/number/unit_scale`, `xbrl_notes` 상수만 import. 엔진 다른 파일 변경 없음.
- `EXTRA` 의 이름 대체(현금흐름·충당부채)가 엔진의 "이름 대체 없음" 원칙과 다름 — 매칭 방법은 `source[year][key].match` 에 남김.
- 교환사채(EB)는 희석에서 제외(자기주식 교환). 전환우선주(RCPS)는 아직 미포함.

## 남은 것

- 롯데건설(비상장): 차입금 계정이 비표준이라 ROIC 투하자본 없음.
- 자사주 매입액은 연결 CF 기준(종속회사 매입 포함 가능) — SCE 열 구분이 API에 없어 분리 못 함.
- 키움증권 발행주식수(stockTotqySttus FY) 미확인 → 희석 비율 공란.
