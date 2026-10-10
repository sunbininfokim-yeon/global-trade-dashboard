"""Loopback-only component preview. Serves an explicit public-asset allowlist."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json

ROOT = Path(__file__).resolve().parents[2] / 'New for anti'
ASSETS = {
    '/public/data/trade_policy/us_sanctions_v1.json': ('public/data/trade_policy/us_sanctions_v1.json', 'application/json'),
    '/export-controls.js': ('export-controls.js', 'text/javascript'),
    '/export-controls.css': ('export-controls.css', 'text/css'),
    '/public/data/trade_policy/us_tariffs_v1.json': ('public/data/trade_policy/us_tariffs_v1.json', 'application/json'),
}
HTML = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>미국 통상 조치 · 로컬 검토</title><link rel="stylesheet" href="/export-controls.css">
<style>body{background:#080f1b;color:#e2e8f0;font-family:system-ui,sans-serif;margin:0}main{max-width:720px;margin:auto;padding:20px}
h1{font-size:20px}.preview-note{color:#94a3b8;font-size:12px;line-height:1.6}nav{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0}
nav button{padding:8px 12px;background:#142338;color:#dbeafe;border:1px solid #36516d;border-radius:6px;cursor:pointer}
.ec-src{font-size:11px;line-height:1.6;margin-top:8px}.ec-src a{color:#7dd3fc}.hidden{display:none}</style>
<main><h1>국가별 미국 통상 조치</h1><p class="preview-note">로컬 구성요소 검토 · 운영 사이트 아님 · 법정 요건과 실제 조치를 분리한 부분 검증 자료</p>
<nav id="countries" aria-label="국가 선택"></nav><div id="export-controls-content"></div><div id="export-controls-legend" class="hidden"></div></main>
<script src="/export-controls.js"></script><script>
(async()=>{const d=await (await fetch('/public/data/trade_policy/us_tariffs_v1.json')).json();
const names={RUS:'러시아',USA:'미국',...Object.fromEntries(Object.entries(d.partners).map(([iso,p])=>[iso,p.name_ko]))};
const nav=document.getElementById('countries');for(const [iso,name] of Object.entries(names)){const b=document.createElement('button');b.type='button';b.textContent=name;b.onclick=()=>{ExportControls.select(iso);document.title=name+' · 미국 통상 조치 로컬 검토';};nav.append(b);}
await ExportControls.mount({setHeader(){},setPanels(){},setMap(){},loadWorldGeo:async()=>{},isActive:()=>true,
worldBaseLayers:()=>[],worldGeo:()=>({type:'FeatureCollection',features:[]}),GeoJsonLayer:class{constructor(o){Object.assign(this,o);}},
resolveIso3:f=>f?.properties?.iso||'',updateLayers(){},hideTooltip(){},isoLabel:iso=>names[iso]||iso,countryLabel:x=>x});
ExportControls.select('RUS');
})().catch(e=>{document.getElementById('export-controls-content').textContent='미리보기 실패: '+e.message;});
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        if route == '/':
            body, mime = HTML.encode(), 'text/html'
        elif route in ASSETS:
            rel, mime = ASSETS[route]
            body = (ROOT / rel).read_bytes()
        elif route == '/public/data/export_controls/manifest.json':
            body, mime = json.dumps({'as_of':'2026-10-09','modules':[],'controls':[]}).encode(), 'application/json'
        elif route == '/public/data/commodity_reports_v1.json':
            body, mime = b'{"boards":{"export_controls":[]},"items":[]}', 'application/json'
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
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Policy component preview: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
