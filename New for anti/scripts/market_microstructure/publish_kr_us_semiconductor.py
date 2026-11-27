#!/usr/bin/env python3
"""Daily publisher for the Korea -> US semiconductor engine.

Calls kr_to_us_semiconductor.py (#1121) and its frozen model without changing
either, and keeps a forecast-vs-actual history for the dashboard:

  oos     the engine's own quarterly walk-forward validation (2016~): each
          quarter is scored by a model fitted only on earlier data
  replay  joint KRX/NYSE dates after the model froze, run after the fact
  live    issued after the Korean close and before the US open

Every replay/live row is settled against the actual US open and close
(previous US close as the base) once that US session has closed. Rows are
never filled in: a missing price stays missing.

Writes public/data/kr_us_semiconductor_v1.json (the cards, same display
schema) and public/data/kr_us_semiconductor_history_v1.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

import exchange_calendars as xc
import pandas as pd
import requests

import kr_to_us_semiconductor as eng
from research_direction_diagnostics import ReviewedCalendar

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "../../public/data"
DISPLAY = DATA / "kr_us_semiconductor_v1.json"
HISTORY = DATA / "kr_us_semiconductor_history_v1.json"
HIST_SCHEMA = "kr-us-semiconductor-history-v1"
DISPLAY_SCHEMA = "kr-us-semiconductor-display-v1"
NAMES = {"mu": "마이크론", "sox": "필라델피아 반도체지수", "nvda": "엔비디아", "amd": "AMD", "avgo": "브로드컴"}
TICKERS = {"mu": "MU", "sox": "^SOX", "nvda": "NVDA", "amd": "AMD", "avgo": "AVGO"}
ORDER = ("mu", "sox", "nvda", "amd", "avgo")
HEADS = ("opening", "closing")
RECENT_OOS = 120


def fetch(directory: Path, rng: str = "max") -> None:
    for key, symbol in eng.SYMBOLS.items():
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/" + quote(symbol, safe=""),
                         params={"range": rng, "interval": "1d"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        (directory / (key + ".json")).write_bytes(r.content)


def calendars(start: pd.Timestamp, end: pd.Timestamp):
    kr = xc.get_calendar("XKRX", start=start, end=end)
    ny = xc.get_calendar("XNYS", start=start, end=end)
    return kr, ny, ReviewedCalendar(kr).sessions


def actual(directory: Path, ticker: str, day: pd.Timestamp) -> dict | None:
    """US open and close of `day` against the previous US close."""
    q = eng.prices(directory, ticker)
    if day not in q.index:
        return None
    i = q.index.get_loc(day)
    if i == 0:
        return None
    prev, o, c = q.close.iloc[i - 1], q.open.iloc[i], q.close.iloc[i]
    if pd.isna(prev) or pd.isna(o) or pd.isna(c):
        return None
    return {"open": round(float(o / prev - 1), 6), "close": round(float(c / prev - 1), 6)}


def probs(result: dict) -> dict:
    out = {}
    for k, r in (result.get("results") or {}).items():
        if r.get("status") == "unavailable":
            continue
        out[k] = {h: round(r[h]["up"], 6) for h in HEADS}
    return out


def oos_block(directory: Path, through: pd.Timestamp) -> dict:
    """Walk-forward scores straight from the engine's validate()."""
    out = {}
    frames = eng.panel(directory, through)
    for k in ORDER:
        groups = eng.features(k)
        out[k] = {}
        for h in HEADS:
            _, summary, scores = eng.validate(frames[k], h, groups)
            p = scores["semiconductors"]
            y = scores["observed_up"]
            tail = scores.tail(RECENT_OOS)
            out[k][h] = {
                "n": int(summary["n"]), "start": summary["start"], "end": summary["end"],
                "hit": round(summary["hit"], 4), "recall_up": round(summary["recall_up"], 4),
                "recall_down": round(summary["recall_down"], 4), "base_rate": round(summary["base_rate"], 4),
                "brier": round(summary["brier"]["semiconductors"], 5), "brier_market": round(summary["brier"]["market"], 5),
                "recent": {"dates": [d.strftime("%Y-%m-%d") for d in tail.index],
                           "p_up": [round(float(v), 4) for v in tail["semiconductors"]],
                           "up": [int(v) for v in tail["observed_up"]]},
            }
            del p, y
    return out


def score(rows: list[dict]) -> dict:
    """Hit rate of settled replay/live rows per ticker and head (50% cut, flat days skipped)."""
    out = {}
    for k in ORDER:
        out[k] = {}
        for h, a_key in (("opening", "open"), ("closing", "close")):
            n = hit = 0
            for r in rows:
                p = (r.get("p") or {}).get(k, {}).get(h)
                a = (r.get("actual") or {}).get(k, {}).get(a_key)
                if p is None or a is None or a == 0 or round(p * 100) == 50:
                    continue
                n += 1
                hit += int((p > 0.5) == (a > 0))
            out[k][h] = {"n": n, "hit": hit}
    return out


