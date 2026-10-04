'use strict';
// Fetch official feeds on the Mac, retain a private snapshot, then archive metadata.
// This script never sends email and never publishes website assets.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { archiveReports } = require('./archive-mailing-reports');
async function main() {
 const root = path.resolve(__dirname, '..');
 const dir = path.join(os.homedir(), 'Documents/policy-downloads/mac-20260930');
 const file = path.join(dir, 'commodity_reports_v1.json');
 if (fs.existsSync(path.join(dir, 'STOP'))) throw Error('STOP exists');
 fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
 const seed = path.join(root, 'New for anti/public/data/commodity_reports_v1.json');
 if (!fs.existsSync(file) && fs.existsSync(seed)) fs.copyFileSync(seed, file);
 const code = await new Promise((resolve, reject) => {
  const child = spawn(process.env.POLICY_PYTHON || '/opt/miniconda3/bin/python3', ['-u', path.join(root, 'New for anti/scripts/commodity_reports/build_reports.py'), 'build', '--output', file, '--print-stats'], { cwd: root, env: process.env, stdio: ['ignore', 'inherit', 'inherit'] });
  const terminate = () => child.kill('SIGTERM');
  process.once('SIGTERM', terminate); process.once('SIGINT', terminate);
  const timeout = setTimeout(terminate, 10 * 60000);
  const cleanup = () => { clearTimeout(timeout); process.removeListener('SIGTERM', terminate); process.removeListener('SIGINT', terminate); };
  child.once('error', e => { cleanup(); reject(e); });
  child.once('close', c => { cleanup(); resolve(c); });
 });
 if (code !== 0 || fs.existsSync(path.join(dir, 'STOP'))) throw Error('local_report_fetch_incomplete');
 const document = JSON.parse(fs.readFileSync(file, 'utf8'));
 const feeds = document.feed_status || [];
 if (!feeds.some(x => x.ok)) throw Error('all_report_sources_failed');
 const result = await archiveReports({ file, skipUndated: true, skipUnclassified: true });
 console.log(JSON.stringify({ ...result, feeds_ok: feeds.filter(x => x.ok).length, feeds_failed: feeds.filter(x => !x.ok).length, source: 'mac_official_feeds' }));
}
main().catch(() => { console.error('local_mailing_report_sync_failed'); process.exitCode = 1; });
