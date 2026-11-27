# 인수인계 2026-11-24 — claude: 사업부문·수주잔고, 금융 업권 지표, 전 종목 스냅샷, 업종 키트 추가

사용자 지시: "순서대로 진행" (1 부문·수주 → 2 금융 업권 → 3 공통 주석 → 4 SEC) +
"어떤 기업이건 검색하면 업종에 맞게 분류되고 엔진 값이 나오길".

## 새 엔진 모듈 (codex 검토 부탁)

| 파일 | 내용 | 테스트 |
|---|---|---|
| `dart_kfa/segments.py` | FY XBRL 영업부문·수익 구분 주석 → 부문/제품/지역별 매출·영업이익. 한글명은 lab-ko.xml. 부문 합(+조정항목)이 부문 합계 행 또는 손익계산서 매출과 ±1.5% 맞아야 `reconciles` | `tests/test_segments_backlog.py` |
| `dart_kfa/order_backlog.py` | 정기보고서 "매출 및 수주상황" 표 → 수주잔고. 열 어휘(수주총액/기납품/잔고, 기초/신규/매출/기말, 기본도급액/완성공사액/계약잔액, 수량·금액 쌍). 합계 행 roll-forward 가 닫히는 표만 채택, 같은 절 회사별 표 합산 | 같은 파일 |
| `dart_kfa/note_items.py` | FY XBRL 주석: 연구개발비(비용)·개발비 자산화(무형자산 증가, CapitalisedDevelopmentExpenditureMember)·자산화 비율, 주식보상비용, 재고평가손실(환입), 충당부채 종류별 기말잔액(ClassesOfProvisionsAxis). DART 확장 태그는 접두어 매칭 | `tests/test_note_items.py` |
| `dart_kfa/financial_kpis.py` | 업권 지표: 재무제표 본문 계산값(은행 CIR·대손비용률·대출/예수, 보험 손익률, 카드·캐피탈 대손비용) + 보고서 표 값(고정이하여신비율, 커버리지, 연체율, NIM). 외화 단위 표 제외, 값 범위 검사, 지주회사의 "[주요 종속회사에 관한 사항]" 이후 표는 `subsidiary` 표시 | `tests/test_financial_kpis.py` |

엔진(`pe_cr*.py`) 코드는 바꾸지 않았다.

## 업종 키트 추가 (`config/pe_cr_inputs.json`, 12줄 추가만)

automotive(C30), electrical_battery(C28), chemicals(C20,C22), steel_metals(C24,C25),
pharma_bio(C21,M701), refining_energy(C19), food_beverage(C10–12), telecom(J61),
utilities(D35,E36), airlines(H51), games(J5821), media_entertainment(J59,J60,R90), aerospace_defense(C313,C252), holding.
`pe_cr_industry.py` 한 줄 변경: 비금융 지주(64992)는 general 대신 holding 키트(없으면 general). 테스트 1줄 추가.
focus 는 기존 카드 키만 사용. 이전에는 이들이 manufacturing 또는 general 로 떨어졌다.

## 전 종목 스냅샷

- `tools/ops/build_kfa_pecr_snapshots.py`: `--universe 'KOSPI:500,KOSDAQ:500'`(Naver 시총 순위, 키 없음
  → DART corpCode.xml 로 corp_code 매핑), `--max-calls`(OpenDART 예산, 020 응답 시 깔끔히 중단),
  `--skip-fresh`(최신 정기보고서 접수번호와 `BUILDER_VERSION` 이 같으면 건너뜀), 스냅샷이 없는 회사 우선.
  공개 파일은 카드별 `inputs` 출처를 빼고 `input_count` 만 남김(용량 약 1/4).
- `.github/workflows/kfa_pecr_snapshots_daily.yml`: 매일 04:30 KST, `secrets.DART_API`, 예산 14,000 호출
  (같은 키를 쓰는 다른 워크플로 몫을 남김). deploy.yml workflow_run 등록.
- `fetch_kfa_market.py` 는 실패 5% 초과일 때만 실패(대상 수백 개사).

## 남은 것

- 3단계 중 PF 우발채무·책임준공(본문 텍스트, 표 양식 제각각)은 미구현. 4단계(SEC) 미착수.
- 보험 CSM 잔액: XBRL 은 상품군별 태그만 있고 총계가 없으며 본문 표 양식이 회사마다 달라 미구현.
  `secrets.FISIS_API_KEY` 가 이미 있으므로 금융통계정보시스템으로 대체 가능성 검토할 것.
- 비상장사는 universe 에 없음 → `config/kfa_pecr_extra_targets.json` 의 `corp_codes` 에 추가하면 매일 빌드.

## 추가 (같은 날, PR 2): SEC 미국 + 배치 병렬화

- `dart_kfa/sec_rows.py`: SEC companyfacts → DART 행 모양(US-GAAP → IFRS 계정 id 매핑, 10-K 1년 기간,
  52/53주 회계연도, 재작성 우선), 총부채·비유동부채·EBIT(세전+이자) 파생행(`derived:` 라벨), 엔진 SEC 경로용
  실제 회계기간, LTM(10-Q YTD), RPO 수주잔고·희석주식수·주식보상·R&D, SIC → 키트 매핑. 테스트 `tests/test_sec_rows.py`.
