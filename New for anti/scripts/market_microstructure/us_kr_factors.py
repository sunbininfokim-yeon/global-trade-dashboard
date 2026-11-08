"""Independent, frozen input bundles for the pre-open display."""

import gzip
import json
import math
import subprocess
import zlib
from pathlib import Path

import exchange_calendars as xc
import pandas as pd
from scipy.special import expit

from option_direction_model import calendar, digest, option_features, probability, unique, window
from research_direction_diagnostics import ReviewedCalendar
from research_option_dynamics import logit
from research_us_lag1_direction import SYMBOLS, previous_us_session, us_vector

DEFAULT_MODEL = Path(__file__).with_name("models") / "shadow" / "us_kr_factors_20261108_v1.json"
VERSION = "us-kr-factors-v1"
TICKERS = ("KOSPI", "005930", "000660")
HEADS = {"opening_up": "open", "closing_up": "close"}
CONFIG = {
    "options": ("KOSPI200 외국인 옵션 수급", ("call_rank60", "put_rank60", "call_mean5", "put_mean5"), TICKERS),
    "foreign_stock_flow": ("개별 주식 외국인 현물 수급", ("foreign_net_share1", "foreign_net_share_mean5"), TICKERS[1:]),
    "us_price": ("미국 주가와 VIX 포함 전망",
                 ("QQQ_return1", "SPY_return1", "VIX_return1", "log_VIX", "SMH_return1", "MU_return1",
                  "NVDA_return1", "AMD_return1"), TICKERS),
}
FLOW_PATH = Path("data/normalized/krx_12009_stock_investor")


class FactorUSCalendar:
    def __init__(self):
        self.base = xc.get_calendar("XNYS", start="2018", end="2027-12-31")
        # NYSE closure for Jimmy Carter's national day of mourning.
        self.sessions = self.base.sessions[self.base.sessions.strftime("%Y-%m-%d") != "2025-01-09"]

    def previous_session(self, day):
        return self.sessions[self.sessions.get_loc(day)-1]

    def session_close(self, day):
        return self.base.session_close(day)


def calendars():
    return ReviewedCalendar(calendar()), FactorUSCalendar()


def flow_share(row):
    buy = row.get("market_total_buy_krw")
    net = row.get("foreign_net_krw")
    other = row.get("other_foreign_net_krw")
    if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x)
           for x in (buy, net, other)) or buy <= 0 or abs(net + other) > buy:
        return None
    total = row.get("foreign_total_net_krw")
    if total is not None and (not isinstance(total, (int, float)) or not math.isfinite(total)
                              or abs(total - net - other) > 1):
        return None
    return (net + other) / buy


def flow_index(rows, now=None):
    latest = {}
    for row in rows:
        ticker, day = row.get("ticker"), row.get("date")
        if ticker not in TICKERS[1:] or str(row.get("source_screen")) != "12009" or row.get("quality") != "observed":
            continue
        stamp = pd.Timestamp(row.get("collected_at"))
        if pd.isna(stamp) or stamp.tzinfo is None or (now is not None and stamp > now):
            continue
        key = (ticker, day)
        if key not in latest or latest[key][0] < stamp:
            latest[key] = stamp, flow_share(row)
        elif latest[key][0] == stamp and latest[key][1] != flow_share(row):
            latest[key] = stamp, None
    return {key: value for key, (_, value) in latest.items()}


def read_flow(krx_root, flow_root, days):
    if not krx_root and not flow_root:
        return []
    checkout = None
    if krx_root and Path(krx_root).parts[-3:] == ("data", "raw", "krx_15007"):
        checkout = Path(krx_root).parents[2]
    if flow_root is None and checkout is None:
        return []
    root = Path(flow_root) if flow_root else checkout / FLOW_PATH
    rows = []
    for month in sorted({day[:7] for day in days}):
        year, month_num = month.split("-")
        part = Path(f"year={year}") / f"month={month_num}" / "part.jsonl.gz"
        try:
            if (root / part).is_file():
                raw = (root / part).read_bytes()
            elif not flow_root and (checkout / ".git").exists():
                # The pre-open workflow already authenticates this sparse checkout.
                proc = subprocess.run(
                    ["git", "-C", str(checkout), "show", f"HEAD:{(FLOW_PATH / part).as_posix()}"],
                    capture_output=True, timeout=10, check=False,
                )
                if proc.returncode:
                    continue
                raw = proc.stdout
            else:
                continue
            rows.extend(row for line in gzip.decompress(raw).splitlines()
                        if (row := json.loads(line)).get("date") in days)
        except (OSError, ValueError, EOFError, zlib.error, subprocess.TimeoutExpired):
            continue
    return rows


