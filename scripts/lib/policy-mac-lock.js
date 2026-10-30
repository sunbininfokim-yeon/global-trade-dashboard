'use strict';
const fs = require('node:fs');
const path = require('node:path');
function acquireLock(dir, owner, alive = pid => { try { process.kill(pid, 0); return true; } catch (e) { if (e.code === 'ESRCH') return false; throw e; } }) {
 try { fs.mkdirSync(dir, { mode: 0o700 }); }
 catch (e) {
  if (e.code !== 'EEXIST') throw e;
  const recovery = dir + '.recovery';
  try { fs.mkdirSync(recovery, { mode: 0o700 }); } catch { throw Error('collector_lock_recovery_busy'); }
  try {
   if (!fs.lstatSync(dir).isDirectory() || fs.lstatSync(dir).isSymbolicLink()) throw Error('unsafe_collector_lock');
   let previous; try { previous = JSON.parse(fs.readFileSync(path.join(dir, 'owner.json'), 'utf8')); } catch { throw Error('unverified_collector_lock'); }
   if (!Number.isInteger(previous.pid) || previous.pid <= 0 || alive(previous.pid)) throw Error('collector_already_running');
   fs.rmSync(dir, { recursive: true }); fs.mkdirSync(dir, { mode: 0o700 });
   // Publish ownership before releasing the recovery mutex.
   fs.writeFileSync(path.join(dir, 'owner.json'), JSON.stringify(owner), { mode: 0o600 });
  } finally { fs.rmdirSync(recovery); }
 }
 fs.writeFileSync(path.join(dir, 'owner.json'), JSON.stringify(owner), { mode: 0o600 });
}
function releaseLock(dir, pid) {
 try {
  const owner = JSON.parse(fs.readFileSync(path.join(dir, 'owner.json'), 'utf8'));
  if (owner.pid !== pid) return false;
  fs.rmSync(dir, { recursive: true });
  return true;
 } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
}
module.exports = { acquireLock, releaseLock };
