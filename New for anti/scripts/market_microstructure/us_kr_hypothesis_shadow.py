"""Freeze and run independent KOSPI index and Samsung cash-flow comparisons."""

import argparse
import gzip
import json
import math
import os
from importlib.metadata import version
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import stdev
from tempfile import NamedTemporaryFile

import exchange_calendars as xc
import pandas as pd
from scipy.special import expit

from build_kospi200_price_panel import fetch_naver_chart
from option_direction_model import calendar, digest, fit, probability, read, unique, window
from research_direction_diagnostics import ReviewedCalendar
from research_option_dynamics import logit, sigmoid_calibration
from research_us_controlled_flows import ReviewedUSCalendar
from research_us_lag1_direction import SYMBOLS, previous_us_session

VERSION = "us-kr-hypothesis-shadow-v1"
ARCHIVE = Path("data/forecasts/us_kr_hypothesis_shadow")
SAMSUNG = "005930"
HEADS = {"opening": "open", "closing": "close"}
INDEX_SYMBOLS = {"SP500": "^GSPC", "NASDAQ100": "^NDX", "NASDAQSOX": "^SOX"}
INDEX_NAMES = list(INDEX_SYMBOLS)
US_FEATURES = ["QQQ", "SPY", "^VIX", "log_VIX", "SMH", "MU", "NVDA", "AMD"]
PRICE_FEATURES = ["momentum5", "volatility20", "return1", "gap1", "intraday1", "momentum20"]
FAMILIES = {
    "kospi_indices_two": ("KOSPI", INDEX_NAMES[:2]),
    "kospi_indices_three": ("KOSPI", INDEX_NAMES),
    "kospi_us8": ("KOSPI", US_FEATURES),
    "samsung_price_us": (SAMSUNG, PRICE_FEATURES + US_FEATURES),
    "samsung_price_us_foreign": (SAMSUNG, PRICE_FEATURES + US_FEATURES + ["foreign_net_share"]),
}
NUMERICAL_PACKAGES = ("exchange-calendars", "numpy", "pandas", "scipy", "scikit-learn")
IMPLEMENTATION = (
    "us_kr_hypothesis_shadow.py", "option_direction_model.py", "research_direction_diagnostics.py",
    "research_option_dynamics.py", "research_us_controlled_flows.py", "research_us_lag1_direction.py",
    "build_kospi200_price_panel.py",
)
PAIRS = [
    ("kospi_indices_three", "kospi_indices_two"),
    ("kospi_indices_three", "kospi_us8"),
    ("samsung_price_us_foreign", "samsung_price_us"),
]


def utc_now():
    return datetime.now(timezone.utc)


def stamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


def valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def level(row, key):
    value = row.get(key)
    if row.get("quality", "observed") != "observed" or not valid_number(value) or value <= 0:
        raise ValueError(f"missing observed {key}")
    return value


def calendars():
    return ReviewedCalendar(calendar()), ReviewedUSCalendar(
        xc.get_calendar("XNYS", start="2018-01-01", end="2027-12-31")
    )


def sessions(target, kr, us):
    target_date = pd.Timestamp(target)
    if target_date.strftime("%Y-%m-%d") != target or not kr.is_session(target):
        raise ValueError("target must be a reviewed KRX session (YYYY-MM-DD)")
    prior = window(kr, target, 1)
    if len(prior) != 2:
        raise ValueError("missing previous KRX session")
    prior_kr = prior[0]
    prior_us, closed, cutoff = previous_us_session(us, target)
    return {
        "target_date": target, "kr_date": prior_kr, "us_date": prior_us,
        "us_previous": us.previous_session(prior_us).strftime("%Y-%m-%d"),
        "us_close_utc": closed, "kr_close_utc": calendar().session_close(prior_kr).isoformat(),
        "cutoff_kst": cutoff,
    }


