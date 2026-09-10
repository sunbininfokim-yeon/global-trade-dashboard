'use strict';

// 공식 House/Senate roster 캐시 경로와 Senate CVC XML → JSON 변환.
// API 키·비공식 원천은 쓰지 않는다. bioguide는 XML의 bioguideId만 사용한다.
const path = require('node:path');

const ROOT = path.resolve(__dirname, '../..');
const CACHE_DIR = path.resolve(ROOT, process.env.COMMITTEE_ROSTER_CACHE_DIR || '.cache/official-rosters');

const HOUSE_SOURCE_URL = 'https://clerk.house.gov/xml/lists/MemberData.xml';
const SENATE_SOURCE_URL = 'https://www.senate.gov/legislative/LIS_MEMBER/cvc_member_data.xml';
const CONGRESS_COMMITTEES_URL = 'https://www.congress.gov/committees';

const HOUSE_XML_PATH = path.resolve(CACHE_DIR, 'MemberData.xml');
const SENATE_XML_PATH = path.resolve(CACHE_DIR, 'cvc_member_data.xml');
const SENATE_JSON_PATH = path.resolve(CACHE_DIR, 'senate-cvc-memberships.json');

function looksLikeHtmlDenial(text) {
  return /<html[\s>]|access denied/i.test(String(text || '').slice(0, 2000));
}

function isHouseMemberDataXml(text) {
  const xml = String(text || '');
  return /<MemberData\b/.test(xml) && /<bioguideID>/.test(xml) && !looksLikeHtmlDenial(xml);
}

function isSenateCvcXml(text) {
  const xml = String(text || '');
  return /<senators\b/.test(xml) && /<bioguideId>/i.test(xml) && !looksLikeHtmlDenial(xml);
}

// Senate CVC XML을 빌더가 읽는 JSON으로 바꾼다.
// 각 <senator>의 <bioguideId>와 <committee code position>만 옮긴다. 이름은 매칭 키가 아니다.
function parseSenateCvcXml(xml) {
  if (!isSenateCvcXml(xml)) {
    throw new Error(
      `Senate CVC XML이 아닙니다. 브라우저에서 ${SENATE_SOURCE_URL} 을 열어 ${path.relative(ROOT, SENATE_XML_PATH)} 로 저장하세요.`,
    );
  }
  const lastUpdate = String(xml.match(/<lastUpdate>[\s\S]*?<date>([^<]+)<\/date>/)?.[1] || '').trim() || null;
  const rows = [];
  let senatorCount = 0;
  for (const block of xml.split(/<senator\b/i).slice(1)) {
    const bioguide = String(block.match(/<bioguideId>([^<]*)<\/bioguideId>/i)?.[1] || '').trim().toUpperCase();
    if (!bioguide) continue;
    senatorCount += 1;
    const committees = block.match(/<committees>([\s\S]*?)<\/committees>/i)?.[1] || '';
    for (const tag of committees.match(/<committee\b[\s\S]*?<\/committee>/gi) || []) {
      const committeeCode = String(tag.match(/\bcode="([^"]+)"/i)?.[1] || '').trim();
      const position = String(tag.match(/\bposition="([^"]+)"/i)?.[1] || 'Member').trim();
      const committeeName = tag.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
      if (!committeeCode) continue;
      rows.push({
        bioguide_id: bioguide,
        committee_code: committeeCode,
        position,
        committee_name: committeeName,
      });
    }
  }
  if (!rows.length) throw new Error('Senate CVC XML에서 위원회 배정 행을 찾지 못했습니다.');
  return { lastUpdate, senatorCount, rows };
}

// Clerk parent comcode (AG00) → Congress.gov system code (hsag00).
// Subcommittee AG03 → hsag03 only when that system code is on the congress.gov list.
function mapHouseClerkCode(clerkCode, parentMap, allowedSystemCodes) {
  const code = String(clerkCode || '').trim().toUpperCase();
  if (!code) return null;
  if (parentMap[code]) return parentMap[code];
  if (!/^[A-Z]{2}\d{2}$/.test(code) || code.endsWith('00')) return null;
  const parent = parentMap[`${code.slice(0, 2)}00`];
  if (!parent) return null;
  const [chamber, parentSystem] = parent;
  const systemCode = `${String(parentSystem).slice(0, -2)}${code.slice(2).toLowerCase()}`;
  if (!allowedSystemCodes.has(systemCode)) return null;
  return [chamber, systemCode];
}

module.exports = {
  ROOT,
  CACHE_DIR,
  HOUSE_SOURCE_URL,
  SENATE_SOURCE_URL,
  CONGRESS_COMMITTEES_URL,
  HOUSE_XML_PATH,
  SENATE_XML_PATH,
  SENATE_JSON_PATH,
  isHouseMemberDataXml,
  isSenateCvcXml,
  parseSenateCvcXml,
  mapHouseClerkCode,
};
