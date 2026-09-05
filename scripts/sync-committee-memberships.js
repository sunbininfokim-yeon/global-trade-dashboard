'use strict';

// Cursor 또는 사람이 공식 House/Senate roster를 확인해 커밋한 파일만 읽는다.
// 이 스크립트는 웹페이지 이름을 추측하거나 AI 출력만으로 위원장을 만들지 않는다.
const fs = require('node:fs');
const path = require('node:path');
const {
  finishSyncRun, requireEnv, startSyncRun, supabaseGet, supabaseRpc, supabaseUpsert, updateSyncState,
} = require('./lib/sync-utils');
const { parseCommitteeMembershipSource } = require('./lib/committee-membership-source');

const ROOT = path.resolve(__dirname, '..');
const SOURCE_PATH = path.resolve(ROOT, process.env.COMMITTEE_MEMBERSHIP_SOURCE_FILE || 'data/policy/committee-memberships.json');
const RESOURCE = 'official-committee-roster:memberships';

function readSource() {
  if (!fs.existsSync(SOURCE_PATH)) return null;
  try {
    return JSON.parse(fs.readFileSync(SOURCE_PATH, 'utf8'));
  } catch (error) {
    throw new Error(`Committee membership source is not valid JSON: ${error.message}`);
  }
}

function chunks(values, size = 100) {
  const output = [];
  for (let start = 0; start < values.length; start += size) output.push(values.slice(start, start + size));
  return output;
}

async function knownValues(table, column, values) {
  const output = new Set();
  for (const group of chunks([...new Set(values)])) {
    const rows = await supabaseGet(table, { select: column, [column]: `in.(${group.join(',')})`, limit: String(group.length) });
    for (const row of rows || []) output.add(row[column]);
  }
  return output;
}

async function validateForeignKeys(rows) {
  const committees = await knownValues('committees', 'committee_id', rows.map((row) => row.committee_id));
  const legislators = await knownValues('us_legislators', 'bioguide_id', rows.map((row) => row.bioguide_id));
  const unknownCommittee = rows.find((row) => !committees.has(row.committee_id));
  if (unknownCommittee) throw new Error(`Committee membership source references unknown committee_id: ${unknownCommittee.committee_id}`);
  const unknownLegislator = rows.find((row) => !legislators.has(row.bioguide_id));
  if (unknownLegislator) throw new Error(`Committee membership source references unknown bioguide_id: ${unknownLegislator.bioguide_id}`);
}

async function run() {
  const source = readSource();
  if (!source) {
    console.log('Committee memberships skipped: data/policy/committee-memberships.json is not present yet.');
    return;
  }
  requireEnv('SUPABASE_URL');
  requireEnv('SUPABASE_SERVICE_ROLE_KEY');
  const parsed = parseCommitteeMembershipSource(source);
  const runId = await startSyncRun(RESOURCE, {
    congress: parsed.congress,
    coverage: parsed.coverage,
    source_name: parsed.sourceName,
    source_file: path.relative(ROOT, SOURCE_PATH),
  });
  const seenAt = new Date().toISOString();
  try {
    await validateForeignKeys(parsed.rows);
    const rows = parsed.rows.map((row) => ({ ...row, current: true, membership_seen_at: seenAt }));
    await supabaseUpsert('committee_members', rows, 'committee_id,bioguide_id,role,congress_number');
    let retired = 0;
    if (parsed.coverage.complete) {
      // 모든 행의 upsert가 성공한 다음에만 같은 역할 범위의 오래된 행을 비활성화한다.
      // 부분 roster·빈 Cursor 결과가 현직 위원장을 한꺼번에 지우지 못하게 하는 핵심 가드다.
      retired = Number(await supabaseRpc('reconcile_committee_membership_snapshot', {
        p_congress_number: parsed.congress,
        p_roles: parsed.coverage.roles,
        p_seen_at: seenAt,
      })) || 0;
    }
    await updateSyncState(RESOURCE, {
      congress: parsed.congress,
      coverage: parsed.coverage,
      source_name: parsed.sourceName,
      source_file: path.relative(ROOT, SOURCE_PATH),
      records: rows.length,
      retired,
      completed_at: seenAt,
    });
    await finishSyncRun(runId, {
      status: 'succeeded', records_read: rows.length, records_written: rows.length,
      metadata: { congress: parsed.congress, coverage: parsed.coverage, retired, source_name: parsed.sourceName },
    });
    console.log(`Committee memberships complete: ${rows.length} verified records for Congress ${parsed.congress}; ${retired} stale records retired.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', error_summary: error.message });
    throw error;
  }
}

run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
