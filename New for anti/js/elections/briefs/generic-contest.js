import { escapeHtml } from '../ui.js';

// 미국 밖 선거의 개괄 창.
//
// 미국 화면은 민주·공화 두 열로 고정돼 있다. 나머지 나라는 그렇게 접을 수 없다 --
// 독일은 여섯 당, 일본은 회파까지 갈리고, 대만은 두 당이 큰 대신 제3당이 캐스팅보트다.
// 그래서 이 화면은 **정당 수를 모른 채** 그린다: 데이터가 준 정당을 준 만큼 세우고,
// 어느 쪽이 이긴다는 말은 하지 않는다.
//
// 구조는 미국 창과 같다. 열(원·선거 종류) → 현재 의석 → 선거구별 대진.
// 데이터 계약: scripts/election_watch/HANDOFF_CURSOR_ELECTION_CONTESTS.md

// 색이 없는 정당은 회색 계열로 돌려 쓴다. 정당색은 정치적 표식이라 **지어내지 않는다** --
// 구분만 되게 하고, 진짜 색은 데이터가 줄 때만 쓴다.
const FALLBACK = ['#94a3b8', '#64748b', '#a1a1aa', '#78716c', '#71717a', '#52525b'];

const colorMap = (parties) => {
    const map = new Map();
    (parties || []).forEach((party, index) => {
        map.set(party.abbr, party.color || FALLBACK[index % FALLBACK.length]);
    });
    return map;
};

const nameMap = (parties) => new Map((parties || []).map((party) => [party.abbr, party.name_ko || party.name_en || party.abbr]));

const seatRows = (byParty) => Object.entries(byParty || {})
    .filter(([, seats]) => Number.isFinite(seats) && seats > 0)
    .sort((a, b) => b[1] - a[1]);

// 현재 의석. 정당 수만큼 칸이 늘어나는 막대 하나 + 숫자 목록.
// **정당별 의석을 더해 총계를 만들지 않는다.** 총계는 데이터가 준 `total` 이고,
// 둘이 어긋나면 어긋난 채로 적는다 -- 무소속·공석·미배분이 그 차이다.
const currentBlock = (column, colors, names) => {
    const current = column.current || {};
    const rows = seatRows(current.by_party);
    if (!rows.length) return '<p class="elections-muted">현재 의석이 수집되지 않았습니다.</p>';
    const counted = rows.reduce((sum, [, seats]) => sum + seats, 0);
    const total = Number.isFinite(current.total) ? current.total : counted;
    const width = (seats) => Math.max(2, Math.round((seats / (total || counted)) * 100));
    const gap = total - counted;
    return `
        <div class="elections-seatbar" role="img" aria-label="${escapeHtml(rows.map(([abbr, seats]) => `${names.get(abbr) || abbr} ${seats}`).join(', '))}">
            ${rows.map(([abbr, seats]) => `<i style="width:${width(seats)}%;background:${escapeHtml(colors.get(abbr) || '#94a3b8')}"></i>`).join('')}
            ${gap > 0 ? `<i class="is-rest" style="width:${width(gap)}%"></i>` : ''}
        </div>
        <ul class="elections-seat-list">
            ${rows.map(([abbr, seats]) => `<li>
                <span class="elections-seat-swatch" style="background:${escapeHtml(colors.get(abbr) || '#94a3b8')}"></span>
                <span class="elections-seat-name">${escapeHtml(names.get(abbr) || abbr)}</span>
                <b>${seats}</b>
            </li>`).join('')}
        </ul>
        <p class="elections-vs-note">${escapeHtml([
            Number.isFinite(current.total) ? `정수 ${current.total}석` : '',
            gap > 0 ? `정당별 합계와 ${gap}석 차이 (무소속·공석 등, 합산하지 않음)` : '',
            Number.isFinite(current.vacancies) ? `공석 ${current.vacancies}석` : '',
            current.as_of ? `${current.as_of} 기준` : '',
        ].filter(Boolean).join(' · '))}</p>
        ${current.note_ko ? `<p class="elections-vs-note">${escapeHtml(current.note_ko)}</p>` : ''}`;
};

const number = (value) => (Number.isFinite(value) ? value.toLocaleString('ko-KR') : '');

