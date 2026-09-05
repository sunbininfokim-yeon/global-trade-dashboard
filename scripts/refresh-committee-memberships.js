'use strict';

// 상임위 roster 정기 갱신 진입점.
// 1분기(1–3월)는 매월, 2·3·4분기는 4·7·10월에만 공식 원천을 다시 받는다.
// GitHub Actions YAML은 Claude 소유이므로 이 스크립트만 호출하면 된다.
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {
  ROOT,
  COMMITTED_JSON_PATH,
  ROSTER_REFRESH_MONTHS,
  shouldRefreshCommitteeRoster,
} = require('./lib/committee-membership-roster');

function runNode(script) {
  const result = spawnSync(process.execPath, [path.join(__dirname, script)], {
    cwd: ROOT,
    env: process.env,
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}

function main() {
  const force = process.env.FORCE_COMMITTEE_ROSTER_REFRESH === 'true' || process.argv.includes('--force');
  const now = new Date();
  if (!force && !shouldRefreshCommitteeRoster(now)) {
    console.log(`Committee roster refresh skipped: UTC month ${now.getUTCMonth() + 1} is outside ${ROSTER_REFRESH_MONTHS.join(',')}.`);
    return;
  }

  const before = fs.existsSync(COMMITTED_JSON_PATH) ? fs.readFileSync(COMMITTED_JSON_PATH, 'utf8') : '';
  runNode('fetch-committee-membership-rosters.js');
  runNode('build-committee-memberships.js');
  runNode('lib/committee-membership-source.test.js');

  if (!fs.existsSync(COMMITTED_JSON_PATH) || before !== fs.readFileSync(COMMITTED_JSON_PATH, 'utf8')) {
    console.log('Committee roster JSON changed. Open a review PR; do not merge without checking bioguide IDs.');
    process.exitCode = 2;
    return;
  }
  console.log('Committee roster JSON unchanged.');
}

main();
