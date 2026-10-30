"""Observed access contracts for priority countries' official monthly trade data.

This registry is deliberately a capability statement, not a substitute for
data.  It keeps the pipeline from treating an absent public endpoint as a zero
trade value or silently falling back to a different commodity classification.
"""

from __future__ import annotations


NATIONAL_SOURCE_REGISTRY: dict[str, dict[str, object]] = {
    "IND": {
        "name_ko": "인도",
        "status": "automated_public_hs4_value",
        "adapter": "india_tradestat",
        "official_url": "https://tradestat.commerce.gov.in/meidb/commoditywise_import",
        "coverage_ko": "월별 ITC-HS 2·4·6·8단위, 인도 전체 수출·수입. 자동 수집은 HS4 일괄표와 HS6 특정품목 공개 폼의 USD 값을 사용한다.",
        "latest_known_coverage": "2018-01 onward; source release-dependent",
        "unit_contract": "USD_million; 이 수집은 가치 화면이므로 질량 비교·합산 금지",
        "automation": "ready",
    },
    "NOR": {
        "name_ko": "노르웨이",
        "status": "automated_public_hs_mass",
        "adapter": "norway_ssb",
        "official_url": "https://data.ssb.no/api/v0/en/table/11008",
        "coverage_ko": "SSB 표 11008: 월별 HS 세번·수출입·All countries·수량(Q1)·NOK 가치. 현재 세번 하위코드를 명시적으로 합산해 이 파이프의 HS4/HS6 버킷을 만든다.",
        "latest_known_coverage": "verified public Tableau crosstab through 2025-09; detailed-table refresh is release-dependent",
        "unit_contract": "Q1=kg인 하위코드만 합산해 kg로 제공; NOK 가치는 보조 필드로 보존",
        "automation": "ready",
    },
    "THA": {
        "name_ko": "태국",
        "status": "automated_public_hs_value",
        "adapter": "thailand_customs",
        "official_url": "https://www.customs.go.th/statistic_report.php?ini_content=statistics_report&ini_menu=nmenu_esevice_007&lang=en&left_menu=nmenu_esevice_007_190422_01&root_left_menu=nmenu_esevice_007",
        "coverage_ko": "태국 관세청 공개 월별 HS 조회: 수출입·국가별 표와 All Country의 SUM을 제공한다. 자동 수집은 HS4/HS6 직접 월의 태국 바트 금액만 사용한다.",
        "latest_known_coverage": "monthly; source release-dependent",
        "unit_contract": "THB_FOB/THB_CIF 가치. 수량 상세는 Thai HS11에서만 제공되므로 이 파이프의 HS4/HS6 계열은 질량 비교·합산 금지",
        "automation": "ready",
    },
    "ZAF": {
        "name_ko": "남아프리카공화국",
        "status": "official_public_monthly_tariff_form_download_contract_unstable",
        "adapter": "south_africa_sars",
        "official_url": "https://tools.sars.gov.za/tradestatsportal/data_download.aspx",
        "coverage_ko": "SARS 공개 Trade Data Download는 월·수출입·관세세번·상대국·통계수량·관세가치를 선택해 내려받는다. 포털의 실제 세번 목록(예: HS26의 26011100·26011200·26030000 등)은 확인했다. 다만 선택 상태별 ASP.NET postback 뒤 최종 내려받기가 비대화형 요청에서 일반 오류를 돌려 현재 자동 계열은 만들지 않는다.",
        "latest_known_coverage": "monthly from 2010; source release-dependent",
        "unit_contract": "통계수량은 원 표의 StatisticalUnit을 함께 확인해야 한다. kg으로 명시된 행만 질량 계열로 사용하며, CustomsValue 통화·기준은 원 표 메타데이터를 보존한다.",
        "automation": "needs_stable_download_contract_or_manual_export",
    },
    "MEX": {
        "name_ko": "멕시코",
        "status": "automated_public_tigie_hs4_value",
        "adapter": "mexico_inegi",
        "official_url": "https://inegi.org.mx/sistemas/Olap/Proyectos/bd/continuas/comex/comex_bcmm_mensual2023.asp",
        "coverage_ko": "INEGI BCMM 월별 공개 OLAP: TIGIE 2·4·6·8·10단위, 수출입·USD FOB 가치와 원 단위 수량을 제공한다. 자동 어댑터는 현재 TIGIE HS4 직접 행만 수집한다. 현재 확인된 원천은 2023-01부터 2026-05까지다.",
        "latest_known_coverage": "through 2026-05 on the verified official page",
        "unit_contract": "USD FOB는 통화 계열로 사용 가능. 수량은 TIGIE 품목별 원 단위이며 NA가 가능하므로 명시적 kg 단위 확인 전 질량 비교·합산 금지",
        "automation": "ready",
    },
    "KAZ": {
        "name_ko": "카자흐스탄",
        "status": "official_public_cumulative_xlsx_pending_history",
        "adapter": None,
        "official_url": "https://stat.gov.kz/ru/industries/economy/foreign-market/spreadsheets/?name=40113&period=&type=spreadsheets&year=",
        "coverage_ko": "통계청 공개 XLSX는 ЕАЭС TN VED 4·6·10단위 수출입을 제공한다. 확인된 2026-01~05 파일은 누적 자료이며, 직접 월별 값이 아니다.",
        "latest_known_coverage": "2026-01 through 2026-05 cumulative release (2026-07-15)",
        "unit_contract": "연속 누적 릴리스의 차분과 TN VED/HS 버전 매핑을 검증한 뒤에만 월별 계열로 제공; 직접 월별·동일 분류라고 표기 금지",
        "automation": "needs_ytd_history_and_eaeu_mapping",
    },
    "CHN": {
        "name_ko": "중국",
        "status": "official_monthly_major_commodity_not_automated",
        "adapter": None,
        "official_url": "https://english.customs.gov.cn/statics/report/preliminary.html",
        "coverage_ko": "해관총서가 월별 주요 수출입 품목의 수량·가치를 공개하지만, 공개 영문 표는 주요 품목 분류이며 이 파이프의 정확한 HS 계약과 일치하지 않을 수 있다.",
        "latest_known_coverage": "monthly, release-dependent",
        "unit_contract": "원 표의 품목별 단위. 정확한 HS 매핑 검증 전 자동 병합 금지",
        "automation": "needs_stable_download_or_query_endpoint",
    },
    "KOR": {
        "name_ko": "대한민국",
        "status": "automated_official_api_env_key",
        "adapter": "korea_customs",
        "official_url": "https://www.data.go.kr/data/15101609/openapi.do",
        "coverage_ko": "관세청 Itemtrade 월별 HS 수출입 API. 한국 전체 수출입의 순중량 kg·USD를 제공하며, 상대국별 세분은 별도 nitemtrade API로 확장한다.",
        "latest_known_coverage": "monthly; previous month is updated around the 15th",
        "unit_contract": "순중량 kg을 주 value로 사용하고 USD는 보조 필드로 보존; KOREA_CUSTOMS_SERVICE_KEY 환경변수 필요",
        "automation": "ready_with_env_key",
        # CI reads this contract to decide whether an optional source can run;
        # the value itself is never placed in the registry or output JSON.
        "required_env": "KOREA_CUSTOMS_SERVICE_KEY",
    },
    "SAU": {
        "name_ko": "사우디아라비아",
        "status": "automated_public_tableau_hs4_mass_value",
        "adapter": "saudi_gastat_tableau",
        "official_url": "https://www.stats.gov.sa/en/search-data-table?category=data-table&delta=60&parentCategory=1317550&sort=createDate%2B",
        "coverage_ko": "GASTAT 공개 Tableau 월별 HS·국가 데이터표. 자동 수집은 Country 필터를 생략한 사우디 전체 수출·수입의 정확 HS4 heading 값·순중량을 사용한다.",
        "latest_known_coverage": "monthly; source release-dependent",
        "unit_contract": "수량은 공식 net weight tons, 가치는 million SAR로 보존한다. 공개 필터 계약은 HS4까지 검증됐으며 HS6·상대국별은 이 어댑터가 만들지 않는다.",
        "automation": "ready",
    },
    "ARE": {
        "name_ko": "아랍에미리트",
        "status": "official_open_data_historical_only",
        "adapter": None,
        "official_url": "https://opendata.fcsc.gov.ae/@federal-customs-authority/uae-foreign-trade-volume-per-month-2012-2021",
        "coverage_ko": "FCSC 공개 월별 외국무역 데이터는 존재하지만 공개 설명상 2012–2023 범위다. 최신 국가 전체 HS 월별 자동 경로는 아직 확인되지 않았다.",
        "latest_known_coverage": "through 2023 in the identified open dataset",
        "unit_contract": "품목 분류·중량·AED 가치; 최신 패널과 섞지 않음",
        "automation": "historical_backfill_candidate_only",
    },
    "IDN": {
        "name_ko": "인도네시아",
        "status": "official_monthly_hs2_not_exact_hs4",
        "adapter": None,
        "official_url": "https://www.bps.go.id/en/exim",
        "coverage_ko": "BPS가 월별 수출입 통계를 공개하며 월간 간행물은 HS2 단위와 국가별 요약을 제공한다. 현 계약의 정확한 HS4/HS6 품목을 자동 충족하지 않는다.",
        "latest_known_coverage": "monthly, about one-month dissemination lag",
        "unit_contract": "HS2는 HS4/HS6로 자동 배분·병합 금지",
        "automation": "needs_exact_hs_download_access",
    },
}


def automated_reporters(*, include_env_key: bool = False) -> list[str]:
    """Return reporters whose official national adapter is ready to run."""
    statuses = {"ready"}
    if include_env_key:
        statuses.add("ready_with_env_key")
    return [iso3 for iso3, source in NATIONAL_SOURCE_REGISTRY.items() if source.get("automation") in statuses]
