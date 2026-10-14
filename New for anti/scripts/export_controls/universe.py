"""Who the weekly export-control survey watches.

Each group started as thirty primary exporters and now also includes the
countries that actually ship the added raw materials. A country is here
because it is a primary exporter, not because a hub re-exports the goods.
Hubs stay on the excluded list so a later pass does not add them back.

The original thirty are a 2023–2024 judgment from crop export rankings
(USDA PSD / FAO), mine production (USGS Mineral Commodity Summaries) and
energy exports (IEA). This file does not re-rank them from the production
Comtrade proxy. That proxy spends a shared API quota, and a weekly
reshuffle is not the survey.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Slugs the catalogue may use. The map colours a slug only after Claude adds
# it to the export-control monitor aliases and Korean labels. Unknown agri
# slugs still show on the crop-monitor list as the raw slug.
#
# Finished chips, chipmaking tools, and company or person sanctions are not
# commodities here. Semiconductor coverage is the raw materials: high-purity
# quartz (the sand crucibles and wafers are made from), silicon metal,
# polysilicon, and the licensed metals around that chain.
COMMODITY_LABELS_KO = {
    "quartz": "석영 광물·규사(반도체용 포함)",
    "boron": "붕소",
    "silicon_metal": "금속규소",
    "polysilicon": "폴리실리콘",
    "indium": "인듐",
    "molybdenum": "몰리브덴",
    "fluorite": "형석",
    "magnesium": "마그네슘",
    "titanium": "티타늄",
    "tantalum": "탄탈럼",
    "niobium": "니오븀",
    "vanadium": "바나듐",
    "superhard": "초경질재료",
    "neon": "네온",
    "potash": "염화칼륨",
}

COMMODITY_KEYS = [
    "wheat", "corn", "barley", "soybeans", "rice", "sugar", "coffee", "cocoa",
    "palm_oil", "rubber", "rapeseed", "sunflower_oil", "sunflower_seed",
    "fertilizer", "urea", "phosphate", "potash", "boron", "cotton", "beef", "pork", "poultry",
    "dairy", "bananas", "shrimp", "olive_oil", "fruit",
    "oil", "gas", "lng", "thermal_coal", "met_coal", "coal",
    "petroleum_products", "uranium",
    "copper", "aluminum", "bauxite", "zinc", "nickel", "cobalt", "lithium",
    "graphite", "rare_earths", "gallium", "germanium", "antimony", "tungsten",
    "molybdenum", "indium", "fluorite", "magnesium", "titanium", "tantalum",
    "niobium", "vanadium", "quartz", "silicon_metal", "polysilicon", "superhard",
    "neon",
    "iron_ore", "manganese", "chromium", "tin", "lead", "gold", "silver",
    "platinum", "palladium", "diamonds", "ferroalloys",
]

EXCLUDED_ENTREPOTS = [
    {"iso": "NLD", "name": "Netherlands", "why": "농산물·석유제품 재수출 허브"},
    {"iso": "BEL", "name": "Belgium", "why": "농산물·다이아몬드 재수출 허브"},
    {"iso": "SGP", "name": "Singapore", "why": "석유제품 혼재·재수출"},
    {"iso": "CHE", "name": "Switzerland", "why": "금 거래 허브. 광산 수출국이 아님"},
    {"iso": "HKG", "name": "Hong Kong", "why": "금·농산물 재수출"},
]

# Watched even though the country is not in that category's top 30.
# Myanmar and Ghana are already in the minerals thirty.
PINNED = [
    {
        "iso": "EGY", "name": "Egypt", "category": "agri",
        "commodities": ["rice", "wheat"],
        "why": "쌀·밀 수출 제한 이력이 있고 농산물 수출 상위 30에는 없다",
    },
    {
        "iso": "MMR", "name": "Myanmar", "category": "agri",
        "commodities": ["rice"],
        "why": "쌀 수출 허가 이력이 있다. 광물 30개국에는 이미 있다",
    },
    {
        "iso": "GHA", "name": "Ghana", "category": "agri",
        "commodities": ["cocoa"],
        "why": "코코아 원두 주요 수출국. 귀금속 30개국(금)에는 이미 있다",
    },
    {
        "iso": "BEL", "name": "Belgium", "category": "minerals",
        "commodities": ["diamonds"],
        "why": "안트워프가 다이아몬드 재수출 통제의 주체다. 농산물·금 통과 허브로는 보지 않는다.",
    },
    {
        "iso": "SGP", "name": "Singapore", "category": "energy",
        "commodities": ["petroleum_products"],
        "why": "석유제품 혼재·재수출에 자체 제한이 걸릴 수 있다. 원유 생산국 목록에는 넣지 않는다.",
    },
]


def _c(iso, name, commodities):
    return {"iso": iso, "name": name, "commodities": list(commodities)}


# Chile is a large fruit exporter. Fruit is one slug until a control names
# a more specific product. It is not a dairy exporter of any consequence.
AGRI = [
    _c("USA", "United States", ["wheat", "corn", "soybeans", "cotton", "beef"]),
    _c("BRA", "Brazil", ["soybeans", "corn", "sugar", "coffee", "beef", "cotton"]),
    _c("ARG", "Argentina", ["soybeans", "corn", "wheat", "beef"]),
    _c("CHN", "China", ["rice", "fertilizer", "urea", "phosphate"]),
    _c("IND", "India", ["rice", "wheat", "sugar", "cotton", "beef", "shrimp"]),
    _c("IDN", "Indonesia", ["palm_oil", "coffee", "cocoa", "rubber"]),
    _c("CAN", "Canada", ["wheat", "rapeseed", "pork", "potash"]),
    _c("AUS", "Australia", ["wheat", "barley", "beef", "rapeseed", "cotton"]),
    _c("FRA", "France", ["wheat", "barley", "corn"]),
    _c("DEU", "Germany", ["wheat", "barley", "pork", "dairy"]),
    _c("RUS", "Russia", ["wheat", "barley", "corn", "sunflower_oil", "sunflower_seed", "potash"]),
    _c("UKR", "Ukraine", ["wheat", "corn", "sunflower_oil", "rapeseed", "soybeans"]),
    _c("THA", "Thailand", ["rice", "rubber", "sugar"]),
    _c("MYS", "Malaysia", ["palm_oil", "rubber"]),
    _c("VNM", "Vietnam", ["rice", "coffee", "rubber"]),
    _c("ESP", "Spain", ["olive_oil", "pork"]),
    _c("MEX", "Mexico", ["beef", "sugar", "corn"]),
    _c("TUR", "Turkey", ["wheat", "barley"]),
    _c("NZL", "New Zealand", ["dairy", "beef"]),
    _c("PAK", "Pakistan", ["rice"]),
    _c("KAZ", "Kazakhstan", ["wheat"]),
    _c("ZAF", "South Africa", ["corn", "sugar"]),
    _c("POL", "Poland", ["wheat", "poultry", "dairy"]),
    _c("ITA", "Italy", ["dairy", "olive_oil"]),
    _c("PRY", "Paraguay", ["soybeans", "corn", "beef"]),
    _c("COL", "Colombia", ["coffee", "bananas"]),
    _c("CIV", "Cote d'Ivoire", ["cocoa"]),
    _c("CHL", "Chile", ["fruit"]),
    _c("PER", "Peru", ["coffee"]),
    _c("ECU", "Ecuador", ["bananas", "cocoa", "shrimp"]),
    _c("MAR", "Morocco", ["phosphate", "fertilizer"]),
    _c("ISR", "Israel", ["potash"]),
    _c("JOR", "Jordan", ["potash"]),
    _c("BLR", "Belarus", ["potash"]),
    _c("ETH", "Ethiopia", ["coffee"]),
    _c("CMR", "Cameroon", ["cocoa"]),
]

MINERALS = [
    _c("CHN", "China", [
        "rare_earths", "graphite", "gallium", "germanium", "aluminum", "tin", "gold",
        "antimony", "tungsten", "molybdenum", "indium", "fluorite", "magnesium",
        "titanium", "vanadium", "quartz", "silicon_metal", "polysilicon", "superhard",
    ]),
    _c("AUS", "Australia", ["iron_ore", "bauxite", "gold", "lithium", "copper", "titanium", "tantalum", "rare_earths"]),
    _c("CHL", "Chile", ["copper", "lithium", "molybdenum"]),
    _c("PER", "Peru", ["copper", "gold", "zinc", "silver", "molybdenum"]),
    _c("RUS", "Russia", ["nickel", "gold", "palladium", "platinum", "aluminum", "titanium", "vanadium", "neon"]),
    _c("USA", "United States", ["copper", "gold", "quartz", "molybdenum"]),
    _c("BRA", "Brazil", ["iron_ore", "bauxite", "gold", "niobium", "tantalum"]),
    _c("ZAF", "South Africa", ["platinum", "palladium", "gold", "manganese", "chromium", "iron_ore", "vanadium"]),
    _c("CAN", "Canada", ["gold", "nickel", "copper", "niobium"]),
    _c("IDN", "Indonesia", ["nickel", "bauxite", "copper", "tin", "gold", "ferroalloys", "cobalt"]),
    _c("COD", "DR Congo", ["cobalt", "copper", "tantalum"]),
    _c("ZMB", "Zambia", ["copper"]),
    _c("MEX", "Mexico", ["silver", "gold", "copper", "fluorite"]),
    _c("IND", "India", ["iron_ore", "aluminum", "zinc", "quartz"]),
    _c("KAZ", "Kazakhstan", ["copper", "chromium", "gold"]),
    _c("PHL", "Philippines", ["nickel"]),
    _c("GIN", "Guinea", ["bauxite"]),
    _c("GHA", "Ghana", ["gold", "manganese"]),
    _c("MNG", "Mongolia", ["copper", "gold", "fluorite"]),
    _c("SWE", "Sweden", ["iron_ore"]),
    _c("PNG", "Papua New Guinea", ["gold", "copper"]),
    _c("BWA", "Botswana", ["diamonds"]),
    _c("NCL", "New Caledonia", ["nickel"]),
    _c("ARG", "Argentina", ["lithium"]),
    _c("MMR", "Myanmar", ["rare_earths", "tin"]),
    _c("BOL", "Bolivia", ["lithium", "tin", "silver"]),
    _c("NAM", "Namibia", ["diamonds", "uranium"]),
    _c("ZWE", "Zimbabwe", ["platinum", "lithium"]),
    _c("UKR", "Ukraine", ["iron_ore", "titanium", "neon"]),
    _c("IRN", "Iran", ["iron_ore", "copper"]),
    _c("RWA", "Rwanda", ["tantalum", "tin"]),
    _c("MOZ", "Mozambique", ["titanium", "graphite"]),
    _c("NOR", "Norway", ["silicon_metal", "quartz"]),
    _c("DEU", "Germany", ["polysilicon"]),
    _c("JPN", "Japan", ["titanium", "indium"]),
    _c("VNM", "Vietnam", ["tungsten", "rare_earths", "quartz"]),
    _c("AGO", "Angola", ["quartz", "silicon_metal", "polysilicon", "diamonds"]),
    _c("GAB", "Gabon", ["manganese"]),
    _c("TJK", "Tajikistan", ["antimony"]),
    _c("TUR", "Turkey", ["boron", "chromium"]),
    _c("UZB", "Uzbekistan", ["gold"]),
]

ENERGY = [
    _c("SAU", "Saudi Arabia", ["oil", "petroleum_products"]),
    _c("RUS", "Russia", ["oil", "gas", "petroleum_products", "coal"]),
    _c("USA", "United States", ["oil", "gas", "lng", "petroleum_products", "coal"]),
    _c("CAN", "Canada", ["oil", "gas", "uranium"]),
    _c("AUS", "Australia", ["lng", "thermal_coal", "met_coal", "uranium"]),
    _c("IRQ", "Iraq", ["oil"]),
    _c("IRN", "Iran", ["oil", "petroleum_products"]),
    _c("ARE", "United Arab Emirates", ["oil", "lng"]),
    _c("QAT", "Qatar", ["lng", "oil"]),
    _c("NOR", "Norway", ["oil", "gas"]),
    _c("KWT", "Kuwait", ["oil"]),
    _c("KAZ", "Kazakhstan", ["oil", "uranium"]),
    _c("NGA", "Nigeria", ["oil", "lng"]),
    _c("BRA", "Brazil", ["oil"]),
    _c("IDN", "Indonesia", ["thermal_coal", "lng"]),
    _c("MYS", "Malaysia", ["lng"]),
    _c("DZA", "Algeria", ["gas", "lng"]),
    _c("AGO", "Angola", ["oil"]),
    _c("LBY", "Libya", ["oil"]),
    _c("OMN", "Oman", ["oil", "lng"]),
    _c("MEX", "Mexico", ["oil"]),
    _c("COL", "Colombia", ["oil", "thermal_coal"]),
    _c("ZAF", "South Africa", ["thermal_coal"]),
    _c("AZE", "Azerbaijan", ["oil", "gas"]),
    _c("CHN", "China", ["thermal_coal", "petroleum_products"]),
    _c("IND", "India", ["petroleum_products"]),
    _c("MNG", "Mongolia", ["thermal_coal"]),
    _c("VEN", "Venezuela", ["oil"]),
    _c("TKM", "Turkmenistan", ["gas"]),
    _c("BRN", "Brunei", ["oil", "lng"]),
    _c("NER", "Niger", ["uranium"]),
    _c("UZB", "Uzbekistan", ["uranium"]),
]


def document():
    return {
        "schema_version": "export-controls-universe-v1",
        "defined_on": "2026-09-24",
        "expanded_on": "2026-10-14",
        "cadence": "weekly",
        "cadence_reason_ko": (
            "매주 월요일. 인도 설탕 시즌(10월 1일), 러시아 석유제품 금지의 예외 기한, "
            "인도네시아·말레이시아 팜유 기준가가 한 달 안에서 바뀐다. "
            "바뀐 조치가 없는 주도 그 주 점검 기록은 남긴다. 카탈로그는 원문을 본 항목만 고친다."
        ),
        "method_ko": (
            "처음 30개국은 2023–2024년 1차 수출이 큰 나라다. "
            "2026-10-14에 반도체 원료·인광석·염화칼륨·우라늄의 실제 수출국을 더했다. "
            "같은 날 팩트체크 뒤에 앙골라(석영), 가봉(망간), 타지키스탄(안티모니), "
            "튀르키예(붕소·크로뮴), 에티오피아(커피), 카메룬(코코아)을 더했다. "
            "농산물은 USDA PSD·FAO, 귀금속·광물은 USGS 광산 생산과 정련 수출, "
            "에너지는 IEA 원유·가스·석탄 수출을 봤다. 재수출 허브는 빼다. "
            "운영 Comtrade 쿼터로 매주 순위를 다시 뽑지 않는다."
        ),
        "commodity_keys": list(COMMODITY_KEYS),
        "commodity_labels_ko": dict(COMMODITY_LABELS_KO),
        "excluded_entrepots": EXCLUDED_ENTREPOTS,
        "pinned_outside_role": PINNED,
        "categories": {
            "agri": {"label_ko": "농산물", "countries": AGRI},
            "minerals": {"label_ko": "귀금속·광물", "countries": MINERALS},
            "energy": {"label_ko": "에너지", "countries": ENERGY},
        },
    }


def write_json(path=None):
    path = Path(path) if path else HERE / "universe.json"
    path.write_text(
        json.dumps(document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load(path=None):
    path = Path(path) if path else HERE / "universe.json"
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    print(write_json())
