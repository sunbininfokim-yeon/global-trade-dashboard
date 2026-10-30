"""
Palm-oil producers modelled here, with their production-weighted weather points.

USDA FAS PSD 2024/25 crude palm oil: Indonesia 47 Mt (indonesia/palm_psd.py),
Malaysia 19.3, Thailand 3.4, Colombia 1.9, Nigeria 1.5 -- together with
Indonesia about 90% of world output. Point weights follow each country's own
production split: MPOB state output (Sabah and Sarawak about half), the
southern Thai provinces (OAE), Fedepalma's four zones, and Nigeria's
south-south and south-east oil-palm belt.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Producer:
    key: str                 # region key in the country's forecast JSON
    country: str             # yield_model/{country}/ folder
    psd_name: str            # PSD Country_Name
    label: str
    label_ko: str
    points: list = field(default_factory=list)


MALAYSIA = Producer(
    key="malaysia_palm_oil", country="malaysia", psd_name="Malaysia",
    label="Malaysia palm oil (CPO) production", label_ko="팜유(CPO) 생산",
    points=[
        {"name": "Sabah_Lahad_Datu", "lat": 5.03, "lon": 118.33, "weight": 0.25},
        {"name": "Sarawak_Bintulu_Miri", "lat": 3.20, "lon": 113.10, "weight": 0.22},
        {"name": "Johor_Kluang", "lat": 2.03, "lon": 103.32, "weight": 0.16},
        {"name": "Pahang_Kuantan", "lat": 3.60, "lon": 102.80, "weight": 0.15},
        {"name": "Perak_Teluk_Intan", "lat": 4.02, "lon": 100.98, "weight": 0.12},
        {"name": "Selangor_N_Sembilan", "lat": 2.80, "lon": 101.75, "weight": 0.10},
    ])

THAILAND = Producer(
    key="thailand_palm_oil", country="thailand", psd_name="Thailand",
    label="Thailand palm oil (CPO) production", label_ko="팜유(CPO) 생산",
    points=[
        {"name": "Surat_Thani", "lat": 9.00, "lon": 99.10, "weight": 0.45},
        {"name": "Krabi", "lat": 8.10, "lon": 98.90, "weight": 0.20},
        {"name": "Chumphon", "lat": 10.40, "lon": 99.00, "weight": 0.20},
        {"name": "Nakhon_Si_Thammarat", "lat": 8.30, "lon": 99.90, "weight": 0.15},
    ])

COLOMBIA = Producer(
    key="colombia_palm_oil", country="colombia", psd_name="Colombia",
    label="Colombia palm oil (CPO) production", label_ko="팜유(CPO) 생산",
    points=[
        {"name": "Oriental_Meta", "lat": 4.00, "lon": -73.00, "weight": 0.30},
        {"name": "Oriental_Casanare", "lat": 4.90, "lon": -72.30, "weight": 0.15},
        {"name": "Central_Puerto_Wilches", "lat": 7.30, "lon": -73.80, "weight": 0.27},
        {"name": "Norte_Magdalena_Cesar", "lat": 10.00, "lon": -73.90, "weight": 0.25},
        {"name": "Suroccidental_Tumaco", "lat": 1.80, "lon": -78.80, "weight": 0.03},
    ])

NIGERIA = Producer(
    key="nigeria_palm_oil", country="nigeria", psd_name="Nigeria",
    label="Nigeria palm oil production", label_ko="팜유 생산",
    points=[
        {"name": "Cross_River", "lat": 5.90, "lon": 8.60, "weight": 0.20},
        {"name": "Akwa_Ibom", "lat": 5.00, "lon": 7.90, "weight": 0.20},
        {"name": "Imo_Rivers", "lat": 5.30, "lon": 7.00, "weight": 0.20},
        {"name": "Edo_Delta", "lat": 6.30, "lon": 5.80, "weight": 0.20},
        {"name": "Ondo", "lat": 6.90, "lon": 5.00, "weight": 0.20},
    ])

ALL = [MALAYSIA, THAILAND, COLOMBIA, NIGERIA]
BY_KEY = {p.key: p for p in ALL}
BY_COUNTRY = {p.country: p for p in ALL}
