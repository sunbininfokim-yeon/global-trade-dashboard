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
    const councils = scaffoldRows(COUNCILS, live.eop_councils, live, consumed);
    const offices = scaffoldRows(OFFICES, live.eop_offices, live, consumed);
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
    `;
};