def samsung_flow_share(row):
    buy = level(row, "market_total_buy_krw")
    fields = [row.get("foreign_net_krw"), row.get("other_foreign_net_krw")]
    if not all(valid_number(v) for v in fields):
        raise ValueError("missing foreign or other-foreign net value")
    net = sum(fields)
    reported = row.get("foreign_total_net_krw")
    if reported is not None and (not valid_number(reported) or abs(net - reported) > 1):
        raise ValueError("foreign subtotal disagrees with KRX foreign total")
    if abs(net) > buy:
        raise ValueError("foreign net exceeds total market buy")
    return net / buy


def flow_rows(rows, now=None):
    newest = {}
    for row in rows:
        if row.get("ticker") != SAMSUNG or str(row.get("source_screen")) != "12009":
            continue
        if row.get("quality") != "observed":
            continue
        collected = stamp(row["collected_at"])
        if now is not None and collected > now:
            continue
        day = row["date"]
        previous = newest.get(day)
        if previous:
            old_time = stamp(previous["collected_at"])
            if collected < old_time:
                continue
            if collected == old_time and row != previous:
                raise ValueError(f"conflicting same-time KRX 12009 observations for {day}")
        newest[day] = row
    return newest


def index_snapshot(snapshot):
    return {
        "kr": {ticker: unique(rows) for ticker, rows in snapshot.get("kr", {}).items()},
        "us": {symbol: unique(rows) for symbol, rows in snapshot.get("us", {}).items()},
    }


def samsung_prices(data, kr, day):
    days = window(kr, day, 20)
    if len(days) != 21:
        raise ValueError("need 21 exact Samsung price sessions")
    bars = data["kr"][SAMSUNG]
    closes = [level(bars[d], "close") for d in days]
    op = level(bars[day], "open")
    returns = [b/a - 1 for a, b in zip(closes[:-1], closes[1:])]
    features = [closes[-1]/closes[-6]-1, stdev(returns), returns[-1],
                op/closes[-2]-1, closes[-1]/op-1, closes[-1]/closes[0]-1]
    return dict(zip(PRICE_FEATURES, features)), [bars[d] for d in days]


def vector(names, data, timing, kr):
    values, evidence = {}, {}
    if any(name in PRICE_FEATURES for name in names):
        values, evidence["samsung_prices"] = samsung_prices(data, kr, timing["kr_date"])
    for name in names:
        if name in values:
            continue
        if name == "foreign_net_share":
            row = data["flow"].get(timing["kr_date"])
            if row is None:
                raise ValueError(f"missing observed Samsung KRX 12009 for {timing['kr_date']}")
            values[name] = samsung_flow_share(row)
            evidence["samsung_flow"] = row
        else:
            symbol = "^VIX" if name == "log_VIX" else name
            by_date = data["us"][symbol]
            latest, earlier = by_date[timing["us_date"]], by_date[timing["us_previous"]]
            a, b = level(latest, "close"), level(earlier, "close")
            values[name] = math.log(a) if name == "log_VIX" else a/b-1
            evidence[symbol] = [earlier, latest]
    x = [values[k] for k in names]
    if not all(valid_number(v) for v in x):
        raise ValueError("nonfinite features")
    return x, evidence


def label(bars, timing, field):
    previous = level(bars[timing["kr_date"]], "close")
    actual = level(bars[timing["target_date"]], field)
    return int(actual > previous) if actual != previous else None


def family_groups():
    return {ticker: {name: features for name, (asset, features) in FAMILIES.items() if asset == ticker}
            for ticker in ("KOSPI", SAMSUNG)}


def implementation_hashes():
    return {name: digest(Path(__file__).with_name(name).read_text()) for name in IMPLEMENTATION}


def runtime_versions():
    return {name: version(name) for name in NUMERICAL_PACKAGES}


