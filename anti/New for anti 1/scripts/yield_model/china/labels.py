"""
Target series for the China models.

The six guides in Regions/중국 all say the same thing about labels, in almost
the same words: do not believe the National Bureau of Statistics. 동북3성 §1
calls the official series "훼손되어 있을 확률이 높습니다" and tells the model to
put USDA FAS at the top of the feature stack; 허난 §4 points out that Beijing
reported a 0.9% wheat loss in 2023 while importing record volumes of milling
wheat; 장강 §4 says to scrape USDA/ECMWF directly rather than trust 통계국.

That advice turns out to be forced rather than optional. data.stats.gov.cn
answers this machine with a 403 from its WAF (URL ACL, not a rate limit), so
province-level official yields are not obtainable at all. What is obtainable
is exactly what the guides asked for: USDA's own estimate of Chinese
production, published in the PSD database that underlies WASDE.

The cost is resolution. PSD is national; the guides are provincial. So a
regional weather signal has to survive dilution into a country aggregate, and
how much survives differs by crop:

    Henan + Huang-Huai-Hai   ~60% of national wheat
    Northeast 3 provinces    ~40% of soybeans, ~30% of corn
    Yangtze + South China    most of rice
    Shandong                 ~11% of vegetables, and the guide's real subject
                             (greenhouse area) is not in any yield series

Nothing here hides that. It is stated per config, carried into the published
forecast, and is the first thing the README says about the results.

Sources, all keyless:
  USDA PSD bulk CSV   grains/pulses and oilseeds, China 1960-2026
  FAOSTAT bulk CSV    vegetables, the one crop PSD does not carry
  UN Comtrade         via this project's own Cloudflare Worker proxy, which
                      holds the subscription key server-side
"""

import io
import json
import os
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

PSD_GRAINS = "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip"
PSD_OILSEEDS = "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip"
PSD_LIVESTOCK = "https://apps.fas.usda.gov/psdonline/downloads/psd_livestock_csv.zip"
FAOSTAT_BULK = ("https://bulks-faostat.fao.org/production/"
                "Production_Crops_Livestock_E_All_Data_(Normalized).zip")

# This project's Worker already proxies UN Comtrade with COMTRADE_API_KEY held
# as a Cloudflare secret (see _worker.js handleComtrade), so the Python side
# needs no credential of its own. The proxy slims each row to six fields;
# netWgt in kg is the one this module wants.
COMTRADE_PROXY = ("https://global-trade-dashboard.sunbin-info-kim.workers.dev"
                  "/api/comtrade")

CHINA_M49 = "156"
WORLD_M49 = "0"


def log(msg):
    print(f"[labels] {msg}", flush=True)


def _fetch(url, timeout=600):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cached_zip_member(url, member_suffix, cache_name, columns, filter_fn):
    """
    Download a bulk zip once, keep only the rows this project needs, cache the
    result as a small CSV.

    The upstream files are 50-500 MB and the China slice of them is a few
    thousand rows. Caching the slice rather than the archive means a rerun
    costs nothing and the repo never carries half a gigabyte of other
    countries' agriculture.
    """
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, cache_name)
    if os.path.exists(cached):
        return pd.read_csv(cached)

    log(f"downloading {url.rsplit('/', 1)[-1]}")
    blob = _fetch(url)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(member_suffix))
        with z.open(name) as fh:
            df = pd.read_csv(fh, usecols=columns, encoding="latin-1",
                             low_memory=False)

    df = filter_fn(df)
    df.to_csv(cached, index=False)
    log(f"  cached {len(df):,} rows -> {cache_name}")
    return df


# ---------------------------------------------------------------------------
# USDA PSD
# ---------------------------------------------------------------------------

PSD_COLUMNS = ["Commodity_Description", "Country_Name", "Market_Year",
               "Attribute_Description", "Unit_Description", "Value"]


def _psd_frame():
    def china_only(df):
        return df[df.Country_Name == "China"].drop(columns=["Country_Name"])

    grains = _cached_zip_member(PSD_GRAINS, "psd_grains_pulses.csv",
                                "psd_grains_china.csv", PSD_COLUMNS, china_only)
    oils = _cached_zip_member(PSD_OILSEEDS, "psd_oilseeds.csv",
                              "psd_oilseeds_china.csv", PSD_COLUMNS, china_only)
    return pd.concat([grains, oils], ignore_index=True)


def psd_series(commodity, attribute):
    """
    One PSD attribute for one commodity, as a year-indexed frame.

    PSD carries a single row per market year per attribute in the bulk file --
    the current vintage, not the history of revisions -- so no vintage
    selection is needed here. Market_Year is used as the season label, which
    for Chinese wheat and rice is the harvest year and for corn and soybeans
    the autumn of harvest.
    """
    df = _psd_frame()
    s = df[(df.Commodity_Description == commodity)
           & (df.Attribute_Description == attribute)]
    if s.empty:
        raise KeyError(f"PSD has no {commodity} / {attribute} for China")

    out = (s[["Market_Year", "Value", "Unit_Description"]]
           .rename(columns={"Market_Year": "year", "Value": "value"})
           .sort_values("year").reset_index(drop=True))
    return out