def flow_vector(flows, kr, ticker, source):
    days = window(kr, source, 4)
    values = [flows.get((ticker, day)) for day in days]
    if len(values) != 5 or None in values:
        return None
    return [values[-1], sum(values) / 5]


def us_input(us_data, us_cal, target):
    try:
        values, meta = us_vector(us_data, us_cal, target)
    except (KeyError, ValueError):
        return None, None
    return (values[0] + values[1], meta["US_session"]) if values else (None, meta.get("day"))


def calibrated(model, x):
    c = model["calibration"]
    return float(expit(c["slope"] * logit(probability(model["fit"], x)) + c["intercept"]))


def scores_for(heads, x):
    result = {}
    for head in HEADS:
        p = calibrated(heads[head], x) if x is not None else None
        state = ("unavailable" if p is None else "recent_base_rate_only" if heads[head]["calibration"]["at_zero_slope"]
                 else "model_score_with_calibration")
        direction = (None if p is None else "REFERENCE_ONLY" if state == "recent_base_rate_only"
                     else "UP" if p > .5 else "DOWN" if p < .5 else "NEUTRAL")
        result[head] = {
            "probability": p, "up_probability": p, "down_probability": 1-p if p is not None else None,
            "score_0_100": p*100 if p is not None else None, "information_state": state, "direction": direction,
        }
    return result


def factor_payload(artifact, board, us_doc, *, target, now, replay=False, krx_root=None, flow_root=None, clock=None):
    if artifact.get("schema_version") != VERSION or set(artifact["factors"]) != set(CONFIG):
        raise ValueError("invalid factor model")
    kr, us = calendars()
    source = window(kr, target, 1)[0]
    us_day, us_close, cutoff = previous_us_session(us, target)
    if (target <= artifact["trained_through"] or now < pd.Timestamp(artifact["created_at"])
            or now < max(calendar().session_close(source), pd.Timestamp(us_close))
            or (not replay and now > pd.Timestamp(cutoff))):
        return unavailable_payload(artifact, "outside factor prediction window", source, us_day)
    try:
        options = option_features(board, kr).get(source)
    except (KeyError, ValueError, TypeError):
        options = None
    try:
        us_data = {symbol: unique(us_doc.get("symbols", {}).get(symbol, [])) for symbol in SYMBOLS}
        market, _ = us_input(us_data, us, target)
    except (KeyError, ValueError, TypeError):
        market = None
    days = window(kr, source, 4)
    try:
        flows = flow_index(read_flow(krx_root, flow_root, days), now)
    except (ValueError, TypeError, AttributeError):
        flows = {}
    finished = clock() if clock else now
    if not replay and finished > pd.Timestamp(cutoff):
        return unavailable_payload(artifact, "factor prediction cutoff passed", source, us_day)
    return render(artifact, {
        "options": {tk: options for tk in TICKERS},
        "us_price": {tk: market for tk in TICKERS},
        "foreign_stock_flow": {tk: flow_vector(flows, kr, tk, source) for tk in TICKERS[1:]},
    }, source, us_day, finished.isoformat())


def unavailable_payload(artifact, reason, source=None, us_day=None):
    return render(artifact, {}, source, us_day, None, reason)


def render(artifact, vectors, source, us_day, generated, reason=None):
    result = {}
    for group, (label, names, tickers) in CONFIG.items():
        factor = artifact["factors"][group]
        if digest({k: v for k, v in factor.items() if k != "model_id"}) != factor["model_id"]:
            raise ValueError(f"factor model integrity check failed: {group}")
        if factor["inputs"] != list(names) or factor["label_ko"] != label or set(factor["models"]) != set(tickers):
            raise ValueError(f"factor feature contract changed: {group}")
        cards = []
        for ticker in tickers:
            x = vectors.get(group, {}).get(ticker)
            cards.append({
                "ticker": ticker, "status": "available" if x is not None else "unavailable",
                "reason": None if x is not None else reason or ("missing exact-session KRX 12009" if group == "foreign_stock_flow" else "missing exact-session inputs"),
                "scores": scores_for(factor["models"][ticker], x),
            })
        n = sum(card["status"] == "available" for card in cards)
        expected = us_day if group == "us_price" else source
        result[group] = {
            "label_ko": label, "model_id": factor["model_id"], "inputs": list(names),
            "status": "available" if n == len(cards) else "partial" if n else "unavailable",
            "as_of": expected if n else None, "expected_source_date": expected, "generated_at": generated,
            "cards": cards, "validation": factor["validation"],
        }
    return result