def freeze(snapshot, cutoff, now):
    kr, us = calendars()
    cutoff_info = sessions(cutoff, kr, us)
    if now < calendar().session_close(cutoff):
        raise ValueError("training cutoff outcome has not matured")
    data = index_snapshot(snapshot)
    data["flow"] = flow_rows(snapshot.get("samsung_flow", []))
    if any(stamp(row["collected_at"]) > now for row in data["flow"].values()):
        raise ValueError("training cash-flow observations postdate the freeze")
    start = (pd.Timestamp(cutoff) + pd.Timedelta(days=1) - pd.DateOffset(months=6)).strftime("%Y-%m-%d")
    models = {}
    for ticker, families in family_groups().items():
        union = list(dict.fromkeys(k for keys in families.values() for k in keys))
        observations = []
        dates = sorted(d for d in data["kr"][ticker] if "2019-01-01" <= d <= cutoff and kr.is_session(d))
        for day in dates:
            timing = sessions(day, kr, us)
            try:
                x, _ = vector(union, data, timing, kr)
                labels = {name: label(data["kr"][ticker], timing, field) for name, field in HEADS.items()}
            except (KeyError, ValueError):
                continue
            observations.append((day, timing["kr_date"], dict(zip(union, x)), labels))
        for name, names in families.items():
            heads = {}
            for head in HEADS:
                training, calibration = [], []
                for day, source, values, labels in observations:
                    y = labels[head]
                    if y is None:
                        continue
                    row = {"x": [values[k] for k in names], "y": y, "target": day}
                    if day < start:
                        training.append(row)
                    elif source >= start:
                        calibration.append(row)
                if len(calibration) < 60 or len({r["y"] for r in calibration}) != 2:
                    raise ValueError(f"{name}/{head}: insufficient independent calibration")
                model = fit(training, "x")
                cal = sigmoid_calibration(
                    [logit(probability(model, r["x"])) for r in calibration], [r["y"] for r in calibration]
                )
                heads[head] = {"model": model, "calibration": cal, "n_train": len(training),
                               "n_calibration": len(calibration), "outcomes_through": calibration[-1]["target"]}
            models[name] = {"ticker": ticker, "features": names, "heads": heads}
    artifact = {"schema_version": VERSION, "created_at": now.isoformat(), "training_cutoff": cutoff,
                "training_input_sha256": digest(snapshot), "models": models,
                "implementation_sha256": implementation_hashes(), "runtime_versions": runtime_versions(),
                "training_source_sessions": cutoff_info}
    return {**artifact, "model_id": digest(artifact)}


def validate_model(model):
    if model.get("schema_version") != VERSION or model["model_id"] != digest(
        {k: v for k, v in model.items() if k != "model_id"}
    ):
        raise ValueError("invalid frozen shadow model")
    if model["implementation_sha256"] != implementation_hashes():
        raise ValueError("shadow implementation changed; freeze a new model")
    if model["runtime_versions"] != runtime_versions():
        raise ValueError("shadow numerical runtime differs from the frozen model")
    actual = {k: (v["ticker"], v["features"]) for k, v in model["models"].items()}
    if actual != FAMILIES:
        raise ValueError("shadow feature contract changed")


def predict(model, snapshot, target, now, replay=False):
    validate_model(model)
    kr, us = calendars()
    timing = sessions(target, kr, us)
    if target <= model["training_cutoff"]:
        raise ValueError("target overlaps training outcomes")
    if now < stamp(model["created_at"]):
        raise ValueError("forecast predates model freeze")
    if now < max(stamp(timing["kr_close_utc"]), stamp(timing["us_close_utc"])):
        raise ValueError("required source session is still open")
    if not replay:
        collected = stamp(snapshot["collected_at"])
        if not max(stamp(timing["us_close_utc"]), stamp(timing["kr_close_utc"])) <= collected <= now:
            raise ValueError("snapshot was not captured after required closes and before generation")
        if now > stamp(timing["cutoff_kst"]):
            raise ValueError("08:30 KST cutoff passed")
    data = index_snapshot(snapshot)
    forecasts, missing = {}, {}
    try:
        data["flow"] = flow_rows(
            [r for r in snapshot.get("samsung_flow", []) if r.get("date") == timing["kr_date"]], now
        )
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        data["flow"] = {}
        missing["samsung_price_us_foreign"] = f"invalid exact KRX 12009 observation: {exc}"
    for name, (_, keys) in FAMILIES.items():
        family = model["models"][name]
        try:
            x, evidence = vector(keys, data, timing, kr)
        except (KeyError, ValueError) as exc:
            missing.setdefault(name, str(exc))
            continue
        scores = {}
        for head, row in family["heads"].items():
            cal = row["calibration"]
            p = float(expit(cal["slope"]*logit(probability(row["model"], x))+cal["intercept"]))
            scores[head] = {"up_probability": p, "down_probability": 1-p,
                            "state": "reference_only" if cal["at_zero_slope"] else "model_probability"}
        forecasts[name] = {
            "schema_version": VERSION, "status": "replay" if replay else "first_preopen_shadow",
            "family": name, "ticker": family["ticker"], "model_id": model["model_id"],
            "generated_at": now.isoformat(), "collected_at": snapshot.get("collected_at"),
            **timing, "input_sha256": digest(evidence), "scores": scores,
        }
    return forecasts, missing


