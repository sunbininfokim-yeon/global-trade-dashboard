"""Map macro_monitor series → live fetch backends."""

from __future__ import annotations

# Yahoo chart history (monthly). Yields: ^TNX/^IRX etc. quote as percent.
YAHOO: dict[tuple[str, str], dict] = {
    ("USA", "bond_10y"): {"symbol": "^TNX"},
    ("USA", "spx"): {"symbol": "^GSPC"},
    ("USA", "ndx"): {"symbol": "^NDX"},
    ("USA", "rut"): {"symbol": "^RUT"},
    ("USA", "vix"): {"symbol": "^VIX"},
    ("USA", "dxy"): {"symbol": "DX-Y.NYB"},
    ("USA", "eurusd"): {"symbol": "EURUSD=X"},
    ("USA", "usdjpy"): {"symbol": "USDJPY=X"},
    ("JPN", "usdjpy"): {"symbol": "USDJPY=X"},
    ("JPN", "nikkei"): {"symbol": "^N225"},
    ("KOR", "kospi"): {"symbol": "^KS11"},
    ("KOR", "usdkrw"): {"symbol": "USDKRW=X"},
    ("GBR", "gbpusd"): {"symbol": "GBPUSD=X"},
    ("GBR", "ftse100"): {"symbol": "^FTSE"},
    ("EMU", "eurusd"): {"symbol": "EURUSD=X"},
    ("EMU", "euro_stoxx50"): {"symbol": "^STOXX50E"},
    ("EMU", "dax40"): {"symbol": "^GDAXI"},
    ("CHN", "usdcnh"): {"symbol": "CNH=X"},
    ("CAN", "usdcad"): {"symbol": "CAD=X"},
    ("AUS", "audusd"): {"symbol": "AUDUSD=X"},
    ("CHE", "usdchf"): {"symbol": "CHF=X"},
    ("BRA", "usdbrl"): {"symbol": "BRL=X"},
    ("IND", "usdinr"): {"symbol": "INR=X"},
    ("TWN", "usdtwd"): {"symbol": "TWD=X"},
    ("SGP", "usdsgd"): {"symbol": "SGD=X"},
    ("HKG", "usdhkd"): {"symbol": "HKD=X"},
    ("ZAF", "usdzar"): {"symbol": "ZAR=X"},
}

# Worker /api/macro?source=fred&series_id=… (limit=1 latest only)
FRED_WORKER_LATEST: dict[str, dict] = {
    "bond_10y": {"id": "DGS10"},
    "bond_2y": {"id": "DGS2"},
    "bond_3m": {"id": "DGS3MO"},
    "tips_10y": {"id": "DFII10"},
    "effr": {"id": "EFFR"},
    "sofr": {"id": "SOFR"},
    "hy_oas": {"id": "BAMLH0A0HYM2"},
    "bei_10y": {"id": "T10YIE"},
    "spread_10y3m": {"id": "T10Y3M"},
    "fed_total_assets": {"id": "WALCL", "scale": 1e-6},  # mn → tn
    "tga": {"id": "WTREGEN", "scale": 1e-3},  # mn → bn
    "on_rrp": {"id": "RRPONTSYD", "scale": 1e-3},
    "fed_mbs": {"id": "WSHOMCB", "scale": 1e-3},
    "unemployment": {"id": "UNRATE"},
    "sahm": {"id": "SAHMREALTIME"},
    "initial_claims": {"id": "ICSA", "scale": 1e-3},
    "cpi_yoy": {"id": "CPIAUCSL", "note": "index — YoY needs history; latest index only skipped"},
}

# Prefer these for FRED worker when we can compute nothing else
FRED_WORKER_OK = {
    "bond_10y",
    "bond_2y",
    "bond_3m",
    "tips_10y",
    "effr",
    "sofr",
    "hy_oas",
    "bei_10y",
    "spread_10y3m",
    "fed_total_assets",
    "tga",
    "on_rrp",
    "fed_mbs",
    "unemployment",
    "sahm",
    "initial_claims",
}

BOK_NAME_MAP: dict[str, str] = {
    "한국은행 기준금리": "bok_base_rate",
    "원/달러 환율(종가)": "usdkrw",
    "코스피지수": "kospi",
    "코스닥지수": "kosdaq",
}

WORKER_BASE = "https://global-trade-dashboard.sunbin-info-kim.workers.dev"
