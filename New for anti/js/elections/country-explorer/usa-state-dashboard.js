import { bioguideUrl, escapeHtml, formatDate, personLinkHtml, stateLabel } from '../ui.js';
import { usaStateSuperPac, usaStateSuperPacHouse, MAPPING_PENDING, MAPPING_FAILED } from './special/usa-state-superpac.js?v=4';

const party = (value) => ({ DEM: '민주당', GOP: '공화당', IND: '무소속', NP: '무당파' }[value] || value || '');
// Returns safe HTML, not plain text: a bioguideId (present on every House/
// Senate row here, absent on governor/lt.gov/AG) links the name to Congress's
// own bio page. Callers must not escapeHtml() this a second time.
const person = (row) => {
    if (!row) return '불명';
    if (typeof row === 'string') return escapeHtml(row);
    if (row.not_applicable) return escapeHtml(`해당 직위 없음${row.note ? ` · ${row.note}` : ''}`);
    const affiliation = party(row.abbr || row.party);
    const label = escapeHtml([row.name || '불명', affiliation, row.note].filter(Boolean).join(' · '));
    return personLinkHtml(label, row.bioguideId && bioguideUrl(row.bioguideId));
};
const seatLine = (body) => {
    if (!body) return '해당 없음';
    const classification = `${party(body.abbr || body.control) || '구성'} ${body.majority ?? '불명'} · 상대 ${body.minority ?? '불명'}`;
    return body.nonpartisan_official ? `공식 비당파 · 분석 분류 ${classification}` : classification;
};
const leaderLine = (leader) => leader ? `${escapeHtml(leader.title || '지도부')}: ${person(leader)}` : '공개 명부 미기재';

// The pipeline only tells us the majority side's abbr (control) and the
// minority floor leader's abbr, not a full member-by-member roster, so a
// coalition-controlled chamber (AK) has no way to split its "majority" count
// into DEM/GOP dots -- coloring those grey rather than guessing keeps this
// honest for the ~2 non-DEM/GOP chambers same as the ~48 clean ones.
const partyDotColor = (abbr) => ({ DEM: '#2563eb', GOP: '#dc2626' }[abbr] || '#64748b');
const partyLabel = (abbr) => {
    if (!abbr) return '정당 불명';
    const mapped = party(abbr);
    return mapped !== abbr ? `${mapped}(${abbr})` : abbr;
};
const seatDots = (chamber) => {
    const groups = [
        { abbr: chamber.abbr, count: chamber.majority },
        { abbr: chamber.leadership?.second_party_floor_leader?.abbr, count: chamber.minority },
    ].filter((group) => Number.isFinite(group.count) && group.count > 0);
    if (!groups.length) return '';
    const dots = groups.flatMap((group) => Array.from({ length: group.count },
        () => `<span class="elections-seat-dot" style="background:${partyDotColor(group.abbr)}" title="${escapeHtml(partyLabel(group.abbr))}"></span>`)).join('');
    const legend = groups.map((group) => `<span class="elections-seat-legend-item"><i style="background:${partyDotColor(group.abbr)}"></i>${escapeHtml(`${partyLabel(group.abbr)} ${group.count}석`)}</span>`).join('');
    return `<div class="elections-seat-dots">${dots}</div><div class="elections-seat-legend">${legend}</div>`;
};

const chamberCard = (label, chamber) => {
    if (!chamber) {
        return `<article class="elections-card"><div class="elections-card-label">${escapeHtml(label)}</div><div class="elections-card-value">해당 없음</div></article>`;
    }
    const leadership = chamber.leadership || {};
    const seats = seatDots(chamber);
    return `
        <article class="elections-card elections-chamber-card">
            <div class="elections-card-label">${escapeHtml(label)}</div>
            <div class="elections-card-value">${escapeHtml(seatLine(chamber))}</div>
            <details class="elections-disclosure">
                <summary>구조·지도부 보기</summary>
                <div class="elections-disclosure-rows">
                    <div>${leaderLine(leadership.presiding_officer)}</div>
                    <div>${leaderLine(leadership.second_party_floor_leader)}</div>
                </div>
            </details>
            ${seats ? `<details class="elections-disclosure"><summary>정당별 의석 보기</summary>${seats}</details>` : ''}
        </article>`;
};

// 부제. `districtMapReady` 가 undefined 면 도형이 아직 오는 중이다 -- 그 사이를 "수집 대기"로
// 단정하지 않는다(도형이 오면 바뀐다).
const subtitleFor = (financeMode, districtMapReady) => {
    if (financeMode) return '여론조사 · 외부 독립지출 · 후보별 지지·반대 금액';
    if (districtMapReady === undefined) return '선거구 지도를 불러오는 중입니다';
    if (districtMapReady === 'failed') return '선거구 도형을 불러오지 못했습니다 · 나갔다 다시 들어오면 재시도합니다';
    return districtMapReady ? '연방 하원 선거구 지도 · 공개 결합 데이터' : '주 경계 지도 · 연방 하원 선거구 공식 도형 수집 대기';
};

