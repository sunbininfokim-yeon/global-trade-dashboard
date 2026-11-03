import pandas as pd

from biomass import pellet_trade as pt


def _rows():
    rows = []
    for y, kr, jp in (("2023", 3.7e9, 5.8e9), ("2024", 4.0e9, 6.4e9)):
        rows += [{"side": "M", "freq": "A", "period": y, "reporter": "410", "partner": "0",
                  "net_kg": kr, "value_usd": kr / 1000 * 130},
                 {"side": "M", "freq": "A", "period": y, "reporter": "392", "partner": "0",
                  "net_kg": jp, "value_usd": jp / 1000 * 200}]
    for i in range(24):
        p = (pd.Timestamp("2024-07-01") + pd.DateOffset(months=i)).strftime("%Y%m")
        kr = 3.0e8 if i < 12 else 3.3e8
        rows += [{"side": "M", "freq": "M", "period": p, "reporter": "410", "partner": "0",
                  "net_kg": kr, "value_usd": kr / 1000 * 140},
                 {"side": "M", "freq": "M", "period": p, "reporter": "410", "partner": "704",
                  "net_kg": kr * 0.5, "value_usd": 1},
                 {"side": "M", "freq": "M", "period": p, "reporter": "410", "partner": "643",
                  "net_kg": kr * 0.2, "value_usd": 1}]
    # An exporter that left the weight blank in its latest year.
    rows += [{"side": "X", "freq": "A", "period": "2024", "reporter": "842", "partner": "0",
              "net_kg": 1.0e10, "value_usd": 1.86e9},
             {"side": "X", "freq": "A", "period": "2023", "reporter": "842", "partner": "0",
              "net_kg": 9.5e9, "value_usd": 1.7e9},
             {"side": "X", "freq": "A", "period": "2025", "reporter": "458", "partner": "0",
              "net_kg": None, "value_usd": 1.5e8},
             {"side": "X", "freq": "A", "period": "2024", "reporter": "458", "partner": "0",
              "net_kg": 1.13e9, "value_usd": 1.5e8}]
    return pd.DataFrame(rows).astype(str).replace("None", "")


def test_summary_imports_and_exporters():
    out = pt.summary(_rows())
    a = {r["year"]: r for r in out["annual_imports"]}
    assert a[2024]["한국"]["kt"] == 4000 and a[2024]["한국"]["price_usd_t"] == 130.0
    kr = out["recent"]["한국"]
    assert kr["last_month"] == "2026-06" and kr["total_kt"] == 3960
    assert kr["yoy_pct"] == 10.0 and kr["price_usd_t"] == 140.0
    assert [s["country"] for s in kr["top_suppliers"]] == ["베트남", "러시아"]
    assert kr["top_suppliers"][0]["share_pct"] == 50.0
    assert out["recent"]["일본"] is None
    ex = {e["country"]: e for e in out["exporters"]}
    assert ex["미국"]["kt"] == 10000 and ex["미국"]["yoy_pct"] == 5.3
    # A blank weight is not zero tonnes: Malaysia falls back to its last weighed year.
    assert ex["말레이시아"]["year"] == 2024 and ex["말레이시아"]["kt"] == 1130
    assert out["exporters"][0]["country"] == "미국"
