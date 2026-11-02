import pandas as pd

from france import eurostat
from france.collect import current_season
from france.regions import NORTH_WHEAT, WEST_MAIZE, _wheat


def test_region_yield_area_weighted_and_partial_years_dropped(tmp_path):
    rows = []
    for year, (ya, aa, yb, ab) in {2020: (7.0, 100, 9.0, 300), 2021: (6.0, 100, None, None)}.items():
        rows += [("C1111", eurostat.YIELD, "FRB0", year, ya), ("C1111", eurostat.AREA, "FRB0", year, aa)]
        if yb:
            rows += [("C1111", eurostat.YIELD, "FRE2", year, yb), ("C1111", eurostat.AREA, "FRE2", year, ab)]
    p = tmp_path / "e.csv"
    pd.DataFrame(rows, columns=["crops", "strucpro", "geo", "year", "value"]).to_csv(p, index=False)
    out = eurostat.region_yield("winter_wheat", ["FRB0", "FRE2"], path=p)
    assert list(out.year) == [2020]          # 2021 lost three quarters of the area
    assert round(out.yield_kg_ha.iloc[0]) == 8500


def test_decode_json_stat():
    d = {"id": ["geo", "time"], "size": [2, 2],
         "dimension": {"geo": {"category": {"index": {"FRB0": 0, "FRE2": 1}}},
                       "time": {"category": {"index": {"2020": 0, "2021": 1}}}},
         "value": {"0": 7.1, "3": 8.2}}
    rows = eurostat._decode(d)
    assert {(r["geo"], r["time"], r["value"]) for r in rows} == {("FRB0", "2020", 7.1), ("FRE2", "2021", 8.2)}


def test_seasons_and_weights():
    from datetime import date
    assert current_season(NORTH_WHEAT, date(2026, 11, 2)) == 2027
    assert current_season(NORTH_WHEAT, date(2026, 6, 1)) == 2026
    assert current_season(WEST_MAIZE, date(2026, 11, 2)) == 2026
    for cfg in (NORTH_WHEAT, WEST_MAIZE):
        assert abs(sum(p["weight"] for p in cfg.points) - 1) < 1e-6


def test_wheat_features_wet_spring():
    d = pd.DataFrame({"date": pd.date_range("2015-09-01", "2016-08-31")})
    d["tmax"], d["tmin"], d["tmean"], d["et0"] = 20.0, 5.0, 12.0, 2.0
    d["precip"] = [5.0 if x.month in (5, 6) else 0.5 for x in d.date]
    f = _wheat(d, 2016)
    assert f["wet_days_may_jun"] == 61 and f["precip_may_jun"] == 305
    assert f["heat_days_28_jun"] == 0
