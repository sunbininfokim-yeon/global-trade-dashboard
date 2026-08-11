from pathlib import Path

import pandas as pd

from .collect import add_causal_anomalies
from .labels import parse_workbook


def test_official_workbook_columns():
    path = Path("/tmp/sagis_historic.xlsx")
    if not path.exists():
        return
    frame = parse_workbook(path)
    row = frame[frame.year == 2025].iloc[0]
    assert round(row.area_ha) == 2_596_700
    assert round(row.production_t) == 16_650_000
    assert 6_400 < row.yield_kg_ha < 6_420


def test_anomaly_excludes_current_year():
    years = list(range(2000, 2012))
    frame = pd.DataFrame({"year": years})
    for name in (
        "rain_planting_mm",
        "rain_critical_mm",
        "edd29_critical_c_days",
        "root_sm_critical",
        "vpd_critical_kpa",
    ):
        frame[name] = range(len(years))
    out = add_causal_anomalies(frame, window=20, min_prior=10)
    expected = (10 - 4.5) / pd.Series(range(10)).std(ddof=1)
    assert abs(out.loc[out.year == 2010, "rain_critical_mm_z"].iloc[0] - expected) < 1e-9


def test_forecast_contract():
    import json

    path = Path(__file__).resolve().parents[3] / "public" / "data" / "south_africa_yield_forecast.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    crop = payload["regions"]["commercial_maize_belt"]["crops"]["corn"]
    assert crop["range_68"][0] < crop["point"] < crop["range_68"][1]
    assert crop["skill"]["low_confidence"] is True
    assert crop["skill"]["model_warnings"]
    assert crop["production"]["range_68"][0] < crop["production"]["point"]
    assert crop["skill"]["challengers"]["boosted_tree"]["adopted"] is False