const candidateRow = (candidate, colors, names) => {
    const color = colors.get(candidate.party_abbr) || '#94a3b8';
    const flags = [
        candidate.incumbent ? '현직' : '',
        candidate.status === 'presumptive' ? '유력 보도' : '',
        candidate.status === 'withdrawn' ? '사퇴' : '',
        candidate.status === '불명' ? '확정 불명' : '',
        // 중복입후보는 소선거구에서 져도 비례로 살아날 수 있다는 뜻이라, 낙선 표시와
        // 같이 읽혀야 한다. 실제 부활 여부는 데이터의 note_ko 가 말한다.
        candidate.dual_listed ? '중복입후보' : '',
    ].filter(Boolean);
    return `<div class="elections-runner${candidate.elected ? ' is-elected' : ''}">
        <span class="elections-runner-party" style="background:${escapeHtml(color)}22;color:${escapeHtml(color)}">${escapeHtml(names.get(candidate.party_abbr) || candidate.party_abbr || '무소속')}</span>
        <span class="elections-runner-name">${escapeHtml(candidate.name || '불명')}</span>
        ${candidate.elected ? '<span class="elections-runner-win">당선</span>' : ''}
        ${Number.isFinite(candidate.votes) ? `<span class="elections-runner-votes">${escapeHtml(number(candidate.votes))}표</span>` : ''}
        ${flags.length ? `<span class="elections-runner-flag">${escapeHtml(flags.join(' · '))}</span>` : ''}
        ${candidate.note_ko ? `<span class="elections-runner-note">${escapeHtml(candidate.note_ko)}</span>` : ''}
    </div>`;
};

// 끝난 선거는 당선자가 곧 결과다. 정당별 당선 수는 수집된 `elected` 를 그대로 센 것이고,
// 그 사실을 화면에 적는다 -- 원문 총계가 아니라 이 파일에 담긴 당선자 수다.
const electedTally = (column) => {
    const counts = new Map();
    let total = 0;
    (column.districts || []).forEach((district) => (district.candidates || []).forEach((candidate) => {
        if (!candidate.elected) return;
        counts.set(candidate.party_abbr, (counts.get(candidate.party_abbr) || 0) + 1);
        total += 1;
    }));
    return { counts, total };
};

const resultBlock = (column, colors, names) => {
    const { counts, total } = electedTally(column);
    if (!total) return '';
    const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const width = (seats) => Math.max(2, Math.round((seats / total) * 100));
    const seats = (column.districts || []).reduce((sum, district) => sum + (Number.isFinite(district.seats) ? district.seats : 0), 0);
    return `
        <p class="elections-brief-current-label">당선</p>
        <div class="elections-seatbar">
            ${rows.map(([abbr, count]) => `<i style="width:${width(count)}%;background:${escapeHtml(colors.get(abbr) || '#94a3b8')}"></i>`).join('')}
        </div>
        <ul class="elections-seat-list">
            ${rows.map(([abbr, count]) => `<li>
                <span class="elections-seat-swatch" style="background:${escapeHtml(colors.get(abbr) || '#94a3b8')}"></span>
                <span class="elections-seat-name">${escapeHtml(names.get(abbr) || abbr)}</span>
                <b>${count}</b>
            </li>`).join('')}
        </ul>
        <p class="elections-vs-note">${escapeHtml(`수집된 당선자 ${total}명 기준${seats ? ` · 이 열의 의석 ${seats}석` : ''}`)}</p>`;
};

// 후보가 없는 칸의 뜻은 하나가 아니다. 경선 전이면 "아직", 무투표면 "단독" --
// 둘을 같은 글자로 적으면 선거가 없는 것처럼 읽힌다.
const districtBody = (district, colors, names) => {
    const runners = district.candidates || [];
    if (runners.length) return runners.map((candidate) => candidateRow(candidate, colors, names)).join('');
    if (district.status === 'uncontested') return '<p class="elections-muted">무투표 — 단독 후보</p>';
    if (district.status === 'completed') return '<p class="elections-muted">종료된 선거구 — 결과 미수집</p>';
    return '<p class="elections-muted">후보 확정 전</p>';
};

const districtBlock = (district, colors, names, { collapsible }) => {
    const head = `<span class="elections-brief-state-id">${escapeHtml(district.id || '?')}</span>
        <span class="elections-brief-state-name">${escapeHtml(district.name_ko || '')}</span>
        <span class="elections-brief-state-meta">${escapeHtml(Number.isFinite(district.seats) ? `${district.seats}석` : '')}</span>`;
    const body = districtBody(district, colors, names);
    if (!collapsible) {
        return `<article class="elections-brief-state">
            <div class="elections-brief-state-head">${head}</div>${body}
        </article>`;
    }
    return `<details class="elections-brief-state is-collapsible">
        <summary class="elections-brief-state-head">${head}</summary>
        <div class="elections-brief-state-body">${body}</div>
    </details>`;
};

