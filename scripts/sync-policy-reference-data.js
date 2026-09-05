'use strict';

// One scheduler entry point for policy reference data. The scheduler (local
// initially, GitHub Actions after backfill) invokes this; each child script
// records its own source-specific run and sync state in Supabase.
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const scripts = ['sync-us-legislators.js', 'sync-committees.js', 'sync-committee-memberships.js'];
for (const script of scripts) {
  const result = spawnSync(process.execPath, [path.join(__dirname, script)], {
    cwd: path.resolve(__dirname, '..'),
    env: process.env,
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}

console.log('Policy reference data complete: legislator roster, committee directory, and any verified committee membership source are current.');
