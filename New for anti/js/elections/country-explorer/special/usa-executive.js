import { escapeHtml } from '../../ui.js';

// The EOP org chart (대통령 → 비서실 → 위원회 → 실·국) is institutional
// structure, not a synced dataset: which councils and offices exist changes
// with statute and executive order, not with today's roster. So the boxes are
// editorial content kept in public/data/elections_us_eop_v1.json -- editable
// without touching code, the way docs/ui-screens.md already says 제도 설명 is
// handled -- and only the *people* come from executive_live.
//
// Data contract (all optional; add to countries[USA].executive_live):
//
//   "eop_councils":      [{ "abbr": "NEC", "head_title_ko": "위원장",
//                           "name_en": "...", "name_ko": "", "party_abbr": "",
//                           "status": "", "note_ko": "" }, ...]
//   "special_assistants":[{ "domain": "economy", "title_ko": "국가경제 보좌관",
//                           "name_en": "...", "status": "" }, ...]
//   "eop_offices":       [{ "abbr": "OMB", "head_title_ko": "국장",
//                           "name_en": "...", "status": "" }, ...]
//
// `name_ko`/`name_en` are always the *person*; an entry the scaffold doesn't
// know yet names its own box with `org_ko`/`org_en` (and a 보좌관 with
// `domain_ko`). Councils/offices join the scaffold by `abbr`, special
// assistants by `domain`. An entry with no match is listed after the
// scaffold rather than dropped, so a newly created office shows up without a
// code change. A scaffold box with no person renders "명단 수집 예정" -- never
// a guess, and never read as "이 자리는 공석".

// prefillTitle keeps a prefilled box reading like a data-filled one
// ("역할 이름"); the source row's own label is often long and repeats the box
// it now sits in ("국가안보보좌관 (NSC 실무 책임)" inside the NSC box).
//
// These are the fallback copy of the chart. The live one is
// public/data/elections_us_eop_v1.json so the org skeleton can be edited
// without touching code; if that file is missing or unreadable the screen
// still draws from here rather than coming up empty.
let COUNCILS = [
    { abbr: 'NSC', ko: '국가안전보장회의', en: 'National Security Council', prefillCore: '국가안보보좌관 (NSC 실무 책임)', prefillTitle: '국가안보보좌관' },
    { abbr: 'NEC', ko: '국가경제위원회', en: 'National Economic Council' },
    { abbr: 'DPC', ko: '국내정책위원회', en: 'Domestic Policy Council' },
    { abbr: 'CEA', ko: '경제자문위원회', en: 'Council of Economic Advisers' },
    { abbr: 'CEQ', ko: '환경위원회', en: 'Council on Environmental Quality' },
    { abbr: 'USTR', ko: '미국무역대표부', en: 'Office of the U.S. Trade Representative', prefillCabinet: '미국무역대표', prefillTitle: '대표' },
];

// The user's brief: 보좌관이 많으면 주요 정책 영역만. These six are the
// domains they named, not a roster -- one line each, filled from data.
let ADVISOR_DOMAINS = [
    { domain: 'security', ko: '안보' },
    { domain: 'economy', ko: '경제' },
    { domain: 'politics', ko: '정치' },
    { domain: 'industry', ko: '산업·통상' },
    { domain: 'military', ko: '군사' },
    { domain: 'economic_security', ko: '경제안보' },
];

let OFFICES = [
    { abbr: 'OMB', ko: '예산관리국', en: 'Office of Management and Budget', prefillCabinet: '관리예산처장', prefillTitle: '국장' },
    { abbr: 'OSTP', ko: '과학기술정책국', en: 'Office of Science and Technology Policy' },
    { abbr: 'ONDCP', ko: '국가마약통제국', en: 'Office of National Drug Control Policy' },
    { abbr: 'OA', ko: '행정국', en: 'Office of Administration' },
    { abbr: 'WHMO', ko: '백악관 군사실', en: 'White House Military Office' },
    { abbr: 'PIAB', ko: '대통령 정보자문위원회', en: "President's Intelligence Advisory Board" },
    { abbr: 'PCLOB', ko: '사생활·시민자유 감독위원회', en: 'Privacy and Civil Liberties Oversight Board' },
];

// Only replaces a list the file actually carries, so a partial or malformed
// file degrades box by box instead of blanking the screen.
export const applyEopChart = (chart) => {
    if (Array.isArray(chart?.councils) && chart.councils.length) COUNCILS = chart.councils;
    if (Array.isArray(chart?.advisor_domains) && chart.advisor_domains.length) ADVISOR_DOMAINS = chart.advisor_domains;
    if (Array.isArray(chart?.offices) && chart.offices.length) OFFICES = chart.offices;
};

const partyKo = (abbr) => ({ GOP: '공화당', DEM: '민주당', IND: '무소속' }[abbr] || abbr || '');

