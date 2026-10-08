import { bioguideUrl, escapeHtml, formatDate, personLinkHtml, stateLabel } from '../ui.js';
// ?v=7: 이전 슈퍼팩 모듈이 배포돼 브라우저에 캐시돼 있을 수 있다. 이 모듈은 내용이 달라졌으므로(MAPPING_* export)
// 같은 URL 을 쓰면 옛 슈퍼팩 모듈과 새 대시보드가 섞여 로드 실패한다. index.js 와 반드시 같은 URL 이어야 한다.
import { usaStateSuperPac, usaStateSuperPacHouse, MAPPING_PENDING, MAPPING_FAILED } from './special/usa-state-superpac.js?v=7';
import { electionOverviewHtml, bindElectionOverview, evidenceSectionHtml } from './special/usa-election-overview.js?v=3';
import { pollEvidenceHtml, latestPollHtml, financeEvidenceHtml } from './special/usa-election-evidence.js?v=3';
import { candidateMatchupHtml } from './special/usa-candidate-matchup.js';
import { ELECTION_OFFICES } from '../data/election-overview.js?v=2';

export const statePollEvidenceHtml = (stateId, board, health, days = 7, selectedDistrict = null) => {
    const races = Object.values(board?.races || {}).filter((r) => r.state === stateId);
    return ELECTION_OFFICES.map(([office, label]) => {
        const selected = races.filter((r) => r.office === office).sort((a, b) => String(a.district || '').localeCompare(String(b.district || ''), undefined, { numeric: true }));
        if (!selected.length) return '';
        return `<section class="elections-state-polls"><h3>${label}</h3>${selected.map((race) => {
            const district = office === 'house' ? String(race.district) : null;
            return `<article class="elections-race-card${district && district === String(selectedDistrict) ? ' is-selected' : ''}" data-poll-race="${escapeHtml(race.race_id)}">
                ${district ? `<button class="elections-race-open" type="button" data-poll-district="${escapeHtml(district)}"><strong>하원 ${Number(district)}구</strong><span>지도에서 보기 →</span></button>` : ''}
                ${latestPollHtml(race, board, health)}${pollEvidenceHtml(race, board, health, days)}</article>`;
        }).join('')}</section>`;
    }).join('') || '<p class="elections-muted">이 주의 여론조사 감시 자료가 아직 연결되지 않았습니다. 조사 자체가 없다는 뜻은 아닙니다.</p>';
};

