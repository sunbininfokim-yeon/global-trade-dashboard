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
