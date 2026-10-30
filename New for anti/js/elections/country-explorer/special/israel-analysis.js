import { escapeHtml } from '../../ui.js';
import { canCalculate, dayAge, koreaToday, seatPolls, selectedSeatSum, sourceHref } from '../../data/israel-analysis.js';
import { koreanText, partyProfile, personProfile, groupingGroups, groupSeatSummary, presetSeatSum, selectionRelationships } from '../../data/israel-context.js?v=2';

import { weeklySeatRows } from '../../data/israel-trend.js';

const e = escapeHtml;
const reviewLabel = (state) => ({ accepted: '원문 채택', partial: '부분 자료', held: '보류' }[state] || '미확인');
const questionLabel = (scenario) => ({ eisenkot_vs_netanyahu: '아이젠콧과 네타냐후',
    bennett_vs_netanyahu: '베넷과 네타냐후', netanyahu_vs_lieberman: '네타냐후와 리버만',
    open_who_should_be_pm: '전체 후보 중 총리 적합도', haredi_party_in_next_coalition: '초정통 정당의 연정 참여 찬반' }[scenario] || '별도 질문');
const answers = { neither: '둘 다 아님', dont_know: '모름', support: '찬성', oppose: '반대' };
const positionLabel = (type) => ({ statement_then_clarification: '발언 뒤 정정', refusal: '참여·협력 거부 발언',
    external_support: '외부 지지 발언', conditional_external_support: '외부 지지 조건',
    not_in_either_bloc: '독자 노선 발언', journalist_and_speaker_prediction: '전망·해석', conditional: '조건부 입장' }[type] || '관련 발언');
const safeLink = (url, label = '원문 보기') => sourceHref(url)
    ? `<a href="${e(sourceHref(url))}" target="_blank" rel="noopener noreferrer">${e(label)} ↗</a>` : '출처 미확인';
const pollLabel = (board, poll) => `${koreanText(board, poll.publisher, poll.publisher || '발표 매체 미확인')} · ${poll.field_end || poll.published_at?.slice(0, 10) || '날짜 미확인'} · ${reviewLabel(poll.review_status)}`;
const partyChip = (board, id) => {
    const p = partyProfile(board, id);
    return `<span class="israel-party-chip" style="--group-color:${p.color}"><b>${e(p.name)}</b><small>${e(p.leader)}</small></span>`;
};
const relationshipParties = (board, relation) => {
    if (relation.kind === 'refusal') return `${partyChip(board,relation.anchor)}<span class="israel-connector israel-connector-refusal" aria-label="함께 참여 거부">×</span><span class="israel-relation-targets">${relation.targets.map((id)=>partyChip(board,id)).join('')}</span>`;
    const connector = relation.kind === 'electoral_refusal' ? '×' : relation.kind === 'unknown' ? '?' : '↔';
    return relation.parties.map((id)=>partyChip(board,id)).join(`<span class="israel-connector" aria-hidden="true">${connector}</span>`)
        + (relation.target_group ? '<span class="israel-connector" aria-hidden="true">→</span><span class="israel-target">정권 교체 추진 정당들</span>' : '');
};
const sourceLinks = (board, ids) => (ids || []).map((id) => {
    const s = board.coalition_context.sources[id];
    return s ? safeLink(s.url, `${s.publisher} · ${s.revised_on || s.published_on || s.reviewed_on || '날짜 미확인'}`) : '';
}).join(' · ');
const sectionHeading = (eyebrow, title, note = '') => `<header class="israel-section-heading"><span>${eyebrow}</span><h5>${title}</h5>${note ? `<p>${note}</p>` : ''}</header>`;

