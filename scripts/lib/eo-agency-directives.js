'use strict';

// EO 원문에서 기관 관계를 만들 때는 역할어와 명령 표현이 함께 있는 경우만
// 허용한다. 제목·키워드·LLM 추정으로 기관을 연결하면 발령 주체(EOP)와 실제
// 시행 기관을 혼동할 수 있으므로, 항상 원문 인용문을 함께 보존한다.
const { supabaseGet, supabaseUpsert } = require('./sync-utils');

const ROLE_PATTERN = [
  'Secretary\\s+of\\s+(?:the\\s+)?[A-Za-z][A-Za-z .,&\\-]+?',
  'Attorney\\s+General',
  'Administrator\\s+of\\s+(?:the\\s+)?[A-Za-z][A-Za-z .,&\\-]+?',
  'Director\\s+of\\s+(?:the\\s+)?[A-Za-z][A-Za-z .,&\\-]+?',
  'United\\s+States\\s+Trade\\s+Representative',
].join('|');

function plainText(value) {
  return String(value || '')
    .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"')
    .replace(/&#(?:x[0-9a-f]+|\d+);/gi, ' ')
    .replace(/\s+/g, ' ').trim();
}

function normalized(value) {
  return plainText(value).toLowerCase()
    .replace(/\bthe\b/g, ' ')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ').trim();
}

function addAlias(map, alias, agencyId) {
  const key = normalized(alias);
  if (!key) return;
  const existing = map.get(key);
  // 같은 약칭이 여러 기관을 뜻하면 연결하지 않는다. 애매한 약칭보다 누락이
  // 안전하며, 원문과 공식 ID가 확인된 별도 별칭을 나중에 추가할 수 있다.
  if (existing === undefined) map.set(key, agencyId);
  else if (existing !== agencyId) map.set(key, null);
}

function agencyAliasMap(agencies) {
  const aliases = new Map();
  for (const agency of agencies || []) {
    if (!agency?.agency_id) continue;
    for (const value of [agency.name, agency.short_name]) addAlias(aliases, value, agency.agency_id);
    const name = normalized(agency.name);
    if (name.startsWith('department of ')) addAlias(aliases, name.slice('department of '.length), agency.agency_id);
  }
  return aliases;
}

function roleCandidates(role) {
  const value = normalized(role);
  if (!value) return [];
  if (value === 'attorney general') return ['department of justice', 'justice'];
  if (value === 'united states trade representative') {
    return ['office of the united states trade representative', 'united states trade representative'];
  }
  const matched = value.match(/^(?:secretary|administrator|director) of (.+)$/);
  if (!matched) return [value];
  const agency = matched[1];
  return [agency, `department of ${agency}`, `office of ${agency}`];
}

function resolveRole(role, aliases) {
  for (const candidate of roleCandidates(role)) {
    const agencyId = aliases.get(normalized(candidate));
    if (agencyId) return agencyId;
  }
  return null;
}

function excerptAt(source, index) {
  const before = source.slice(0, Math.max(0, index));
  const boundary = Math.max(before.lastIndexOf('.'), before.lastIndexOf(';'), before.lastIndexOf(':'));
  const start = Math.max(0, boundary + 1);
  const after = source.slice(index);
  const endMatch = after.search(/[.;](?:\s|$)/);
  const end = endMatch < 0 ? Math.min(source.length, index + 1_000) : index + endMatch + 1;
  return source.slice(start, end).trim().slice(0, 1_200);
}

function addDirective(output, aliases, role, relationshipType, source, index, evidenceSection) {
  const agencyId = resolveRole(role, aliases);
  if (!agencyId) return;
  output.push({
    agency_id: agencyId,
    relationship_type: relationshipType,
    evidence_excerpt: excerptAt(source, index),
    evidence_section: evidenceSection,
  });
}

function parseExecutiveOrderAgencyDirectives(value, agencies) {
  const source = plainText(value);
  if (!source) return [];
  const aliases = agencyAliasMap(agencies);
  const output = [];
  const command = new RegExp(`\\b(?:the\\s+)?(${ROLE_PATTERN})\\s*(?:,\\s*)?(?:shall|must|is\\s+(?:hereby\\s+)?directed\\s+to)\\b`, 'gi');
  for (const match of source.matchAll(command)) {
    addDirective(output, aliases, match[1], 'directed_agency', source, match.index, 'directive');
  }

  // "in consultation with"는 최종 지휘 권한을 뜻하지 않는다. 별도 역할로
  // 저장해 화면에서 시행 기관과 협의 기관을 구분할 수 있게 한다.
  const consultation = new RegExp(`\\b(?:in\\s+consultation\\s+with|consulting\\s+with)\\s+(?:the\\s+)?(${ROLE_PATTERN})\\b`, 'gi');
  for (const match of source.matchAll(consultation)) {
    addDirective(output, aliases, match[1], 'consulted_agency', source, match.index, 'consultation');
  }

  const coordination = new RegExp(`\\b(?:in\\s+coordination\\s+with|coordinate\\s+with)\\s+(?:the\\s+)?(${ROLE_PATTERN})\\b`, 'gi');
  for (const match of source.matchAll(coordination)) {
    addDirective(output, aliases, match[1], 'coordinating_agency', source, match.index, 'coordination');
  }

  const seen = new Set();
  return output.filter((item) => {
    const key = `${item.agency_id}:${item.relationship_type}:${item.evidence_excerpt.toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function saveEoAgencyDirectives(eoNumber, officialText, sourceUrl) {
  if (!officialText) return 0;
  const agencies = await supabaseGet('agencies', {
    select: 'agency_id,name,short_name', order: 'name.asc', limit: '2000',
  });
  const directives = parseExecutiveOrderAgencyDirectives(officialText, agencies);
  for (const directive of directives) {
    await supabaseUpsert('executive_order_agencies', [{
      eo_number: eoNumber,
      agency_id: directive.agency_id,
      relationship_type: directive.relationship_type,
      relation_origin: 'official_text_citation',
      source_url: sourceUrl || null,
      evidence_excerpt: directive.evidence_excerpt,
      evidence_section: directive.evidence_section,
    }], 'eo_number,agency_id,relationship_type,relation_origin');
  }
  return directives.length;
}

module.exports = {
  agencyAliasMap,
  parseExecutiveOrderAgencyDirectives,
  saveEoAgencyDirectives,
};
