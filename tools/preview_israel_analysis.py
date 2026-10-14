#!/usr/bin/env python3
"""Local-only Israel election integration preview. Never serves repository secrets."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / 'New for anti'
PREVIEW = '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><base href="/">
<title>이스라엘 선거 분석 · 로컬 검증</title><link rel="stylesheet" href="/style.css">
<style>body{margin:0;background:#07111f;color:#e2e8f0;font-family:Arial,sans-serif}nav{padding:14px 20px;border-bottom:1px solid #334155}main{display:grid;grid-template-columns:1fr 320px;min-height:calc(100vh - 90px)}.map-pane{position:relative;min-height:calc(100vh - 50px);background:radial-gradient(ellipse at center,#152940,#07111f)}.preview-note{padding:20px;color:#94a3b8;font-size:12px}.panel-section{padding:20px}.elections-country{max-width:none}#timeline{display:none}.hidden{display:none!important}@media(max-width:720px){main{grid-template-columns:1fr}.map-pane{min-height:calc(100vh - 50px)}#country{order:-1}.panel-section{padding:14px}}</style></head>
<body><nav>정치 → 국가별 선거분석 → 이스라엘 <small>· 로컬 검증</small></nav>
<main><section class="map-pane"><p class="preview-note">실제 선거 모듈과 데이터 로더를 사용합니다. 이 검증 화면의 지도 호스트는 대체 어댑터입니다.</p><div id="modal" class="elections-modal-host hidden"></div></section><aside id="country"></aside><aside id="timeline"></aside></main>
<script type="module">
import '/js/elections/index.js';
const host={roots:{country:document.querySelector('#country'),timeline:document.querySelector('#timeline'),modal:document.querySelector('#modal')},
 layers:{GeoJsonLayer:class{constructor(props){this.props=props}}},worldBaseLayers:()=>[],setElectionMap:()=>{},setWorldMap:()=>{},
 loadWorldGeo:async()=>({type:'FeatureCollection',features:[]}),resolveIso3:()=>null,setPanels:()=>{},
 readRoute:()=>{const p=location.pathname.split('/');return {country:p[2]||'ISR',screen:p[3]||null}},
 writeRoute:(r,{replace=false}={})=>{const p='/politics'+(r.country?'/'+r.country:'')+(r.screen?'/'+r.screen:'');history[replace?'replaceState':'pushState']({},'',p)}};
window.previewHost=host;
await window.ElectionApp.openWorld(host);
window.previewReady=true;
</script></body></html>'''


class Handler(SimpleHTTPRequestHandler):
    preview = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/politics') or path == '/':
            body = PREVIEW.encode() if self.preview else (ROOT/'index.html').read_bytes()
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        elif path.startswith('/api/'):
            self.send_error(404, 'No production API in local preview')
        else:
            super().do_GET()

    def list_directory(self, path):
        self.send_error(404); return None


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8766)
    p.add_argument('--app', action='store_true', help='Serve existing full app shell instead of test host')
    args = p.parse_args(); Handler.preview = not args.app
    print(f'http://127.0.0.1:{args.port}/politics/ISR/election_analysis', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
