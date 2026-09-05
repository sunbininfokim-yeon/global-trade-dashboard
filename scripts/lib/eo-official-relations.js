'use strict';

const { loadOfficialEoText, saveEoAuthorities } = require('./eo-authorities');
const { saveEoAgencyDirectives } = require('./eo-agency-directives');

async function saveOfficialEoTextRelations(eoNumber, document, options = {}) {
  // 같은 원문을 법령 근거와 기관 역할 파서가 함께 사용한다. 캐시 전용 모드는
  // Federal Register에 요청하지 않으므로 차단 중인 역사 데이터에도 안전하다.
  const officialText = await loadOfficialEoText(document, options);
  const authorityLinks = await saveEoAuthorities(eoNumber, document, officialText);
  const agencyLinks = officialText?.text
    ? await saveEoAgencyDirectives(eoNumber, officialText.text, officialText.official_url)
    : 0;
  return { authorityLinks, agencyLinks, usedOfficialText: Boolean(officialText?.text) };
}

module.exports = { saveOfficialEoTextRelations };
