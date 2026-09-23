import { escapeHtml, formatDate, stateLabel } from '../../ui.js';
import { countryEvents } from '../../data/selectors.js';
import { hemicycle, seatLegend, seatingOrder } from './hemicycle.js';
import { chamberSwitch } from './chamber-switch.js';
import { jpnColorScale, jpnPartyKo, jpnPartyLabel, jpnPerson } from './jpn.js';

// 국회 화면. 미국 의회 화면과 같은 4분면 + 정당 카드 구조이고, 원만 중의원/참의원으로
// 바뀐다 -- "의회나 행정부나 다 우측 대시보드는 고정" 이라는 요청 그대로다.
//
// 미국 화면과 다른 칸이 하나 있다. 미국은 좌하단이 상임위 칩이지만, 일본 상임위는
// 매니페스트가 legislature_detail.missing 으로 committees·committee_chairs 를
// 명시하고 있어 아직 없다. 빈 상임위 칸을 만들어 두는 대신 의원내각제에서 그 자리에
// 해당하는 것 -- 내각을 떠받치는 과반 계산 -- 을 넣고, 상임위는 미수집이라고 적는다.

const CHAMBERS = [
    { key: 'shugiin', ko: '중의원', seatKey: 'shugiin_by_party_abbr', leadershipKey: 'house_of_representatives' },
    { key: 'sangiin', ko: '참의원', seatKey: 'sangiin_by_abbr', leadershipKey: 'house_of_councillors' },
];

const seatEntries = (byParty) => Object.entries(byParty || {})
    .filter(([, seats]) => Number.isFinite(seats) && seats > 0)
    .sort((a, b) => b[1] - a[1]);

const total = (entries) => entries.reduce((sum, [, seats]) => sum + seats, 0);

const groupsFor = (entries, color) => seatingOrder(entries)
    .map(([abbr, seats]) => ({ label: jpnPartyKo(abbr), count: seats, color: color(abbr) }));

const leadershipPanel = (rows, color) => (rows.length
    ? `<div class="elections-disclosure-rows elections-leader-rows">${rows.map((row) => `<div>
            <span>${escapeHtml(row.office_ko || row.office || '직책')}</span>
            <strong><i class="elections-party-dot" style="background:${color(row.party_abbr)}"></i>${escapeHtml([jpnPerson(row) || '불명', row.party_abbr ? jpnPartyLabel(row.party_abbr) : ''].filter(Boolean).join(' · '))}</strong>
            ${row.note ? `<em class="elections-person-mark">${escapeHtml(row.note)}</em>` : ''}
        </div>`).join('')}</div>`
    : '<p class="elections-muted">공개된 의장단 명부가 없습니다.</p>');

// 과반선은 공개 회파표 합계에서 계산한다. 참의원처럼 합계가 정수(定数)에 못 미치는
// 원이 있어서, 어느 수를 기준으로 잡은 것인지 항상 같이 적는다 -- 모자란 의석을
// 임의로 채워 과반선을 "고쳐" 놓으면 그게 틀린 숫자가 된다.
const majorityPanel = (chamber, entries, rulingAbbr, declaredSeats) => {
    const seats = total(entries);
    if (!seats) return '<p class="elections-muted">공개 의석 집계가 없습니다.</p>';
    const line = Math.floor(seats / 2) + 1;
    const ruling = entries.find(([abbr]) => abbr === rulingAbbr)?.[1];
    const gap = Number.isFinite(ruling) ? ruling - line : null;
    return `
        <div class="elections-card-grid">
            <article class="elections-card"><div class="elections-card-label">집계 의석</div><div class="elections-card-value">${seats}석</div>${
                Number.isFinite(declaredSeats) && declaredSeats !== seats
                    ? `<div class="elections-event-meta">${escapeHtml(`공개 정수 ${declaredSeats}석과 다름`)}</div>`
                    : ''}</article>
            <article class="elections-card"><div class="elections-card-label">과반선</div><div class="elections-card-value">${line}석</div><div class="elections-event-meta">집계 의석 기준</div></article>
            <article class="elections-card"><div class="elections-card-label">${escapeHtml(rulingAbbr ? `${jpnPartyKo(rulingAbbr)} 단독` : '집권 회파')}</div><div class="elections-card-value">${escapeHtml(Number.isFinite(ruling) ? `${ruling}석` : '집계 없음')}</div>${
                gap === null ? '' : `<div class="elections-event-meta">${escapeHtml(gap >= 0 ? `과반 +${gap}석` : `과반까지 ${-gap}석`)}</div>`}</article>
        </div>
        <p class="elections-panel-note">연립 상대 회파를 데이터가 따로 표시하지 않아 연립 합계는 내지 않습니다. 위 수치는 ${escapeHtml(jpnPartyKo(rulingAbbr))} 단독 의석입니다.</p>
        <p class="elections-panel-note">${escapeHtml(chamber.ko)} 상임위원회 명부는 아직 수집 대상이 아닙니다(위원회·위원장·위원 명부 미확보).</p>`;
};

