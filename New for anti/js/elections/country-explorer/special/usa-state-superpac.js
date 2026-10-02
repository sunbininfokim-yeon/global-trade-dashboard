import { escapeHtml } from '../../ui.js';
import { pollEvidenceHtml } from './usa-election-evidence.js';

// Every figure here is independent expenditure: money outside groups spent of
// their own accord to promote or attack a named candidate. The index says so
// itself -- measure_label_ko is "후보 대상 외부 독립지출 (캠프가 받은 후원금 아님)"
// -- and letting a bare amount sit next to a candidate's name would read as
// what they raised, which is a different and politically loaded claim. So the
// direction (지지/반대) is rendered as part of every number, the panel opens
// with what the measure is, and the badge is captioned 지지지출 우세 rather than
// left to look like an election result.
//
// The badge ranks by support only. Oppose money cannot be flipped into the
// other side's support -- the same index's limitations_ko forbids exactly that
// ("반대 지출을 다른 후보 또는 정당의 지원액으로 전환하지 않습니다") -- so it is
// shown in full beside the support figure and left out of the ranking.
//
// Which spending categories count is NOT the same for every office, and the
// index says so in display_contract: federal races are 슈퍼팩 (`super_pac`),
// but a governor's money arrives through state disclosure and is filed under
// `state_independent_*` with the spender type unverified -- calling that
// 슈퍼팩 would be a claim the source explicitly refuses. So the categories and
// the label both come from the contract, per office.
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
const FEDERAL_FALLBACK = ['super_pac'];

// Before the contract ships, every office falls back to super_pac -- which is
// exactly the previous behaviour, so this file is safe to run against either
// version of the data.
const viewFor = (office, contract) => (office === 'governor'
    ? {
        categories: contract?.governor_independent_expenditure_categories || FEDERAL_FALLBACK,
        label: contract?.governor_label_ko || '주 공시 독립지출 (유형 미확인)',
    }
    : {
        categories: contract?.federal_superpac_categories || FEDERAL_FALLBACK,
        label: '슈퍼팩 독립지출',
    });

// null is "not observed" and must never become 0 (the index's rules_ko). A sum
// stays null until at least one listed category is actually observed; once one
// is, the total is a partial sum of the observed ones only.
const sumCents = (totals, categories, field) => {
    let sum = null;
    categories.forEach((category) => {
        const value = totals?.[category]?.[field];
        if (value != null) sum = (sum || 0) + value;
    });
    return sum;
};
const supportOf = (totals, categories) => sumCents(totals, categories, 'support_cents');
const opposeOf = (totals, categories) => sumCents(totals, categories, 'oppose_cents');

const formatUsd = (cents) => {
    if (cents == null) return null;
    const dollars = cents / 100;
    if (Math.abs(dollars) >= 1_000_000) return `$${(dollars / 1_000_000).toFixed(1)}M`;
    if (Math.abs(dollars) >= 1_000) return `$${(dollars / 1_000).toFixed(0)}K`;
    return `$${Math.round(dollars).toLocaleString('en-US')}`;
};

const sideTotals = (race, keys, categories) => {
    let support = null;
    let oppose = null;
    Object.entries(race.totals_by_reported_party || {}).forEach(([party, node]) => {
        if (!keys.has(party)) return;
        const forCents = supportOf(node, categories);
        const againstCents = opposeOf(node, categories);
        if (forCents != null) support = (support || 0) + forCents;
        if (againstCents != null) oppose = (oppose || 0) + againstCents;
    });
    return { support, oppose };
};

const winnerOf = (race, categories) => {
    const dem = sideTotals(race, DEM_KEYS, categories).support;
    const gop = sideTotals(race, GOP_KEYS, categories).support;
    if (dem == null && gop == null) return null;
    if ((dem || 0) === (gop || 0)) return 'TIE';
    return (dem || 0) > (gop || 0) ? 'DEM' : 'GOP';
};

const winnerBadge = (race, categories) => {
    const winner = winnerOf(race, categories);
    if (!winner) return '<span class="elections-spac-badge is-none">관측 없음</span>';
    if (winner === 'TIE') return '<span class="elections-spac-badge is-none">동률</span>';
    const side = SIDES.find((row) => row.key === (winner === 'DEM' ? 'dem' : 'gop'));
    return `<span class="elections-spac-badge ${side.cls}">${escapeHtml(side.ko)}</span>`;
};