const skeletonHtml = () => `
    <div class="elections-spac-skeleton" aria-busy="true">
        <p class="elections-panel-note">선거 자금·여론조사 자료를 불러오는 중입니다. 지도는 먼저 표시됩니다.</p>
        <i></i><i></i><i></i>
    </div>`;

const failureNote = (failed) => (failed > 0
    ? `<p class="elections-panel-note is-warning">선거 자금 파일 ${failed}개를 불러오지 못했습니다. 해당 레이스는 아래에서 빠지거나 "자료 연결 대기"로 보일 수 있고, 금액이 없다는 뜻이 아닙니다. 나갔다 다시 들어오면 재시도합니다.</p>`
    : '');

// 단계 렌더. 반환값의 두 메서드로 나머지를 채운다:
//   setFinance({...})  금액·여론조사 자료가 도착했다 → 본문을 그린다
//   setMapped({...})   선거구 도형이 도착했다 → 부제와 하원 구획만 갈아끼운다
//
// 이렇게 쪼갠 이유: 한 번에 다 기다리면 우측 패널이 가장 느린 자료(캘리포니아 도형 16MB)가
// 올 때까지 이전 화면 그대로였다. 지금은 주를 누른 즉시 패널이 바뀌고, 금액은 도착하는 대로,
// 도형은 마지막에 붙는다.
export const renderUsaStateDashboard = (root, {
    state, districtMapReady, onBackToUsa,
    financeMode = false, financeRaces = null, financeContract = null, mappedDistricts = null, openDistrict = null,
    pollBoard = null, pollHealth = null, windowDays = 7, onWindowChange,
    onToggleFinance, onHighlightDistrict, loading = false, financeFailed = 0,
}) => {
    const legislature = state.state_legislature || {};
    const delegation = state.federal_delegation || {};
    const members = [...(delegation.house_members || [])].sort((a, b) => String(a.district || '').localeCompare(String(b.district || ''), undefined, { numeric: true }));
    root.className = 'panel-section elections-country elections-state-dashboard';
    const header = `
        <div class="elections-country-actions">
            <button class="elections-button" type="button" data-election-back-usa>← 미국 주 지도</button>
            <button class="elections-button${financeMode ? ' is-active' : ''}" type="button" data-election-finance-toggle aria-pressed="${financeMode}">선거·슈퍼팩</button>
        </div>
        <div class="panel-header"><h2>${escapeHtml(state.state)}</h2><p>${escapeHtml(subtitleFor(financeMode, districtMapReady))}</p></div>`;
    const bindHeader = () => {
        root.querySelector('[data-election-back-usa]')?.addEventListener('click', onBackToUsa);
        root.querySelector('[data-election-finance-toggle]')?.addEventListener('click', () => onToggleFinance?.());
    };

    if (financeMode) {
        // 도형이 먼저 왔는지 나중에 오는지 모른다. 마지막으로 알려 준 값을 들고 있다가 본문을
        // 그릴 때 쓴다 -- 작은 주는 도형이 금액보다 먼저 도착한다.
        let mapped = loading ? MAPPING_PENDING : mappedDistricts;
        let bodyPainted = false;
        let latest = { financeRaces, financeContract, pollBoard, pollHealth, windowDays, openDistrict, financeFailed };

        const bindHouse = (scope) => {
            // Opening a district is a local DOM change, not a re-render: the list
            // runs to 50+ rows and rebuilding it would throw away the scroll
            // position on every click. Only the map is told to change.
            scope.querySelectorAll('[data-spac-toggle]').forEach((button) => button.addEventListener('click', () => {
                const wrap = button.closest('.elections-spac-district');
                const wasOpen = wrap.classList.contains('is-open');
                root.querySelectorAll('.elections-spac-district.is-open').forEach((row) => row.classList.remove('is-open'));
                if (!wasOpen) wrap.classList.add('is-open');
                // 도형이 아직 안 온 행은 열고 닫기만 한다 -- 강조할 지도가 아직 없다.
                if (mapped === MAPPING_PENDING || mapped === MAPPING_FAILED) return;
                // A row without geometry still opens; it just clears the map's
                // highlight rather than asking for one that cannot be drawn.
                const district = button.dataset.spacDistrict;
                onHighlightDistrict?.(wasOpen || district === undefined ? null : district);
            }));
        };

        const openByDistrict = (district) => {
            if (district == null) return;
            const wrap = root.querySelector(`[data-district-key="${CSS.escape(String(district))}"]`);
            wrap?.classList.add('is-open');
        };

        const paintBody = () => {
            const html = failureNote(latest.financeFailed)
                + usaStateSuperPac(state, latest.financeRaces, mapped, latest.financeContract, latest.pollBoard, latest.pollHealth, latest.windowDays);
            const skeleton = root.querySelector('.elections-spac-skeleton');
            if (!skeleton) return;
            // 형제 노드 구조를 그대로 둔다(래퍼를 씌우면 패널의 간격 규칙이 깨진다).
            skeleton.insertAdjacentHTML('afterend', html);
            skeleton.remove();
            bodyPainted = true;
            const house = root.querySelector('[data-spac-house]');
            if (house) bindHouse(house);
            // A district named in the URL opens without a click; the map was
            // already drawn with that highlight, so this does not re-report it.
            openByDistrict(latest.openDistrict);
        };

        root.innerHTML = header + `<div class="elections-window-switch" role="group" aria-label="최근 여론조사 집계 기간">
            <span>최근 조사</span><button type="button" data-window="7" aria-pressed="${windowDays === 7}">7일</button>
            <button type="button" data-window="14" aria-pressed="${windowDays === 14}">14일</button></div>`
            + skeletonHtml();
        bindHeader();
        root.querySelectorAll('[data-window]').forEach((button) => button.addEventListener('click', () => onWindowChange?.(Number(button.dataset.window))));
        if (!loading) paintBody();

        return {
            setFinance(next) {
                latest = { ...latest, ...next };
                if (!bodyPainted) paintBody();
            },
            // 도형이 도착했다. 본문이 이미 그려졌으면 하원 구획만 갈아끼운다 -- 열어 둔 행과 스크롤을
            // 그대로 둔다. 본문이 아직이면 값만 받아 두고 본문을 그릴 때 쓴다.
            setMapped({ mappedDistricts: nextMapped }) {
                mapped = nextMapped;
                if (!bodyPainted) return;
                const house = root.querySelector('[data-spac-house]');
                if (!house) return;
                const openRace = house.querySelector('.elections-spac-district.is-open')?.dataset.raceId;
                const scroll = root.scrollTop;
                house.innerHTML = usaStateSuperPacHouse(state, latest.financeRaces, mapped, latest.financeContract,
                    latest.pollBoard, latest.pollHealth, latest.windowDays);
                if (openRace) house.querySelector(`[data-race-id="${CSS.escape(openRace)}"]`)?.classList.add('is-open');
                bindHouse(house);
                root.scrollTop = scroll;
            },
        };
    }

    root.innerHTML = `
        ${header}
        <section class="elections-detail-section">
            <p class="section-title">1 · 주 행정부</p>
            <div class="elections-card-grid">
                <article class="elections-card"><div class="elections-card-label">주지사</div><div class="elections-card-value">${person(state.governor)}</div></article>
                <article class="elections-card"><div class="elections-card-label">부지사</div><div class="elections-card-value">${person(state.lieutenant_governor)}</div></article>
                <article class="elections-card"><div class="elections-card-label">법무장관</div><div class="elections-card-value">${person(state.attorney_general)}</div></article>
                <article class="elections-card"><div class="elections-card-label">주 단위 계파</div><div class="elections-card-value">공개 정본 없음</div></article>
            </div>
        </section>
        <section class="elections-detail-section">
            <p class="section-title">2 · 연방 의회</p>
            <div class="elections-card"><div class="elections-card-label">연방 상원의원</div><div class="elections-card-value">${(delegation.senators || []).map(person).join(' / ') || '불명'}</div></div>
            <details class="elections-disclosure elections-house-delegation">
                <summary>연방 하원의원 ${members.length}명 · 선거구 순으로 보기</summary>
                <div class="elections-member-list">${members.map((member) => `<div class="elections-member-row"><span>하원 ${escapeHtml(state.id)}-${escapeHtml(member.district ?? 'AL')}</span><span>${person(member)}</span></div>`).join('') || '<p class="elections-muted">하원 명단 없음</p>'}</div>
            </details>
        </section>
        <section class="elections-detail-section">
            <p class="section-title">3 · 주 의회</p>
            <div class="elections-card-grid">
                ${chamberCard('주 상원', legislature.state_senate)}
                ${chamberCard(legislature.state_house?.label_ko || '주 하원', legislature.state_house)}
            </div>
            <p class="elections-panel-note">일반 주의원 개인 명단은 범위에서 제외합니다. 각 원의 의장·제2당 원내지도부만 표시합니다.</p>
        </section>
        ${state.primary_2026 ? `<section class="elections-detail-section"><p class="section-title">2026 선거 과정</p><div class="elections-card"><div class="elections-card-value">${escapeHtml(state.primary_2026.headline || '공개된 경선 요약 없음')}</div><div class="elections-event-meta">${escapeHtml(formatDate(state.primary_2026.date))} · ${escapeHtml(stateLabel(state.primary_2026.status))}</div></div></section>` : ''}
    `;
    bindHeader();
    return {
        setFinance() {},
        // 지도 소식이 오면 부제만 바꾼다 (본문은 주 자료라 도형과 무관하다).
        setMapped({ districtMapReady: ready }) {
            const subtitle = root.querySelector('.panel-header p');
            if (subtitle) subtitle.textContent = subtitleFor(false, ready);
        },
    };
};
