'use strict';
// Fetch official feeds on the Mac, retain a private snapshot, then archive metadata.
// This script never sends email and never publishes website assets.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { archiveReports } = require('./archive-mailing-reports');
const { updateSyncState, checkpointSyncState } = require('./lib/sync-utils');
const HEALTH_RESOURCE = 'mailing:reports:mac';
async function main() {
 const root = path.resolve(__dirname, '..');
 const dir = path.join(os.homedir(), 'Documents/policy-downloads/mac-20260930');
 const file = path.join(dir, 'commodity_reports_v1.json');
 if (fs.existsSync(path.join(dir, 'STOP'))) throw Error('STOP exists');
 fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
 const seed = path.join(root, 'New for anti/public/data/commodity_reports_v1.json');
 if (!fs.existsSync(file) && fs.existsSync(seed)) fs.copyFileSync(seed, file);
 let timedOut = false, interrupted = false;
 const code = await new Promise((resolve, reject) => {
  const child = spawn(process.env.POLICY_PYTHON || '/opt/miniconda3/bin/python3', ['-u', path.join(root, 'New for anti/scripts/commodity_reports/build_reports.py'), 'build', '--output', file, '--print-stats'], { cwd: root, env: process.env, stdio: ['ignore', 'inherit', 'inherit'] });
  const terminate = () => { interrupted = true; child.kill('SIGTERM'); };
  process.once('SIGTERM', terminate); process.once('SIGINT', terminate);
  const timeout = setTimeout(() => { timedOut = true; child.kill('SIGTERM'); }, 10 * 60000);
  const cleanup = () => { clearTimeout(timeout); process.removeListener('SIGTERM', terminate); process.removeListener('SIGINT', terminate); };
  child.once('error', e => { cleanup(); reject(e); });
  child.once('close', c => { cleanup(); resolve(c); });
 });
 if (fs.existsSync(path.join(dir, 'STOP'))) throw Error('STOP exists');
 if (timedOut) throw Error('local_report_fetch_timeout');
 if (interrupted) throw Error('local_report_fetch_interrupted');
 if (code !== 0) throw Error('local_report_fetch_incomplete');
 const document = JSON.parse(fs.readFileSync(file, 'utf8'));
 const feeds = document.feed_status || [];
 if (!feeds.some(x => x.ok)) throw Error('all_report_sources_failed');
 const result = await archiveReports({ file, skipUndated: true, skipUnclassified: true });
 const quality = { checked_at: new Date().toISOString(), last_success_at: new Date().toISOString(), source_generated_at: document.generated_at || null, feeds_ok: feeds.filter(x => x.ok).length, feeds_failed: feeds.filter(x => !x.ok).length, carried_over: feeds.reduce((n,x) => n + (Number(x.carried_over) || 0), 0), skipped_undated: result.skipped_undated, skipped_unclassified: (document.stats?.unclassified || 0) + result.skipped_unclassified, reports: result.reports, status: feeds.some(x => !x.ok) || result.partial ? 'partial' : 'succeeded' };
 const qualityFile = path.join(dir, 'rss-quality.json');
 fs.writeFileSync(qualityFile + '.tmp', JSON.stringify(quality, null, 2), { mode: 0o600 }); fs.renameSync(qualityFile + '.tmp', qualityFile);
 await updateSyncState(HEALTH_RESOURCE, quality);
 console.log(JSON.stringify({ ...result, feeds_ok: feeds.filter(x => x.ok).length, feeds_failed: feeds.filter(x => !x.ok).length, source: 'mac_official_feeds' }));
}
main().catch(async error => { const known=['STOP exists','local_report_fetch_incomplete','local_report_fetch_timeout','local_report_fetch_interrupted','all_report_sources_failed','invalid_report_rows']; const reason=known.includes(error.message)?error.message:(error.code==='ENOENT'?'python_runtime_unavailable':'archive_or_fetch_failed'); const qualityFile=path.join(os.homedir(),'Documents/policy-downloads/mac-20260930/rss-quality.json');try{let previous={};if(fs.existsSync(qualityFile))previous=JSON.parse(fs.readFileSync(qualityFile,'utf8'));fs.writeFileSync(qualityFile+'.tmp',JSON.stringify({...previous,status:'failed',checked_at:new Date().toISOString(),reason},null,2),{mode:0o600});fs.renameSync(qualityFile+'.tmp',qualityFile)}catch{}try{await checkpointSyncState(HEALTH_RESOURCE,{status:'failed',checked_at:new Date().toISOString(),reason})}catch{}console.error(JSON.stringify({event:'local_mailing_report_sync_failed',reason})); process.exitCode = 1; });
