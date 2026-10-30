'use strict';
// Preloaded in the actual task process. If the supervisor crashes, its orphan
// cannot overlap a newly restarted task because it still owns this lock.
const path = require('node:path');
const os = require('node:os');
const { acquireLock, releaseLock } = require('./policy-mac-lock');
const lock = path.join(os.tmpdir(), 'chokemonitor-policy-task.lock');
acquireLock(lock, { pid: process.pid, started_at: new Date().toISOString() });
process.once('exit', () => releaseLock(lock, process.pid));
