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
    ("CHE", "eurchf"): {"symbol": "EURCHF=X"},
    ("BRA", "usdbrl"): {"symbol": "BRL=X"},
    ("IND", "usdinr"): {"symbol": "INR=X"},
    ("TWN", "usdtwd"): {"symbol": "TWD=X"},
    ("SGP", "usdsgd"): {"symbol": "SGD=X"},
    ("HKG", "usdhkd"): {"symbol": "HKD=X"},
    ("ZAF", "usdzar"): {"symbol": "ZAR=X"},
    # stock indices (Yahoo chart, monthly closes; symbols checked 2026-09-29 -- HSTECH and an S-REIT
    # index have no usable Yahoo history, so those cards stay as they are)
    ("ZAF", "jse_top40"): {"symbol": "^J200.JO"},
    ("HKG", "hsi"): {"symbol": "^HSI"},
    ("HKG", "hscei"): {"symbol": "^HSCE"},
    ("SGP", "sti"): {"symbol": "^STI"},
    ("TWN", "taiex"): {"symbol": "^TWII"},
    ("CHE", "smi"): {"symbol": "^SSMI"},
    ("AUS", "asx200"): {"symbol": "^AXJO"},
    ("AUS", "asx_vix"): {"symbol": "^AXVI"},
    ("IDN", "usdidr"): {"symbol": "IDR=X"},
    ("IDN", "jci"): {"symbol": "^JKSE"},
    # 2026-09-30: indices / crosses for the countries wired by wire_world_public_series.py (CSI 300 and
    # VN-Index have a single Yahoo point, Euro Stoxx Banks no symbol -- left out)
    ("CAN", "tsx"): {"symbol": "^GSPTSE"},
    ("GBR", "eurgbp"): {"symbol": "EURGBP=X"},
    ("GBR", "ftse250"): {"symbol": "^FTMC"},
    ("EMU", "eurjpy"): {"symbol": "EURJPY=X"},
    ("EMU", "eurgbp"): {"symbol": "EURGBP=X"},
    ("EMU", "cac40"): {"symbol": "^FCHI"},
    ("BRA", "ibovespa"): {"symbol": "^BVSP"},
    ("IND", "nifty50"): {"symbol": "^NSEI"},
    ("IND", "sensex"): {"symbol": "^BSESN"},
    ("ISR", "usdils"): {"symbol": "ILS=X"},
    ("ISR", "ta125"): {"symbol": "^TA125.TA"},
    ("CHN", "usdcny"): {"symbol": "CNY=X"},
    ("CHN", "sse_composite"): {"symbol": "000001.SS"},
    ("CHN", "hscei"): {"symbol": "^HSCE"},
    ("KAZ", "usdkzt"): {"symbol": "KZT=X"},
    ("VNM", "usdvnd"): {"symbol": "VND=X"},
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
    # RRPONTSYD is the ON RRP *award rate* (percent) -- fine as a level around
    # 4-5, catastrophic if pinned onto a balance series scaled in bn USD. The
    # August pin did exactly that: on_rrp's fixture history ran ~150-170bn,
    # then the live overlay wrote 0.00125 (= 4.25% * 1e-3) over the last point,
    # reading as the balance collapsing to zero. RRPONTTLD is the actual daily
    # ON RRP balance -- and FRED already reports it in bn USD, not millions,
    # so it takes no rescaling (a second 1e-3 here would repeat the same class
    # of bug on the fixed series). The real balance genuinely is near zero as
    # of 2026-08 ($0.45bn on 08-13) -- usage has drained the way it did in
    # 2023-24, this indicator just wasn't reading the number that shows it.
    "on_rrp": {"id": "RRPONTTLD"},
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
