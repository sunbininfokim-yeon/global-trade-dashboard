"""Loopback-only USPolicy integration preview. No real DB, keys, or API calls.

The policy module, policy styles and simulator assets are real; overview is an
explicit empty fixture. Production deployment uses the normal site shell.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json

ROOT = Path(__file__).resolve().parents[2] / 'New for anti'
ASSETS = {
    '/policy.js': ('policy.js', 'text/javascript'),
    '/style.css': ('style.css', 'text/css'),
    '/policy-evidence.js': ('policy-evidence.js', 'text/javascript'),
    '/policy-simulator/country-model.mjs': ('policy-simulator/country-model.mjs', 'text/javascript'),
    '/policy-simulator/company-model.mjs': ('policy-simulator/company-model.mjs', 'text/javascript'),
    '/policy-simulator/company-view.mjs': ('policy-simulator/company-view.mjs', 'text/javascript'),
    '/policy-simulator/company-profiles.mjs': ('policy-simulator/company-profiles.mjs', 'text/javascript'),
    '/policy-simulator/antidumping-catalog.mjs': ('policy-simulator/antidumping-catalog.mjs', 'text/javascript'),
    '/policy-simulator/antidumping-model.mjs': ('policy-simulator/antidumping-model.mjs', 'text/javascript'),
    '/policy-simulator/antidumping-view.mjs': ('policy-simulator/antidumping-view.mjs', 'text/javascript'),
    '/policy-simulator/elasticities.mjs': ('policy-simulator/elasticities.mjs', 'text/javascript'),
    '/policy-simulator/form-validation.mjs': ('policy-simulator/form-validation.mjs', 'text/javascript'),
    '/policy-simulator/view.mjs': ('policy-simulator/view.mjs', 'text/javascript'),
    '/policy-simulator/policy-catalog.mjs': ('policy-simulator/policy-catalog.mjs', 'text/javascript'),
    '/policy-simulator/suppliers-2025.mjs': ('policy-simulator/suppliers-2025.mjs', 'text/javascript'),
    '/policy-simulator/style.css': ('policy-simulator/style.css', 'text/css'),
}
OVERVIEW = {'congress_overview': {'committees': [], 'stage_counts': {}},
            'executive_overview': {'agencies': []}, 'policy_areas': [], 'cfr_titles': []}
HTML = '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>국가·기업 관세 시뮬레이터 · 로컬 검토</title>
<link rel="stylesheet" href="/style.css"><style>
body{display:block!important;overflow:auto!important;background:#0b1220;color:#e2e8f0;margin:0;font-family:system-ui,sans-serif}
.preview-top{border-bottom:1px solid #27364a;padding:15px 24px;font-size:13px;display:flex;gap:20px;align-items:center}.preview-top b{color:#5de0ce}.preview-top small{color:#9baec2;font-size:11px}
#preview-surface{display:block!important;position:static!important;min-height:100vh;overflow:visible!important;width:100%;max-width:1480px;margin:auto}
.policy-surface-inner{max-width:none!important;padding:24px!important}.policy-modes{flex-wrap:wrap}.policy-search{max-width:250px}
@media(max-width:540px){.preview-top{padding:10px 12px;flex-wrap:wrap;gap:5px 15px}.policy-surface-inner{padding:12px!important}}
</style></head><body><header class="preview-top"><b>ChokeMonitor</b><span>정책 → 미국</span><small>로컬 통합 검토 · 의회·행정부 목록은 빈 테스트 자료</small></header><main id="preview-surface"></main>
<script src="/policy-evidence.js"></script><script src="/policy.js"></script><script>
const render=()=>USPolicy.render('us-policy-hub',document.getElementById('preview-surface'));
window.addEventListener('popstate',render);render();
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ('/', '/policy/us', '/policy/us/executive', '/policy/us/simulator'):
            body, mime = HTML.encode(), 'text/html'
        elif route == '/api/us/overview':
            body, mime = json.dumps(OVERVIEW).encode(), 'application/json'
        elif route in ASSETS:
            rel, mime = ASSETS[route]
            body = (ROOT / rel).read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8773)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'USPolicy integration preview: http://127.0.0.1:{args.port}/policy/us/simulator', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
