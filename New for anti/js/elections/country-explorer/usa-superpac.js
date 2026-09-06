import { escapeHtml } from '../ui.js';

const offices = { house: '연방 하원', senate: '연방 상원', president: '대통령', governor: '주지사' };
const partyLabel = (value) => ({ DEM: '민주당', REP: '공화당 (REP)', GOP: '공화당 (GOP)', IND: '무소속', UNKNOWN: '정당 미확인' }[value] || value);
const categories = { super_pac: '슈퍼팩 (FEC O)', single_candidate_ie: '단일후보 독립지출 위원회 (U)', hybrid_pac: '하이브리드 PAC', state_independent_expenditure_committee: '주 독립지출 위원회', other_independent_spender: '기타 독립지출', unclassified: '분류 미확인' };
const qualityLabels = { memo: '메모 항목', candidate_office_conflict: '후보 ID·직위 불일치', out_of_scope_office: '범위 밖·미기재 직위', unresolved_id: '후보 ID 미확인', unresolved_state: '주 미확인', unresolved_district: '선거구 미확인', amendment_status_unverified: '정정 여부 미확인', duplicate_sub_id: '중복 공시', deleted: '삭제 공시', notice_or_unknown: '긴급보고·유형 미확인', missing_amount: '금액 누락', invalid_amount: '금액 오류', unresolved_support_oppose: '지지·반대 미확인' };
const phaseLabel = (code) => /^P\d{4}$/.test(code) ? `경선 (${code})` : /^G\d{4}$/.test(code) ? `본선 (${code})` : code;
const usd = (cents) => Number.isSafeInteger(cents) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100) : '미확보';
const option = (value, text) => `<option value="${escapeHtml(value)}">${escapeHtml(text)}</option>`;
const safeUrl = (url) => { try { return new URL(url).protocol === 'https:' ? url : '#'; } catch { return '#'; } };

export const aggregateParties = (rows) => {
    const parties = new Map();
    rows.forEach((row) => {
        const key = row.party || 'UNKNOWN';
        const value = parties.get(key) || { party: key, support_cents: 0, oppose_cents: 0 };
        value.support_cents += row.support_cents;
        value.oppose_cents += row.oppose_cents;
        parties.set(key, value);
    });
    return [...parties.values()];
};

