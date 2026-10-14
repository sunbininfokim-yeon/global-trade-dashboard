import { escapeHtml } from '../../ui.js';
import { ballotPartyLabel, ballotPartyClass, displayPersonName, senateTenureLabel } from '../../data/election-matchups.js';

export const senateCurrentHtml = (state) => {
    const members = [...(state?.federal_delegation?.senators || [])].sort((a,b) => {
        const nonMajor = (m) => !['DEM','GOP','REP'].includes(m.abbr) ? 0 : 1;
        return nonMajor(a) - nonMajor(b) || (a.senate_class || 0) - (b.senate_class || 0);
    });
    return `<div class="elections-senate-current"><h4>현재 의원 · 연방 상원 2석</h4>
        <div class="elections-senate-members">${members.map((m) => `<article class="${ballotPartyClass(m.abbr)}"><small>${escapeHtml(ballotPartyLabel(m.abbr))}</small>
            <strong>${escapeHtml(displayPersonName(m.name))}</strong><small>${escapeHtml(senateTenureLabel(m))} · ${m.up_in_2026 === true ? '이번 선거 대상' : m.up_in_2026 === false ? '이번 선거 없음' : '선거 대상 확인 필요'}${m.senate_class ? ` · Class ${escapeHtml(m.senate_class)}` : ''}</small></article>`).join('')}
        ${members.length < 2 ? `<article><strong>${2-members.length}석 현직 명부 확인 필요</strong></article>` : ''}</div></div>`;
};
