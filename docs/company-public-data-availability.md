# 요청 기업의 공개 데이터 확보 결과

확인: 2026-10-11. 비교 기간은 공통 2025년 연간. 이는 각 회사의 최신 분기 실적을 모두 수집했다는 뜻이 아니다. 모든 수치는 원화이며 제품 손익 입력(USD)과 구분한다.

| 기업 | 매출 · 억원 | 영업이익 · 억원 | 확인 범위·공식 출처 |
|---|---:|---:|---|
| LS전선 | 75,882 | 2,798 | [LS그룹의 LS전선 회사 실적](https://lsholdings.com/ko/ir/investment). LS ELECTRIC 실적과 별도 행. |
| 대한전선 | 36,360 | 1,286 | [회사 보도자료의 2025 연결 실적 비교표](https://www.taihan.com/news/pr/releaseDetail?idx=439). |
| 기아 | 1,141,409.19 | 90,781.48 | [K-IFRS 연결 요약손익계산서](https://worldwide.kia.com/en/company/investor-relations/financial/summary-statements). 원문 단위 백만원. |
| 효성중공업 | 59,685.12 | 7,469.68 | [연결 손익계산서](https://www.hyosungheavyindustries.com/kr/company/ir/financial/income-statement). 전력기기 외 건설 등도 포함. |
| HS효성첨단소재 | 32,830.45 | 1,574.33 | [연결 요약손익계산서](https://www.hshyosungadvancedmaterials.com/kr/ir/balance-sheet?tabId=pills-balanceSheet2-tab). 별도 재무와 구분. |
| 한국타이어앤테크놀로지 | 103,186 | 16,843 | [2025 실적 발표의 타이어 부문](https://www.hankooktire.com/us/en/company/media-center/media-detail.632666.html?contentType=&tabCode=). 한온시스템을 포함한 연결 전사 실적과 구분. |

저장 단위는 `KRW million`, 화면은 억원(÷100)이다. 각 필드에 기간·범위·출처·확인일·`context_only`를 저장한다. 한국타이어 북미 지역 매출도 한국산 제품의 미국 수입 신고가격과 같지 않다.

## 확보 가능 범위

| 자료 | 이번 확보 상태 | 사용 방법 / 추가 조건 |
|---|---|---|
| 기업·주요 제품군 | 6개사 등록 | 실제 제품의 상세 규격·HTS·생산지 결정은 별도. LS/대한전선은 알루미늄 특정 규격에 자동 배정하지 않고 품목 직접 정의로 시작. |
| 공식 전사/타이어 부문 매출·영업이익 | 위 표 수치 구조화 | 회사 규모·사업 범위 참고만 표시. 제품의 매출·원가로 자동 대입하지 않음. |
| 사업보고서·감사보고서·IR 다운로드 | [기아](https://worldwide.kia.com/ko/company/investor-relations/financial/reports), [효성중공업](https://www.hyosungheavyindustries.com/kr/company/ir/archive/financial-statements), [HS효성첨단소재](https://www.hshyosungadvancedmaterials.com/kr/ir/report), [LS그룹](https://lsholdings.com/ko/ir/investment), [대한전선](https://www.taihan.com), [한국타이어](https://www.hankooktire.com/global/en/investors/financial-information-results/financial-results.html) 공개 경로 확인 | 다운로드 경로 확보와 모든 주석의 구조화는 다름. 분기별 자동 수집을 연결하지 않음. 이번 공식 페이지 접근에는 API 키를 사용하지 않음. |
| 한국산 특정 품목의 미국 수입·공급국 집계 | 국가 시뮬레이터에 DataWeb 2025 공급국 집계 기존 연결 | 시장 노출 참고. 특정 회사 매출로 이름을 바꾸지 않음. |
| 회사별 공표 AD 마진·예치 조건 | 효성중공업 포함 변압기 4개 법인, 한국타이어 포함 타이어 3개 법인 확인 | 반덤핑 탭에서 정확한 사건·법인·통관일·범위 조건에 맞춰 참고. |
| LS전선·대한전선·기아·HS효성첨단소재의 AD 적용 여부 전체 | 미확인 | 해당 제품·생산자/수출자·원산지의 사건 조사부터 필요. 이번 등록 사건에 없다는 이유로 AD 0% 처리하지 않음. |
| 제품별 실제 미국 신고가격·물량·변동원가·배분 고정비 | 이번 공개자료 검토에서 계산에 넣을 수 있는 조합을 확보하지 못함 | ERP·계약·통관·원가 자료 또는 검증된 제품별 자료 필요. 회사명 선택 시 가상 100/70/10,000 값을 채우지 않고 공란 유지. 공개자료에 전혀 존재하지 않는다고 단정한 것은 아님. |
| 제품별 가격 전가율·고객 전환 탄력성·잠금 계약 물량 | 실측값 미확보 | 수동 가정 표시. 산업 대체탄력성을 기업 고유 탄력성으로 바꾸지 않음. |

현재 기업 화면의 실제 데이터는 공식 기업·제품 설명과 재무 참고란이다. 제품 손익 결과는 사용자가 입력한 제품별 거래·원가·반응 가정에 따른 결과다. 자동으로 공시의 원가율을 제품 변동원가로 사용하거나 원화 재무를 USD 거래로 환산하지 않는다.

반덤핑 부담부터 확인하려면 효성중공업 또는 한국타이어의 **이 기업의 반덤핑 사건 보기**를 누른다. 다른 기업·사건은 반덤핑 탭의 직접 확인 예치율 경로로 사용할 수 있다. 법적 적용 범위와 예치율 출처가 먼저 필요하다.
