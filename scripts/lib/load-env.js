'use strict';

// Local dev convenience only. CI (GitHub Actions) and any real deployment set
// environment variables directly, so this never runs there in any meaningful
// way -- .env.local simply won't exist on that machine. Locally, it lets a
// non-technical operator fill in three values once in a text file instead of
// re-exporting them in every new terminal.
//
// Intentionally dependency-free (no npm package, no `npm install` step): the
// parser only needs to handle KEY=VALUE lines, which plain fs/string code
// does in a dozen lines.

const fs = require('node:fs');
const path = require('node:path');

// Never print a key name or value -- only whether the file existed and how
// many lines it filled in, which is enough for an operator to tell the file
// was found without echoing anything secret to a terminal or CI log.
function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return 0;
  const contents = fs.readFileSync(filePath, 'utf8');
  let filled = 0;
  for (const rawLine of contents.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (!key) continue;
    // Strip one layer of matching quotes, the way a shell would, so a value
    // copied from somewhere that quoted it still comes through clean.
    if (value.length >= 2 && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))) {
      value = value.slice(1, -1);
    }
    // A real environment variable -- an actual export, or a CI secret --
    // always wins over the file. This never overwrites one that is already set.
    if (!(key in process.env)) {
      process.env[key] = value;
      filled += 1;
    }
  }
  return filled;
}

let loaded = false;

function loadLocalEnv() {
  if (loaded) return; // module-cached: every script's require() only pays for the read once
  loaded = true;
  const root = path.resolve(__dirname, '..', '..');
  // .env.local first so it wins if both exist; loadEnvFile's "don't
  // overwrite" rule means .env only ever fills gaps .env.local left open.
  const filled = loadEnvFile(path.join(root, '.env.local')) + loadEnvFile(path.join(root, '.env'));
  if (filled > 0) console.log(`Loaded ${filled} value(s) from a local .env file (not logging names or values).`);
}

module.exports = { loadLocalEnv, loadEnvFile };