def run(directory: Path, model: dict, now: pd.Timestamp, prev: dict | None, with_oos: bool) -> tuple[dict, dict]:
    hist = prev if prev and prev.get("schema_version") == HIST_SCHEMA else {"rows": []}
    rows = {r["date"]: r for r in hist.get("rows", [])}
    frozen = pd.Timestamp(model["trained_through"])
    kr, ny, kr_sessions = calendars(frozen - pd.Timedelta(days=10), now.tz_convert(None).normalize() + pd.Timedelta(days=20))
    today_kst = now.tz_convert("Asia/Seoul").tz_localize(None).normalize()

    # Replays: joint dates after the freeze whose US session has closed and
    # that have no live row.
    joint = [d for d in ny.sessions if d in kr_sessions and frozen < d <= today_kst]
    for d in joint:
        if now < ny.session_close(d) or (d.strftime("%Y-%m-%d") in rows and rows[d.strftime("%Y-%m-%d")]["kind"] == "live"):
            continue
        key = d.strftime("%Y-%m-%d")
        if key in rows:
            continue
        when = kr.session_close(d) + pd.Timedelta(minutes=30)
        res = eng.infer(model, directory, d, when, True)
        rows[key] = {"date": key, "kind": "replay", "as_of": res["as_of"], "p": probs(res)}

    # Live: today's joint session, inside the KR-close -> US-open window.
    live = None
    if today_kst in kr_sessions and today_kst in ny.sessions \
            and kr.session_close(today_kst) <= now < ny.session_open(today_kst):
        res = eng.infer(model, directory, today_kst, now, False)
        key = today_kst.strftime("%Y-%m-%d")
        rows[key] = {"date": key, "kind": "live", "as_of": res["as_of"], "p": probs(res)}
        live = rows[key]

    # Settle every row whose US session has closed.
    for key, r in rows.items():
        d = pd.Timestamp(key)
        if r.get("actual") or d not in ny.sessions or now < ny.session_close(d):
            continue
        acts = {k: a for k in ORDER if (a := actual(directory, k, d))}
        if acts:
            r["actual"] = acts

    ordered = [rows[k] for k in sorted(rows)]
    last_closed = max((d for d in ny.sessions if ny.session_close(d) <= now), default=None)
    oos = (hist.get("oos") or None)
    if with_oos and last_closed is not None:
        oos = oos_block(directory, last_closed)
    history = {
        "schema_version": HIST_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_id": model["model_id"], "trained_through": model["trained_through"],
        "names_ko": NAMES, "tickers": TICKERS,
        "rows": ordered, "forward_score": score(ordered), "oos": oos,
        "notes_ko": [
            "순차 검증(2016~)은 매 분기 그 이전 자료로만 학습한 모델이 그 분기를 맞힌 비율입니다. 동결 모델의 계수와는 다릅니다.",
            "사후 재현은 모델 동결일 이후 날짜를 한국 마감 직후 시점으로 놓고 나중에 돌린 값이고, 실시간은 한국 마감 뒤 미국 개장 전에 발행한 값입니다.",
            "실제값은 미국 전 거래일 종가 대비 정규장 시가·종가입니다. 보합은 채점에서 뺍니다.",
        ],
    }

    # Display file: the newest settled-or-live row becomes the cards.
    head_row = live or (ordered[-1] if ordered else None)
    display = prev_display(model)
    if head_row:
        cards = []
        for k in ORDER:
            p = head_row["p"].get(k)
            if not p:
                continue
            a = (head_row.get("actual") or {}).get(k, {})
            cards.append({"key": k, "ticker": TICKERS[k], "name_ko": NAMES[k], "opening_up": p["opening"],
                          "closing_up": p["closing"],
                          "incremental_skill": model["validation"][k]["opening"]["incremental_skill"],
                          "actual_open_return": a.get("open")})
        display["latest"] = {"status": "research_forecast" if head_row["kind"] == "live" else "retrospective_replay",
                             "target_date_us": head_row["date"], "kr_source_date": head_row["date"],
                             "as_of": head_row["as_of"], "cards": cards}
    upcoming = [d for d in ny.sessions if d in kr_sessions and d > (pd.Timestamp(head_row["date"]) if head_row else today_kst)]
    if upcoming:
        n = upcoming[0].strftime("%Y-%m-%d")
        display["next"] = {"target_date_us": n, "kr_source_date": n, "status": "pending",
                           "note_ko": f"{n} 한국 장 마감(15:30 KST) 뒤, 미국 개장 전에 자동으로 나옵니다."}
    return history, display


def prev_display(model: dict) -> dict:
    return {"schema_version": DISPLAY_SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model_id": model["model_id"], "engine": "kr_to_us_semiconductor.py (#1121)",
            "probability_basis": "전 미국 거래일 종가 대비 미국 정규장 시가(opening)·종가(closing)가 오를 확률"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, default=eng.MODEL)
    ap.add_argument("--prices", type=Path, help="Yahoo chart JSON folder (default: download now)")
    ap.add_argument("--now", help="override the clock (tests)")
    ap.add_argument("--no-oos", action="store_true", help="keep the previous walk-forward block")
    ap.add_argument("--display", type=Path, default=DISPLAY)
    ap.add_argument("--history", type=Path, default=HISTORY)
    args = ap.parse_args()
    model = json.loads(args.model.read_text())
    if model.get("model_id") != eng.digest(model):
        raise SystemExit("frozen model digest mismatch")
    now = pd.Timestamp(args.now) if args.now else pd.Timestamp.now(tz="UTC")
    prev = json.loads(args.history.read_text()) if args.history.exists() else None
    with TemporaryDirectory() as tmp:
        directory = args.prices or Path(tmp)
        if not args.prices:
            fetch(directory)
        history, display = run(directory, model, now, prev, not args.no_oos)
    args.history.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    args.display.write_text(json.dumps(display, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fs = history["forward_score"]["mu"]
    print(json.dumps({"rows": len(history["rows"]), "last": history["rows"][-1]["date"] if history["rows"] else None,
                      "mu_forward": fs, "mu_oos_open": {k: v for k, v in ((history.get("oos") or {}).get("mu", {}).get("opening") or {}).items() if k != "recent"},
                      "latest": display.get("latest", {}).get("target_date_us"), "next": (display.get("next") or {}).get("target_date_us")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