// A candidate only ever targeted by attack money belongs on this list as much
// as one being promoted -- filtering on support alone silently dropped them
// (Texas 2026: Colin Allred, $0 support and $15,000 spent against him). Order
// by how much outside money moved around each name, either direction.
const candidatesForSide = (race, keys, categories) => (race.candidates || [])
    .map((row) => ({
        name: row.name,
        party: (row.reported_parties || [])[0],
        support: supportOf(row.totals_by_category, categories),
        oppose: opposeOf(row.totals_by_category, categories),
    }))
    .filter((row) => keys.has(row.party) && ((row.support || 0) > 0 || (row.oppose || 0) > 0))
    .sort((a, b) => ((b.support || 0) + (b.oppose || 0)) - ((a.support || 0) + (a.oppose || 0)));

// Every amount carries its direction. A bare number beside a candidate's name
// reads as "this is what they raised", which is the one thing this measure is
// not -- so 지지/반대 is part of the number, not a caption somewhere else.
const amount = (label, cents, cls) => `<span class="elections-spac-amt ${cls}"><i>${label}</i>${escapeHtml(formatUsd(cents) ?? '—')}</span>`;

const sideColumn = (race, side, categories) => {
    const rows = candidatesForSide(race, side.keys, categories);
    const { support, oppose } = sideTotals(race, side.keys, categories);
    const shown = rows.slice(0, CANDIDATE_LIMIT);
    return `
        <div class="elections-spac-side ${side.cls}">
            <div class="elections-spac-side-head"><span>${escapeHtml(side.ko)} 후보 대상</span></div>
            <div class="elections-spac-amts">
                ${amount('지지', support, 'is-support')}
                ${amount('반대', oppose, 'is-oppose')}
            </div>
            ${shown.length ? shown.map((row) => `
                <div class="elections-spac-cand">
                    <span>${escapeHtml(row.name)}</span>
                    <span class="elections-spac-amts">
                        ${amount('지지', row.support, 'is-support')}
                        ${amount('반대', row.oppose, 'is-oppose')}
                    </span>
                </div>`).join('') : '<p class="elections-muted">관측된 외부 지출 없음</p>'}
            ${rows.length > shown.length ? `<p class="elections-panel-note">외 ${rows.length - shown.length}명</p>` : ''}
        </div>`;
};

const raceBody = (race, view) => `
    <div class="elections-spac-sides">${SIDES.map((side) => sideColumn(race, side, view.categories)).join('')}</div>
    <p class="elections-panel-note">${escapeHtml(view.label)}${race.coverage_note_ko ? ` · ${race.coverage_note_ko}` : ''}</p>
    <p class="elections-panel-note">반대 지출은 그 후보를 떨어뜨리려 쓴 돈입니다. 상대 정당의 지지액으로 옮기지 않으며, 우세 판정에도 넣지 않습니다.</p>`;

// "지지지출 우세" sits next to the party name wherever a badge appears, so the
// badge cannot be read as an election result.
const badgeCaption = '<span class="elections-spac-caption">지지지출 우세</span>';

const statewideBlock = (label, race, contract, pollRace, pollBoard, pollHealth, days) => {
    if (!race) return `
        <section class="elections-spac-block">
            <div class="elections-spac-block-head"><span>${escapeHtml(label)}</span><span class="elections-spac-badge is-none">해당 선거 없음</span></div>
            ${pollEvidenceHtml(pollRace, pollBoard, pollHealth, days)}
        </section>`;
    const view = viewFor(race.office, contract);
    const unverified = pollRace?.schedule_status === 'watch_slot_unverified';
    return `
        <section class="elections-spac-block">
            <div class="elections-spac-block-head"><span>${escapeHtml(label)}${unverified ? ' · 2026 선거 미확인' : ''}</span>${badgeCaption}${winnerBadge(race, view.categories)}</div>
            ${unverified ? '<p class="elections-panel-note">이 주의 해당 직위에 2026 선거가 있는지 검증 전입니다. 공시 금액은 선거자금 기록으로만 읽어주세요.</p>' : ''}
            ${pollEvidenceHtml(pollRace, pollBoard, pollHealth, days)}
            ${raceBody(race, view)}
        </section>`;
};