const schedulePanel = (country, chamber) => {
    const events = countryEvents(country).slice(0, 6);
    return `
        ${events.length
        ? `<div class="elections-disclosure-rows">${events.map((event) => `<div>
                <span>${escapeHtml(formatDate(event.date))}</span>
                <strong>${escapeHtml(event.label_ko || event.label_en || '일정')}</strong>
                <em class="elections-person-mark">${escapeHtml(stateLabel(event.status))}</em>
            </div>`).join('')}</div>`
        : '<p class="elections-muted">공개된 일정 행이 없습니다.</p>'}
        <p class="elections-panel-note">${escapeHtml(chamber.key === 'shugiin'
        ? '중의원은 임기 4년이지만 해산이 있어 만료일이 곧 선거일은 아닙니다.'
        : '참의원은 3년마다 절반을 새로 뽑습니다. 해산은 없습니다.')}</p>`;
};

const partyCard = (abbr, seats, { seatsTotal, leadership, factions, color }) => {
    const leaders = leadership.filter((row) => row.party_abbr === abbr);
    const share = seatsTotal ? ((seats / seatsTotal) * 100).toFixed(1) : null;
    return `
        <article class="elections-party-card">
            <header class="elections-party-card-head">
                <i class="elections-party-dot" style="background:${color(abbr)}"></i>
                <strong>${escapeHtml(jpnPartyKo(abbr))}</strong>
                <span>${escapeHtml(`${seats}석`)}</span>
            </header>

            <p class="elections-party-card-label">1 · 의석</p>
            <div class="elections-disclosure-rows">
                <div><span>회파 약칭</span><strong>${escapeHtml(abbr)}</strong></div>
                <div><span>의석 점유</span><strong>${escapeHtml(share === null ? '집계 없음' : `${share}%`)}</strong></div>
            </div>

            <p class="elections-party-card-label">2 · 이 원의 당직자</p>
            ${leaders.length
        ? `<div class="elections-disclosure-rows">${leaders.map((row) => `<div><span>${escapeHtml(row.office_ko || '직책')}</span><strong>${escapeHtml(jpnPerson(row) || '불명')}</strong></div>`).join('')}</div>`
        : '<p class="elections-muted">이 회파의 공개 의장단 기록이 없습니다.</p>'}

            <p class="elections-party-card-label">3 · 계파 분류</p>
            ${factions || '<p class="elections-muted">이 회파의 파벌 데이터는 수집 대상이 아닙니다.</p>'}
        </article>`;
};

