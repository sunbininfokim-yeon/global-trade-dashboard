import { escapeHtml } from '../../ui.js';

// The 선거 panel reads one rule: 더 많은 슈퍼팩을 모은 쪽이 승리정당. "모은" is
// support money -- spending *for* a candidate. Oppose money is spent against
// one, and usa_election_finance_index_v1.json's limitations_ko forbids turning
// it into the other side's support ("반대 지출을 다른 후보 또는 정당의 지원액으로
// 전환하지 않습니다"), so it is shown but never counted toward a winner.
//
// Layout follows the sketch: 민주 left, 공화 right, 주지사·상원 always on, and
// the House as one row per district that opens its candidates on click.

// DFL is Minnesota's Democratic affiliate and files under its own FEC code.
const DEM_KEYS = new Set(['DEM', 'DFL']);
const GOP_KEYS = new Set(['REP']);
const SIDES = [
    { key: 'dem', ko: '민주당', keys: DEM_KEYS, color: '#2563eb', cls: 'is-dem' },
    { key: 'gop', ko: '공화당', keys: GOP_KEYS, color: '#dc2626', cls: 'is-gop' },
];

const CANDIDATE_LIMIT = 4;

const supportOf = (totals) => totals?.super_pac?.support_cents ?? null;
const opposeOf = (totals) => totals?.super_pac?.oppose_cents ?? null;

const formatUsd = (cents) => {
    if (cents == null) return null;
    const dollars = cents / 100;
    if (Math.abs(dollars) >= 1_000_000) return `$${(dollars / 1_000_000).toFixed(1)}M`;
    if (Math.abs(dollars) >= 1_000) return `$${(dollars / 1_000).toFixed(0)}K`;
    return `$${Math.round(dollars).toLocaleString('en-US')}`;
};

const sideTotal = (race, keys) => {
    let total = null;
    Object.entries(race.totals_by_reported_party || {}).forEach(([party, node]) => {
        if (!keys.has(party)) return;
        const value = supportOf(node);
        if (value != null) total = (total || 0) + value;
    });
    return total;
};

const winnerOf = (race) => {
    const dem = sideTotal(race, DEM_KEYS);
    const gop = sideTotal(race, GOP_KEYS);
    if (dem == null && gop == null) return null;
    if ((dem || 0) === (gop || 0)) return 'TIE';
    return (dem || 0) > (gop || 0) ? 'DEM' : 'GOP';
};

const winnerBadge = (race) => {
    const winner = winnerOf(race);
    if (!winner) return '<span class="elections-spac-badge is-none">관측 없음</span>';
    if (winner === 'TIE') return '<span class="elections-spac-badge is-none">동률</span>';
    const side = SIDES.find((row) => row.key === (winner === 'DEM' ? 'dem' : 'gop'));
    return `<span class="elections-spac-badge ${side.cls}">${escapeHtml(side.ko)}</span>`;
};

const candidatesForSide = (race, keys) => (race.candidates || [])
    .map((row) => ({
        name: row.name,
        party: (row.reported_parties || [])[0],
        cents: supportOf(row.totals_by_category),
    }))
    .filter((row) => keys.has(row.party) && row.cents != null && row.cents > 0)
    .sort((a, b) => b.cents - a.cents);

const sideColumn = (race, side) => {
    const rows = candidatesForSide(race, side.keys);
    const total = sideTotal(race, side.keys);
    const shown = rows.slice(0, CANDIDATE_LIMIT);
    return `
        <div class="elections-spac-side ${side.cls}">
            <div class="elections-spac-side-head">
                <span>${escapeHtml(side.ko)}</span>
                <strong>${escapeHtml(formatUsd(total) || '관측 없음')}</strong>
            </div>
            ${shown.length ? shown.map((row) => `
                <div class="elections-spac-cand">
                    <span>${escapeHtml(row.name)}</span>
                    <strong>${escapeHtml(formatUsd(row.cents))}</strong>
                </div>`).join('') : '<p class="elections-muted">지원 지출이 관측된 후보 없음</p>'}
            ${rows.length > shown.length ? `<p class="elections-panel-note">외 ${rows.length - shown.length}명</p>` : ''}
        </div>`;
};

const raceBody = (race) => `
    <div class="elections-spac-sides">${SIDES.map((side) => sideColumn(race, side)).join('')}</div>
    ${opposeOf(race.totals_by_category) ? `<p class="elections-panel-note">반대 지출 ${escapeHtml(formatUsd(opposeOf(race.totals_by_category)))} — 승리정당 판정에는 넣지 않습니다.</p>` : ''}`;

const statewideBlock = (label, race) => {
    if (!race) return `
        <section class="elections-spac-block">
            <div class="elections-spac-block-head"><span>${escapeHtml(label)}</span><span class="elections-spac-badge is-none">해당 선거 없음</span></div>
        </section>`;
    return `
        <section class="elections-spac-block">
            <div class="elections-spac-block-head"><span>${escapeHtml(label)}</span>${winnerBadge(race)}</div>
            ${raceBody(race)}
        </section>`;
};

const districtLabel = (race) => {
    const district = String(race.district ?? '').replace(/^0+/, '');
    return district ? `하원 ${district}구` : '하원 전역구';
};

// The row is the button: clicking it opens its own candidate block and tells
// the map which district to light up. Both live on one element so the panel
// and the map can never disagree about which district is selected.
const districtRow = (race) => `
    <div class="elections-spac-district" data-district="${escapeHtml(race.district ?? '')}">
        <button class="elections-spac-district-head" type="button" data-spac-district="${escapeHtml(race.district ?? '')}">
            <span>${escapeHtml(districtLabel(race))}</span>
            ${winnerBadge(race)}
        </button>
        <div class="elections-spac-district-body">${raceBody(race)}</div>
    </div>`;

const byDistrict = (a, b) => String(a.district ?? '').localeCompare(String(b.district ?? ''), undefined, { numeric: true });

export const usaStateSuperPac = (state, races) => {
    if (!Array.isArray(races)) {
        return '<p class="elections-muted">이 주의 선거자금 자료를 불러오지 못했습니다. 로컬 정적 서버에서는 /public/data 경로가 필요합니다.</p>';
    }
    const governor = races.find((race) => race.office === 'governor');
    const senate = races.find((race) => race.office === 'senate');
    const house = races.filter((race) => race.office === 'house').sort(byDistrict);

    return `
        <section class="elections-detail-section">
            ${statewideBlock('주지사', governor)}
            ${statewideBlock('연방 상원의원', senate)}
        </section>
        <section class="elections-detail-section">
            <p class="section-title">연방 하원 · 선거구를 누르면 후보별 금액과 지도 위치가 함께 표시됩니다</p>
            <div class="elections-spac-district-list">${house.map(districtRow).join('') || '<p class="elections-muted">하원 선거구 자료가 없습니다.</p>'}</div>
        </section>
        <p class="elections-panel-note">슈퍼팩(super_pac) 독립지출 중 지지 금액 기준이며, 후보 캠프가 받은 후원금이 아닙니다. 금액이 큰 쪽을 승리정당으로 표시합니다 — 실제 개표 결과가 아닙니다.</p>`;
};