// executive_live.white_house (usa_eop.json -> tier12_executives.json) is keyed
// and shaped for its own consumers -- councils carry the head under whichever
// of staff_director/director/advisor/executive_director the body actually
// uses, and office/assistant rows are keyed by `id`, not the `abbr` this
// scaffold joins on. This turns that shape into the {abbr, head_title_ko,
// name_en, note_ko} rows scaffoldRows()/orgBox() already know how to draw,
// rather than teaching the scaffold two data shapes.
const councilHead = (council) => council.staff_director || council.director
    || council.advisor || council.executive_director || null;

const whCouncilRows = (whiteHouse) => (whiteHouse?.councils || []).map((council) => {
    const head = councilHead(council);
    return {
        abbr: String(council.id || '').toUpperCase(),
        // org_ko only matters for a council the scaffold doesn't already have a
        // box for (HSC/NEDC today) -- scaffoldRows() ignores it for a matched
        // abbr and uses the scaffold's own ko/en instead.
        org_ko: council.name_ko || null,
        org_en: council.name_en || null,
        head_title_ko: head?.office_ko || '',
        name_en: head?.name_en || null,
        note_ko: council.note_ko || null,
    };
});

const whOfficeRows = (whiteHouse) => (whiteHouse?.eop_office_heads || []).map((office) => ({
    abbr: String(office.id || '').toUpperCase(),
    head_title_ko: office.office_ko || '',
    name_en: office.name_en || null,
    status: office.status || null,
    note_ko: office.note_ko || null,
}));

// Partitions the combined council+office rows by which scaffold actually
// declares that abbr, instead of feeding the same list to both scaffoldRows()
// calls -- each call treats everything it doesn't recognise as an "extra" box
// for its own section, so an unpartitioned list would draw every row twice.
const partitionByScaffold = (rows, scaffold) => {
    const abbrs = new Set(scaffold.map((box) => box.abbr));
    const matched = [];
    const rest = [];
    rows.forEach((row) => (abbrs.has(row.abbr) ? matched : rest).push(row));
    return [matched, rest];
};

// wh_counsel/press_secretary/communications_director are real West Wing
// offices with no council or EOP-office box in the scaffold at all (nsa/
// nec_director/dpc_director/homeland_security_advisor duplicate the council
// heads above and are dropped here to avoid showing the same person twice).
// Synthetic abbrs that can't collide with a real scaffold box route them
// through scaffoldRows()'s own "extra" path.
const WH_STAFF_ORG_KO = {
    wh_counsel: '법률고문실',
    press_secretary: '대변인실',
    communications_director: '홍보실',
};
const whStaffExtraRows = (whiteHouse) => {
    const assistants = (whiteHouse?.assistants_to_the_president || [])
        .filter((row) => WH_STAFF_ORG_KO[row.id])
        .map((row, index) => ({
            abbr: `WH_STAFF_${index}`,
            org_ko: WH_STAFF_ORG_KO[row.id],
            head_title_ko: row.office_ko || '',
            name_en: row.name_en || null,
            note_ko: row.note_ko || null,
        }));
    const deputies = (whiteHouse?.deputy_chiefs_of_staff || []).map((row, index) => ({
        abbr: `WH_DCOS_${index}`,
        org_ko: row.office_ko || '부비서실장',
        name_en: row.name_en || null,
    }));
    return [...assistants, ...deputies];
};

const personText = (row) => {
    if (!row) return '';
    const name = row.name_ko || row.name_en;
    if (!name) return '';
    return [name, partyKo(row.party_abbr), row.status].filter(Boolean).join(' · ');
};

const card = (label, value, note = '') => `
    <article class="elections-card">
        <div class="elections-card-label">${escapeHtml(label)}</div>
        <div class="elections-card-value">${escapeHtml(value || '명단 수집 예정')}</div>
        ${note ? `<div class="elections-event-meta">${escapeHtml(note)}</div>` : ''}
    </article>`;

// One box per body, laid out side by side like the EOP chart's rows rather
// than as full-width rows. The person line is pushed to the bottom of the
// box so it lands on the same baseline across a row of uneven name lengths.
const orgBox = ({ abbr, ko, en, title, person, note }) => `
    <article class="elections-org-box">
        <div class="elections-org-box-ko">${escapeHtml(ko)}</div>
        ${abbr ? `<div class="elections-org-box-abbr">${escapeHtml(abbr)}</div>` : ''}
        ${en ? `<div class="elections-org-box-en">${escapeHtml(en)}</div>` : ''}
        <div class="elections-org-box-person${person ? '' : ' is-empty'}">
            ${person && title ? `<span class="elections-org-box-title">${escapeHtml(title)}</span>` : ''}
            ${escapeHtml(person || '명단 수집 예정')}
        </div>
        ${note ? `<div class="elections-org-box-note">${escapeHtml(note)}</div>` : ''}
    </article>`;

// Exact-string prefill against rows the pipeline already publishes. A wording
// change in the source breaks the match into "명단 수집 예정" rather than into
// the wrong person, which is the failure mode worth having.
const findBy = (rows, key, value) => (rows || []).find((row) => row[key] === value) || null;

