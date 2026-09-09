// Local-only, allowlisted native-module smoke test server; never serves repo data.
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
const root = new URL('../../', import.meta.url);
const allowed = new Set(['tests/portfolio-engine/scenario-browser.html',
  ...['scenario.mjs', 'scenario-stats.mjs', 'math.mjs'].map(f => `New for anti/portfolio-engine/${f}`)]);
createServer((req, res) => {
  let name;
  try { name = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).slice(1); }
  catch { res.writeHead(400).end(); return; }
  if (!allowed.has(name)) { res.writeHead(404).end(); return; }
  res.writeHead(200, {'Content-Type': name.endsWith('.html') ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8',
    'Cache-Control': 'no-store'}).end(readFileSync(new URL(name, root)));
}).listen(8769, '127.0.0.1', () => console.log('Scenario smoke: http://127.0.0.1:8769/tests/portfolio-engine/scenario-browser.html'));