// 파벌 데이터는 자민당 하나뿐이고(factions.party_abbr), 다른 당은 데이터 자체가
// "없음" 이라고 적고 있다. 그 구분을 카드에서 지우지 않는다.
const factionSummary = (factions, abbr) => {
    if (!factions || factions.party_abbr !== abbr) return '';
    const rows = (factions.factions || []).map((faction) => {
        // n_approx_latest 는 세어진 경우에만 숫자이고, 아니면 "불명" 이라는 문자열로
        // 온다. 문자열을 숫자 자리에 그대로 흘리면 "불명명" 같은 글자가 나온다.
        const count = Number.isFinite(faction.n_approx_latest) ? `약 ${faction.n_approx_latest}명` : '집계 없음';
        return `<div>
            <span>${escapeHtml(`${faction.name_ko || faction.abbr}${faction.spectrum_ko && faction.spectrum_ko !== '불명' ? ` · ${faction.spectrum_ko}` : ''}`)}</span>
            <strong>${escapeHtml(count)}</strong>
        </div>`;
    });
    if (!rows.length) return '';
    return `<details class="elections-disclosure"><summary>파벌 ${rows.length}곳</summary><div class="elections-disclosure-rows">${rows.join('')}</div></details>
        <p class="elections-panel-note">2024년 파벌 해산 이후 공식 파벌은 일부만 남아 있어 합산하지 않습니다. 자세한 분류는 파벌 화면에 있습니다.</p>`;
};

const chamberPanel = (country, chamber, legislature) => {
    const color = jpnColorScale();
    const entries = seatEntries(legislature[chamber.seatKey]);
    const groups = groupsFor(entries, color);
    const leadership = (legislature.chamber_leadership || []).filter((row) => row.chamber === chamber.leadershipKey);
    const rulingAbbr = country.ruling_party?.abbr;
    const seatsTotal = total(entries);
    const declared = chamber.key === 'shugiin' ? legislature.shugiin_members : null;
    // 여당과 제1야당 두 장. 미국 화면이 소수당·다수당 두 장을 내는 자리와 같다.
    const cardAbbrs = [
        entries.find(([abbr]) => abbr === rulingAbbr),
        entries.find(([abbr]) => abbr !== rulingAbbr),
    ].filter(Boolean);

    return `
        <div class="elections-chamber-quadrants">
            <section class="elections-quadrant">
                <p class="section-title">의장 · 부의장</p>
                ${leadershipPanel(leadership, color)}
            </section>
            <section class="elections-quadrant">
                <p class="section-title">의석 분포</p>
                ${hemicycle(groups) || '<p class="elections-muted">공개 의석 집계가 없습니다.</p>'}
                ${groups.length ? seatLegend(groups) : ''}
            </section>
            <section class="elections-quadrant">
                <p class="section-title">과반 · 상임위</p>
                ${majorityPanel(chamber, entries, rulingAbbr, declared)}
            </section>
            <section class="elections-quadrant">
                <p class="section-title">선거 일정</p>
                ${schedulePanel(country, chamber)}
            </section>
        </div>
        <div class="elections-party-card-grid">
            ${cardAbbrs.map(([abbr, seats]) => partyCard(abbr, seats, {
        seatsTotal, leadership, color, factions: factionSummary(country.factions, abbr),
    })).join('')}
        </div>`;
};

export const jpnLegislature = (country) => {
    const legislature = country.legislature_live;
    if (!legislature) return null;
    const panels = CHAMBERS.map((chamber) => {
        const entries = seatEntries(legislature[chamber.seatKey]);
        return {
            label: `${chamber.ko}${entries.length ? ` ${total(entries)}석` : ''}`,
            panel: chamberPanel(country, chamber, legislature),
        };
    });
    return `
        ${chamberSwitch(panels)}
        <p class="elections-panel-note">의석은 원내 회파(교섭단체) 기준입니다. 무소속·소회파가 큰 회파에 묶여 신고되면 정당 의석과 어긋날 수 있어, 공개 회파표를 그대로 표시합니다.</p>
        ${legislature.leadership_source?.url ? `<p class="elections-panel-note">의장단 출처: ${escapeHtml(legislature.leadership_source.url)}</p>` : ''}
    `;
};
