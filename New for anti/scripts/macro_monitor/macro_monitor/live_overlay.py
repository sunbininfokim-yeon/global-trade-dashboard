"""Fetch live series and overlay onto a macro_monitor universe dict."""

from __future__ import annotations

import json
import math
import subprocess
import time
import urllib.parse
from datetime import date, datetime
from typing import Any

from .live_catalog import (
    BOK_NAME_MAP,
    FRED_WORKER_LATEST,
    FRED_WORKER_OK,
    WORKER_BASE,
    YAHOO,
)
from .series import format_value, month_ends


def _curl(url: str, timeout: int = 25) -> bytes:
    proc = subprocess.run(
        ["curl", "-sS", "-L", "--http1.1", "-m", str(timeout), "-A", "macro-monitor/0.23", url],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:180]
        raise RuntimeError(f"curl rc={proc.returncode}: {err}")
    return proc.stdout


def fetch_yahoo_monthly(symbol: str, years: int = 11) -> list[tuple[date, float]]:
    return fetch_yahoo(symbol, years)[0]


def fetch_yahoo(symbol: str, years: int = 11) -> tuple[list[tuple[date, float]], date | None]:
    """Monthly closes plus the date of the newest price. Yahoo stamps a monthly bar with the first of
    its month, and the current month's bar holds the latest price, so the bar's own date says nothing
    about when that price was struck; `meta.regularMarketTime` does."""
    period2 = int(time.time())
    period1 = period2 - years * 365 * 24 * 3600
    enc = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
        f"?period1={period1}&period2={period2}&interval=1mo"
    )
    doc = json.loads(_curl(url).decode("utf-8"))
    result = ((doc.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return [], None
    ts = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
    out: list[tuple[date, float]] = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        try:
            d = datetime.utcfromtimestamp(int(t)).date()
            v = float(c)
        except (TypeError, ValueError, OSError):
            continue
        if math.isfinite(v):
            out.append((d, v))
    out.sort(key=lambda x: x[0])
    last_obs = None
    try:
        last_obs = datetime.utcfromtimestamp(int((result.get("meta") or {}).get("regularMarketTime"))).date()
    except (TypeError, ValueError, OSError):
        pass
    return out, last_obs


def fetch_fred_worker_latest(series_id: str) -> tuple[date, float]:
    url = f"{WORKER_BASE}/api/macro?source=fred&series_id={urllib.parse.quote(series_id)}"
    doc = json.loads(_curl(url).decode("utf-8"))
    if isinstance(doc, dict) and doc.get("ok") and "body" in doc:
        doc = doc["body"]
    obs = (doc.get("observations") or [None])[0]
    if not obs or obs.get("value") in (None, "."):
        raise RuntimeError(f"no observation for {series_id}")
    return date.fromisoformat(obs["date"][:10]), float(obs["value"])


def fetch_bok_worker() -> dict[str, tuple[str, float]]:
    doc = json.loads(_curl(f"{WORKER_BASE}/api/macro?source=bok").decode("utf-8"))
    if isinstance(doc, dict) and doc.get("ok") and "body" in doc:
        doc = doc["body"]
    rows = (doc.get("KeyStatisticList") or {}).get("row") or []
    out: dict[str, tuple[str, float]] = {}
    for r in rows:
        name = r.get("KEYSTAT_NAME")
        try:
            val = float(str(r.get("DATA_VALUE")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        out[name] = (str(r.get("CYCLE") or ""), val)
    return out


def _cycle_to_date(cycle: str, today: date) -> date:
    """The observation date of an ECOS KeyStatisticList row from its CYCLE ("20260924" a day, "202608"
    a month, "2026Q2" a quarter), never later than `today`. Unreadable -> today (the run date, an
    upper bound that claims nothing fresher)."""
    import calendar

    c = (cycle or "").strip()
    try:
        if len(c) == 8 and c.isdigit():
            d = date(int(c[:4]), int(c[4:6]), int(c[6:]))
        elif len(c) == 6 and c.isdigit():
            d = date(int(c[:4]), int(c[4:]), calendar.monthrange(int(c[:4]), int(c[4:]))[1])
        elif len(c) == 6 and c[4] == "Q":
            q = int(c[5]) * 3
            d = date(int(c[:4]), q, calendar.monthrange(int(c[:4]), q)[1])
        else:
            return today
    except ValueError:
        return today
    return min(d, today)


def _to_month_map(points: list[tuple[date, float]]) -> dict[str, float]:
    import calendar

    by_ym: dict[str, tuple[date, float]] = {}
    for d, v in points:
        ym = f"{d.year:04d}-{d.month:02d}"
        if ym not in by_ym or d >= by_ym[ym][0]:
            by_ym[ym] = (d, v)
    out: dict[str, float] = {}
    for _ym, (d, v) in by_ym.items():
        me = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        out[me.isoformat()] = v
    return out


def _overlay_history(ind: dict[str, Any], dates: list[str], month_map: dict[str, float], source: str,
                     last_obs: date | None = None) -> bool:
    """`last_obs` is the date of the newest observation. It is what the card is "as of", and the
    history's last point carries it when that month is still running (never a month-end that has not
    happened). A grid month with no observation after the last real one stays empty: carrying the last
    value forward made a stale series read as this month's."""
    vals: list[float | None] = []
    for ds in dates:
        if ds in month_map:
            vals.append(round(month_map[ds], 6))
            continue
        ym = ds[:7]
        hit = next((v for k, v in month_map.items() if k.startswith(ym)), None)
        vals.append(round(hit, 6) if hit is not None else None)
    if sum(v is not None for v in vals) < max(12, len(dates) // 5):
        return False
    last = None
    filled: list[float | None] = []
    for v in vals:
        if v is not None:
            last = v
        filled.append(last)
    last_real = max((i for i, v in enumerate(vals) if v is not None), default=None)
    if filled[-1] is None or last_real is None:
        return False
    for i in range(last_real + 1, len(filled)):
        filled[i] = None                                   # no observation for these months
    ind["value"] = filled[last_real]
    fmt = ind.get("format") or "number1"
    if fmt not in ("rating", "fx_watch", "flag", "fedwatch"):
        ind["display"] = format_value(filled[last_real], fmt)
    for y in (5, 10):
        key = f"{y}y"
        if key not in ind.get("history", {}):
            continue
        n = y * 12
        slice_v = filled[-n:]
        ind["history"][key]["values"] = slice_v
        ind["history"][key]["dates"] = list(dates[-n:])
        if last_obs is not None and last_real == len(dates) - 1 and last_obs.isoformat() < dates[-1]:
            ind["history"][key]["dates"][-1] = last_obs.isoformat()          # this month is not over
        if ind.get("category") == "equity":
            ma = []
            for i in range(len(slice_v)):
                window = [x for x in slice_v[max(0, i - 4) : i + 1] if x is not None]
                ma.append(round(sum(window) / len(window), 6) if window else None)
            ind["history"][key]["ma5"] = ma
    ind["source"] = source
    ind["quality"] = "live"
    # The badge reads data_status, not quality. A card added to the Yahoo catalog after the pack was
    # built kept its "demo" badge over a real price history until this was set here too.
    ind["data_status"] = "live"
    real_date = (last_obs.isoformat() if last_obs is not None and last_obs.isoformat()[:7] == dates[last_real][:7] else dates[last_real])
    ind["asof"] = real_date
    ind["observed_at"] = real_date
    return True


def _pin_latest(ind: dict[str, Any], value: float, source: str, asof_s: str) -> None:
    # This overwrites exactly one point -- history[:-1] stays fixture_synth.
    # quality="live_latest" says that in the schema, but a line chart drawn
    # straight through fixture history into that one real point reads as a
    # real trend (or a real cliff, if the fixture tail happened to sit far
    # from the real value). real_points_from_end tells the chart where the
    # observed data actually starts, so it can stop drawing history as if it
    # were one continuous series.
    for key in ("5y", "10y"):
        if key in ind.get("history", {}) and ind["history"][key].get("values"):
            ind["history"][key]["values"][-1] = round(value, 6)
            ind["history"][key]["real_points_from_end"] = 1
            hd = ind["history"][key].get("dates") or []
            if hd and hd[-1][:7] == asof_s[:7] and asof_s <= hd[-1]:
                hd[-1] = asof_s                # the overwritten point is the pinned observation, on its own date
    ind["value"] = round(value, 6)
    fmt = ind.get("format") or "number1"
    if fmt not in ("rating", "fx_watch", "flag", "fedwatch"):
        ind["display"] = format_value(value, fmt)
    ind["source"] = source
    ind["quality"] = "live_latest"
    ind["asof"] = asof_s
    ind["observed_at"] = asof_s


def _sync_chips(pack: dict[str, Any], ind: dict[str, Any]) -> None:
    for chips in (pack.get("categories") or {}).values():
        for ch in chips:
            if ch["id"] == ind["id"]:
                ch["display"] = ind.get("display_chip") or ind["display"]
                ch["value"] = ind["value"]
                ch["asof"] = ind["asof"]
                for k in ("data_status", "source"):
                    if k in ind:
                        ch[k] = ind[k]
                if "observed_at" in ch or "observed_at" in ind:
                    ch["observed_at"] = ind.get("observed_at", ind["asof"])
    # Headlines are a projection too; left alone they kept the fixture's quote (USD/CHF 0.812 over a
    # live 0.834 card).
    for h in pack.get("headlines") or []:
        if h.get("id") == ind["id"]:
            h["display"] = ind.get("display_chip") or ind["display"]
            if "data_status" in ind:
                h["data_status"] = ind["data_status"]


def overlay_live(universe: dict[str, Any], *, asof: date | None = None) -> dict[str, Any]:
    asof = asof or date.today()
    dates = month_ends(asof, 120)
    stats = {"ok": [], "fail": [], "skip": []}
    by_country = {c["iso3"]: c for c in universe.get("countries") or []}

    # Yahoo histories
    for (iso3, sid), meta in YAHOO.items():
        pack = by_country.get(iso3)
        if not pack:
            continue
        ind = next((i for i in pack["indicators"] if i["id"] == sid), None)
        if not ind:
            stats["skip"].append(f"{iso3}:{sid}")
            continue
        symbol = meta["symbol"]
        print(f"  yahoo {iso3}:{sid} {symbol}", flush=True)
        try:
            pts, last_obs = fetch_yahoo(symbol)
            if _overlay_history(ind, dates, _to_month_map(pts), f"yahoo:{symbol}", last_obs or min(asof, date.fromisoformat(dates[-1]))):
                stats["ok"].append(f"{iso3}:{sid}")
                _sync_chips(pack, ind)
            else:
                stats["fail"].append(f"{iso3}:{sid}:sparse")
        except Exception as exc:  # noqa: BLE001
            stats["fail"].append(f"{iso3}:{sid}:{exc}")

    # FRED latest via Worker
    usa = by_country.get("USA")
    if usa:
        by_id = {i["id"]: i for i in usa["indicators"]}
        for sid in FRED_WORKER_OK:
            meta = FRED_WORKER_LATEST[sid]
            if sid not in by_id:
                stats["skip"].append(f"USA:{sid}")
                continue
            # If yahoo already filled bond_10y/2y with full history, still refresh latest from FRED
            print(f"  fred-worker {sid}", flush=True)
            try:
                d, raw = fetch_fred_worker_latest(meta["id"])
                val = raw * float(meta.get("scale") or 1.0)
                # d is FRED's own observation date -- labeling the badge with
                # dates[-1] (the monthly grid's current-month-end) instead
                # made a value read as fresher than it was, e.g. TGA (a
                # weekly series) showing "asof" the last day of the month
                # when the real print was up to three weeks earlier.
                _pin_latest(by_id[sid], val, f"fred_worker:{meta['id']}", d.isoformat())
                # If not already live history, keep fixture path but mark latest
                if by_id[sid].get("quality") != "live":
                    by_id[sid]["quality"] = "live_latest"
                else:
                    # overwrite last point already; keep live
                    by_id[sid]["quality"] = "live"
                _sync_chips(usa, by_id[sid])
                stats["ok"].append(f"USA:{sid}:latest")
            except Exception as exc:  # noqa: BLE001
                stats["fail"].append(f"USA:{sid}:{exc}")

        # net liquidity from latest live components
        if all(k in by_id for k in ("fed_total_assets", "tga", "on_rrp")):
            fed, tga, rrp = (by_id[k]["value"] for k in ("fed_total_assets", "tga", "on_rrp"))
            if None not in (fed, tga, rrp) and all(
                by_id[k].get("quality", "").startswith("live") for k in ("fed_total_assets", "tga", "on_rrp")
            ):
                net = float(fed) - float(tga) / 1000.0 - float(rrp) / 1000.0
                if "net_liquidity" in by_id:
                    _pin_latest(by_id["net_liquidity"], net, "derived:live_latest",
                                min(by_id[k].get("asof") or dates[-1] for k in ("fed_total_assets", "tga", "on_rrp")))
                    _sync_chips(usa, by_id["net_liquidity"])
                    stats["ok"].append("USA:net_liquidity:latest")

        if all(k in by_id and by_id[k].get("quality", "").startswith("live") for k in ("bond_10y", "bond_2y")):
            if "spread_10y2y" in by_id:
                sp = (float(by_id["bond_10y"]["value"]) - float(by_id["bond_2y"]["value"])) * 100.0
                _pin_latest(by_id["spread_10y2y"], sp, "derived:live",
                            min(by_id[k].get("asof") or dates[-1] for k in ("bond_10y", "bond_2y")))
                _sync_chips(usa, by_id["spread_10y2y"])
                stats["ok"].append("USA:spread_10y2y")

    # BOK
    try:
        print("  bok-worker", flush=True)
        bok = fetch_bok_worker()
        pack = by_country.get("KOR")
        if pack:
            by_id = {i["id"]: i for i in pack["indicators"]}
            for name, sid in BOK_NAME_MAP.items():
                if name not in bok or sid not in by_id:
                    continue
                cycle, val = bok[name]
                # Prefer yahoo history for kospi/usdkrw; still pin BOK latest
                _pin_latest(by_id[sid], val, "bok:ecos_keystat", _cycle_to_date(cycle, asof).isoformat())
                if by_id[sid].get("quality") == "live":
                    by_id[sid]["quality"] = "live"
                _sync_chips(pack, by_id[sid])
                stats["ok"].append(f"KOR:{sid}")
    except Exception as exc:  # noqa: BLE001
        stats["fail"].append(f"BOK:{exc}")

    # Sovereign ratings (Wikipedia S&P / Moody's / Fitch)
    try:
        print("  wikipedia-ratings", flush=True)
        from .ratings_wiki import fetch_agency_tables, ratings_for_iso  # noqa: WPS433

        tables = fetch_agency_tables()
        for iso3, pack in by_country.items():
            ind = next((i for i in pack["indicators"] if i["id"] == "sovereign_ratings"), None)
            if not ind:
                continue
            hit = ratings_for_iso(iso3, tables)
            if not hit:
                stats["skip"].append(f"{iso3}:sovereign_ratings")
                continue
            ind["display"] = hit["display"]
            ind["display_chip"] = hit["display"]
            ind["components"] = hit["components"]
            ind["chart_type"] = "status"
            ind["source"] = hit["source"]
            ind["quality"] = hit["quality"]
            ind["note_ko"] = hit["note_ko"]
            ind["asof"] = asof.isoformat()                 # a table read today, not a month-end
            ind["observed_at"] = asof.isoformat()
            # keep a numeric placeholder for schema; not used for display
            if ind.get("value") is None:
                ind["value"] = 0.0
            _sync_chips(pack, ind)
            # chips may need components too
            for chips in (pack.get("categories") or {}).values():
                for ch in chips:
                    if ch["id"] == "sovereign_ratings":
                        ch["components"] = hit["components"]
                        ch["chart_type"] = "status"
                        ch["note_ko"] = hit["note_ko"]
            stats["ok"].append(f"{iso3}:sovereign_ratings")
    except Exception as exc:  # noqa: BLE001
        stats["fail"].append(f"RATINGS:{exc}")

    # QRA issuance bars from local qra_engine_v1.json (run build_qra_engine.py)
    try:
        print("  qra-engine", flush=True)
        from .qra.build import load_latest_issuance  # noqa: WPS433
        from .qra.compare import apply_real_history  # noqa: WPS433

        hit = load_latest_issuance()
        usa = by_country.get("USA")
        if hit and usa:
            for ind in usa.get("indicators") or []:
                if ind.get("id") != "qra_issuance":
                    continue
                if hit.get("components") and len(hit["components"]) >= 6:
                    ind["components"] = hit["components"]
                ind["chart_type"] = "bar"
                ind["quality"] = "live"
                ind["source"] = hit.get("source") or "qra_engine_v1"
                ind["note_ko"] = hit.get("summary_ko") or ind.get("note_ko")
                ind["asof"] = (hit.get("asof") or "")[:10] or dates[-1]
                if hit.get("compare"):
                    ind["compare"] = hit["compare"]
                    ind["ui"] = {
                        **(ind.get("ui") or {}),
                        "click_view": "compare_bar_table",
                        "secondary_view": "maturity_components",
                    }
                if hit.get("history_net_borrowing"):
                    ind["history_net_borrowing"] = hit["history_net_borrowing"]
                apply_real_history(ind, hit.get("history_net_borrowing"))
                if hit.get("flags"):
                    ind["flags"] = hit["flags"]
                if hit.get("tga_vs_qra"):
                    ind["tga_vs_qra"] = hit["tga_vs_qra"]
                if hit["components"]:
                    # Prefer current compare bar as chip value when present
                    cur = next(
                        (
                            s
                            for s in ((hit.get("compare") or {}).get("series") or [])
                            if s.get("id") == "current"
                        ),
                        None,
                    )
                    val = float(cur["value"]) if cur else float(hit["components"][0]["value"])
                    ind["value"] = val
                    ind["display"] = format_value(val, ind.get("unit") or "bn")
                    ind["display_chip"] = ind["display"]
                _sync_chips(usa, ind)
                for chips in (usa.get("categories") or {}).values():
                    for ch in chips:
                        if ch["id"] == "qra_issuance":
                            if hit.get("components") and len(hit["components"]) >= 6:
                                ch["components"] = hit["components"]
                            ch["chart_type"] = "bar"
                            ch["note_ko"] = hit.get("summary_ko")
                            if hit.get("compare"):
                                ch["compare"] = hit["compare"]
                            if hit.get("history_net_borrowing"):
                                ch["history_net_borrowing"] = hit["history_net_borrowing"]
                stats["ok"].append("USA:qra_issuance")
                break
            else:
                stats["skip"].append("USA:qra_issuance")
        else:
            stats["skip"].append("USA:qra_issuance_no_json")
    except Exception as exc:  # noqa: BLE001
        stats["fail"].append(f"QRA:{exc}")

    live_n = len(stats["ok"])
    universe["source"] = {
        "kind": "hybrid_live" if live_n else "fixture_synth",
        "quality": "partial_live" if live_n else "demo_not_live",
        "live_ok": live_n,
        "live_fail": len(stats["fail"]),
        "note": (
            f"실데이터 오버레이 {live_n}건: Yahoo + Worker FRED latest + BOK + Wikipedia 신용등급 + QRA 엔진. "
            "ISM PMI·CDS 스킵. FedWatch는 CME 사이트 스크래핑 금지(ToS/IP 차단) — "
            "FF 선물 정산가 기반 자체 스코어링 예정. "
            "KOSIS 미사용. BOJ는 Time-Series Search CSV 매핑 예정."
        ),
        "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "backends": [
            "yahoo_chart",
            "fred_worker_latest",
            "bok_worker",
            "wikipedia_ratings",
            "qra_engine",
        ],
    }
    universe["live_stats"] = stats
    # The per-country badge counts are read from the indicators; a card this overlay turned live
    # (a new Yahoo symbol) otherwise stayed counted as demo.
    from .us_public_series import refresh_status_summary
    for country in by_country.values():
        refresh_status_summary(country)
    return stats