def write_once(path, document):
    """Publish a complete JSON atomically, preserving any first writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        try:
            json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            try:
                os.link(tmp, path)
            except FileExistsError:
                return False
            return True
        finally:
            tmp.unlink()


def first_path(root, record):
    return root / record["target_date"] / record["model_id"] / record["family"] / "first.json"


def live_snapshot(target, flow_root):
    import yfinance as yf

    kr, us = calendars()
    timing = sessions(target, kr, us)
    current = utc_now()
    if not max(stamp(timing["kr_close_utc"]), stamp(timing["us_close_utc"])) <= current <= stamp(timing["cutoff_kst"]):
        raise ValueError("live collection is outside the preopen window")
    aliases = {**INDEX_SYMBOLS, **{s: s for s in SYMBOLS}}
    us_rows, errors = {}, {}
    end = (pd.Timestamp(timing["us_date"]) + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        data = yf.download(list(aliases.values()), start=timing["us_previous"], end=end,
                           auto_adjust=True, group_by="ticker", threads=False, progress=False, timeout=10)
        for key, symbol in aliases.items():
            if symbol in data.columns.get_level_values(0):
                series = data[symbol]["Close"].dropna()
                us_rows[key] = [{"date": t.strftime("%Y-%m-%d"), "close": float(value)}
                                for t, value in series.items()]
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        errors["us"] = str(exc)
    days = window(kr, timing["kr_date"], 20)
    kr_rows = {}
    try:
        bars = fetch_naver_chart(SAMSUNG, days[0].replace("-", ""), days[-1].replace("-", ""))
        kr_rows[SAMSUNG] = [{"date": d, **bars[d]} for d in days if d in bars]
    except (OSError, ValueError, IndexError) as exc:
        errors[SAMSUNG] = str(exc)
    flows = []
    if flow_root is None:
        errors["12009"] = "no local KRX 12009 root supplied"
    else:
        year, month, _ = timing["kr_date"].split("-")
        part = flow_root / f"year={year}" / f"month={month}" / "part.jsonl.gz"
        try:
            with gzip.open(part, "rt", encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    if row.get("date") == timing["kr_date"] and row.get("ticker") == SAMSUNG:
                        flows.append(row)
        except (OSError, ValueError) as exc:
            errors["12009"] = str(exc)
    return {"kr": kr_rows, "us": us_rows, "samsung_flow": flows,
            "collected_at": utc_now().isoformat(), "collection_errors": errors}


def metrics(rows):
    n_up = sum(y for y, _ in rows)
    n_down = len(rows)-n_up
    hit_up = sum(y == 1 and p > .5 for y, p in rows)
    hit_down = sum(y == 0 and p < .5 for y, p in rows)
    up = hit_up/n_up if n_up else None
    down = hit_down/n_down if n_down else None
    forecast_up = sum(p > .5 for _, p in rows)
    forecast_down = sum(p < .5 for _, p in rows)
    return {"n": len(rows), "actual_up": n_up, "actual_down": n_down, "hit_up": hit_up, "hit_down": hit_down,
            "forecast_up": forecast_up, "forecast_down": forecast_down, "neutral": len(rows)-forecast_up-forecast_down,
            "up_precision": hit_up/forecast_up if forecast_up else None,
            "down_precision": hit_down/forecast_down if forecast_down else None, "up_recall": up, "down_recall": down,
            "balanced_recall": (up+down)/2 if up is not None and down is not None else None,
            "brier": sum((p-y)**2 for y, p in rows)/len(rows) if rows else None}


def score(root, model, snapshot, now):
    validate_model(model)
    kr, us = calendars()
    collected = stamp(snapshot["collected_at"])
    if collected > now:
        raise ValueError("outcome snapshot postdates evaluation")
    bars = {ticker: unique(rows) for ticker, rows in snapshot["kr"].items()}
    records = {}
    for path in sorted(root.glob(f"*/{model['model_id']}/*/first.json")):
        row = read(path)
        family, day = row["family"], row["target_date"]
        if family not in FAMILIES or row["ticker"] != FAMILIES[family][0]:
            raise ValueError(f"invalid archived family: {path}")
        timing = sessions(day, kr, us)
        published = stamp(row["generated_at"])
        if (row["status"] != "first_preopen_shadow" or row["model_id"] != model["model_id"]
                or row["schema_version"] != VERSION or path != first_path(root, row)
                or day <= model["training_cutoff"] or published < stamp(model["created_at"])
                or not max(stamp(timing["kr_close_utc"]), stamp(timing["us_close_utc"])) <= stamp(row["collected_at"]) <= published
                or published > stamp(timing["cutoff_kst"]) or any(row[k] != v for k, v in timing.items())):
            raise ValueError(f"invalid archived first forecast: {path}")
        if collected >= calendar().session_close(day):
            records.setdefault(family, {})[day] = row
    results = {}
    for candidate, base in PAIRS:
        candidates, baselines = records.get(candidate, {}), records.get(base, {})
        dates = sorted(candidates.keys() & baselines.keys())
        results[candidate + "_vs_" + base] = {}
        for head, field in HEADS.items():
            tested, reference = [], []
            for day in dates:
                c, b = candidates[day], baselines[day]
                try:
                    y = label(bars[c["ticker"]], c, field)
                except (KeyError, ValueError):
                    continue
                if y is None:
                    continue
                for record, target_rows in ((c, tested), (b, reference)):
                    p = record["scores"][head]["up_probability"]
                    if not valid_number(p) or not 0 <= p <= 1:
                        raise ValueError("invalid archived forecast probability")
                    target_rows.append((y,p))
            a, b = metrics(tested), metrics(reference)
            results[candidate + "_vs_" + base][head] = {
                "candidate": a, "baseline": b, "matched_dates": len(dates),
                "brier_difference": a["brier"]-b["brier"] if tested else None,
            }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "predict", "score"))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--cutoff")
    parser.add_argument("--target")
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--flow-root", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        if not args.snapshot or not args.cutoff or args.live or args.replay:
            parser.error("freeze requires --snapshot and --cutoff")
        if args.model.exists():
            parser.error("freeze requires a new --model path")
        model = freeze(read(args.snapshot), args.cutoff, utc_now())
        if not write_once(args.model, model):
            parser.error("model path already exists")
        print(json.dumps({"model_id": model["model_id"], "training_cutoff": model["training_cutoff"]}))
        return 0
    model = read(args.model)
    if args.command == "score":
        if not args.snapshot or args.live or args.replay:
            parser.error("score requires an outcome --snapshot")
        print(json.dumps(score(args.archive, model, read(args.snapshot), utc_now()), indent=2))
        return 0
    if not args.target or bool(args.snapshot) == args.live or (args.live and args.replay):
        parser.error("predict requires --target and exactly one of --snapshot or --live; replay uses a snapshot")
    validate_model(model)
    snapshot = live_snapshot(args.target, args.flow_root) if args.live else read(args.snapshot)
    forecasts, missing = predict(model, snapshot, args.target, utc_now(), replay=args.replay)
    if not args.replay:
        for family, record in forecasts.items():
            path = first_path(args.archive, record)
            if not write_once(path, record):
                forecasts[family] = read(path)
    print(json.dumps({"forecasts": forecasts, "missing": missing,
                      "collection_errors": snapshot.get("collection_errors", {})}, indent=2))
    return 0 if forecasts else 2


if __name__ == "__main__":
    raise SystemExit(main())
