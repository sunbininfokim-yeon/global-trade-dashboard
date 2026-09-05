'use strict';

// Builds data/policy/committee-memberships.json from official House/Senate
// rosters. Committee IDs use Congress.gov system codes so they match
// scripts/sync-committees.js. This script never guesses a bioguide from a name.
const fs = require('node:fs');
const path = require('node:path');
const { officialSourceUrl, parseCommitteeMembershipSource } = require('./lib/committee-membership-source');

const ROOT = path.resolve(__dirname, '..');
const HOUSE_XML = path.resolve(ROOT, process.env.HOUSE_MEMBER_DATA_XML || '.cache/official-rosters/MemberData.xml');
const SENATE_JSON = path.resolve(ROOT, process.env.SENATE_CVC_JSON || '.cache/official-rosters/senate-cvc-memberships.json');
const OUT = path.resolve(ROOT, process.env.COMMITTEE_MEMBERSHIP_SOURCE_FILE || 'data/policy/committee-memberships.json');
const CONGRESS = 119;
const HOUSE_SOURCE_URL = 'https://clerk.house.gov/xml/lists/MemberData.xml';
const SENATE_SOURCE_URL = 'https://www.senate.gov/legislative/LIS_MEMBER/cvc_member_data.xml';

// Verified against https://www.congress.gov/committees on 2026-09-06.
const HOUSE_CLERK_TO_CONGRESS = {
  AG00: ['house', 'hsag00'],
  AP00: ['house', 'hsap00'],
  AS00: ['house', 'hsas00'],
  BA00: ['house', 'hsba00'],
  BU00: ['house', 'hsbu00'],
  EC00: ['joint', 'jsec00'],
  ED00: ['house', 'hsed00'],
  FA00: ['house', 'hsfa00'],
  GO00: ['house', 'hsgo00'],
  HA00: ['house', 'hsha00'],
  HM00: ['house', 'hshm00'],
  IF00: ['house', 'hsif00'],
  IG00: ['house', 'hlig00'],
  II00: ['house', 'hsii00'],
  IT00: ['joint', 'jstx00'],
  JL00: ['joint', 'jslc00'],
  JP00: ['joint', 'jspr00'],
  JU00: ['house', 'hsju00'],
  PW00: ['house', 'hspw00'],
  RU00: ['house', 'hsru00'],
  SM00: ['house', 'hssm00'],
  SO00: ['house', 'hsso00'],
  SY00: ['house', 'hssy00'],
  VR00: ['house', 'hsvr00'],
  WM00: ['house', 'hswm00'],
  ZS00: ['house', 'hlzs00'],
};

const SENATE_ALLOWED = new Set([
  'jcse00', 'jsec00', 'jslc00', 'jspr00', 'jstx00',
  'scnc00', 'slet00', 'slia00', 'slin00', 'spag00',
  'ssaf00', 'ssap00', 'ssas00', 'ssbk00', 'ssbu00', 'sscm00', 'sseg00',
  'ssev00', 'ssfi00', 'ssfr00', 'ssga00', 'sshr00', 'ssju00', 'ssra00',
  'sssb00', 'ssva00',
]);

const HOUSE_LEADERSHIP = {
  Chair: 'chair',
  Chairman: 'chair',
  Chairwoman: 'chair',
  'Vice Chair': 'vice_chair',
  'Vice Chairman': 'vice_chair',
  'Vice Chairwoman': 'vice_chair',
  'Ranking Member': 'ranking_member',
  Ranking: 'ranking_member',
  'Ex Officio': 'ex_officio',
};

const SENATE_POSITION = {
  Member: 'member',
  Chairman: 'chair',
  Chairwoman: 'chair',
  Chair: 'chair',
  'Vice Chairman': 'vice_chair',
  'Vice Chair': 'vice_chair',
  'Vice Chairwoman': 'vice_chair',
  Ranking: 'ranking_member',
  'Ranking Member': 'ranking_member',
  'Ex Officio': 'ex_officio',
};

const MONTHS = {
  january: '01', february: '02', march: '03', april: '04', may: '05', june: '06',
  july: '07', august: '08', september: '09', october: '10', november: '11', december: '12',
};

function isoDay(value) {
  const match = String(value || '').trim().match(
    /(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})/,
  );
  if (!match) return null;
  const month = MONTHS[match[1].toLowerCase()];
  if (!month) return null;
  return `${match[3]}-${month}-${String(match[2]).padStart(2, '0')}T00:00:00Z`;
}

function senateChamber(code) {
  const lower = String(code || '').toLowerCase();
  if (lower.startsWith('js') || lower.startsWith('jc')) return 'joint';
  if (lower.startsWith('ss') || lower.startsWith('sl') || lower.startsWith('sp') || lower.startsWith('sc')) return 'senate';
  return null;
}

function record(partial) {
  const sourceUrl = officialSourceUrl(partial.source_url);
  if (!sourceUrl) throw new Error(`non-official source_url: ${partial.source_url}`);
  return {
    committee_id: partial.committee_id,
    bioguide_id: String(partial.bioguide_id).trim().toUpperCase(),
    role: partial.role,
    source_url: sourceUrl,
    source_updated_at: partial.source_updated_at,
    raw_source: partial.raw_source,
  };
}

