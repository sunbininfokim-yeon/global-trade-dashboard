#!/usr/bin/env python3
"""Generate expanded industry_kits.json + export/BOK coverage maps."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def kit(
    label_ko: str,
    label_en: str,
    ksic: list[str],
    *,
    notes: list[str],
    watch: list[str],
    priority: list[str],
    ma: list[str],
    flags: list[dict] | None = None,
    de_emphasize: list[str] | None = None,
    mti: list[str] | None = None,
    adjusted: list[dict] | None = None,
    sources: list[str] | None = None,
) -> dict:
    out = {
        "label_ko": label_ko,
        "label_en": label_en,
        "ksic_prefixes": ksic,
        "mti_export_items": mti or [],
        "notes_ko": notes,
        "watch_notes": watch,
        "priority_metrics": priority,
        "de_emphasize": de_emphasize or [],
        "flags": flags or [],
        "ma_focus": ma,
        "sources": sources
        or [
            "BOK Financial Statement Analysis (KSIC)",
            "MOTIE major export items (MTI)",
        ],
    }
    if adjusted:
        out["adjusted_views"] = adjusted
    return out


COMMON_PRI = [
    "current_ratio",
    "debt_ratio",
    "roe",
    "operating_margin",
    "fcf",
    "earnings_quality",
]

CYCLE_FLAGS = [
    {
        "id": "cycle_peak_earnings",
        "when": "operating_margin_very_high",
        "severity_ko": "업황 호황기 마진일 수 있어 DCF·배수에 영구치로 쓰지 마세요.",
    }
]

CAPEX_FLAGS = [
    {
        "id": "capex_heavy_fcf",
        "when": "fcf_negative_and_capex_large",
        "severity_ko": "대규모 설비투자로 FCF가 음수일 수 있습니다. 투자 계획을 확인하세요.",
    }
]

INV_FLAGS = [
    {
        "id": "inventory_build",
        "when": "inventory_turnover_falling",
        "severity_ko": "재고회전 하락은 수요 둔화·가격 하락 신호일 수 있습니다.",
    }
]

kits = {
    # --- MOTIE 15 / IT·자본재 ---
    "semiconductor": kit(
        "반도체",
        "Semiconductors",
        ["C261"],
        mti=["반도체"],
        notes=[
            "메모리·시스템 사이클과 ASP가 마진·FCF를 지배합니다.",
            "EBITDA·순차입금은 단년보다 다년(3년) 평균으로 보는 편이 맞습니다.",
            "대규모 Fab Capex로 FCF가 장기간 음수여도 성장 투자일 수 있습니다.",
        ],
        watch=["inventory_valuation", "capex_commitments", "related_party", "customer_concentration"],
        priority=["roic", "operating_margin", "fcf", "earnings_quality", "inventory_turnover", "cash_ratio"],
        ma=["normalized_ebitda_proxy", "fcf", "net_debt_to_ebitda", "roic"],
        flags=CAPEX_FLAGS + INV_FLAGS + CYCLE_FLAGS,
        de_emphasize=["debt_ratio"],
        sources=["KIS Electronics methodology", "MOTIE MTI 반도체", "BOK C26/C261"],
    ),
    "display": kit(
        "디스플레이",
        "Displays",
        ["C262"],
        mti=["디스플레이"],
        notes=[
            "패널 판가·가동률 사이클이 큽니다. 한 해 마진을 영구치로 쓰지 마세요.",
            "대형 증설 Capex와 고객(세트사) 협상력이 현금흐름을 좌우합니다.",
        ],
        watch=["capex_commitments", "customer_concentration", "inventory_valuation"],
        priority=["operating_margin", "fcf", "roic", "earnings_quality", "cash_ratio"],
        ma=["fcf", "normalized_ebitda_proxy", "net_debt_to_ebitda"],
        flags=CAPEX_FLAGS + CYCLE_FLAGS,
        sources=["MOTIE MTI 디스플레이", "BOK C26"],
    ),
    "computers": kit(
        "컴퓨터·SSD",
        "Computers / Storage",
        ["C263"],
        mti=["컴퓨터"],
        notes=[
            "SSD·서버향 수요와 부품 원가에 민감합니다.",
            "재고·매출채권 회전과 고객 집중도를 함께 보세요.",
        ],
        watch=["inventory_valuation", "customer_concentration", "warranty_provisions"],
        priority=["operating_margin", "inventory_turnover", "receivables_turnover", "fcf", "roe"],
        ma=["fcf", "earnings_quality", "net_cash_proxy"],
        flags=INV_FLAGS,
    ),
    "telecom_devices": kit(
        "무선통신기기",
        "Wireless / Handsets",
        ["C264"],
        mti=["무선통신"],
        notes=[
            "세트 교체 주기·채널 재고가 분기 실적을 흔듭니다.",
            "로열티·소송·품질보증 충당금을 주석에서 확인하세요.",
        ],
        watch=["warranty_provisions", "litigation", "inventory_valuation", "related_party"],
        priority=["operating_margin", "inventory_turnover", "fcf", "cash_ratio", "roe"],
        ma=["fcf", "net_cash_proxy", "earnings_quality"],
        flags=INV_FLAGS,
    ),
    "home_appliances": kit(
        "가전",
        "Home Appliances",
        ["C285"],
        mti=["가전"],
        notes=[
            "내수·환율·물류비가 마진에 영향이 큽니다.",
            "재고와 판매보증, 할부·금융 자회사가 있으면 연결 기준으로 보세요.",
        ],
        watch=["warranty_provisions", "inventory_valuation", "finance_subsidiary"],
        priority=["operating_margin", "inventory_turnover", "current_ratio", "fcf", "roe"],
        ma=["fcf", "net_debt_proxy", "earnings_quality"],
        flags=INV_FLAGS,
    ),
    "electronics_components": kit(
        "전자부품·기타 IT하드웨어",
        "Electronic Components / IT hardware",
        ["C26"],
        mti=[],
        notes=[
            "세부 키트(반도체·디스플레이 등)에 안 걸리면 C26 일반 전자로 분류됩니다.",
            "Capex·재고·고객 집중이 공통 포인트입니다.",
        ],
        watch=["inventory_valuation", "capex_commitments", "related_party"],
        priority=["roic", "operating_margin", "fcf", "inventory_turnover", "earnings_quality"],
        ma=["fcf", "roic", "net_debt_to_ebitda"],
        flags=CAPEX_FLAGS + INV_FLAGS,
        de_emphasize=["debt_ratio"],
    ),
    "auto": kit(
        "자동차",
        "Automobiles",
        ["C30"],
        mti=["자동차"],
        notes=[
            "대당 ASP·믹스(하이브리드/EV)·지역 믹스가 영업이익을 좌우합니다.",
            "판매금융·보증·리콜 충당은 본업 마진과 분리해 보세요.",
            "관세·현지생산 전환이 수출·마진 가정에 핵심입니다.",
        ],
        watch=["warranty_provisions", "finance_subsidiary", "recall_provisions", "related_party"],
        priority=["operating_margin", "roe", "fcf", "asset_turnover", "interest_coverage", "current_ratio"],
        ma=["fcf", "normalized_ebitda_proxy", "net_debt_to_ebitda", "roic"],
        flags=CAPEX_FLAGS,
        sources=["MOTIE MTI 자동차", "BOK C30", "KIS auto-related practice"],
    ),
    "auto_parts": kit(
        "자동차부품",
        "Auto Parts",
        ["C303"],
        mti=["자동차부품"],
        notes=[
            "완성차 고객 집중도가 높고, 단가 인하 압력이 상시적입니다.",
            "재고·매출채권과 특정 OEM 의존을 주석·공시에서 확인하세요.",
        ],
        watch=["customer_concentration", "inventory_valuation", "related_party"],
        priority=["operating_margin", "receivables_turnover", "inventory_turnover", "fcf", "roe"],
        ma=["fcf", "earnings_quality", "net_debt_proxy"],
        flags=INV_FLAGS,
    ),
    "machinery": kit(
        "일반기계",
        "General Machinery",
        ["C29"],
        mti=["일반기계"],
        notes=[
            "수주·백로그 변동이 크고, 프로젝트성 매출이 많습니다.",
            "선수금·계약자산과 보증을 부채 해석 시 구분하세요.",
        ],
        watch=["construction_backlog", "contract_liabilities_advances", "guarantee_obligations"],
        priority=["operating_margin", "fcf", "current_ratio", "interest_coverage", "earnings_quality"],
        ma=["fcf", "backlog_note", "net_debt_ex_contract_liab"],
        flags=[
            {
                "id": "advances_inflate_liabilities",
                "when": "contract_liabilities_high",
                "severity_ko": "선수금/계약부채가 부채비율을 높일 수 있습니다.",
            }
        ],
    ),
    "petrochemical": kit(
        "석유화학",
        "Petrochemicals",
        ["C20"],
        mti=["석유화학"],
        notes=[
            "스프레드(제품−원료) 사이클이 이익을 결정합니다. 단년 ROE만으로 판단 금지.",
            "정기보수·가동률·중국 증설이 공급과잉 리스크입니다.",
        ],
        watch=["commodity_hedges", "turnaround_capex", "environmental_provisions"],
        priority=["operating_margin", "fcf", "roic", "interest_coverage", "cash_ratio"],
        ma=["normalized_ebitda_proxy", "fcf", "net_debt_to_ebitda"],
        flags=CYCLE_FLAGS + CAPEX_FLAGS,
        de_emphasize=["roe"],
        sources=["MOTIE MTI 석유화학", "BOK C20", "spread-cycle credit practice"],
    ),
    "petroleum_products": kit(
        "석유제품(정유)",
        "Petroleum Products / Refining",
        ["C19"],
        mti=["석유제품"],
        notes=[
            "정제마진·유가·재고평가손익이 분기 이익을 크게 흔듭니다.",
            "재고회계(평균법 등)와 일회성 재고효과를 구분해 보세요.",
        ],
        watch=["inventory_valuation", "commodity_hedges", "environmental_provisions"],
        priority=["operating_margin", "fcf", "current_ratio", "interest_coverage", "earnings_quality"],
        ma=["normalized_ebitda_proxy", "fcf", "net_debt_to_ebitda"],
        flags=CYCLE_FLAGS + INV_FLAGS,
        sources=["MOTIE MTI 석유제품", "BOK C19"],
    ),
    "steel": kit(
        "철강",
        "Steel",
        ["C241"],
        mti=["철강"],
        notes=[
            "글로벌 공급과잉·판가·원재료(철광석·고철) 스프레드가 핵심입니다.",
            "고정비 비중 커 가동률 하락 시 레버리지가 급격히 악화됩니다.",
        ],
        watch=["commodity_hedges", "capex_commitments", "environmental_provisions"],
        priority=["operating_margin", "fcf", "interest_coverage", "debt_ratio", "cash_ratio"],
        ma=["normalized_ebitda_proxy", "net_debt_to_ebitda", "fcf"],
        flags=CYCLE_FLAGS + CAPEX_FLAGS,
        sources=["MOTIE MTI 철강", "BOK C24"],
    ),
    "shipbuilding": kit(
        "조선·기타 운송장비(선박)",
        "Shipbuilding",
        ["C311", "C31"],
        mti=["선박"],
        notes=[
            "선수금·계약부채가 커서 부채비율이 높아 보일 수 있습니다(이자부 차입과 구분).",
            "공사진행률·예상원가 변경이 손익을 좌우합니다.",
            "건조계약 잔고(백로그)와 강재·환율 헤지를 주석에서 보세요.",
        ],
        watch=[
            "contract_liabilities_advances",
            "percentage_of_completion",
            "construction_backlog",
            "raw_material_hedges",
            "guarantee_obligations",
        ],
        priority=["operating_margin", "fcf", "earnings_quality", "current_ratio", "interest_coverage", "debt_ratio"],
        ma=["backlog_note", "fcf", "net_debt_ex_contract_liab", "percentage_of_completion_risk"],
        flags=[
            {
                "id": "advances_inflate_liabilities",
                "when": "contract_liabilities_high",
                "severity_ko": "선수금/계약부채가 부채를 부풀립니다. 이자부 차입금과 분리해 보세요.",
            },
            {
                "id": "poc_earnings_quality",
                "when": "earnings_quality_low",
                "severity_ko": "진행기준 손익은 현금과 어긋날 수 있어 CFO/순이익을 함께 봅니다.",
            },
        ],
        de_emphasize=["inventory_turnover"],
        adjusted=[
            {
                "id": "leverage_ex_contract",
                "label_ko": "계약부채·선수금 제외 레버리지",
                "requires_accounts": ["CONTRACT_LIABILITIES"],
                "note_ko": "보고 부채비율과 해석이 달라질 수 있습니다.",
            }
        ],
        sources=["KIS Shipbuilding methodology", "NICE shipbuilding adjustments", "MOTIE MTI 선박", "BOK C311"],
    ),
    "textile": kit(
        "섬유·의류",
        "Textiles / Apparel",
        ["C13", "C14"],
        mti=["섬유"],
        notes=[
            "원자재·임가공·환율과 패스트패션 수요에 민감합니다.",
            "운전자본(재고·매출채권) 부담이 커질 수 있습니다.",
        ],
        watch=["inventory_valuation", "receivables_quality", "fx_exposure"],
        priority=["operating_margin", "inventory_turnover", "receivables_turnover", "current_ratio", "fcf"],
        ma=["fcf", "net_cash_proxy", "earnings_quality"],
        flags=INV_FLAGS,
    ),
    "biohealth": kit(
        "바이오헬스",
        "Biohealth / Pharma",
        ["C21"],
        mti=["바이오헬스"],
        notes=[
            "R&D 자산화·임상 성과·허가 리스크가 회계이익보다 중요할 수 있습니다.",
            "마일스톤·라이선스 수익의 일회성을 구분해 보세요.",
        ],
        watch=["rd_capitalization", "milestone_revenue", "litigation", "inventory_valuation"],
        priority=["operating_margin", "fcf", "cash_ratio", "roe", "earnings_quality"],
        ma=["fcf", "net_cash_proxy", "pipeline_note"],
        flags=CAPEX_FLAGS,
        sources=["MOTIE MTI 바이오헬스", "BOK C21"],
    ),
    "battery": kit(
        "이차전지",
        "Secondary Batteries",
        ["C282"],
        mti=["이차전지"],
        notes=[
            "증설 Capex·메탈 가격·수율·고객(EV OEM) 계약이 핵심입니다.",
            "공급과잉 국면에서 마진·가동률이 급변할 수 있습니다.",
        ],
        watch=["capex_commitments", "customer_concentration", "commodity_hedges", "inventory_valuation"],
        priority=["operating_margin", "fcf", "roic", "interest_coverage", "cash_ratio"],
        ma=["fcf", "normalized_ebitda_proxy", "net_debt_to_ebitda"],
        flags=CAPEX_FLAGS + CYCLE_FLAGS + INV_FLAGS,
        sources=["MOTIE MTI 이차전지", "BOK C28"],
    ),
    # --- MOTIE 20대 추가 ---
    "electrical_equipment": kit(
        "전기기기·전기장비",
        "Electrical Equipment",
        ["C28"],
        mti=["전기기기"],
        notes=[
            "전력기기·전선 등은 프로젝트 수주와 원자재(구리)에 민감합니다.",
            "세부 이차전지(C282)가 있으면 battery 키트가 우선합니다.",
        ],
        watch=["construction_backlog", "commodity_hedges", "guarantee_obligations"],
        priority=["operating_margin", "fcf", "interest_coverage", "current_ratio", "roe"],
        ma=["fcf", "net_debt_proxy", "backlog_note"],
        flags=CAPEX_FLAGS,
    ),
    "nonferrous": kit(
        "비철금속",
        "Non-ferrous Metals",
        ["C242"],
        mti=["비철금속"],
        notes=[
            "LME 등 메탈 가격·프리미엄이 실적을 좌우하는 원자재 업종입니다.",
            "재고평가와 헤지 회계를 반드시 확인하세요.",
        ],
        watch=["commodity_hedges", "inventory_valuation"],
        priority=["operating_margin", "fcf", "current_ratio", "interest_coverage", "cash_ratio"],
        ma=["normalized_ebitda_proxy", "fcf", "net_debt_to_ebitda"],
        flags=CYCLE_FLAGS + INV_FLAGS,
    ),
    "food_agri": kit(
        "식료품·농수산 관련 제조",
        "Food / Agri processing",
        ["C10", "C11"],
        mti=["농수산식품"],
        notes=[
            "원재료 작황·수입 곡물가·환율이 원가에 직접 반영됩니다.",
            "운전자본과 재고 신선도·폐기율이 중요합니다.",
        ],
        watch=["inventory_valuation", "commodity_hedges", "fx_exposure"],
        priority=["operating_margin", "inventory_turnover", "current_ratio", "fcf", "roe"],
        ma=["fcf", "earnings_quality", "net_cash_proxy"],
        flags=INV_FLAGS,
    ),
    "cosmetics": kit(
        "화장품·생활화학",
        "Cosmetics",
        ["C204"],
        mti=["화장품"],
        notes=[
            "브랜드·유통 채널·해외 비중(중국 등)이 성장과 마진을 좌우합니다.",
            "마케팅비·반품·재고진부화를 보세요.",
        ],
        watch=["inventory_valuation", "return_provisions", "related_party"],
        priority=["operating_margin", "roe", "inventory_turnover", "fcf", "cash_ratio"],
        ma=["fcf", "net_cash_proxy", "earnings_quality"],
        flags=INV_FLAGS,
    ),
    "household_goods": kit(
        "생활용품·기타 소비재 제조",
        "Household / Consumer goods",
        ["C33", "C32"],
        mti=["생활용품"],
        notes=[
            "내수 소비와 유통 협상력이 핵심입니다.",
            "재고·매출채권 관리가 현금흐름을 가릅니다.",
        ],
        watch=["inventory_valuation", "receivables_quality"],
        priority=["operating_margin", "inventory_turnover", "current_ratio", "fcf", "roe"],
        ma=["fcf", "net_cash_proxy"],
        flags=INV_FLAGS,
    ),
    # --- BOK / 물류·인프라·기타 중분류 ---
    "shipping": kit(
        "해운(수상 운송)",
        "Shipping / Water transport",
        ["H50"],
        mti=[],
        notes=[
            "IFRS 16 용선·리스부채가 부채비율·레버리지를 크게 올립니다.",
            "운임 사이클에 EBITDA가 민감해 한 해 배수만으로 판단하기 어렵습니다.",
            "선대 담보·SPC·용선 만기표를 주석에서 확인하세요.",
        ],
        watch=["ifrs16_lease_maturity", "charter_commitments", "vessel_collateral", "spc_affiliates", "bunker_hedges"],
        priority=["fcf", "earnings_quality", "interest_coverage", "cash_ratio", "operating_margin", "debt_ratio"],
        ma=["net_debt_incl_lease", "fcf", "normalized_ebitda_note", "fleet_nav_note"],
        flags=[
            {
                "id": "lease_inflates_leverage",
                "when": "lease_liabilities_present_or_high_debt",
                "severity_ko": "부채비율이 높아 보여도 상당 부분이 용선·리스일 수 있습니다.",
            },
            {
                "id": "cycle_peak_earnings",
                "when": "operating_margin_very_high",
                "severity_ko": "운임 호황기 이익을 영구 수준으로 쓰지 마세요(DCF·배수 가정 주의).",
            },
        ],
        de_emphasize=["debt_ratio_raw_only"],
        adjusted=[
            {
                "id": "leverage_ex_lease",
                "label_ko": "리스 제외 레버리지(가능 시)",
                "requires_accounts": ["LEASE_LIABILITIES"],
                "note_ko": "리스부채를 뺀 순차입/이익으로 보면 보고 부채비율과 해석이 달라집니다.",
            }
        ],
        sources=["KIS Shipping methodology 2020", "K-IFRS 1116", "BOK H50"],
    ),
    "airline": kit(
        "항공 운송",
        "Airlines",
        ["H51"],
        notes=[
            "항공기 리스(IFRS 16)로 부채·사용권자산이 크게 인식됩니다.",
            "유가·환율·수요(여객/화물) 민감도가 극단적입니다.",
        ],
        watch=["ifrs16_lease_maturity", "fuel_hedges", "fx_exposure"],
        priority=["fcf", "operating_margin", "interest_coverage", "cash_ratio", "debt_ratio"],
        ma=["net_debt_incl_lease", "fcf", "normalized_ebitda_note"],
        flags=[
            {
                "id": "lease_inflates_leverage",
                "when": "lease_liabilities_present_or_high_debt",
                "severity_ko": "리스부채가 레버리지를 크게 올립니다.",
            }
        ]
        + CYCLE_FLAGS,
        adjusted=[
            {
                "id": "leverage_ex_lease",
                "label_ko": "리스 제외 레버리지(가능 시)",
                "requires_accounts": ["LEASE_LIABILITIES"],
                "note_ko": "리스부채 총액이 공시된 경우에만 보고 부채비율과 별도로 제시합니다.",
            }
        ],
        sources=["KIS IFRS16 airline/shipping reviews", "BOK H51"],
    ),
    "construction": kit(
        "건설",
        "Construction",
        ["F41", "F42", "F"],
        notes=[
            "진행기준·미청구공사·주택 분양 수익 인식이 핵심 왜곡 요인입니다.",
            "PF·지급보증·공사손실충당을 주석에서 확인하세요.",
        ],
        watch=["percentage_of_completion", "unbilled_receivables", "guarantee_obligations", "project_financing"],
        priority=["operating_margin", "fcf", "current_ratio", "debt_ratio", "earnings_quality"],
        ma=["fcf", "guarantee_contingent", "percentage_of_completion_risk"],
        flags=[
            {
                "id": "poc_earnings_quality",
                "when": "earnings_quality_low",
                "severity_ko": "진행기준 이익과 영업현금 괴리를 점검하세요.",
            }
        ],
        sources=["BOK F construction", "construction credit practice"],
    ),
    "utilities": kit(
        "전기·가스·유틸리티",
        "Utilities",
        ["D35", "D"],
        notes=[
            "규제요금·연료비 연동·대규모 설비자산이 특징입니다.",
            "차입·사채 만기구조와 이자보상이 핵심입니다.",
        ],
        watch=["regulatory_assets", "capex_commitments", "fuel_cost_pass_through"],
        priority=["interest_coverage", "fcf", "debt_ratio", "operating_margin", "cash_ratio"],
        ma=["fcf", "net_debt_to_ebitda", "interest_coverage"],
        flags=CAPEX_FLAGS,
    ),
    "retail_wholesale": kit(
        "도소매",
        "Retail / Wholesale",
        ["G46", "G47", "G45", "G"],
        notes=[
            "임차·리스(점포)와 재고회전이 핵심입니다.",
            "매출총이익률·동일점포 성장보다 운전자본을 같이 보세요.",
        ],
        watch=["ifrs16_lease_maturity", "inventory_valuation", "franchise_receivables"],
        priority=["operating_margin", "inventory_turnover", "current_ratio", "fcf", "cash_ratio"],
        ma=["fcf", "net_debt_incl_lease", "earnings_quality"],
        flags=INV_FLAGS
        + [
            {
                "id": "lease_inflates_leverage",
                "when": "lease_liabilities_present_or_high_debt",
                "severity_ko": "점포 리스부채가 레버리지를 올립니다.",
            }
        ],
    ),
    "precision_instruments": kit(
        "의료·정밀기기",
        "Precision / Medical devices",
        ["C27"],
        notes=["인허가·품질·병원 고객 집중이 중요합니다.", "R&D와 재고 진부화를 확인하세요."],
        watch=["rd_capitalization", "regulatory_approval", "inventory_valuation"],
        priority=["operating_margin", "roe", "fcf", "cash_ratio", "earnings_quality"],
        ma=["fcf", "net_cash_proxy"],
    ),
    "rubber_plastic": kit(
        "고무·플라스틱",
        "Rubber / Plastics",
        ["C22"],
        notes=["유가·나프타 연동 원가와 전방(자동차·가전) 수요에 연동됩니다."],
        watch=["commodity_hedges", "customer_concentration"],
        priority=["operating_margin", "fcf", "inventory_turnover", "interest_coverage"],
        ma=["fcf", "net_debt_proxy"],
        flags=CYCLE_FLAGS + INV_FLAGS,
    ),
    "primary_metal_other": kit(
        "1차 금속(기타)",
        "Primary metals (broad)",
        ["C24"],
        notes=["철강·비철 세부가 없으면 금속 사이클 일반 가정을 적용합니다."],
        watch=["commodity_hedges", "inventory_valuation"],
        priority=["operating_margin", "fcf", "interest_coverage", "debt_ratio"],
        ma=["normalized_ebitda_proxy", "net_debt_to_ebitda"],
        flags=CYCLE_FLAGS,
    ),
    "manufacturing_other": kit(
        "기타 제조(한은 중분류 폴백)",
        "Other manufacturing",
        ["C"],
        notes=[
            "세분 키트에 없는 제조업 KSIC는 여기로 옵니다.",
            "공통으로 유동성·레버리지·FCF·이익의 질을 봅니다.",
        ],
        watch=["contingent_liabilities", "related_party", "lease_commitments"],
        priority=COMMON_PRI,
        ma=["fcf", "net_cash_proxy", "earnings_quality", "interest_coverage"],
    ),
    "general": kit(
        "일반(미분류)",
        "General",
        [],
        notes=["업종 미지정 — 공통 재무지표만 적용합니다."],
        watch=["contingent_liabilities", "related_party", "lease_commitments"],
        priority=COMMON_PRI,
        ma=["fcf", "net_cash_proxy", "earnings_quality", "interest_coverage"],
    ),
}

# Remove obsolete combined "electronics" — replaced by semiconductor + electronics_components etc.
# Keep alias in map file.

export_15 = [
    {"mti": "반도체", "kit": "semiconductor", "ksic": ["C261"]},
    {"mti": "자동차", "kit": "auto", "ksic": ["C30"]},
    {"mti": "일반기계", "kit": "machinery", "ksic": ["C29"]},
    {"mti": "석유화학", "kit": "petrochemical", "ksic": ["C20"]},
    {"mti": "석유제품", "kit": "petroleum_products", "ksic": ["C19"]},
    {"mti": "철강", "kit": "steel", "ksic": ["C241"]},
    {"mti": "디스플레이", "kit": "display", "ksic": ["C262"]},
    {"mti": "자동차부품", "kit": "auto_parts", "ksic": ["C303"]},
    {"mti": "선박", "kit": "shipbuilding", "ksic": ["C311"]},
    {"mti": "컴퓨터", "kit": "computers", "ksic": ["C263"]},
    {"mti": "무선통신", "kit": "telecom_devices", "ksic": ["C264"]},
    {"mti": "섬유", "kit": "textile", "ksic": ["C13", "C14"]},
    {"mti": "바이오헬스", "kit": "biohealth", "ksic": ["C21"]},
    {"mti": "이차전지", "kit": "battery", "ksic": ["C282"]},
    {"mti": "가전", "kit": "home_appliances", "ksic": ["C285"]},
]

export_20_extra = [
    {"mti": "전기기기", "kit": "electrical_equipment", "ksic": ["C28"]},
    {"mti": "비철금속", "kit": "nonferrous", "ksic": ["C242"]},
    {"mti": "농수산식품", "kit": "food_agri", "ksic": ["C10", "C11"]},
    {"mti": "화장품", "kit": "cosmetics", "ksic": ["C204"]},
    {"mti": "생활용품", "kit": "household_goods", "ksic": ["C33", "C32"]},
]

# BOK manufacturing mid-classes (KSIC 11th) + key non-manufacturing used in FSA
bok_mid = [
    ("C10", "식료품", "food_agri"),
    ("C11", "음료", "food_agri"),
    ("C12", "담배", "manufacturing_other"),
    ("C13", "섬유제품", "textile"),
    ("C14", "의복", "textile"),
    ("C15", "가죽·가방·신발", "manufacturing_other"),
    ("C16", "목재", "manufacturing_other"),
    ("C17", "펄프·종이", "manufacturing_other"),
    ("C18", "인쇄", "manufacturing_other"),
    ("C19", "코크스·연탄·석유정제품", "petroleum_products"),
    ("C20", "화학(의약품 제외)", "petrochemical"),
    ("C21", "의약품", "biohealth"),
    ("C22", "고무·플라스틱", "rubber_plastic"),
    ("C23", "비금속광물", "manufacturing_other"),
    ("C24", "1차 금속", "primary_metal_other"),
    ("C25", "금속가공", "manufacturing_other"),
    ("C26", "전자·컴퓨터·통신장비", "electronics_components"),
    ("C27", "의료·정밀·광학", "precision_instruments"),
    ("C28", "전기장비", "electrical_equipment"),
    ("C29", "기타 기계·장비", "machinery"),
    ("C30", "자동차·트레일러", "auto"),
    ("C31", "기타 운송장비", "shipbuilding"),
    ("C32", "가구", "household_goods"),
    ("C33", "기타 제품", "household_goods"),
    ("D35", "전기·가스·증기", "utilities"),
    ("F41", "종합건설", "construction"),
    ("F42", "전문직별 공사", "construction"),
    ("G45", "자동차·부품 판매", "retail_wholesale"),
    ("G46", "도매", "retail_wholesale"),
    ("G47", "소매", "retail_wholesale"),
    ("H49", "육상운송", "general"),
    ("H50", "수상운송", "shipping"),
    ("H51", "항공운송", "airline"),
    ("H52", "창고·운송관련", "general"),
]

doc = {
    "schema_version": "dart-industry-kits-2.0.0",
    "engine_note": "Longest KSIC prefix wins. Rule-based; no LLM. See INDUSTRY_RATIONALE.md and EXPORT_BOK_COVERAGE.md",
    "kits": kits,
}

coverage = {
    "schema_version": "dart-export-bok-coverage-1.0.0",
    "motie_15_major_export_items": export_15,
    "motie_20_additional_items": export_20_extra,
    "motie_source_ko": "산업통상자원부 주력 수출 품목(기존 15대 + 2026년 20대 확대: 전기기기·비철금속·농수산식품·화장품·생활용품)",
    "bok_ksic_midclass_map": [
        {"ksic": k, "label_ko": lab, "kit": kit_id} for k, lab, kit_id in bok_mid
    ],
    "bok_source_ko": "한국은행 기업경영분석은 통계청 KSIC(제11차) 기준으로 업종별 재무비율을 공표",
    "aliases": {
        "electronics": "electronics_components",
        "반도체": "semiconductor",
        "해운": "shipping",
        "조선": "shipbuilding",
    },
}

CONFIG.mkdir(parents=True, exist_ok=True)
(CONFIG / "industry_kits.json").write_text(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
(CONFIG / "export_bok_coverage.json").write_text(
    json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("kits", len(kits))
print("motie15", len(export_15), "extra", len(export_20_extra), "bok_mid", len(bok_mid))