const weeklyTrend = (board, today) => {
    const rows = weeklySeatRows(board, today);
    const legend = rows[0]?.groups || [];
    return `<section class="israel-weekly" aria-labelledby="israel-weekly-title">
        <header><h5 id="israel-weekly-title">최근 7일 · 진영별 의석</h5><span>발표일 기준 · 최신순</span></header>
        ${rows.length ? `<div class="israel-weekly-legend">${legend.map((g) => `<span><i style="background:${g.color}" aria-hidden="true"></i>${g.label}</span>`).join('')}</div>
        <div class="israel-weekly-axis" aria-hidden="true"><span>0석</span><span>61석</span><span>120석</span></div>
        <div class="israel-weekly-rows">${rows.map(({poll, publishedDay, groups}, index) => {
            const publisher = koreanText(board, poll.publisher, '발표 매체 미확인');
            const description = groups.map((g) => `${g.label} ${g.total === null ? '미발표' : `${g.total}석`}`).join(' · ');
            const notes = groups.filter((g) => g.total === null || g.total < 8).map((g) => `${g.label} ${g.total === null ? '미발표' : `${g.total}석`}`).join(' · ');
            return `<div class="israel-weekly-row" data-israel-weekly-poll="${e(poll.poll_id)}">
                <div class="israel-weekly-label"><time datetime="${e(publishedDay)}">${e(publishedDay.slice(5).replace('-', '.'))}</time>${index === 0 ? '<small>최신</small>' : ''}<span>${e(publisher)}</span></div>
                <div class="israel-weekly-plot"><div class="israel-weekly-bar" role="img" aria-label="${e(`${publishedDay} ${publisher} · ${description}`)}">${groups.filter((g) => g.total !== null && g.total > 0).map((g) => `<span style="width:${g.total / 120 * 100}%;background:${g.color}" title="${e(`${g.label} ${g.total}석`)}">${g.total >= 8 ? g.total : ''}</span>`).join('')}<i class="israel-weekly-majority" aria-hidden="true"></i></div>
                <div class="israel-weekly-source"><span>조사 ${e(poll.field_end)}${notes ? ` · ${e(notes)}` : ''}</span>${safeLink(poll.source_url)}</div></div></div>`;
        }).join('')}</div>` : '<p class="israel-empty">최근 7일에 발표된 채택 조사가 없습니다.</p>'}
        <p class="israel-data-note">개별 조사별 발표 의석 · 아랍계 별도 분류 · 조사 없는 날은 생략 · 61석은 산술 과반이며 정부 구성 확정이 아닙니다.</p>
    </section>`;
};

const groupCards = (board, poll, grouping, selected, canSelect) => groupingGroups(board, grouping).map((g) => {
    const s = groupSeatSummary(board, poll, g.id, grouping);
    const ideology = grouping === 'ideology';
    const rowHtml = (v) => {
        const p = partyProfile(board, v.list_id);
        return `<label class="israel-seat-row" title="${e(ideology ? p.ideologyNote : p.note)}"><input type="checkbox" data-israel-list="${e(v.list_id)}" aria-label="${e(p.name)} 선택" ${selected.includes(v.list_id) ? 'checked' : ''} ${canSelect ? '' : 'disabled'}><span><b>${e(p.name)}</b><small>${e(p.leader)}</small><em class="israel-axis-tag" style="--tag-color:${ideology ? p.color : p.ideologyColor}">${ideology ? '협력' : '성향'} · ${e(ideology ? p.groupLabel : p.ideologyLabel)}</em></span><strong>${v.seats}<small>석</small></strong></label>`;
    };
    const pairs = ideology ? [] : (board.coalition_context.cooperation_pairs || []).filter((p) => p.group === g.id);
    const ids = [...new Set((board.coalition_context.parties || []).filter((p) => p.ideology_group === g.id).flatMap((p) => p.ideology_source_ids || []))];
    return `<section class="israel-group" data-israel-group="${e(g.id)}" style="--group-color:${g.color}"><div class="israel-group-badge">${ideology ? '정치 성향' : e(g.badge_ko)}</div><header><h6><span class="israel-party-dot"></span>${e(g.label_ko)}</h6><strong>${s.total === null ? '미확인' : s.total}<small>${s.total === null ? '' : '석'}</small></strong></header><p>${e(g.description_ko)}</p>
        <div class="israel-seat-list">${s.values.slice().sort((a,b) => b.seats-a.seats).map(rowHtml).join('') || '<p class="israel-empty">발표 의석 미확인</p>'}</div>
        ${s.missing.length ? `<details class="israel-unpublished" data-israel-details="unpublished-${grouping}-${e(g.id)}"><summary>의석 미발표 명부 ${s.missing.length}개</summary>${s.missing.map((id) => {const p=partyProfile(board,id);return `<p><b>${e(p.name)}</b> · ${e(p.leader)} <span>의석 미확인</span></p>`;}).join('')}</details>` : ''}
        ${pairs.length ? `<div class="israel-pair-list">${pairs.map((pair) => `<div><span class="israel-pair-caption">${e(pair.label_ko)} · ${e(pair.event_date.slice(5))}</span><p>${pair.parties.map((id) => `<b>${e(partyProfile(board,id).name)}</b>`).join('<span aria-hidden="true"> ↔ </span>')}</p>${sourceLinks(board,pair.source_ids)}</div>`).join('')}</div>` : ''}
        ${ideology && ids.length ? `<details class="israel-ideology-sources" data-israel-details="ideology-${e(g.id)}"><summary>성향 설명·근거</summary>${(board.coalition_context.parties || []).filter((p) => p.ideology_group === g.id).map((p) => {const profile=partyProfile(board,p.list_id); return `<p><b>${e(profile.name)}</b> ${e(profile.ideologyNote)}</p>`;}).join('')}<footer>${sourceLinks(board,ids)}</footer></details>` : ''}
        <small class="israel-group-foot">발표 의석만 합산${s.missing.length ? ' · 미발표는 합계에서 제외' : ''}</small></section>`;
}).join('');

