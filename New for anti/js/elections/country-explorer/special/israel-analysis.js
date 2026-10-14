import { escapeHtml } from '../../ui.js';
import { canCalculate, dayAge, koreaToday, seatPolls, selectedSeatSum, sourceHref } from '../../data/israel-analysis.js';

const labels = {
    'דרך': '야샤르', 'מחל': '리쿠드', 'רק': '비야하드', 'אמת': '데모크라트', 'ל': '이스라엘 베이테누',
    'ג': '통합토라유다', 'ודם': '공동명부', 'שס': '샤스', 'ב': '오츠마 예후디트',
    'ט': '종교시온주의·제후트', 'עם': '라암', 'ך': '암하 이스라엘', 'די': '예비군·신경제',
    'כן': '청백', 'זך': '하레디 공중', 'ני': '노암',
};
const colors = ['#60a5fa', '#fb7185', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#22d3ee', '#c084fc', '#f97316', '#2dd4bf', '#818cf8', '#a3e635', '#94a3b8'];
const reviewLabel = (state) => ({ accepted: '원문 채택', partial: '부분 자료', held: '보류' }[state] || '미확인');
const questionLabel = (scenario) => ({ eisenkot_vs_netanyahu: '아이젠콧·네타냐후 총리 적합도',
    bennett_vs_netanyahu: '베넷·네타냐후 총리 적합도', netanyahu_vs_lieberman: '네타냐후·리버만 총리 적합도',
    open_who_should_be_pm: '총리 적합도 전체 질문', haredi_party_in_next_coalition: '초정통 정당의 다음 연정 참여' }[scenario] || '별도 질문');
const answerLabel = (name) => ({ neither: '둘 다 아님', dont_know: '모름', support: '찬성', oppose: '반대' }[name] || name);
const positionLabel = (type) => ({ statement_then_clarification: '발언 뒤 정정', refusal: '참여·협력 거부 발언',
    external_support: '외부 지지 발언', conditional_external_support: '외부 지지 조건',
    not_in_either_bloc: '어느 블록에도 속하지 않는다는 발언', journalist_and_speaker_prediction: '전망·해석', conditional: '조건부 입장' }[type] || '관련 발언');
const agreementLabel = (id) => ({ 'surplus-likud-rz-2026-10-06': '리쿠드–종교시온주의',
    'surplus-change-bloc-2026-09-10': '비야하드–이스라엘 베이테누 / 야샤르–데모크라트',
    'surplus-joint-raam-2026-09-11': '공동명부–라암', 'surplus-shas-utj-2026-10-11': '샤스–통합토라유다',
    'surplus-map-2026-10-13': '발표된 협약 묶음 재보도' }[id] || '협약 발표');
const readable = (value) => value === null || value === undefined ? '미확인' : value;
const safeLink = (url, label = '원문') => sourceHref(url)
    ? `<a href="${escapeHtml(sourceHref(url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : '출처 미확인';
const nameOf = (list) => labels[list?.ballot] || list?.name_en || list?.name_he || '명부 미확인';
const pollLabel = (poll) => `${poll.publisher || '발표 매체 미확인'} · ${poll.field_end || poll.published_at?.slice(0, 10) || '날짜 미확인'} · ${reviewLabel(poll.review_status)}`;

export const israelAnalysisPlaceholder = () => '<div data-israel-analysis></div>';

export const israelAnalysisHtml = (board, { pollId = null, days = null, selected = [], today = koreaToday() } = {}) => {
    if (!board) return '<p class="elections-muted" role="status">이스라엘 검토 자료를 불러오지 못했습니다. 조사 없음이나 0석으로 대체하지 않습니다.</p>';
    const polls = seatPolls(board, { days, today });
    const poll = polls.find((row) => row.poll_id === pollId)
        || polls.find((row) => row.review_status === 'accepted') || polls[0] || null;
    const index = new Map(board.lists.map((list, i) => [list.id, { ...list, color: colors[i % colors.length] }]));
    const values = [...(poll?.values || [])].sort((a, b) => b.seats - a.seats);
    const total = selectedSeatSum(poll, selected, board);
    const age = dayAge(board.evidence_as_of, today);
    const canSelect = canCalculate(poll, board);
    const shares = board.observations.filter((row) => row.poll_id === poll?.poll_id && row.question_id === 'party_vote_share');
    const otherQuestions = board.observations.filter((row) => row.poll_id === poll?.poll_id && ['preferred_pm', 'approval'].includes(row.question_id));
    const held = board.observations.filter((row) => row.question_id === 'reported_seats' && row.review_status === 'held');
    const positions = board.coalition_positions.filter((row) => row.record_type === 'position' && !row.position_type?.includes('surplus'));
    const agreements = board.coalition_positions.filter((row) => row.position_type?.includes('surplus'));
    return `<section class="israel-analysis">
        <header class="israel-heading"><p class="israel-eyebrow">26대 크네세트 · 조사별 의석</p>
            <h4>이스라엘 선거 분석</h4><p>검토 기준 ${escapeHtml(board.evidence_as_of)} · ${age > 0 ? `${age}일 경과 · ` : ''}검토 스냅샷 · 자동 갱신 미설치</p>
        </header>
        <div class="israel-stats">
            <div><strong>${board.coverage.accepted_seat_polls}</strong><span>원문 채택 조사</span></div>
            <div><strong>${board.coverage.partial_seat_polls}</strong><span>부분 자료</span></div>
            <div><strong>120</strong><span>분석 의석 단위</span></div>
        </div>
        <p class="israel-notice">최근 30일 전수 미완료 · 현직 의석·공식 후보 순위 보류. 예상 의석은 언론 발표값입니다.</p>
        ${age < 0 ? '<p class="israel-notice">검토일이 현재 날짜보다 뒤에 있습니다. 날짜를 확인하세요.</p>' : ''}
        <div class="israel-controls">
            <label>조사 기간<select data-israel-window>
                ${[[null, '전체 검토 기록'], [7, '최근 7일'], [14, '최근 14일']].map(([value, label]) => `<option value="${value ?? ''}" ${days === value ? 'selected' : ''}>${label}</option>`).join('')}
            </select></label>
            <label>발표 조사<select data-israel-poll ${polls.length ? '' : 'disabled'}>
                ${polls.length ? polls.map((row) => `<option value="${escapeHtml(row.poll_id)}" ${row.poll_id === poll?.poll_id ? 'selected' : ''}>${escapeHtml(pollLabel(row))}</option>`).join('') : '<option>기간 내 검토 조사 없음</option>'}
            </select></label>
        </div>
        ${poll ? `<div class="israel-poll-meta"><strong>${escapeHtml(pollLabel(poll))}</strong>
            <p>조사기관 ${escapeHtml(readable(poll.pollster))} · 응답 ${escapeHtml(readable(poll.n_respondents))}명</p>
            <p>현장 ${escapeHtml(readable(poll.field_start))} ~ ${escapeHtml(readable(poll.field_end))} · 발표 ${escapeHtml(poll.published_at || '미확인')}</p>
            <p>표본오차 ${escapeHtml(poll.sampling_error_as_printed || (poll.sampling_error_pp == null ? '미확인' : `±${poll.sampling_error_pp}%p`))} · 의석 오차범위로 사용하지 않습니다. ${safeLink(poll.source_url)}</p>
            ${poll.hold_reason ? `<p class="israel-notice">${escapeHtml(poll.hold_reason)}</p>` : ''}</div>
            <div class="israel-seat-bar" role="img" aria-label="선택한 조사의 발표 의석 합계 120석">${values.map((value) => `<span style="flex:${value.seats};background:${index.get(value.list_id).color}" title="${escapeHtml(nameOf(index.get(value.list_id)))} ${value.seats}석"></span>`).join('')}</div>
            <div class="israel-seat-list">${values.map((value) => {
                const list = index.get(value.list_id);
                return `<label class="israel-seat-row"><input type="checkbox" data-israel-list="${escapeHtml(value.list_id)}" ${selected.includes(value.list_id) ? 'checked' : ''} ${canSelect ? '' : 'disabled'}>
                    <span class="israel-party-dot" style="background:${list.color}"></span><span class="israel-party-name">${escapeHtml(nameOf(list))}<small lang="he" dir="auto">${escapeHtml(value.name_as_published)}</small></span><strong>${value.seats}<small>석</small></strong></label>`;
            }).join('')}</div>
            <section class="israel-coalition" aria-label="선택 명부 의석 계산"><h5>선택 명부의 의석 합계</h5>
                <div data-israel-total aria-live="polite">${total.total === null ? '부분 자료는 의석 조합 계산을 보류합니다.' : `<strong>${total.total}석</strong> · ${total.reachesMajority ? '산술 과반 도달' : `61석까지 ${total.gap}석`}`}</div>
                <p>같은 조사에서 선택한 명부만 더합니다. 61석은 120석의 산술 과반이며, 연정 합의나 정부 구성 확정은 아닙니다.</p>
                <button type="button" class="elections-button" data-israel-clear ${canSelect ? '' : 'disabled'}>선택 해제</button>
            </section>
            <details class="israel-details"><summary>봉쇄선 관련 발표 지지율</summary>
                <p>${escapeHtml(board.rules.threshold_note_ko)}</p>
                ${shares.length ? shares.map((row) => `<p>${escapeHtml(reviewLabel(row.review_status))} · ${safeLink(row.source_url)}</p>${(row.values || []).map((value) => `<div class="israel-small-row"><span>${escapeHtml(index.has(value.list_id) ? nameOf(index.get(value.list_id)) : value.name_as_published)}</span><strong>${value.pct == null ? '미확인' : `${escapeHtml(value.pct)}%`}</strong></div>`).join('')}`).join('') : '<p>이 조사에서 확인한 명부별 지지율이 없습니다.</p>'}
                <p>의석을 득표율로 역산하지 않습니다. 미발표 값은 미확인입니다.</p>
            </details>
            ${otherQuestions.length ? `<details class="israel-details"><summary>총리 적합도·기타 질문</summary><p>선거 지지율·예상 의석과 다른 질문입니다. 미발표 응답은 채우지 않습니다.</p>
                ${otherQuestions.map((row) => `<article><p><strong>${escapeHtml(questionLabel(row.scenario))}</strong> · ${escapeHtml(reviewLabel(row.review_status))} · ${safeLink(row.source_url)}</p>
                    ${(row.values || []).map((value) => `<div class="israel-small-row"><span dir="auto">${escapeHtml(answerLabel(value.name))}</span><strong>${value.pct == null ? '미확인' : `${escapeHtml(value.pct)}%`}</strong></div>`).join('')}
                    ${row.hold_reason || row.remainder_not_stated ? '<p>응답 일부 미확인 · 100%로 재조정하지 않습니다.</p>' : ''}</article>`).join('')}</details>` : ''}`
            : '<p class="israel-notice">선택 기간에 검토한 조사가 없습니다. 다른 기간의 자료를 최신 조사로 대체하지 않습니다.</p>'}
        <details class="israel-details"><summary>조사 기록 ${polls.length}건 · 보류 기록 ${held.length}건</summary>
            ${polls.map((row) => `<p>${escapeHtml(pollLabel(row))} · 합계 ${row.seat_sum}석 · ${safeLink(row.source_url)}</p>`).join('')}
            ${held.map((row) => `<p>${escapeHtml(row.publisher || row.poll_id)} · 보류 · ${escapeHtml(row.hold_reason || '원문·회차 미확인')} · ${safeLink(row.source_url)}</p>`).join('')}
        </details>
        <details class="israel-details"><summary>연정 관련 발언 · 참여 조건</summary><p>보도된 발언과 정정을 함께 보관합니다. 참여 확정이나 연정 성립 확률로 사용하지 않습니다.</p>
            ${positions.map((row) => `<article><p><strong dir="auto">${escapeHtml(row.speaker || row.id)}</strong> · ${escapeHtml(row.speech_day || '발언일 미확인')} · ${escapeHtml(reviewLabel(row.review_status))} · ${safeLink(row.source_url)}</p>
                <p>${escapeHtml(positionLabel(row.position_type))}</p>${row.sequence ? '<p>첫 발언 뒤 정정이 있어 단일 입장으로 확정하지 않습니다.</p>' : ''}</article>`).join('')}
        </details>
        <details class="israel-details"><summary>잉여표 협약 발표 · 위원회 접수 보류</summary><p>보도된 협약 발표입니다. 위원회 접수 원문 미확보로 의석 배분 계산에 사용하지 않습니다.</p>
            ${agreements.map((row) => `<p>${escapeHtml(row.speech_day || row.published?.slice(0, 10) || '날짜 미확인')} · ${escapeHtml(agreementLabel(row.id))} · ${safeLink(row.source_url)}</p>`).join('')}
        </details>
        <details class="israel-details"><summary>보도 명부 ${board.lists.length}개 · 공식 후보 순위 보류</summary>
            <p>출처 ${safeLink(board.list_source.url, board.list_source.publisher)} · 보도 명부와 공식 확정 후보 명단을 구분합니다. 현직 의석은 재수집 전까지 미확인입니다.</p>
            ${board.lists.map((list) => `<div class="israel-roster-row"><strong>${escapeHtml(nameOf(list))}</strong><span lang="he" dir="auto">${escapeHtml(list.ballot)} · ${escapeHtml(list.name_he)}</span><small>후보 순위 미확인 · 공식 명부 확인 보류</small></div>`).join('')}
        </details>
        <details class="israel-details"><summary>일정 · 공식 확인 공백</summary>
            ${board.calendar.map((row) => `<p>${escapeHtml(row.label_ko)} · ${escapeHtml(row.date || '미확인')} · ${row.official_source_opened ? '공식 확인' : row.date ? '보도·잠정 근거 / 공식 확인 보류' : '보류'}</p>`).join('')}
            <p>판결은 방송사 보관 요약 사본 확인 · 법원 공식 원문·전체 이유 보류.</p>
            <p>의석 배분·총리 승률·평균 계산은 연결하지 않았습니다.</p>
        </details>
    </section>`;
};

export const mountIsraelAnalysis = (root, result, { today = koreaToday() } = {}) => {
    if (!root) return;
    root.closest('.elections-modal-host')?.classList.add('israel-analysis-host');
    const state = { days: null, pollId: null, selected: [], today };
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = new URL('./israel-analysis.css', import.meta.url).href;
    if (!document.querySelector('link[data-israel-style]')) { css.dataset.israelStyle = '1'; document.head.append(css); }
    const render = () => {
        root.innerHTML = israelAnalysisHtml(result?.board, state);
        if (!result?.board) return;
        state.pollId = root.querySelector('[data-israel-poll]')?.value || null;
        root.querySelector('[data-israel-window]')?.addEventListener('change', (event) => {
            state.days = event.target.value ? Number(event.target.value) : null;
            state.pollId = null; state.selected = []; render();
        });
        root.querySelector('[data-israel-poll]')?.addEventListener('change', (event) => {
            state.pollId = event.target.value; state.selected = []; render();
        });
        root.querySelectorAll('[data-israel-list]').forEach((checkbox) => checkbox.addEventListener('change', () => {
            state.selected = [...root.querySelectorAll('[data-israel-list]:checked')].map((el) => el.dataset.israelList);
            const poll = result.board.observations.find((row) => row.poll_id === state.pollId && row.question_id === 'reported_seats');
            const sum = selectedSeatSum(poll, state.selected, result.board);
            root.querySelector('[data-israel-total]').textContent = sum.total === null ? '계산 보류'
                : `${sum.total}석 · ${sum.reachesMajority ? '산술 과반 도달' : `61석까지 ${sum.gap}석`}`;
        }));
        root.querySelector('[data-israel-clear]')?.addEventListener('click', () => { state.selected = []; render(); });
    };
    render();
};
