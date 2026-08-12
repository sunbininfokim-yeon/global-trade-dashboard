"""Join Ethiopian coffee climate, yield, production and structural lags."""

from pathlib import Path

import pandas as pd

from .climate import collect_seasonal
from .labels import load_labels
from .regions import BELT_KEY

HERE = Path(__file__).resolve().parent


def build(refresh: bool = False, end_year: int = None) -> pd.DataFrame:
    labels = load_labels(refresh=refresh)
    frame = collect_seasonal(end_year=end_year, refresh=refresh).merge(labels, on="year", how="left")
    by_year = labels.set_index("year")
    # Forecast rows have no current FAOSTAT target, but their two-year lags are
    # known. Fill those causal structural features explicitly from Y-2.
    for index, row in frame.iterrows():
        prior_year = int(row.year) - 2
        if prior_year not in by_year.index:
            continue
        if pd.isna(row.get("yield_lag2_kg_ha")):
            frame.loc[index, "yield_lag2_kg_ha"] = by_year.loc[prior_year, "yield_kg_ha"]
        if pd.isna(row.get("area_growth_lag2")):
            frame.loc[index, "area_growth_lag2"] = by_year.loc[prior_year, "area_growth"]
    frame["target_status"] = frame.target_status.fillna("missing")
    (HERE / "training").mkdir(parents=True, exist_ok=True)
    frame.to_csv(HERE / "training" / f"{BELT_KEY}.csv", index=False)
    return frame


if __name__ == "__main__":
    print(build().tail(12).to_string(index=False))