export const districtFocusHtml = (state, district, financeRaces, contract, board, health, days = 7) => {
    if (district == null) return '';
    const key = String(district).padStart(2,'0');
    const member = state.federal_delegation?.house_members?.find((m) => String(m.district ?? '00').padStart(2,'0') === key);
    const id = `USA:${state.id}:house:${key}`;
    const finance = (financeRaces || []).find((r) => r.race_id === id);
    const poll = board?.races?.[id];
    return `<section class="elections-district-focus" tabindex="-1"><header><h3>${escapeHtml(state.id)} · 하원 ${key === '00' ? '전역구' : Number(key) + '구'}</h3><button type="button" data-clear-district aria-label="선거구 선택 해제">×</button></header>
        <p>현재 의원: ${member ? person(member) : '공석·현직 명부 미확인'}</p>
        ${candidateMatchupHtml(poll, finance, contract, board, health, days)}
        <p class="elections-panel-note">참고 · 공시 누적 합계 (본선·경선·과거 포함, 위 후보별 본선 금액과 별개)</p>
        ${financeEvidenceHtml(finance,contract)}
        <p class="elections-panel-note">${finance ? '아래 슈퍼팩 목록에서 경선·과거 공시와 정당별 누적 금액을 더 볼 수 있습니다.' : '이 선거구의 외부 지출 자료 연결 대기'}</p></section>`;
};

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
        <p class="elections-panel-note">선거 자금·여론조사 자료를 불러오는 중입니다.<span class="inline-spinner" aria-hidden="true"></span><br>지도는 먼저 표시됩니다.</p>
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
    state, country = null, ratings = null, evidenceOpen = {}, districtMapReady, onBackToUsa,
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
        <div class="panel-header"><h2>${escapeHtml(state.state)}</h2><p>${escapeHtml(subtitleFor(financeMode, districtMapReady))}${
            !financeMode && districtMapReady === undefined ? '<span class="inline-spinner" aria-hidden="true"></span>' : ''
        }</p></div>`;
    const bindHeader = () => {
        root.querySelector('[data-election-back-usa]')?.addEventListener('click', onBackToUsa);
        root.querySelector('[data-election-finance-toggle]')?.addEventListener('click', () => onToggleFinance?.());
    };

    if (financeMode) {
        // 도형이 먼저 왔는지 나중에 오는지 모른다. 마지막으로 알려 준 값을 들고 있다가 본문을
        // 그릴 때 쓴다 -- 작은 주는 도형이 금액보다 먼저 도착한다.
        let mapped = loading ? MAPPING_PENDING : mappedDistricts;
        let bodyPainted = false;
        let latest = { financeRaces, financeContract, pollBoard, pollHealth, windowDays, openDistrict, financeFailed, ratings };

        const bindHouse = (scope) => {
            // Opening a district is a local DOM change, not a re-render: the list
            // runs to 50+ rows and rebuilding it would throw away the scroll
            // position on every click. Only the map is told to change.
            scope.querySelectorAll('[data-spac-toggle]').forEach((button) => button.addEventListener('click', () => {
                const wrap = button.closest('.elections-spac-district');
                const wasOpen = wrap.classList.contains('is-open');
                root.querySelectorAll('.elections-spac-district.is-open').forEach((row) => row.classList.remove('is-open'));
                if (!wasOpen) wrap.classList.add('is-open');
                // 도형이 아직 안 온(또는 못 받은) 행은 열고 닫기만 한다 -- 강조할 지도가 없다.
                if (mapped === MAPPING_PENDING || mapped === MAPPING_FAILED) return;
                // A row without geometry still opens; it just clears the map's
                // highlight rather than asking for one that cannot be drawn.
                const district = button.dataset.spacDistrict;
                selectDistrict(wasOpen || district === undefined ? null : district);
            }));
        };

        const contestIds = () => latest.ratings ? new Set(Object.values(latest.ratings.offices || {}).flatMap((o) => o.races || []).map((r) => r.race_id)) : null;
        const drawFocus = () => {
            const target = root.querySelector('[data-district-focus]');
            if (!target) return;
            target.innerHTML = districtFocusHtml(state, latest.openDistrict, latest.financeRaces, latest.financeContract, latest.pollBoard, latest.pollHealth, latest.windowDays);
            target.querySelector('[data-clear-district]')?.addEventListener('click', () => selectDistrict(null));
        };
        const selectDistrict = (district, { notify = true, focus = true } = {}) => {
            latest.openDistrict = district;
            drawFocus();
            root.querySelectorAll('[data-district-key]').forEach((row) => row.classList.toggle('is-open', district != null && row.dataset.districtKey === String(district)));
            root.querySelectorAll('[data-poll-race]').forEach((row) => row.classList.toggle('is-selected', district != null && row.dataset.pollRace === `USA:${state.id}:house:${district}`));
            if (notify) onHighlightDistrict?.(district);
            if (district != null && focus) root.querySelector('.elections-district-focus')?.focus({preventScroll:false});
        };
        // Separate polling section and duplicated evidence beside candidate spending.
        const financeSection = () => usaStateSuperPac(state, latest.financeRaces, mapped, latest.financeContract,
            latest.pollBoard, latest.pollHealth, latest.windowDays, { showPolls: true, contestIds: contestIds() });

        const bodyHtml = () => {
            const { pollBoard: board, pollHealth: health, windowDays: days, openDistrict: open } = latest;
            const polledRaces = Object.values(board?.races || {}).filter((r) => r.state === state.id);
            const observationCount = polledRaces.reduce((n, r) => n + (r.observations?.length || 0), 0);
            const pollContent = `<div class="elections-window-switch" role="group" aria-label="최근 여론조사 집계 기간">
                <span>최근 조사</span><button type="button" data-window="7" aria-pressed="${days === 7}">7일</button>
                <button type="button" data-window="14" aria-pressed="${days === 14}">14일</button></div>
                <p class="elections-panel-note">최근 기간의 조사 우세와 누적 기록을 따로 봅니다. 단일 기관은 참고로 표시합니다.</p>
                ${statePollEvidenceHtml(state.id, board, health, days, open)}`;
            // 실패 안내는 접이식 섹션 **밖**에 둔다 -- 닫힌 <details> 안에 있으면 아무도 못 본다.
            return '<div data-district-focus></div>' + electionOverviewHtml(country, latest.ratings, { state, board, health, days })
                + failureNote(latest.financeFailed)
                + '<p class="elections-panel-note">하원 지도: 옅은 파랑 DEM · 옅은 빨강 GOP = Cook Solid/Likely 우세 가정. 진한 색 = 최근 조사상 우세. 회색 = 미정. 선거 후에는 공식 결과만 칠합니다.</p>'
                + '<p class="elections-section-heading">선거별 자료 <small>눌러서 펼치기</small></p>'
                + evidenceSectionHtml('poll', '여론조사', `감시 ${polledRaces.length}개 선거 · 누적 ${observationCount}건 · 최근 ${days}일`, pollContent, evidenceOpen.poll)
                + evidenceSectionHtml('finance', '슈퍼팩 · 외부 독립지출', '주지사·상원·하원 후보별 공시', financeSection(), evidenceOpen.finance || (open != null && !evidenceOpen.poll));
        };

        const paintBody = () => {
            const skeleton = root.querySelector('.elections-spac-skeleton');
            if (!skeleton) return;
            // 형제 노드 구조를 그대로 둔다(래퍼를 씌우면 패널의 간격 규칙이 깨진다).
            skeleton.insertAdjacentHTML('afterend', bodyHtml());
            skeleton.remove();
            bodyPainted = true;
            drawFocus();
            bindElectionOverview(root, (id, district, office) => {
                if (district != null) selectDistrict(district);
                else {
                    const section = root.querySelector('[data-evidence-section="finance"]'); if (section) section.open = true;
                    root.querySelector(`[data-spac-office="${office}"]`)?.scrollIntoView({block:'start'});
                }
            });
            root.querySelectorAll('[data-window]').forEach((button) => button.addEventListener('click', () => onWindowChange?.(Number(button.dataset.window))));
            root.querySelectorAll('[data-poll-district]').forEach((button) => button.addEventListener('click', () => {
                root.querySelectorAll('[data-poll-race]').forEach((row) => row.classList.remove('is-selected'));
                button.closest('[data-poll-race]').classList.add('is-selected');
                selectDistrict(button.dataset.pollDistrict);
            }));
            const house = root.querySelector('[data-spac-house]');
            if (house) bindHouse(house);
            // A district named in the URL opens without a click; the map was
            // already drawn with that highlight, so this does not re-report it.
            if (latest.openDistrict != null) {
                root.querySelector(`[data-district-key="${CSS.escape(String(latest.openDistrict))}"]`)
                    ?.classList.add('is-open');
            }
        };

        root.innerHTML = header + skeletonHtml();
        bindHeader();
        if (!loading) paintBody();

        return {
            selectDistrict(district, options) { selectDistrict(district, options); },
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
                    latest.pollBoard, latest.pollHealth, latest.windowDays, { showPolls: true, contestIds: contestIds() });
                if (openRace) house.querySelector(`[data-race-id="${CSS.escape(openRace)}"]`)?.classList.add('is-open');
                bindHouse(house);
                root.scrollTop = scroll;
            },
        };
    }

    root.innerHTML = `
        ${header}<div data-district-focus></div>
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
        selectDistrict(district) {
            const target = root.querySelector('[data-district-focus]');
            target.innerHTML = districtFocusHtml(state,district,null,null,null,null,windowDays);
            target.querySelector('[data-clear-district]')?.addEventListener('click', () => {target.innerHTML='';onHighlightDistrict?.(null);});
            target.querySelector('.elections-district-focus')?.focus();
            onHighlightDistrict?.(district);
        },
        setFinance() {},
        // 지도 소식이 오면 부제만 바꾼다 (본문은 주 자료라 도형과 무관하다).
        setMapped({ districtMapReady: ready }) {
            const subtitle = root.querySelector('.panel-header p');
            if (subtitle) subtitle.textContent = subtitleFor(false, ready);
        },
    };
};