function houseRecords(xml, sourceUpdatedAt) {
  const minority = String(xml.match(/<minority>([^<]+)<\/minority>/)?.[1] || '').trim();
  const rows = [];
  for (const memberBlock of xml.split('<member>').slice(1)) {
    const bioguide = String(memberBlock.match(/<bioguideID>([^<]*)<\/bioguideID>/)?.[1] || '').trim().toUpperCase();
    const caucus = String(memberBlock.match(/<caucus>([^<]*)<\/caucus>/)?.[1] || '').trim();
    const assignBlock = memberBlock.match(/<committee-assignments>([\s\S]*?)<\/committee-assignments>/)?.[1] || '';
    if (!bioguide || !assignBlock) continue;
    for (const tag of assignBlock.match(/<committee\b[^>]*>/g) || []) {
      const clerkCode = String(tag.match(/comcode="([^"]+)"/)?.[1] || '').trim().toUpperCase();
      const mapped = HOUSE_CLERK_TO_CONGRESS[clerkCode];
      if (!mapped) continue;
      const [chamber, systemCode] = mapped;
      const leadership = tag.match(/leadership="([^"]+)"/)?.[1] || '';
      const rank = tag.match(/rank="([^"]+)"/)?.[1] || '';
      let role = HOUSE_LEADERSHIP[leadership] || 'member';
      let roleBasis = leadership ? 'clerk_leadership_attribute' : 'committee_assignment';
      if (!HOUSE_LEADERSHIP[leadership] && rank === '1' && minority && caucus === minority) {
        role = 'ranking_member';
        roleBasis = 'clerk_minority_rank_1';
      }
      rows.push(record({
        committee_id: `${CONGRESS}-${chamber}-${systemCode}`,
        bioguide_id: bioguide,
        role,
        source_url: HOUSE_SOURCE_URL,
        source_updated_at: sourceUpdatedAt,
        raw_source: {
          official_page_title: 'House Member Data XML (Clerk of the House)',
          clerk_comcode: clerkCode,
          congress_gov_system_code: systemCode,
          chamber,
          clerk_rank: rank || null,
          clerk_leadership: leadership || null,
          caucus,
          role_basis: roleBasis,
        },
      }));
    }
  }
  return rows;
}

function senateRecords(source, sourceUpdatedAt) {
  const rows = [];
  for (const item of source.rows || []) {
    const systemCode = String(item.committee_code || '').trim().toLowerCase();
    if (!SENATE_ALLOWED.has(systemCode)) continue;
    const chamber = senateChamber(systemCode);
    const role = SENATE_POSITION[item.position] || null;
    if (!chamber || !role || !item.bioguide_id) continue;
    rows.push(record({
      committee_id: `${CONGRESS}-${chamber}-${systemCode}`,
      bioguide_id: item.bioguide_id,
      role,
      source_url: SENATE_SOURCE_URL,
      source_updated_at: sourceUpdatedAt,
      raw_source: {
        official_page_title: 'Current Senators Information including Full Committee Assignments (Senate LIS CVC)',
        senate_committee_code: String(item.committee_code || '').trim().toUpperCase(),
        congress_gov_system_code: systemCode,
        chamber,
        senate_position: item.position,
        committee_name: item.committee_name || null,
        role_basis: 'cvc_position_attribute',
      },
    }));
  }
  return rows;
}

function main() {
  if (!officialSourceUrl(HOUSE_SOURCE_URL) || !officialSourceUrl(SENATE_SOURCE_URL)) {
    throw new Error('official source URLs failed host validation');
  }
  const houseXml = fs.readFileSync(HOUSE_XML, 'utf8');
  const houseUpdatedAt = isoDay(houseXml.match(/publish-date="([^"]+)"/)?.[1]) || '2026-09-02T00:00:00Z';
  const senate = JSON.parse(fs.readFileSync(SENATE_JSON, 'utf8'));
  const senateUpdatedAt = isoDay(senate.lastUpdate) || '2026-08-12T00:00:00Z';

  const merged = new Map();
  for (const row of [...houseRecords(houseXml, houseUpdatedAt), ...senateRecords(senate, senateUpdatedAt)]) {
    merged.set(`${row.committee_id}:${row.bioguide_id}:${row.role}`, row);
  }
  const records = [...merged.values()].sort((a, b) => (
    a.committee_id.localeCompare(b.committee_id)
    || a.role.localeCompare(b.role)
    || a.bioguide_id.localeCompare(b.bioguide_id)
  ));
  const roles = [...new Set(records.map((row) => row.role))].sort();
  const source = {
    schema_version: 1,
    congress_number: CONGRESS,
    source_name: 'cursor-verified-official-roster',
    source_updated_at: '2026-09-06T00:00:00Z',
    coverage: {
      complete: false,
      roles,
    },
    notes: [
      'Parent committees only. House/Senate subcommittee rosters are omitted because Senate committee-membership XML has no bioguide IDs, and House subcommittee codes were not all confirmed on congress.gov.',
      'House ranking_member is the Clerk XML minority-party rank-1 assignment when the Clerk did not emit a leadership attribute. Majority rank-1 is the labeled chair.',
      'Skipped House QJ00 (not on congress.gov current committee list) and Senate JSIK00 (2024 inaugural joint committee).',
    ],
    records,
  };
  parseCommitteeMembershipSource(source);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, `${JSON.stringify(source, null, 2)}\n`);
  const byRole = Object.fromEntries(roles.map((role) => [role, records.filter((row) => row.role === role).length]));
  console.log(`Wrote ${records.length} records to ${path.relative(ROOT, OUT)}`);
  console.log(JSON.stringify({ coverage: source.coverage, byRole, houseUpdatedAt, senateUpdatedAt }, null, 2));
}

main();
