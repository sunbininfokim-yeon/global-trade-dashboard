"""Local FuelEU viewer. Run: python3 server.py --port 8772, then open http://127.0.0.1:8772

Reads source_data/pool_prices.json if collect_pool_prices.py has been run;
without it the price panel says so instead of showing sample numbers.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import engine

ROOT = Path(__file__).resolve().parent
STATIC = {"/": ("viewer.html", "text/html"), "/viewer.js": ("viewer.js", "text/javascript"),
          "/viewer.css": ("viewer.css", "text/css")}


def market():
    path = ROOT / "source_data" / "pool_prices.json"
    if not path.exists():
        return {"status": "missing", "hint": "python3 collect_pool_prices.py"}
    data = json.loads(path.read_text())
    return {k: data.get(k) for k in ("schema", "retrieved_at", "source", "source_index_url", "price_type",
                                     "unit", "redistribution", "note", "series", "latest_topbar", "missing_pages")}


def calculate(body):
    year = int(body["year"])
    pool = float(body["pool_price"])
    nxt = None if body.get("next_pool_price") in (None, "") else float(body["next_pool_price"])
    kw = {"consecutive_deficits": int(body.get("consecutive_deficits") or 0),
          "borrowed_last_period": bool(body.get("borrowed_last_period"))}
    y = engine.ship_year(body["legs"], year, pool_price=pool, **kw)
    full = y["full_year"]
    fleet = {k: (full["compliance_balance_tco2e"] if v is None else float(v)) for k, v in (body.get("fleet") or {}).items()}
    return {"year": y, "options": engine.options(full, pool, nxt),
            "fleet": engine.fleet_pool(fleet) if fleet else None,
            "constants": {"target": full["target"], "penalty_eur_per_tco2e": full["penalty_eur_per_tco2e"]}}


def quick(body):
    intra = float(body.get("intra_eu_pct") or 0) / 100
    berth = float(body.get("at_berth_pct") or 0) / 100
    share = {k: v for k, v in {"intra_eu": intra, "at_berth": berth, "extra_eu": 1 - intra - berth}.items() if v}
    if any(v < 0 for v in share.values()):
        raise ValueError("EU 내 항해와 정박 비중의 합은 100%를 넘을 수 없습니다")
    fuels = {f: float(t) for f, t in (body.get("fuels") or {}).items() if f and t not in (None, "")}
    gt = None if body.get("gross_tonnage") in (None, "") else float(body["gross_tonnage"])
    pool = None if body.get("pool_price") in (None, "") else float(body["pool_price"])
    return engine.quick_check(gt, fuels, share, int(body.get("year") or 2025), pool_price=pool)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, kind="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/market":
            return self.reply(200, market())
        if self.path == "/api/fuels":
            return self.reply(200, {k: v["label"] for k, v in engine.FUELS.items()})
        if self.path == "/api/example":
            return self.reply(200, json.loads((ROOT / "example_voyages.json").read_text()))
        if self.path not in STATIC:
            return self.reply(404, {"error": "not found"})
        name, mime = STATIC[self.path]
        self.reply(200, (ROOT / name).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        handlers = {"/api/calculate": calculate, "/api/quick": quick}
        if self.path not in handlers:
            return self.reply(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.reply(200, handlers[self.path](body))
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8772)
    args = ap.parse_args()
    print(f"http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