def psd_livestock_series(commodity, attribute):
    """
    One PSD livestock attribute for China, year-indexed.

    This is the hog inventory 거시_수입수요 §2A asks for and that China itself
    stopped publishing at useful frequency. USDA still estimates it, and the
    two series that matter are here:

      Animal Numbers, Swine / Sow Beginning Stocks
          The breeding herd. Feed demand follows it with a 10-12 month lag,
          because a sow bred this year is a finishing pig eating soybean meal
          the next -- which makes it a genuinely leading indicator rather than
          a contemporaneous one.

      Animal Numbers, Swine / Beginning Stocks
          Total herd. African swine fever cut this by roughly 40% across
          2019-20 and the collapse and rebuild are both visible.
    """
    def china_only(df):
        return df[df.Country_Name == "China"].drop(columns=["Country_Name"])

    df = _cached_zip_member(PSD_LIVESTOCK, "psd_livestock.csv",
                            "psd_livestock_china.csv", PSD_COLUMNS, china_only)

    s = df[(df.Commodity_Description == commodity)
           & (df.Attribute_Description == attribute)]
    if s.empty:
        raise KeyError(f"PSD livestock has no {commodity} / {attribute}")

    return (s[["Market_Year", "Value"]]
            .rename(columns={"Market_Year": "year", "Value": "value"})
            .sort_values("year").reset_index(drop=True))


def psd_yield_kg_ha(commodity):
    """PSD yield in kg/ha. The source unit is MT/HA."""
    s = psd_series(commodity, "Yield")
    unit = s.Unit_Description.iloc[0]
    if "MT/HA" not in unit:
        raise ValueError(f"unexpected PSD yield unit for {commodity}: {unit}")
    return pd.DataFrame({"year": s.year, "target": s.value * 1000.0})


def psd_area_1000ha(commodity):
    """PSD harvested area, 1000 HA."""
    s = psd_series(commodity, "Area Harvested")
    return pd.DataFrame({"year": s.year, "target": s.value})


# ---------------------------------------------------------------------------
# FAOSTAT -- vegetables only
# ---------------------------------------------------------------------------

FAO_COLUMNS = ["Area", "Item", "Element", "Year", "Unit", "Value"]


def faostat_yield_kg_ha(item="Vegetables Primary"):
    """
    FAOSTAT yield for one item, China mainland, kg/ha.

    PSD covers grains and oilseeds only, so Shandong's vegetables have no USDA
    series to fall back on. FAOSTAT's China figures are themselves compiled
    from the NBS returns the guides distrust -- which makes this the one label
    in the set that the guides' own advice cannot rescue. Said plainly in the
    config rather than buried here.
    """
    def veg_only(df):
        return df[(df.Area == "China, mainland")
                  & (df.Element.isin(["Yield", "Area harvested", "Production"]))
                  & (df.Item.isin(["Vegetables Primary"]))]

    df = _cached_zip_member(
        FAOSTAT_BULK, "(Normalized).csv", "faostat_china_veg.csv",
        FAO_COLUMNS, veg_only)

    s = df[(df.Item == item) & (df.Element == "Yield")]
    if s.empty:
        raise KeyError(f"FAOSTAT has no yield for {item}")
    unit = s.Unit.iloc[0]
    if unit not in ("kg/ha", "hg/ha"):
        raise ValueError(f"unexpected FAOSTAT unit: {unit}")
    scale = 1.0 if unit == "kg/ha" else 0.1

    return (pd.DataFrame({"year": s.Year.astype(int),
                          "target": s.Value.astype(float) * scale})
            .sort_values("year").reset_index(drop=True))


# ---------------------------------------------------------------------------
# UN Comtrade, through this project's Worker
# ---------------------------------------------------------------------------

def comtrade_imports_mt(hs_code, years):
    """
    China's imports of one HS commodity from the world, in tonnes.

    허난 §4 asks for exactly this series and for an unusual reason: when the
    weather indices spike but the official harvest barely moves, the import
    book is where the loss actually shows up. So this is not decoration on the
    import model -- it is the guide's proposed ground truth for the wheat
    model's bad years.

    Fetched through the Worker's /api/comtrade proxy, which holds the
    subscription key. Periods are batched because Comtrade accepts a
    comma-separated list and each call is cached in KV by the full key.
    """
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"comtrade_{hs_code}.csv")
    if os.path.exists(cached):
        have = pd.read_csv(cached)
        missing = sorted(set(years) - set(have.year))
        if not missing:
            return have
    else:
        have = pd.DataFrame(columns=["year", "import_mt"])
        missing = sorted(years)

    rows = []
    for i in range(0, len(missing), 10):
        chunk = missing[i:i + 10]
        url = (f"{COMTRADE_PROXY}?hs={hs_code}&reporters={CHINA_M49}"
               f"&partners={WORLD_M49}&freq=A"
               f"&period={','.join(str(y) for y in chunk)}")
        log(f"  comtrade {hs_code}: {chunk[0]}-{chunk[-1]}")
        try:
            body = json.loads(_fetch(url, timeout=120))
        except Exception as e:  # noqa: BLE001 - a trade gap must not stop a run
            log(f"  comtrade {hs_code} {chunk[0]}-{chunk[-1]} failed: {e}")
            continue
        for row in body.get("data", []):
            if row.get("flowCode") != "M":
                continue
            wgt = row.get("netWgt")
            if not wgt:
                continue
            rows.append({"year": int(row["period"]),
                         "import_mt": float(wgt) / 1000.0})

    if rows:
        have = (pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
                .drop_duplicates(subset=["year"], keep="last")
                .sort_values("year").reset_index(drop=True))
        have.to_csv(cached, index=False)
    return have