export const israelAnalysisPlaceholder = () => '<div data-israel-analysis></div>';
export const israelAnalysisHtml = (board, { pollId = null, days = null, selected = [], presetId = null, grouping = 'cooperation', relationFilter = 'all', today = koreaToday() } = {}) => {
    if (!board) return '<p class="elections-muted" role="status">이스라엘 검토 자료를 불러오지 못했습니다. 조사 없음이나 0석으로 대체하지 않습니다.</p>';
    const ko = (source, fallback) => koreanText(board, source, fallback);
    const polls = seatPolls(board, { days, today });
    const poll = polls.find((row) => row.poll_id === pollId) || polls.find((row) => row.review_status === 'accepted') || polls[0] || null;
    const context = board.coalition_context || { groups: [], relationships: [], presets: [] };
    grouping = grouping === 'ideology' ? 'ideology' : 'cooperation';
    const groups = groupingGroups(board, grouping);
    const total = selectedSeatSum(poll, selected, board);
    const age = dayAge(board.evidence_as_of, today);
    const canSelect = canCalculate(poll, board);
    const shares = board.observations.filter((row) => row.poll_id === poll?.poll_id && row.question_id === 'party_vote_share');
    const otherQuestions = board.observations.filter((row) => row.poll_id === poll?.poll_id && ['preferred_pm', 'approval'].includes(row.question_id));
    const held = board.observations.filter((row) => row.question_id === 'reported_seats' && row.review_status === 'held');
    const positions = board.coalition_positions.filter((row) => row.record_type === 'position' && !row.position_type?.includes('surplus'));
    const agreements = board.coalition_positions.filter((row) => row.position_type?.includes('surplus'));
    const activeRelations = selectionRelationships(board, selected);
    const preset = context.presets.find((row) => row.id === presetId);
    const relations = context.relationships.filter((row) => relationFilter !== 'likud' || row.parties.includes('k26:מחל') || row.target_person === 'Benjamin Netanyahu');
    const shareCard = (value) => {
        const p = partyProfile(board, value.list_id);
        return `<article class="israel-share-card" style="--group-color:${p.color}"><div><span class="israel-party-dot"></span><strong>${e(p.name)}</strong><b class="israel-share-value">${value.pct == null ? '미확인' : `${e(value.pct)}%`}</b></div>
            <p class="israel-person">${e(value.leader ? ko(value.leader) : p.leader)}</p><p>${e(p.description)}</p>
            ${typeof value.pct === 'number' ? `<div class="israel-share-track" aria-hidden="true"><i style="width:${Math.min(100, value.pct / 3.25 * 100)}%"></i></div>` : ''}
            <small>${value.pct == null ? '비율 미확인' : value.pct < 3.25 ? `보도상 봉쇄선 3.25%보다 ${(3.25 - value.pct).toFixed(2)}%p 낮음` : '보도상 봉쇄선 이상'} · 의석 역산 없음</small><footer>${sourceLinks(board,p.sourceIds)}</footer></article>`;
    };
    return `<section class="israel-analysis">
        <header class="israel-heading"><p class="israel-eyebrow">이스라엘 · 26대 크네세트</p><h4>누가 누구와 함께할 수 있나</h4>
            <p>누가 같은 편이고, 정치색은 얼마나 비슷할까요? 협력 관계와 정치 성향을 나눠 살펴보세요.</p>
            <div class="israel-status-line"><span>의석 자료 ${e(board.evidence_as_of)}${age > 0 ? ` · ${age}일 경과` : ''}</span><span>관계 검토 ${e(context.reviewed_on || '미확인')}</span><span>자동 갱신 미설치</span></div>
        </header>
        ${weeklyTrend(board, today)}
        <nav class="israel-section-nav" aria-label="분석 바로가기"><a href="#israel-seats">정당·의석</a><a href="#israel-relations">연정 관계</a><a href="#israel-threshold">봉쇄선 지지율</a><a href="#israel-people">총리 적합도</a></nav>
        <div class="israel-controls"><label>조사 기간<select data-israel-window>${[[null, '전체 검토 기록'], [7, '최근 7일'], [14, '최근 14일']].map(([value, label]) => `<option value="${value ?? ''}" ${days === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
            <label>발표 조사<select data-israel-poll ${polls.length ? '' : 'disabled'}>${polls.length ? polls.map((row) => `<option value="${e(row.poll_id)}" ${row.poll_id === poll?.poll_id ? 'selected' : ''}>${e(pollLabel(board, row))}</option>`).join('') : '<option>기간 내 검토 조사 없음</option>'}</select></label></div>
        <p class="israel-data-note">원문 채택 ${board.coverage.accepted_seat_polls}건 · 부분 ${board.coverage.partial_seat_polls}건 · 최근 30일 전수 미완료 · 현직 의석·공식 후보 순위 보류</p>
        ${poll ? `<section id="israel-seats" class="israel-section">
            ${sectionHeading('01 / 정당 지도', '정당을 묶어 보는 두 가지 기준', '정당명 아래 대표 인물과 다른 기준의 분류를 함께 표시합니다.')}
            <div class="israel-grouping-control" role="group" aria-label="정당 묶음 기준">${[['cooperation','연합·협력','지금 누구와 손잡았나'],['ideology','정치 성향','어떤 정치색이 비슷한가']].map(([id,label,note]) => `<button type="button" data-israel-grouping="${id}" aria-pressed="${grouping === id}"><b>${label}</b><small>${note}</small></button>`).join('')}</div>
            <div class="israel-grouping-note" role="status">${grouping === 'ideology' ? `<b>정치 성향으로 다시 묶었습니다</b><p>${e(context.ideology_basis_ko)}</p><small>예: 리쿠드와 베이테누는 우파 계열이지만 협력 진영은 다릅니다.</small>` : `<b>검토한 연합·협력 현황 · ${e(context.reviewed_on)}</b><p>공동 원칙 발표와 선거 협약을 표시합니다. 리쿠드 중심은 보도상 블록이며 통합토라유다의 참여 조건이 남아 있습니다.</p><small>잉여표 협약은 정부 구성 합의와 별개입니다. 위원회 접수 원문은 보류 중입니다.</small>`}</div>
            <details class="israel-method"><summary>${e(pollLabel(board, poll))} · ${poll.n_respondents == null ? '표본 미확인' : `응답 ${e(poll.n_respondents)}명`} · 조사방법·원문</summary><p>조사기관 ${e(ko(poll.pollster))}</p><p>현장 ${e(poll.field_start || '미확인')} ~ ${e(poll.field_end || '미확인')} · 발표 ${e(poll.published_at || '미확인')}</p>
                <p>표본오차 ${e(poll.sampling_error_as_printed || (poll.sampling_error_pp == null ? '미확인' : `±${poll.sampling_error_pp}%p`))} · 의석 오차범위로 사용하지 않습니다. ${safeLink(poll.source_url)}</p>${poll.hold_reason ? `<p>${e(ko(poll.hold_reason))}</p>` : ''}</details>
            <div class="israel-seat-bar" role="img" aria-label="${grouping === 'ideology' ? '정치 성향' : '연합·협력'}별 발표 의석 분포, ${poll.seat_sum}석">${groups.map((g) => { const s = groupSeatSummary(board, poll, g.id, grouping); return s.total == null ? '' : `<span style="flex:${s.total};background:${g.color}" title="${e(g.label_ko)} 발표 의석 ${s.total}석"></span>`; }).join('')}</div>
            <div class="israel-group-grid" data-israel-grouping-view="${grouping}">${groupCards(board,poll,grouping,selected,canSelect)}</div>
            <p class="israel-preset-caption">의석 조합 살펴보기 <span>같은 조사 안의 산술 합계</span></p><div class="israel-presets" aria-label="의석 조합 예시">${context.presets.map((p) => { const sum = presetSeatSum(board, poll, p.id); return `<button type="button" data-israel-preset="${e(p.id)}" aria-pressed="${presetId === p.id}" ${canSelect && sum.total !== null ? '' : 'disabled'}>${e(p.label_ko)}<b>${sum.total === null ? '합산 보류' : `${sum.total}석`}</b></button>`; }).join('')}</div>
            <section class="israel-coalition" aria-label="선택 명부 의석 계산"><div class="israel-selection-header"><h5>선택한 정당의 의석</h5><button type="button" data-israel-clear ${canSelect ? '' : 'disabled'}>선택 해제</button></div>
                <div class="israel-selected-chips">${selected.map((id) => partyChip(board, id)).join('') || '<span>위의 정당 또는 조합 예시를 선택하세요.</span>'}</div>
                <div data-israel-total aria-live="polite">${total.total === null ? '부분 자료는 의석 조합 계산을 보류합니다.' : `<strong>${total.total}<small>석</small></strong><span>${total.reachesMajority ? '산술 과반 도달' : `61석까지 ${total.gap}석`}</span>`}</div>
                ${total.total !== null ? `<div class="israel-majority-track" role="img" aria-label="선택 의석 ${total.total}석, 산술 과반 기준 61석"><i style="width:${total.total/120*100}%"></i><span style="left:${61/120*100}%"></span></div>` : ''}
                ${preset ? `<p>${e(preset.note_ko)}</p>` : ''}
                <div class="israel-selection-conditions">${activeRelations.filter((r) => ['refusal','conditional','external_support','electoral_refusal'].includes(r.kind)).map((r) => `<p class="israel-condition ${r.kind === 'refusal' || r.kind === 'electoral_refusal' ? 'israel-condition-refusal' : ''}"><b>${e(r.label_ko)}</b> ${e(ko(r.summary))} ${sourceLinks(board, r.source_ids)}</p>`).join('')}</div>
                <p>61석은 120석의 산술 과반입니다. 연정 합의나 정부 구성 확정은 아닙니다.</p></section></section>` : '<p class="israel-notice">선택 기간에 검토한 조사가 없습니다. 다른 기간의 자료를 최신 조사로 대체하지 않습니다.</p>'}
        <section id="israel-relations" class="israel-section">
            ${sectionHeading('02 / 협력과 제약', '누구와 협력하고, 어디에서 막히나', '공동 원칙, 선거 협약, 외부 지지, 참여 거부를 구분했습니다. 확률이나 최종 연정 예측은 제공하지 않습니다.')}
            <div class="israel-relation-filters" role="group" aria-label="연정 관계 필터">${[['all','모든 관계'],['likud','리쿠드와의 관계']].map(([id,label]) => `<button type="button" data-israel-relation-filter="${id}" aria-pressed="${relationFilter === id}">${label}</button>`).join('')}</div>
            <div class="israel-relation-grid">${relations.map((r) => `<article class="israel-relation-card israel-relation-${e(r.kind)}"><div class="israel-relation-top"><span class="israel-relation-badge">${e(r.label_ko)}</span><time>${e(r.event_date)}</time></div><div class="israel-relation-parties">${relationshipParties(board,r)}</div>
                <p>${e(ko(r.summary))}</p><p class="israel-relation-condition">${e(ko(r.condition))}</p><footer>${sourceLinks(board,r.source_ids)}</footer></article>`).join('')}</div>
        </section>
        <section id="israel-threshold" class="israel-section">${sectionHeading('03 / 봉쇄선', '의석을 얻지 못할 수 있는 명부', '봉쇄선 관련 발표 지지율 · 정당명 아래 대표 인물과 소속을 함께 표시합니다.')}
            <p class="israel-notice">${e(board.rules.threshold_note_ko)}. 막대는 보도상 기준 3.25%와의 비교입니다.</p>
            ${shares.length ? shares.map((row) => `<div class="israel-card-grid">${(row.values || []).map(shareCard).join('')}</div><p class="israel-source-line">${reviewLabel(row.review_status)} · ${safeLink(row.source_url)} · 선택한 조사의 발표값</p>`).join('') : '<p class="israel-empty">이 조사에서 확인한 명부별 지지율이 없습니다.</p>'}
            <p class="israel-data-note">미발표 지지율·의석은 미확인으로 둡니다. 아래 수치를 의석으로 환산하지 않습니다.</p></section>
        <section id="israel-people" class="israel-section">${sectionHeading('04 / 인물과 질문', '총리 적합도, 누구를 묻는 조사인가', '선거 지지율·예상 의석과 다른 질문입니다. 인물 이름과 정당을 함께 읽어 주세요.')}
            <div class="israel-question-grid">${otherQuestions.length ? otherQuestions.map((row) => `<article class="israel-question-card"><header><h6>${e(questionLabel(row.scenario))}</h6><span>${reviewLabel(row.review_status)}</span></header>${(row.values || []).map((v) => {const p = answers[v.name] ? {name:answers[v.name],role:'기타 응답'} : personProfile(board,v.name); return `<div class="israel-answer"><div><b>${e(p.name)}</b><small>${e(p.role)}</small></div><strong>${v.pct == null ? '미확인' : `${e(v.pct)}%`}</strong></div>`;}).join('')}
                ${row.hold_reason || row.remainder_not_stated ? '<p class="israel-data-note">응답 일부 미확인 · 100%로 재조정하지 않습니다.</p>' : ''}<footer>${safeLink(row.source_url)}</footer></article>`).join('') : '<p class="israel-empty">이 조사에서 검토한 총리 적합도·기타 질문이 없습니다.</p>'}</div></section>
        <details class="israel-details"><summary>발언 원기록 · 발언자와 참여 조건</summary><p>아래는 원기록의 검토 상태입니다. 날짜 미확인 발언은 현재의 확정 입장으로 올리지 않습니다.</p>
            ${positions.map((row) => { const p = row.list_id ? partyProfile(board,row.list_id) : null; return `<article><div class="israel-record-heading"><strong>${e(ko(row.speaker,'발언자 미확인'))}</strong><span>${e(positionLabel(row.position_type))}</span></div><p>${e(row.role ? ko(row.role) : p ? p.description : '직책 미확인')}</p><p>${e(row.speech_day || '발언일 미확인')} · ${reviewLabel(row.review_status)} · ${safeLink(row.source_url)}</p>${row.about ? `<p>${e(ko(row.about))}</p>` : ''}${(row.conditions_listed_in_article || row.conditions_as_paraphrased_by_n12 || []).map((s) => `<p>· ${e(ko(s))}</p>`).join('')}${row.sequence ? '<p>최초 조건부 발언 뒤 참여 거부로 정정한 기록이 있습니다.</p>' : ''}${row.hold_reason ? `<p class="israel-data-note">${e(ko(row.hold_reason))}</p>` : ''}</article>`;}).join('')}</details>
        <details class="israel-details"><summary>잉여표 협약 발표 · 위원회 접수 보류</summary><p>같이 정부에 참여한다는 뜻과 구분합니다. 위원회 접수 원문이 없어 의석 배분 계산은 보류합니다.</p>
            <div class="israel-agreement-grid">${[['k26:מחל','k26:ט'],['k26:רק','k26:ל'],['k26:דרך','k26:אמת'],['k26:ודם','k26:עם'],['k26:שס','k26:ג']].map((pair) => `<article>${partyChip(board,pair[0])}<span>↔</span>${partyChip(board,pair[1])}</article>`).join('')}</div>${agreements.map((row) => `<p>${e(row.speech_day || row.published?.slice(0,10) || '날짜 미확인')} · 발표 보도 · ${safeLink(row.source_url)}</p>`).join('')}</details>
        <details class="israel-details"><summary>조사 기록 ${polls.length}건 · 보류 기록 ${held.length}건</summary>${polls.map((row) => `<p>${e(pollLabel(board,row))} · 합계 ${row.seat_sum}석 · ${safeLink(row.source_url)}</p>`).join('')}${held.map((row) => `<p>${e(ko(row.publisher,'발표 매체 미확인'))} · 보류 · ${e(ko(row.hold_reason,'원문·회차 미확인'))} · ${safeLink(row.source_url)}</p>`).join('')}</details>
        <details class="israel-details"><summary>보도 명부 ${board.lists.length}개 · 공식 후보 순위 보류</summary><p>${safeLink(board.list_source.url,board.list_source.publisher)} 보도 기준 · 후보 순위·현직 의석 미확인</p>
            ${board.lists.map((list) => {const p=partyProfile(board,list.id);return `<div class="israel-roster-row"><b>${e(p.name)}</b><span>${e(p.leader)}</span><details><summary>원문 표기</summary><span lang="he" dir="auto">${e(list.ballot)} · ${e(list.name_he)}</span></details></div>`;}).join('')}</details>
        <details class="israel-details"><summary>일정 · 공식 확인 공백 · 번역 정보</summary>${board.calendar.map((row) => `<p>${e(row.label_ko)} · ${e(row.date || '미확인')} · ${row.official_source_opened ? '공식 확인' : row.date ? '보도·잠정 근거 / 공식 확인 보류' : '보류'}</p>`).join('')}<p>판결은 방송사 보관 요약 사본 확인 · 법원 공식 원문·전체 이유 보류.</p>
            <p>한국어 문구: Gemini API 사전 번역 · 기계 번역 · ${e(board.localization?.model || '모델 미확인')} · ${board.localization?.translations?.length || 0}개. 번역은 정치적 분류와 조사 수치를 결정하지 않습니다.</p><p>의석 배분·총리 승률·평균 계산은 연결하지 않았습니다.</p></details>
    </section>`;
};

export const mountIsraelAnalysis = (root, result, { today = koreaToday() } = {}) => {
    if (!root) return;
    root.closest('.elections-modal-host')?.classList.add('israel-analysis-host');
    const state = { days: null, pollId: null, selected: [], presetId: null, grouping: 'cooperation', relationFilter: 'all', today };
    const css = document.createElement('link');
    css.rel='stylesheet'; css.href=new URL('./israel-analysis.css',import.meta.url).href;
    if (!document.querySelector('link[data-israel-style]')) {css.dataset.israelStyle='1';document.head.append(css);}
    const render = (focusSelector = null) => {
        const detailKey = (el) => el.dataset.israelDetails || el.querySelector('summary')?.textContent;
        const details = new Set([...root.querySelectorAll('details[open]')].map(detailKey));
        const container = root.closest('.elections-modal-body');
        const scroll = container?.scrollTop;
        root.innerHTML=israelAnalysisHtml(result?.board,state);
        if (!result?.board) return;
        root.querySelectorAll('details').forEach((el) => {if(details.has(detailKey(el))) el.open=true;});
        state.pollId=root.querySelector('[data-israel-poll]')?.value || null;
        const reset = () => {state.selected=[];state.presetId=null;};
        root.querySelector('[data-israel-window]')?.addEventListener('change',(ev) => {state.days=ev.target.value?Number(ev.target.value):null;state.pollId=null;reset();render('[data-israel-window]');});
        root.querySelector('[data-israel-poll]')?.addEventListener('change',(ev) => {state.pollId=ev.target.value;reset();render('[data-israel-poll]');});
        root.querySelectorAll('[data-israel-list]').forEach((cb) => cb.addEventListener('change',() => {state.selected=[...root.querySelectorAll('[data-israel-list]:checked')].map((el)=>el.dataset.israelList);state.presetId=null;render(`[data-israel-list="${cb.dataset.israelList}"]`);}));
        root.querySelectorAll('[data-israel-preset]').forEach((button) => button.addEventListener('click',() => {const p=result.board.coalition_context.presets.find((row)=>row.id===button.dataset.israelPreset);state.selected=[...p.list_ids];state.presetId=p.id;render(`[data-israel-preset="${p.id}"]`);}));
        root.querySelectorAll('[data-israel-grouping]').forEach((button) => button.addEventListener('click',() => {state.grouping=button.dataset.israelGrouping;render(`[data-israel-grouping="${state.grouping}"]`);}));
        root.querySelectorAll('[data-israel-relation-filter]').forEach((button) => button.addEventListener('click',() => {state.relationFilter=button.dataset.israelRelationFilter;render(`[data-israel-relation-filter="${state.relationFilter}"]`);}));
        root.querySelectorAll('.israel-section-nav a').forEach((link) => link.addEventListener('click',(ev)=>{ev.preventDefault();root.querySelector(link.getAttribute('href'))?.scrollIntoView({behavior:'smooth',block:'start'});}));
        root.querySelector('[data-israel-clear]')?.addEventListener('click',()=>{reset();render('[data-israel-clear]');});
        if (focusSelector) root.querySelector(focusSelector)?.focus({preventScroll:true});
        if (container && scroll !== undefined) container.scrollTop=scroll;
    };
    render();
};
