import { escapeHtml } from '../../ui.js';
import { currentElectionSeats, electionRatingSummary, electionOutlook, ELECTION_OFFICES } from '../../data/election-overview.js?v=3';
import { pollSignal, raceClosedByDate } from '../../data/usa-election-context.js?v=2';
import { electionMatchup, ballotPartyLabel, ballotPartyClass, senateTenureLabel, displayPersonName, usaStateNameKo, pollMatchesMatchup } from '../../data/election-matchups.js';

const number = (value) => Number.isFinite(value) ? String(value) : '—';
const tile = (label, value, cls, key, office) => `<button type="button" class="elections-rating-tile ${cls}" data-rating-filter="${key}" aria-expanded="false" aria-controls="elections-${office}-${key}"><span>${label}</span><strong>${number(value)}</strong></button>`;
const ratingLabel = (value) => ({solid_dem:'DEM Solid',likely_dem:'DEM Likely',lean_dem:'DEM Lean',solid_rep:'GOP Solid',likely_rep:'GOP Likely',lean_rep:'GOP Lean',toss_up:'Toss-Up'}[value] || value);
const groupFor = (value) => ['solid_dem','likely_dem'].includes(value) ? 'dem' : ['solid_rep','likely_rep'].includes(value) ? 'gop' : value.startsWith('lean_') ? 'lean' : 'toss';
const contestList = (races, country, board, health, days, now) => races.map((race) => {
    const state = country?.ui_ready?.state_drilldown?.states?.find((s) => s.id === race.state);
    const office = race.race_id.includes(':house:') ? 'house' : race.race_id.endsWith(':senate') ? 'senate' : 'governor';
    const label = `${usaStateNameKo(race.state,state?.state)}${office === 'house' ? ` · 하원 ${race.district === '00' ? '전역구' : Number(race.district) + '구'}` : office === 'senate' ? ' · 상원' : ' · 주지사'}`;
    const incumbent = office === 'house' ? state?.federal_delegation?.house_members?.find((m) => String(m.district ?? '00').padStart(2,'0') === race.district)
        : office === 'senate' ? state?.federal_delegation?.senators?.find((m) => m.senate_class === race.senate_class) : state?.governor;
    const poll = board?.races?.[race.race_id];
    const matchup = electionMatchup(state,race.race_id,poll,now);
    const nominees = matchup?.candidates || [];
    const incumbentParty = ballotPartyLabel(incumbent?.abbr);
    const opponent = nominees.filter((c) => ballotPartyLabel(c.party) !== incumbentParty);
    const personBox = (party, name, extra = '') => `<span class="elections-contest-person ${ballotPartyClass(party)}"><strong>${escapeHtml(ballotPartyLabel(party))} ${escapeHtml(displayPersonName(name))}${extra ? ` <span class="elections-tenure">(${escapeHtml(extra)})</span>` : ''}</strong></span>`;
    const field = nominees.length ? nominees.map((c) => personBox(c.party,c.name)).join('') : '<span class="elections-muted">본선 명부 확인 필요 · 경선 미완료와 별개</span>';
    return `<button type="button" class="elections-contest-row" data-overview-state="${escapeHtml(race.state)}" data-overview-office="${office}" data-overview-district="${office === 'house' ? escapeHtml(race.district) : ''}">
        <span class="elections-contest-heading"><strong>${escapeHtml(label)}${race.senate_class === 3 ? ' · 특별선거' : ''}</strong><span class="elections-contest-rating">${escapeHtml(ratingLabel(race.effective_rating))}${race.additional ? ' · 추가 경합' : ''}</span></span>
        <small>현재 의원${matchup?.incumbent_ballot_status === 'not_running' ? ' · 이번 본선 불출마' : ''}</small>
        <span class="elections-contest-pair">${incumbent ? personBox(incumbent.abbr,incumbent.name,office === 'senate' ? senateTenureLabel(incumbent) : '') : '<span>공석·현직 명부 확인 필요</span>'}
            ${office === 'senate' && matchup?.incumbent_ballot_status === 'running' && opponent.length ? personBox(opponent[0].party,opponent[0].name) : ''}</span>
        <small>이번 선거 구도${matchup?.status === 'certified_ballot' ? ' · 공식 본선 명부' : matchup ? ' · 공개 주요 후보 명부' : ''}</small><span class="elections-contest-pair">${field}</span>
        <small>${poll ? poll.required_candidates?.length && !pollMatchesMatchup(poll,matchup) ? '조사 후보와 본선 명부 대조 대기' : escapeHtml(compactPollLabel(poll, board, health, days)) : '여론조사 감시 미연결'}</small></button>`;
}).join('') || '<p class="elections-muted">해당 분류의 선거가 없습니다.</p>';