const scaffoldRows = (scaffold, supplied, live, consumed) => {
    const byAbbr = new Map((supplied || []).map((row) => [row.abbr, row]));
    const rows = scaffold.map((box) => {
        const data = byAbbr.get(box.abbr);
        byAbbr.delete(box.abbr);
        let person = personText(data);
        let title = data?.head_title_ko || '';
        if (!person && box.prefillCore) {
            const core = findBy(live.core, 'office_ko', box.prefillCore);
            if (core) { person = personText(core); title = title || box.prefillTitle; consumed.add(box.prefillCore); }
        }
        if (!person && box.prefillCabinet) {
            const seat = findBy(live.cabinet, 'portfolio_ko', box.prefillCabinet);
            if (seat) { person = personText(seat); title = title || box.prefillTitle; consumed.add(box.prefillCabinet); }
        }
        return orgBox({ abbr: box.abbr, ko: box.ko, en: box.en, title, person, note: data?.note_ko });
    });
    // Anything the data carries that the scaffold doesn't know about yet.
    const extra = [...byAbbr.values()].map((row) => orgBox({
        abbr: row.abbr,
        ko: row.org_ko || row.abbr,
        en: row.org_en || '',
        title: row.head_title_ko,
        person: personText(row),
        note: row.note_ko,
    }));
    return [...rows, ...extra].join('');
};

const advisorRows = (supplied) => {
    const byDomain = new Map((supplied || []).map((row) => [row.domain, row]));
    const rows = ADVISOR_DOMAINS.map((box) => {
        const data = byDomain.get(box.domain);
        byDomain.delete(box.domain);
        return orgBox({ ko: box.ko, en: '', title: data?.title_ko, person: personText(data), note: data?.note_ko });
    });
    const extra = [...byDomain.values()].map((row) => orgBox({
        ko: row.domain_ko || row.domain || '기타',
        title: row.title_ko,
        person: personText(row),
        note: row.note_ko,
    }));
    return [...rows, ...extra].join('');
};

export const usaExecutive = (country) => {
    const live = country.executive_live;
    if (!live) return null;
    const consumed = new Set();

    // Councils and offices are rendered first so their prefill claims the
    // core/cabinet rows before tier 1 and the cabinet list draw the rest --
    // otherwise the NSC adviser and the OMB director appear twice.
    const whiteHouse = live.white_house;
    const [whCouncilMatches, whCouncilLeftover] = partitionByScaffold(whCouncilRows(whiteHouse), COUNCILS);
    const [whOfficeMatches] = partitionByScaffold(whOfficeRows(whiteHouse), OFFICES);
    const councils = scaffoldRows(
        COUNCILS,
        [...(live.eop_councils || []), ...whCouncilMatches, ...whCouncilLeftover],
        live,
        consumed,
    );
    const offices = scaffoldRows(
        OFFICES,
        [...(live.eop_offices || []), ...whOfficeMatches, ...whStaffExtraRows(whiteHouse)],
        live,
        consumed,
    );
    const advisors = advisorRows(live.special_assistants);

    const coreRows = (live.core || []).filter((row) => !consumed.has(row.office_ko));
    const cabinet = (live.cabinet || []).filter((row) => !consumed.has(row.portfolio_ko));
    const sourceLabels = (live.sources || []).map((source) => [source.org, source.as_of ? `${source.as_of} 기준` : ''].filter(Boolean).join(' · '));

    return `
        <p class="section-title">1 · 대통령·부통령·비서실</p>
        <div class="elections-card-grid">
            ${coreRows.map((row) => card(row.office_ko || '직책', personText(row))).join('') || '<p class="elections-muted">확보된 공개 명부가 없습니다.</p>'}
        </div>

        <p class="section-title">2 · 대통령 직속 위원회</p>
        <div class="elections-org-grid">${councils}</div>

        <p class="section-title">3 · 대통령 특별보좌관</p>
        <div class="elections-org-grid">${advisors}</div>
        <p class="elections-panel-note">주요 정책 영역만 둡니다. 전체 보좌관 명부는 범위 밖입니다.</p>

        <p class="section-title">4 · 실·국 (수석급)</p>
        <div class="elections-org-grid">${offices}</div>

        ${cabinet.length ? `<details class="elections-disclosure elections-cabinet-list"><summary>내각 ${cabinet.length}명 보기</summary><div class="elections-disclosure-rows">${cabinet.map((row) => `<div><span>${escapeHtml(row.portfolio_ko || '직책')}</span><strong>${escapeHtml(personText(row) || '불명')}</strong></div>`).join('')}</div></details>` : ''}
        <p class="elections-panel-note">2~4단은 대통령실(EOP) 조직도 기준 골격입니다. 사람이 비어 있는 칸은 명단 미수집이며, 공석이라는 뜻이 아닙니다.</p>
        ${sourceLabels.length ? `<p class="elections-panel-note">공개 명부: ${escapeHtml(sourceLabels.join(' / '))}</p>` : ''}
        ${(whiteHouse?.missing || []).length ? `<p class="elections-panel-note">미확보: ${escapeHtml(whiteHouse.missing.join(', '))}</p>` : ''}
    `;
};