const load = async (path) => {
    const response = await fetch(`/public/data/${path}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('공시 파일을 불러오지 못했습니다.');
    return response.json();
};

// Mounted separately: the existing reviewed board and maps keep their contract.
export const mountUsaSuperpac = (root, { stateId = 'US' } = {}) => {
    const panel = document.createElement('details');
    panel.className = 'elections-disclosure';
    panel.innerHTML = '<summary>슈퍼팩 분석 · 경선 포함</summary><div data-superpac-body><p>펼치면 공개 공시를 불러옵니다.</p></div>';
    root.append(panel);
    let started = false;
    panel.addEventListener('toggle', async () => {
        if (!panel.open || started) return;
        started = true;
        const body = panel.querySelector('[data-superpac-body]');
        body.textContent = '공시 수집 상태 확인 중…';
        try {
            const index = await load('usa_superpac_index_v1.json');
            if (!panel.isConnected) return;
            const cycles = Object.keys(index.cycles || {}).sort().reverse();
            if (!cycles.length) {
                body.textContent = index.reason_ko || '전국 공시 수집 전입니다. 미수집은 지출 0을 뜻하지 않습니다.';
                return;
            }
            body.innerHTML = `<p class="elections-panel-note">후보를 대상으로 한 공개 독립지출입니다. 정당별 수치는 대상 후보의 정당 기준이며 후보 캠프 후원금과 다릅니다.</p>
                <div class="elections-card-grid">
                <label>공시 사이클 <select data-cycle>${cycles.map((c) => option(c, c)).join('')}</select></label>
                <label>지역 <select data-state></select></label>
                <label>선거 <select data-office>${option('', '전체')}${Object.entries(offices).map(([k, v]) => option(k, v)).join('')}</select></label>
                <label>단체 종류 <select data-category>${option('super_pac', categories.super_pac)}${option('', '전체 독립지출')}${Object.entries(categories).filter(([k]) => k !== 'super_pac').map(([k, v]) => option(k, v)).join('')}</select></label>
                <label>대상 정당 <select data-party></select></label>
                <label>경선·본선 <select data-phase></select></label>
                <label>하원 선거구 <input data-district placeholder="01 / 00(전역)" maxlength="2"></label>
                <label>후보·단체 검색 <input data-query type="search" placeholder="이름 또는 공시 ID"></label>
                </div><div data-health></div><div data-results></div>`;
            const field = (name) => body.querySelector(`[data-${name}]`);
            let shard = { spending: [], candidates: [] };
            let generation = 0;
            let page = 0;
            let loading = false;
            const draw = () => {
                if (loading) return;
                const meta = index.cycles[field('cycle').value];
                const state = field('state').value;
                const selectedOffice = field('office').value;
                const query = field('query').value.trim().toLowerCase();
                const district = field('district').value.trim();
                const rows = (shard.spending || []).filter((r) => (!selectedOffice || r.office === selectedOffice)
                    && (!field('category').value || r.category === field('category').value)
                    && (!field('party').value || r.party === field('party').value)
                    && (!field('phase').value || r.election_type === field('phase').value)
                    && (!district || (r.office === 'house' && r.district === district.padStart(2, '0')))
                    && (!query || [r.candidate_name, r.candidate_id, r.committee_name, r.committee_id].some((v) => String(v).toLowerCase().includes(query))));
                const stale = Date.now() - Date.parse(meta.generated_at) > 72 * 3600 * 1000;
                const coverage = meta.coverage?.governor?.[state];
                field('health').innerHTML = `<p class="elections-panel-note">${meta.status === 'partial' ? '일부 자료 · 검증 제외 항목 있음' : '처리된 정기보고 기준'} · 수집 ${escapeHtml(meta.generated_at)}${stale ? ' · 72시간 이상 경과: 갱신 지연' : ''} · 최신 포함 신고 ${escapeHtml(meta.coverage?.last_filing_date || '미확보')} · 긴급보고 제외</p>
                    ${coverage && (!selectedOffice || selectedOffice === 'governor') ? `<p>${escapeHtml(coverage.reason_ko)}</p>` : ''}
                    <p>정정 여부·후보 식별 등의 검증에서 제외된 행: ${Object.entries(meta.quality?.excluded_records || {}).map(([key, count]) => `${escapeHtml(qualityLabels[key] || '기타 검증 제외')} ${Number(count).toLocaleString()}건`).join(' · ') || '없음'}</p>`;
                const partyTotals = aggregateParties(rows);
                const candidates = (shard.candidates || []).filter((c) => (!selectedOffice || ({ H: 'house', S: 'senate', P: 'president' }[c.office]) === selectedOffice)
                    && (!field('party').value || c.party === field('party').value)
                    && (!district || (c.office === 'H' && String(c.district).padStart(2, '0') === district.padStart(2, '0')))
                    && (!query || `${c.name} ${c.candidate_id}`.toLowerCase().includes(query)));
                const shown = rows.slice(page * 100, (page + 1) * 100);
                field('results').innerHTML = `<div class="elections-card-grid">${partyTotals.map((p) => `<article class="elections-card"><div>${escapeHtml(partyLabel(p.party))} 후보 대상</div><div>지지 ${usd(p.support_cents)} · 반대 ${usd(p.oppose_cents)}</div></article>`).join('')}</div>
                    <p>${rows.length}개 후보·단체·선거유형 조합${rows.length ? ` · ${page + 1}/${Math.ceil(rows.length / 100)}쪽` : ' · 해당 필터의 집계 없음 (실제 지출 0 또는 후보 미출마를 뜻하지 않음)'}</p>
                    ${shown.map((r) => `<details class="elections-disclosure"><summary>${escapeHtml(r.candidate_name)} · ${escapeHtml(partyLabel(r.party))} · ${escapeHtml(offices[r.office])} ${escapeHtml(r.district || '')} · ${escapeHtml(phaseLabel(r.election_type))} / ${escapeHtml(r.committee_name)}</summary><p>지지 ${usd(r.support_cents)} · 반대 ${usd(r.oppose_cents)} · ${escapeHtml(categories[r.category])}</p><p>${escapeHtml(r.candidate_id)} / ${escapeHtml(r.committee_id)}</p><p>${Object.entries(r.monthly || {}).sort().map(([month, value]) => `${escapeHtml(month)}: 지지 ${usd(value.support_cents)}, 반대 ${usd(value.oppose_cents)}`).join('<br>')}</p><a href="${escapeHtml(safeUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">원본 공시</a></details>`).join('')}
                    <button type="button" data-prev ${page === 0 ? 'disabled' : ''}>이전</button> <button type="button" data-next ${(page + 1) * 100 >= rows.length ? 'disabled' : ''}>다음</button>
                    <details class="elections-disclosure"><summary>FEC 등록 후보 ${candidates.length}명 · 경선 후보 포함</summary><p>투표용지 등재·사퇴·경선 통과 여부는 미검증. 공시가 없는 후보도 포함합니다. 후보 검색으로 좁힐 수 있습니다.</p>${candidates.slice(0, 100).map((c) => `<div>${escapeHtml(c.name)} · ${escapeHtml(partyLabel(c.party))} · ${escapeHtml(c.candidate_id)} · ${escapeHtml(c.election_year)}</div>`).join('')}${candidates.length > 100 ? '<p>처음 100명 표시. 후보 검색을 사용하세요.</p>' : ''}</details>
                    <details class="elections-disclosure"><summary>자료 범위와 한계</summary>${(meta.limitations_ko || []).map((v) => `<p>${escapeHtml(v)}</p>`).join('')}</details>`;
                field('prev').addEventListener('click', () => { page -= 1; draw(); });
                field('next').addEventListener('click', () => { page += 1; draw(); });
            };
            const readState = async () => {
                const token = ++generation;
                loading = true;
                field('results').textContent = '선택 지역 공시 로딩 중…';
                field('health').textContent = '';
                shard = { spending: [], candidates: [] };
                const meta = index.cycles[field('cycle').value];
                const path = meta.state_files[field('state').value];
                try {
                    const next = path ? await load(path) : { spending: [], candidates: [] };
                    if (token !== generation || !panel.isConnected) return;
                    shard = next;
                    loading = false;
                    field('party').innerHTML = option('', '전체') + [...new Set([...shard.spending, ...shard.candidates].map((r) => r.party || 'UNKNOWN'))].sort().map((v) => option(v, partyLabel(v))).join('');
                    field('phase').innerHTML = option('', '전체') + [...new Set(shard.spending.map((r) => r.election_type))].sort().map((v) => option(v, phaseLabel(v))).join('');
                    page = 0; draw();
                } catch (error) {
                    if (token === generation) { loading = true; field('results').textContent = error.message; }
                }
            };
            const readCycle = () => {
                const meta = index.cycles[field('cycle').value];
                const states = [...new Set([...Object.keys(meta.state_files), ...Object.keys(meta.coverage?.governor || {})])].sort();
                field('state').innerHTML = states.map((s) => option(s, s === 'US' ? '전국 · 대통령' : s)).join('');
                field('state').value = states.includes(stateId) ? stateId : states[0];
                readState();
            };
            field('cycle').addEventListener('change', readCycle);
            field('state').addEventListener('change', readState);
            field('office').addEventListener('change', () => { if (field('office').value === 'governor') { field('category').value = ''; page = 0; draw(); } });
            ['office', 'category', 'party', 'phase', 'district', 'query'].forEach((name) => field(name).addEventListener('input', () => { page = 0; draw(); }));
            readCycle();
        } catch (error) {
            body.textContent = `${error.message} 미수집은 지출 0을 뜻하지 않습니다.`;
            started = false;
        }
    });
};