// district is a zero-padded number for a real seat, and the pipeline's own
// "could not place this" markers otherwise -- UNKNOWN when the filing left it
// blank, ZZ for a code with no seat behind it. Those must not be dressed up as
// "하원 UNKNOWN구".
const NON_DISTRICT = new Set(['UNKNOWN', 'ZZ', '']);
const districtLabel = (race, mapped) => {
    const raw = String(race.district ?? '').toUpperCase();
    if (NON_DISTRICT.has(raw)) return '하원 · 선거구 미지정';
    const trimmed = raw.replace(/^0+/, '');
    // "00" is the state's at-large seat where one exists (its geometry is filed
    // under the same id) and otherwise the pipeline's statewide bucket for
    // House spending it could not put in a district.
    if (!trimmed) return mapped ? '하원 전역구' : '하원 · 주 전체 집계';
    return `하원 ${trimmed}구`;
};

// The row is the button: clicking it opens its own candidate block and, when
// the district has geometry, tells the map which one to light up. Both live on
// one element so the panel and the map cannot disagree about the selection.
//
// Rows whose district the state's map does not have still appear -- the money
// is really reported -- but say so instead of posing as a seat that exists.
const districtRow = (race, mapped, contract, pollRace, pollBoard, pollHealth, days) => `
    <div class="elections-spac-district${mapped ? '' : ' is-unmapped'}">
        <button class="elections-spac-district-head" type="button" data-spac-toggle
            ${mapped ? `data-spac-district="${escapeHtml(race.district ?? '')}"` : ''}>
            <span>${escapeHtml(districtLabel(race, mapped))}</span>
            ${mapped ? '' : '<span class="elections-spac-unmapped-tag">지도 미대응</span>'}
            ${winnerBadge(race, viewFor(race.office, contract).categories)}
        </button>
        <div class="elections-spac-district-body">${pollEvidenceHtml(pollRace, pollBoard, pollHealth, days)}${raceBody(race, viewFor(race.office, contract))}</div>
    </div>`;

const byDistrict = (a, b) => String(a.district ?? '').localeCompare(String(b.district ?? ''), undefined, { numeric: true });

export const usaStateSuperPac = (state, races, mappedDistricts = null, contract = null, pollBoard = null, pollHealth = null, days = 7) => {
    if (!Array.isArray(races)) {
        return '<p class="elections-muted">이 주의 선거자금 자료를 불러오지 못했습니다. 로컬 정적 서버에서는 /public/data 경로가 필요합니다.</p>';
    }
    const governor = races.find((race) => race.office === 'governor');
    const senate = races.find((race) => race.office === 'senate');
    const house = races.filter((race) => race.office === 'house').sort(byDistrict);
    const pollFor = (race) => pollBoard?.races?.[race?.race_id] || null;
    // No geometry loaded at all (a state whose district file is missing) means
    // nothing can be highlighted, rather than everything being unmapped.
    const isMapped = (race) => (mappedDistricts ? mappedDistricts.has(String(race.district ?? '')) : false);
    const mapped = house.filter(isMapped);
    const unmapped = house.filter((race) => !isMapped(race));

    return `
        <p class="elections-spac-lede">외부 단체(슈퍼팩 등)가 특정 후보를 <strong>지지하거나 반대하려고 독자적으로 쓴 돈</strong>입니다.
            후보 캠프가 모금한 후원금이 아니며, 캠프를 거치지도 않습니다.</p>
        <section class="elections-detail-section">
            ${statewideBlock('주지사', governor, contract, pollFor(governor), pollBoard, pollHealth, days)}
            ${statewideBlock('연방 상원의원', senate, contract, pollFor(senate), pollBoard, pollHealth, days)}
        </section>
        <section class="elections-detail-section">
            <p class="section-title">연방 하원 · 배지는 지지지출이 더 많은 정당입니다. 선거구를 누르면 후보별 지지·반대 금액과 지도 위치가 함께 표시됩니다</p>
            <div class="elections-spac-district-list">
                ${mapped.map((race) => districtRow(race, true, contract, pollFor(race), pollBoard, pollHealth, days)).join('')}
                ${unmapped.map((race) => districtRow(race, false, contract, pollFor(race), pollBoard, pollHealth, days)).join('')}
            </div>
            ${house.length ? '' : '<p class="elections-muted">하원 선거구 자료가 없습니다.</p>'}
            ${unmapped.length ? `<p class="elections-panel-note">아래 ${unmapped.length}건은 공시에 적힌 선거구 번호가 이 주의 현행 선거구 도형에 없어 지도에 표시되지 않습니다. 금액은 공시 그대로입니다.</p>` : ''}
        </section>
        <p class="elections-panel-note">배지는 지지 지출이 더 많은 정당일 뿐, 개표 결과나 당선 전망이 아닙니다.</p>`;
};