- `tools/ops/build_kfa_sec_snapshots.py`: 엔진 SEC 경로(카드) + investor_metrics + financial_kpis(미국 은행) → `us_<TICKER>_v1.json`.
  지주사 재편(ExxonMobil 2026: 새 CIK 는 10-Q 뿐)은 accession 접두어로 이전 CIK 를 찾아 facts 병합.
  워크플로 `kfa_sec_snapshots_daily.yml`(NASDAQ·NYSE 상위 150개씩, 20:00 KST).
- `financial_kpis.py`: 영업이익 행이 없으면 세전이익을 충당금 적립 전 이익 산식에 사용(미국 은행).
- 화면: `calculator-pecr.js` 금액 표시를 스냅샷 통화(KRW/USD)로, 미국 계산기에 "엔진 분석" 탭 줄 추가(`calculator.js`).
  피어 표는 같은 시장끼리만.
- `fetch_kfa_market.py`: 미국 종목은 api.stock.naver.com (Reuters 코드) 시총·종가.
- 한국 배치: 첫 수동 실행(2026-11-23)이 직렬 4분/사 속도로 340분 한도에 걸려 커밋 전 취소됨 →
  `--workers 4`(스레드, 호출 카운터 락) + `--max-minutes 290`. 키트: construction 에 M721(엔지니어링, 삼성E&A).

## 추가 (PR 3): 종합상사·광업 키트

- `pe_cr_inputs.json`: `trading_house`(G4680), `mining_smelting`(B05–B08, C242 비철 제련; SEC SIC 1000–1099, 1200–1299, 1400–1499, 3330–3341).
- 상사는 KSIC 로 플랫폼(G461)과 구분이 안 됨 → 빌더가 `config/kfa_issuer_kits.json` 검토 목록 + 규칙(G461/467/468 + 인터내셔널·상사·코퍼레이션)으로 `industry` 를 지정(엔진의 explicit 경로).
- `investor_metrics.industry_metrics`: 상사(매출총이익률·영업이익률·지분법이익 비중·매출채권/재고 일수), 광업(감가상각/매출·재투자율·EBITDA 마진·손상차손). 국내 요약 현금흐름표는 XBRL 주석 D&A 로 채움.
- `segments.py`: 부문 매출이 이미 외부매출 기준(LX인터내셔널)이면 ±0.2% 정확 일치일 때만 `income_statement_external` 로 인정.

## 추가 (PR 4, 2026-11-26): 카드 클릭 → 계산 근거 + 분기별 변화

- `dart_kfa/quarterly.py`: 분기말(FY-1 말, FY Q1/H1/Q3, FY 말, FY+1 Q1/H1/Q3) 재무상태표 + LTM 손익 →
  시가총액(월말 종가 × 현재 주식수), 순차입금(엔진 reported 와 같은 계정), 비지배지분, EV, EV/EBIT, 유동·부채비율.
  미국은 `sec_rows.sec_points`(10-Q/10-K 시점 잔액, LTM). 테스트 `tests/test_quarterly.py`.
- 빌더: 카드 `inputs` 를 버리지 않고 `parts`(계정명·금액·기준일·접수번호·보고서)로 압축. 스냅샷 `quarterly`.
  월말 종가: 국내 fchart.stock.naver.com, 미국 api.stock.naver.com chart. BUILDER_VERSION 2026-11-26.1 / us2.
- 화면: 엔진 카드 클릭 → 상세 박스(구성 요소·출처·분기 막대·분기 표). 딜 탭 EV 행 클릭 → 오늘 시세 EV 근거.

## 추가 (PR 5, 2026-11-27): 만기 차입금·PF·CCC/EV 확대, 보험 CSM(FISIS), 복합기업 분리, 검색 자동 분석

- `dart_kfa/liquidity.py`: 이자부 유동부채 유형별(계정 id → 계정명), 현금 배수·비중·÷EBITDA, 최신 분기, XBRL 만기 구간
  (재무상태표 대비 50% 미만이면 `partial`), PF·금융보증 만기, 넓힌 CCC(기타채권 포함 표시), 계정명 순차입금.
  실시간 EV 는 계정명 순차입금이 더 많은 차입을 찾을 때 사용(삼성전자 단기차입금 17.6조가 표준코드 없음).
- `segments.py`: 부문 자산·D&A(부문 ROA·EBITDA 마진), 같은 부문의 부문간거래 포함/제외 두 태그 분리(삼성물산 FY2024),
  표준 멤버는 같은 종류 모든 표에 합류, `segment_history`(사업보고서 3개). 키트 `conglomerate`(삼성물산 검토 지정).
- FISIS: `tools/ops/fetch_kfa_fisis.py` + `kfa_fisis_insurance.yml`(주 1회) → `kfa_fisis_insurance_v1.json`.
  SH156/SI152 A113 보험계약마진, A112 위험조정, A111 최선추정. 손익(SH155/SI151)은 연초 누적. 개별(별도) 기준.
  FISIS 키는 무료 가입 키 — 사용자 승인(2026-11-27)으로 키 없는 원칙의 예외.
- 검색 자동 분석: Worker 경로 `/api/kfa-request`(KV 큐), `kfa_requested.py` + `kfa_requested_snapshots.yml`(30분마다,
  국내 8·미국 5개). 화면이 스냅샷 없는 회사를 열면 자동 요청.