export const bindElectionOverview = (root, onOpen) => {
    root.querySelectorAll('[data-rating-filter]').forEach((button) => button.addEventListener('click', () => {
        const card = button.closest('.elections-seat-card');
        const wasOpen = button.getAttribute('aria-expanded') === 'true';
        card.querySelectorAll('[data-rating-filter]').forEach((b) => b.setAttribute('aria-expanded','false'));
        card.querySelectorAll('[data-rating-list]').forEach((list) => { list.hidden = true; });
        if (!wasOpen) {
            button.setAttribute('aria-expanded','true');
            card.querySelector(`[data-rating-list="${button.dataset.ratingFilter}"]`).hidden = false;
        }
    }));
    root.querySelectorAll('[data-overview-state]').forEach((button) => button.addEventListener('click', () => onOpen?.(button.dataset.overviewState, button.dataset.overviewDistrict || null, button.dataset.overviewOffice)));
};

export const electionOverviewHtml = (country, ratings, { state = null, board = null, health = null, days = 7, now = Date.now() } = {}) => {
    const current = currentElectionSeats(country, state);
    const summary = country?.ui_ready?.congress?.summary;
    const afterElection = raceClosedByDate({ election_date: '2026-11-03' }, now);
    return `<section class="elections-seat-overview" aria-label="현재 정당별 보유와 2026 선거 분류">
        <p class="elections-panel-note">${afterElection ? '공식 확정 승자를 반영합니다. 결과 미확정은 미정으로 남깁니다.' : `조건부 전망 · 최근 ${days}일 · 미정=판정 보류`}</p>
        ${ELECTION_OFFICES.map(([office, label]) => {
            const row = current[office];
            const rating = electionRatingSummary(ratings, office, country, state?.id, now);
            const resultUniverse = rating || electionRatingSummary(ratings, office, country, state?.id, now, { resultsOnly: true });
            const outlook = electionOutlook(country, office, resultUniverse, { state, board, health, days, now });
            const others = row.counts?.IND ? `무소속 ${row.counts.IND}` : '';
            const unknown = row.counts?.unknown ? `정당 미확인 ${row.counts.unknown}` : '';
            const vacant = row.vacancies ? `공석 ${row.vacancies}` : '';
            return `<article class="elections-seat-card" data-office="${office}">
                <header><h3>${label}</h3><span>${number(row.total)}${office === 'governor' ? '개 주' : '석'} · 전체</span></header>
                <div class="elections-seat-row"><span class="elections-seat-row-label">현재</span>
                <div class="elections-current-parties" aria-label="현재 보유">
                    <div class="is-dem"><span>DEM</span><strong>${number(row.counts?.DEM)}</strong></div>
                    <div class="is-gop"><span>GOP</span><strong>${number(row.counts?.GOP)}</strong></div>
                </div></div>
                ${[others, unknown, vacant].filter(Boolean).length ? `<p class="elections-seat-extras">${[others, unknown, vacant].filter(Boolean).join(' · ')}</p>` : ''}
                ${office === 'senate' && resultUniverse ? `<div class="elections-senate-scope" aria-label="상원 비선거와 선거 대상 현재 보유">
                    <div><span>비선거 유지 <strong>${number(outlook?.retained)}석</strong></span><span><b class="is-dem">DEM ${number(outlook?.retainedCounts.DEM)}</b> · <b class="is-gop">GOP ${number(outlook?.retainedCounts.GOP)}</b>${outlook?.retainedCounts.IND ? ` · 무소속 ${outlook.retainedCounts.IND}` : ''}</span></div>
                    <div><span>이번 선거 <strong>${resultUniverse.contested}석</strong> · 현재</span><span><b class="is-dem">DEM ${number(outlook?.contestedCurrentCounts?.DEM)}</b> · <b class="is-gop">GOP ${number(outlook?.contestedCurrentCounts?.GOP)}</b>${outlook?.contestedCurrentCounts?.IND ? ` · 무소속 ${outlook.contestedCurrentCounts.IND}` : ''}</span></div>
                    ${resultUniverse.contested === 0 ? '<small>이 주는 이번 상원 선거 없음 · 기존 2석 유지</small>' : ''}</div>` : ''}
                <div class="elections-seat-row"><span class="elections-seat-row-label">${resultUniverse?.afterElection ? '결과' : '전망'}</span>
                <div class="elections-outlook-parties" aria-label="${resultUniverse?.afterElection ? '선거 후 · 공식 결과' : `전망 · 최근 ${days}일 반영`}">
                    <span class="is-dem">DEM <strong>${number(outlook?.counts.DEM)}</strong></span>
                    <span class="is-gop">GOP <strong>${number(outlook?.counts.GOP)}</strong></span>
                    <span>미정 <strong>${number(outlook?.pending)}</strong></span>
                </div></div>
                ${office === 'senate' && outlook ? `<p class="elections-seat-extras">선거 후 전체 ${outlook.total}석 = 비선거 ${outlook.retained} + 이번 선거 ${resultUniverse.contested}</p>` : ''}
                ${outlook?.counts.IND ? `<p class="elections-seat-extras">전망 무소속 ${outlook.counts.IND}</p>` : ''}
                ${outlook?.single ? `<p class="elections-seat-extras">단일 기관 참고 ${outlook.single}${office === 'governor' ? '곳' : '석'} 포함</p>` : ''}
                ${rating ? `<p class="elections-rating-heading">${office === 'senate' ? '전망 · ' : ''}이번 선거 ${rating.contested}${office === 'governor' ? '곳' : '석'} 분류 <small>칩을 눌러 목록 보기</small></p>
                <div class="elections-rating-grid" aria-label="2026 선거 분류">
                    ${tile('DEM', rating.blue, 'is-dem', 'dem', office)}
                    ${tile('GOP', rating.red, 'is-gop', 'gop', office)}
                    ${tile('Lean', rating.lean, 'is-lean', 'lean', office)}
                    ${tile('Toss-up', rating.toss, 'is-toss', 'toss', office)}
                </div>${['dem','gop','lean','toss'].map((key) => `<div id="elections-${office}-${key}" data-rating-list="${key}" hidden>${contestList(rating.races.filter((r) => groupFor(r.effective_rating) === key), country, board, health, days,now)}</div>`).join('')}
                ${office === 'senate' && rating.contested ? `<details class="elections-disclosure elections-senate-contests"><summary>이번 상원 선거 ${rating.contested}석 전체 목록</summary>${contestList(rating.races, country, board, health, days,now)}<p class="elections-panel-note">괄호는 현재까지 상원 당선 횟수입니다. 임명은 별도로 표시하며 하원 경력이나 상원 Class와 합치지 않습니다. 주요 후보 보도 명부는 전체 공식 투표용지와 구분합니다.</p></details>` : ''}<p class="elections-rating-date"><a href="${escapeHtml(rating.sourceUrl)}" target="_blank" rel="noopener noreferrer">Cook ${escapeHtml(rating.asOf)}</a> · 선거 ${rating.contested}${outlook?.retained ? ` · 비선거 유지 ${outlook.retained}` : ''}</p>
                ${rating.additional.length ? `<details class="elections-disclosure elections-extra-contests"><summary>Cook ${rating.cookToss} + 추가 경합 ${rating.additional.length}곳</summary>
                    <p>추가 경합은 사용자 기준입니다. Cook 원본 등급을 보존하고 전망에서는 경합으로 보류합니다. 주의 대선 색과 지역구 보유 정당의 차이는 동일 지역구의 교차투표와 구분합니다.</p>
                    ${rating.additional.map((r) => `<p><strong>${escapeHtml(r.state)}-${escapeHtml(r.district)}</strong> · Cook ${escapeHtml(r.rating.replaceAll('_',' '))}<br>${r.reasons.map((reason) => `${escapeHtml(reason.basis_ko)} <a href="${escapeHtml(reason.source_url)}" target="_blank" rel="noopener noreferrer">근거</a>`).join('<br>')}<br>${board?.races?.[r.race_id] ? escapeHtml(compactPollLabel(board.races[r.race_id], board, health, days)) : '여론조사 감시 미연결 · 전망 미정'}</p>`).join('')}
                </details>` : ''}`
                    : `<p class="elections-panel-note">${resultUniverse?.afterElection ? '지난 Cook 등급의 우세 가정은 중단합니다.' : '미연결·오래된 등급은 전망과 함께 —로 표시합니다.'}</p>`}
            </article>`;
        }).join('')}
        <details class="elections-disclosure elections-overview-basis"><summary>숫자와 색의 기준</summary>
            <p>현재 보유는 공개 현직 명부 기준입니다. 무소속·공석은 따로 셉니다. ${state ? '상원·하원은 주 의회가 아닌 연방 의회입니다.' : `하원 현원 ${number(summary?.house_voting_members)}명 / 정원 ${number(summary?.house_voting_seats)}석.`}</p>
            <p>전망은 비선거 현직 유지 + Cook Solid/Likely 우세 가정 + Lean/Toss-up의 최근 조사 우세를 더한 조건부 수치입니다. 조사 없음·동률·갱신 지연은 미정이며 당선확률이 아닙니다. 공식 결과가 확인되면 승자를 반영합니다.</p>
            <p>DEM·GOP 칩은 이번 선거 대상 중 Cook Solid/Likely의 민주·공화 우세입니다. Lean·Toss-up은 따로 셉니다. 지도 색은 2024 대선 기준의 주 분류이고, 하원 선거 분류는 지역구별 Cook 등급입니다. 주 색으로 의석을 계산하지 않습니다. Cook 등급은 검토 스냅샷이며 21일 경과 시 집계를 멈춥니다.</p>
            <p>같은 지역구의 대선·하원 승자 불일치는 경계가 검증된 이력만 추가합니다. 전국 지역구별 대선 결과는 아직 미연동입니다. PVI는 대선 승자와 다릅니다.</p>
            <p>현재 명부: 하원 ${escapeHtml(country?.ui_ready?.congress?.context_coverage?.house_source_published_on || '시점 미기재')} · 상원 ${escapeHtml((country?.ui_ready?.congress?.context_coverage?.senate_roster_as_of || '').slice(0,10) || '시점 미기재')} · 주지사 ${escapeHtml((country?.ui_ready?.state_drilldown?.source_as_of?.governors || '').slice(0,10) || '시점 미기재')}.</p>
        </details>
    </section>`;
};

export const evidenceSectionHtml = (kind, title, caption, content, open = false) => `<details class="elections-evidence-section" data-evidence-section="${kind}"${open ? ' open' : ''}>
    <summary><span><strong>${title}</strong><small>${escapeHtml(caption)}</small></span><span class="elections-expand-icon" aria-hidden="true">＋</span></summary>
    <div class="elections-evidence-content">${content}</div></details>`;

export const compactPollLabel = (race, board, health, days) => {
    const signal = pollSignal(race, board, health, days);
    return signal.status === 'certified_result' ? '공식 결과'
        : signal.status === 'single_poll_lead' ? '단일 기관 참고'
        : signal.status === 'poll_lead' ? '복수 기관 우세'
        : signal.status === 'tie' ? '조사 동률'
        : signal.status === 'awaiting_certified_result' ? '공식 결과 대기'
        : signal.status === 'stale' ? '갱신 대기'
        : !race?.required_candidates?.length ? '조사 대진 검토 대기' : '최근 조사 없음';
};
