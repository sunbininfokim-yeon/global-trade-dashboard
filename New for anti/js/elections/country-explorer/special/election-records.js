import { escapeHtml } from '../../ui.js';

// 국가 화면의 '선거' 블록. 행정수반 → 의회 → 지방 순으로, 각 직위마다
//   직전 선거(날짜·투표율·결과, 결선이면 1차와 결선을 따로) · 임기 · 다음 선거
// 를 보여 준다. 대통령선거급 쟁점이 조사된 나라는 맨 뒤에 붙는다.
// 자료: public/data/election_records/<ISO3>.json (계약은 docs/ops/ELECTION_RECORDS_REQUEST_20261107.md).
// 숫자를 만들지 않는다: 없는 투표율·득표는 칸을 비우지 않고 '수집 전'이라고 말한다.

const GROUPS = [
    ['executive', '행정수반'],
    ['legislature', '의회'],
    ['local', '지방선거'],
];

const pct = (value) => (typeof value === 'number' ? `${value.toFixed(2).replace(/\.?0+$/, '')}%` : null);
const num = (value) => (typeof value === 'number' ? value.toLocaleString('ko-KR') : null);
const safeUrl = (url) => (typeof url === 'string' && /^https?:\/\//.test(url) ? url : null);
// 선거 기록은 몇 년 전 것도 섞이므로 연도까지 쓴다.
const day = (value) => (value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value.slice(0, 4)}년 ${Number(value.slice(5, 7))}월 ${Number(value.slice(8))}일` : value || null);

const row = (label, value) => (value ? `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>` : '');

const candidateTable = (candidates, basis) => {
    if (!candidates?.length) return '';
    const body = candidates.map((c) => `<tr${c.elected ? ' class="is-elected"' : ''}>
        <td>${escapeHtml(c.name || '불명')}${c.incumbent ? ' <span class="elections-er-tag">현직</span>' : ''}${c.elected ? ' <span class="elections-er-tag is-win">당선</span>' : ''}${c.advanced ? ' <span class="elections-er-tag">결선 진출</span>' : ''}</td>
        <td>${escapeHtml(c.party || '')}</td>
        <td class="num">${escapeHtml(num(c.votes) || '')}</td>
        <td class="num">${escapeHtml(pct(c.vote_pct) || '')}</td>
    </tr>`).join('');
    return `<table class="elections-er-table"><thead><tr><th>후보</th><th>정당</th><th class="num">득표</th><th class="num">득표율</th></tr></thead><tbody>${body}</tbody></table>
        ${basis === 'listed_candidates' ? '<p class="elections-panel-note">득표율은 표에 있는 후보 득표의 합을 분모로 계산했습니다 (공식 득표율과 소수점이 다를 수 있음).</p>' : ''}`;
};

const seatTable = (seats, total) => {
    if (!seats?.length) return '';
    const body = seats.map((s) => `<tr><td>${escapeHtml(s.party_ko || s.party || '불명')}</td>
        <td class="num">${escapeHtml(num(s.seats) || '')}</td><td class="num">${escapeHtml(pct(s.vote_pct) || '')}</td></tr>`).join('');
    return `<table class="elections-er-table"><thead><tr><th>정당</th><th class="num">의석${total ? ` / ${escapeHtml(num(total))}` : ''}</th><th class="num">득표율</th></tr></thead><tbody>${body}</tbody></table>`;
};

const roundBlock = (round, basis) => `
    <div class="elections-er-round">
        <p class="elections-er-round-head">${round.round === 2 ? '결선' : `${round.round || 1}차`}${round.date ? ` · ${escapeHtml(day(round.date))}` : ''}${pct(round.turnout_pct) ? ` · 투표율 ${escapeHtml(pct(round.turnout_pct))}` : ''}</p>
        ${candidateTable(round.candidates, round.vote_pct_basis || basis)}
        ${!round.candidates?.length && round.summary_ko ? `<p>${escapeHtml(round.summary_ko)}</p>` : ''}
    </div>`;

const sources = (list) => {
    const links = (list || []).map(safeUrl).filter(Boolean).slice(0, 4);
    return links.length ? `<p class="elections-panel-note">출처: ${links.map((url, i) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${i + 1}</a>`).join(' · ')}</p>` : '';
};

const recordBody = (rec) => {
    const rounds = rec.rounds?.length ? rec.rounds : null;
    // 결선이 있으면 1차 표에 '결선 진출'을 단다 (결선 표에 이름이 있는 후보).
    if (rounds?.length === 2 && rounds[1].candidates?.length) {
        const finalists = new Set(rounds[1].candidates.map((c) => c.name));
        rounds[0].candidates?.forEach((c) => { if (finalists.has(c.name)) c.advanced = true; });
    }
    return `
        <div class="elections-er-rows">
            ${row('선거일', [day(rec.first_round_date), day(rec.date)].filter(Boolean).join(' → '))}
            ${row('임기', [day(rec.term_start), day(rec.term_end)].filter(Boolean).join(' ~ '))}
            ${row('투표율', pct(rec.turnout_pct))}
            ${row('선거인 수', num(rec.electorate))}
            ${row('당선', rec.winner_ko)}
        </div>
        ${rounds ? rounds.map((round) => roundBlock(round, rec.vote_pct_basis)).join('') : `
            ${candidateTable(rec.candidates, rec.vote_pct_basis)}
            ${seatTable(rec.seats, rec.seats_total)}
            ${rec.summary_ko ? `<p>${escapeHtml(rec.summary_ko)}</p>` : ''}`}
        ${rec.detail_ko ? `<details class="elections-disclosure"><summary>세부</summary><p class="elections-panel-note">${escapeHtml(rec.detail_ko)}</p></details>` : ''}
        ${rec.origin === 'researched' ? '' : rec.origin ? '<p class="elections-panel-note">선거 일정판에서 옮긴 기록입니다. 세부 득표는 조사 중일 수 있습니다.</p>' : ''}
        ${sources(rec.sources)}`;
};

const nextLine = (office) => {
    if (office.next?.date) return `${day(office.next.date)}${office.next.date_status === 'tentative' ? ' (잠정)' : ''}${office.next.label_ko ? ` · ${office.next.label_ko}` : ''}`;
    if (office.next) return `날짜 미정${office.next.label_ko ? ` · ${office.next.label_ko}` : ''}`;
    if (office.next_due?.year) return `${office.next_due.year}년 무렵 (임기 기준)`;
    return null;
};

const officeTitle = (office) => office.title_ko || office.system_id || '선거';

const officeBlock = (office, country) => {
    const main = office.records.filter((rec) => !rec.by_election);
    const last = main[0] || null;
    const older = [...main.slice(1), ...office.records.filter((rec) => rec.by_election)];
    const head = [
        office.elected_how === 'by_legislature' ? '의회에서 선출' : null,
        office.term_years ? `임기 ${office.term_years}년` : null,
        office.runoff_rule_ko ? '결선 있음' : null,
    ].filter(Boolean).join(' · ');
    const incumbent = office.incumbent
        ? `${office.incumbent.name}${office.incumbent.since ? ` · ${day(office.incumbent.since)} 취임` : ''}${office.incumbent.term_end ? ` · 임기 만료 ${day(office.incumbent.term_end)}` : ''}`
        : null;
    const selectedBy = office.selected_by_system_id
        ? country.election_records.offices.find((o) => o.system_id === office.selected_by_system_id) : null;
    return `
        <article class="elections-er-office">
            <p class="elections-er-office-title">${escapeHtml(officeTitle(office))}${head ? ` <span>${escapeHtml(head)}</span>` : ''}</p>
            <div class="elections-er-rows">
                ${row('현직', incumbent)}
                ${row('선출 방식', office.method_ko)}
                ${row('결선 규칙', office.runoff_rule_ko)}
                ${selectedBy ? row('근거 선거', `${officeTitle(selectedBy)} 결과로 결정`) : ''}
                ${row('다음 선거', nextLine(office))}
            </div>
            ${last ? `<p class="elections-er-sub">직전 선거${last.label_ko ? ` · ${escapeHtml(last.label_ko)}` : ''}</p>${recordBody(last)}`
                : office.elected_how === 'by_legislature' ? ''
                : '<p class="elections-muted">직전 선거 기록이 아직 수집되지 않았습니다.</p>'}
            ${older.length ? `<details class="elections-disclosure"><summary>이전·보궐 선거 ${older.length}건</summary>
                ${older.map((rec) => `<div class="elections-er-older"><p class="elections-er-sub">${escapeHtml(day(rec.date))}${rec.by_election ? ' · 보궐' : ''}${rec.label_ko ? ` · ${escapeHtml(rec.label_ko)}` : ''}</p>${recordBody(rec)}</div>`).join('')}
            </details>` : ''}
        </article>`;
};

const issuesBlock = (data) => {
    const issues = data.issues || [];
    if (!issues.length) {
        return data.issues_expected
            ? '<p class="section-title">쟁점</p><p class="elections-muted">대통령선거급 쟁점은 조사 중입니다.</p>' : '';
    }
    return `<p class="section-title">쟁점</p>${issues.map((issue) => `
        <article class="elections-er-office">
            <p class="elections-er-office-title">${escapeHtml(issue.title_ko || '쟁점')}${issue.election_id ? ` <span>${escapeHtml(issue.election_id)}</span>` : ''}</p>
            ${issue.summary_ko ? `<p>${escapeHtml(issue.summary_ko)}</p>` : ''}
            ${(issue.positions || []).length ? `<div class="elections-er-rows">${issue.positions.map((p) => row(p.actor_ko || p.party || '', p.stance_ko)).join('')}</div>` : ''}
            ${sources(issue.sources)}
        </article>`).join('')}`;
};

export const electionRecordsHtml = (country) => {
    const data = country?.election_records;
    if (!data?.offices?.length) return null;
    const groups = GROUPS.map(([key, label], i) => {
        const offices = data.offices.filter((office) => office.key === key);
        if (!offices.length) return '';
        return `<p class="section-title">${i + 1} · ${escapeHtml(label)}</p>${offices.map((office) => officeBlock(office, country)).join('')}`;
    }).join('');
    return `${groups}${issuesBlock(data)}
        <p class="elections-panel-note">행정수반 → 의회 → 지방 순. 득표·투표율은 선관위 등 공식 집계만 씁니다.</p>`;
};
