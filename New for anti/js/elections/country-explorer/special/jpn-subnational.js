import { escapeHtml } from '../../ui.js';
import { card, disclosure, noteLine } from './org-chart.js';

// 지도 블록 옆에 상시로 붙는 47개 도도부현 요약. 미국의 주 대시보드에 해당하는
// 자리지만, 일본 쪽은 지사 명부까지만 있고 현의회 의석은 매니페스트가
// subnational_map.missing 에 prefectural_assembly_detail 로 못박아 두었다.
//
// 일본 지사 45명이 무소속으로 신고돼 있는 것은 데이터 누락이 아니라 실제 관행이다
// (여러 당의 추천을 함께 받아 무소속으로 출마). 그래서 "정당 불명"이 아니라
// 신고 그대로 무소속으로 세고, 추천 정당은 이 데이터에 없다고 적는다 -- 무소속
// 45명을 어느 당으로 배분하는 순간 그건 없는 사실을 만드는 것이다.

const INDEPENDENT = '無所属';

const monthsAhead = (isoDate, months) => {
    const end = Date.parse(isoDate);
    if (Number.isNaN(end)) return false;
    const limit = new Date();
    limit.setMonth(limit.getMonth() + months);
    return end <= limit.getTime();
};

export const jpnSubnational = (country) => {
    const live = country.subnational_live;
    const governors = live?.governors;
    if (!Array.isArray(governors) || !governors.length) return null;

    const byParty = new Map();
    governors.forEach((row) => {
        const key = row.party || '신고 없음';
        byParty.set(key, (byParty.get(key) || 0) + 1);
    });
    const independents = byParty.get(INDEPENDENT) || 0;
    const partyRows = [...byParty.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([party, count]) => `<div><span>${escapeHtml(party === INDEPENDENT ? '무소속 신고' : party)}</span><strong>${count}명</strong></div>`);

    const expiring = governors
        .filter((row) => row.term_end && monthsAhead(row.term_end, 12))
        .sort((a, b) => String(a.term_end).localeCompare(String(b.term_end)));
    const expiringRows = expiring.map((row) => `<div>
        <span>${escapeHtml(row.prefecture || '도도부현')}</span>
        <strong>${escapeHtml(row.name || '불명')}</strong>
        <em class="elections-person-mark">${escapeHtml(`${row.term_end} 만료`)}</em>
    </div>`);

    return `
        <div class="elections-card-grid">
            ${card('도도부현 지사', `${governors.length}명`)}
            ${card('무소속 신고', `${independents}명`, independents ? '추천 정당은 이 데이터에 없음' : '')}
            ${card('1년 내 임기 만료', `${expiring.length}곳`, expiring.length ? `가장 이른 만료 ${expiring[0].term_end}` : '')}
        </div>
        ${disclosure(`정당 신고 ${partyRows.length}종`, partyRows)}
        ${disclosure(`1년 내 임기 만료 ${expiringRows.length}곳`, expiringRows)}
        ${noteLine('일본 지사는 여러 당의 추천을 함께 받아 무소속으로 출마하는 경우가 많습니다. 무소속 신고를 특정 정당으로 배분하지 않습니다.')}
        ${noteLine('현의회 의석 구성은 아직 수집 대상이 아닙니다(도도부현 단위 집행부만 확보).')}
        ${live.source?.url ? noteLine(`출처: ${live.source.url}${live.source.grade ? ` · ${live.source.grade}` : ''}`) : ''}
    `;
};