// 선거구가 많으면 묶음(주·권역)으로 접는다. 묶음 이름이 없으면 선거구 자체를 접는다.
const districtsBlock = (column, colors, names) => {
    const districts = column.districts || [];
    if (!districts.length) return '<p class="elections-muted">선거구별 대진이 아직 없습니다. 후보가 없다는 뜻이 아닙니다.</p>';
    const collapsible = districts.length > 12;
    const groups = new Map();
    districts.forEach((district) => {
        const key = district.group_ko || '';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(district);
    });
    if (groups.size <= 1) {
        return `<div class="elections-brief-states">${districts.map((district) => districtBlock(district, colors, names, { collapsible })).join('')}</div>`;
    }
    // 묶음을 여는 기준은 묶음 크기가 아니라 열 전체 크기다. 한 묶음이 작아도 묶음이
    // 마흔일곱이면 다 열린 채로 뜬다 -- 일본 소선거구 289곳이 그랬다.
    const openByDefault = districts.length <= 40;
    return [...groups.entries()].map(([group, rows]) => `
        <details class="elections-contest-group"${openByDefault ? ' open' : ''}>
            <summary>${escapeHtml(group || '기타')}<span>${rows.length}곳</span></summary>
            <div class="elections-brief-states">${rows.map((district) => districtBlock(district, colors, names, { collapsible: rows.length > 12 })).join('')}</div>
        </details>`).join('');
};

const columnHtml = (column, colors, names, { finished }) => `
    <section class="elections-brief-column">
        <header class="elections-brief-column-head">
            <h4>${escapeHtml(column.label_ko || column.key || '선거')}</h4>
            ${column.contested_ko ? `<span>${escapeHtml(column.contested_ko)}</span>` : ''}
        </header>
        ${finished ? resultBlock(column, colors, names) : ''}
        <p class="elections-brief-current-label">${finished ? '선거 전 의석' : '현재 의석'}</p>
        ${currentBlock(column, colors, names)}
        ${column.seat_note_ko ? `<p class="elections-vs-note">${escapeHtml(column.seat_note_ko)}</p>` : ''}
        <p class="elections-brief-column-sub">${escapeHtml(`대진 ${(column.districts || []).length}곳`)}</p>
        ${districtsBlock(column, colors, names)}
    </section>`;

// 창을 열 때는 파일이 아직 안 왔다. 빈 창을 띄우고 내용만 채운다 -- 전망 칸과 같은 방식이다.
export const contestSkeleton = (event) => `
    <div class="elections-brief" data-contest-root>
        <p class="elections-muted">${escapeHtml(`${event?.label_ko || '선거'} 대진을 불러오는 중입니다.`)}</p>
    </div>`;

export const contestHtml = (contest, event) => {
    if (!contest) {
        return `<p class="elections-panel-note">이 선거의 대진 파일을 읽지 못했습니다. 수집 전이거나 경로가 바뀌었을 수 있습니다.</p>`;
    }
    const colors = colorMap(contest.parties);
    const names = nameMap(contest.parties);
    const columns = contest.columns || [];
    // 이미 치른 선거면 "현재 의석"이 아니라 "선거 전 의석"이고, 당선자가 곧 결과다.
    const finished = Boolean(contest.date) && contest.date < new Date().toISOString().slice(0, 10);
    return `
        ${event?.contested_ko ? `<p class="elections-brief-lede">${escapeHtml(event.contested_ko)}</p>` : ''}
        <div class="elections-brief-columns">${columns.map((column) => columnHtml(column, colors, names, { finished })).join('')}</div>
        ${columns.length ? '' : '<p class="elections-muted">표시할 선거 종류가 없습니다.</p>'}
        <p class="elections-panel-note">${finished ? '당선·득표는 수집된 개표 자료입니다.' : '현재 의석과 대진은 공식 명부·후보 등록 자료입니다. 어느 쪽이 이길지는 이 화면이 말하지 않습니다.'}</p>
        <p class="elections-panel-note">${escapeHtml([
        contest.as_of ? `${contest.as_of} 기준` : '',
        contest.date ? `선거일 ${contest.date}` : '',
        (contest.sources || []).length ? `출처 ${contest.sources.length}건` : '출처 없음',
    ].filter(Boolean).join(' · '))}</p>`;
};

export const applyContest = (root, contest, event) => {
    const host = root?.querySelector?.('[data-contest-root]');
    if (!host) return false;
    host.innerHTML = contestHtml(contest, event);
    return true;
};
