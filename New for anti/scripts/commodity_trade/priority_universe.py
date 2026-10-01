"""Bounded country and commodity universe for free monthly trade collection.

This is intentionally a priority panel, not a claim of world coverage.  It
targets reporting countries that matter for the dashboard's commodity view and
keeps HS selections explicit so that incompatible sub-products are not merged.
"""

from __future__ import annotations


PRIORITY_REPORTERS: dict[str, dict[str, str]] = {
    "USA": {"m49": "842", "name_ko": "미국", "role": "agri_energy_importer_exporter"},
    "BRA": {"m49": "076", "name_ko": "브라질", "role": "agri_minerals_exporter"},
    "ARG": {"m49": "032", "name_ko": "아르헨티나", "role": "agri_energy_exporter"},
    "CHN": {"m49": "156", "name_ko": "중국", "role": "major_commodity_importer"},
    "KOR": {"m49": "410", "name_ko": "대한민국", "role": "major_commodity_importer"},
    "JPN": {"m49": "392", "name_ko": "일본", "role": "major_commodity_importer"},
    "AUS": {"m49": "036", "name_ko": "호주", "role": "minerals_energy_agri_exporter"},
    "ZAF": {"m49": "710", "name_ko": "남아프리카공화국", "role": "minerals_energy_exporter"},
    "SAU": {"m49": "682", "name_ko": "사우디아라비아", "role": "energy_exporter"},
    "ARE": {"m49": "784", "name_ko": "아랍에미리트", "role": "energy_trade_hub"},
    "IDN": {"m49": "360", "name_ko": "인도네시아", "role": "nickel_coal_palm_exporter"},
    "MYS": {"m49": "458", "name_ko": "말레이시아", "role": "palm_lng_exporter"},
    "CHL": {"m49": "152", "name_ko": "칠레", "role": "copper_exporter"},
    "CAN": {"m49": "124", "name_ko": "캐나다", "role": "energy_minerals_agri_exporter"},
    "IND": {"m49": "356", "name_ko": "인도", "role": "agri_energy_importer_exporter"},
    "RUS": {"m49": "643", "name_ko": "러시아", "role": "energy_metals_agri_exporter"},
    "QAT": {"m49": "634", "name_ko": "카타르", "role": "lng_exporter"},
    "NOR": {"m49": "578", "name_ko": "노르웨이", "role": "oil_gas_exporter"},
    "KAZ": {"m49": "398", "name_ko": "카자흐스탄", "role": "oil_uranium_metals_exporter"},
    "IRQ": {"m49": "368", "name_ko": "이라크", "role": "crude_oil_exporter"},
    "KWT": {"m49": "414", "name_ko": "쿠웨이트", "role": "crude_oil_exporter"},
    "NGA": {"m49": "566", "name_ko": "나이지리아", "role": "oil_lng_exporter"},
    "AGO": {"m49": "024", "name_ko": "앙골라", "role": "crude_oil_exporter"},
    "PER": {"m49": "604", "name_ko": "페루", "role": "copper_minerals_exporter"},
    "MEX": {"m49": "484", "name_ko": "멕시코", "role": "oil_metals_trade_partner"},
    "THA": {"m49": "764", "name_ko": "태국", "role": "rice_agri_exporter"},
    "VNM": {"m49": "704", "name_ko": "베트남", "role": "rice_coffee_trade_exporter"},
}


# One explicit HS code per dashboard commodity.  A code may be a useful proxy
# but is never silently widened to every related product.  The label is kept in
# output so the UI can explain the scope to the user.
PRIORITY_COMMODITIES: dict[str, dict[str, str]] = {
    "crude_oil": {"hs": "2709", "sector": "energy", "scope_ko": "HS2709 원유"},
    "petroleum_products": {"hs": "2710", "sector": "energy", "scope_ko": "HS2710 석유제품"},
    "lng": {"hs": "271111", "sector": "energy", "scope_ko": "HS271111 액화천연가스"},
    "coal": {"hs": "2701", "sector": "energy", "scope_ko": "HS2701 석탄"},
    "uranium": {"hs": "284410", "sector": "energy", "scope_ko": "HS284410 천연우라늄·화합물"},
    "iron_ore": {"hs": "2601", "sector": "minerals", "scope_ko": "HS2601 철광석·정광"},
    "copper": {"hs": "2603", "sector": "minerals", "scope_ko": "HS2603 구리광·정광"},
    "nickel": {"hs": "7502", "sector": "minerals", "scope_ko": "HS7502 비합금 니켈"},
    "aluminum": {"hs": "7601", "sector": "minerals", "scope_ko": "HS7601 비합금 알루미늄"},
    "bauxite": {"hs": "2606", "sector": "minerals", "scope_ko": "HS2606 알루미늄광·정광"},
    "cobalt": {"hs": "8105", "sector": "minerals", "scope_ko": "HS8105 코발트 매트·제품"},
    "graphite": {"hs": "2504", "sector": "minerals", "scope_ko": "HS2504 천연 흑연"},
    "tungsten": {"hs": "2611", "sector": "minerals", "scope_ko": "HS2611 텅스텐광·정광"},
    "antimony": {"hs": "2617", "sector": "minerals", "scope_ko": "HS2617 안티몬광·정광"},
    "wheat": {"hs": "1001", "sector": "agri_trade", "scope_ko": "HS1001 밀·메슬린"},
    "barley": {"hs": "1003", "sector": "agri_trade", "scope_ko": "HS1003 보리"},
    "corn": {"hs": "1005", "sector": "agri_trade", "scope_ko": "HS1005 옥수수"},
    "rice": {"hs": "1006", "sector": "agri_trade", "scope_ko": "HS1006 쌀"},
    "soybeans": {"hs": "1201", "sector": "agri_trade", "scope_ko": "HS1201 대두"},
    "soybean_meal": {"hs": "2304", "sector": "agri_trade", "scope_ko": "HS2304 대두유박"},
    "palm_oil": {"hs": "1511", "sector": "agri_trade", "scope_ko": "HS1511 팜유"},
    "sugar": {"hs": "1701", "sector": "agri_trade", "scope_ko": "HS1701 사탕수수·사탕무 설탕"},
    "cotton": {"hs": "5201", "sector": "agri_trade", "scope_ko": "HS5201 미가공 면화"},
}


FLOW_LABELS = {"X": "exports", "M": "imports"}
