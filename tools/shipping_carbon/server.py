"""Local-only scenario viewer. Run: python3 server.py --port 8768."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from engine import calculate, defaults, json_value
from presets import catalog
from fueleu_adapter import call_fueleu
from combined_finance import observed_reference

ROOT = Path(__file__).resolve().parent
FORCE_SYNTHETIC = False


def snapshot():
    path = ROOT / "source_data/reference_prices.json"
    if FORCE_SYNTHETIC:
        return json.loads((ROOT / "synthetic_snapshot.json").read_text())
    if path.exists():
        return json.loads(path.read_text())
    return {"as_of": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(), "sources": {}, "status": "missing"}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, kind="application/json; charset=utf-8"):
        body = json.dumps(json_value(data), ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/market":
            def local_json(name, fallback):
                path = ROOT / "source_data" / name
                return json.loads(path.read_text()) if path.exists() else fallback
            return self.reply(200, {"prices": snapshot(),
                "market_structure": local_json("market_structure.json", {"status": "not_collected", "records": []}),
                "fueleu_audit": local_json("fueleu_audit.json", {"status": "not_collected"})})
        if self.path == "/api/presets":
            path = ROOT / "source_data/vessel_emissions.json"
            return self.reply(200, catalog(json.loads(path.read_text()) if path.exists() else {}))
        if self.path == "/api/defaults":
            return self.reply(200, defaults(snapshot()))
        if self.path == "/api/observations":
            s = snapshot()
            mrv = ROOT / "source_data/vessel_emissions.json"
            structure = ROOT / "source_data/market_structure.json"
            audit = ROOT / "source_data/fueleu_audit.json"
            return self.reply(200, {"prices": s,
                "market_structure": json.loads(structure.read_text()) if structure.exists() else {"status": "not_collected", "records": []},
                "fueleu_audit": json.loads(audit.read_text()) if audit.exists() else {"status": "not_collected"},
                "vessels": json.loads(mrv.read_text()) if mrv.exists() else {
                "status": "source_not_collected", "records": [],
                "source_url": "https://mrv.emsa.europa.eu/#public/emission-report"},
                "private_inputs": {key: None for key in ("allowance_inventory", "futures_positions", "initial_margin", "customer_contracts", "pooling_quotes")}})
        files = {"/climate": ("market.html", "text/html"), "/market.css": ("market.css", "text/css"),
                 "/market-ui.js": ("market-ui.js", "text/javascript"), "/market-math.mjs": ("market-math.mjs", "text/javascript"),
                 "/": ("viewer.html", "text/html"), "/viewer.js": ("viewer.js", "text/javascript"),
                 "/extras.js": ("extras.js", "text/javascript"),
                 "/observations.js": ("observations.js", "text/javascript"),
                 "/presets.js": ("presets.js", "text/javascript"),
                 "/viewer.css": ("viewer.css", "text/css")}
        if self.path not in files:
            return self.reply(404, {"error": "Not found"})
        name, mime = files[self.path]
        self.reply(200, (ROOT / name).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        if self.path not in ("/api/calculate", "/api/combined"):
            return self.reply(404, {"error": "Not found"})
        # A browser from another origin cannot submit changes to the local viewer.
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self.reply(403, {"error": "Origin mismatch"})
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 32000:
                raise ValueError("입력 크기를 확인하세요")
            p = json.loads(self.rfile.read(size))
            if not isinstance(p, dict):
                raise ValueError("입력 형식을 확인하세요")
            if self.path == "/api/combined":
                result = call_fueleu({"mode": "combined", "inputs": p, "reference": observed_reference(snapshot())})
                result["inputs"] = p
                self.reply(200, result)
            else:
                self.reply(200, calculate(p, snapshot()))
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--synthetic", action="store_true", help="Use only the bundled synthetic reference fixture")
    args = parser.parse_args()
    FORCE_SYNTHETIC = args.synthetic
    print(f"Local viewer: http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
