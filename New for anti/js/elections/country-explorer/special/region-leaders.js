import { escapeHtml } from '../../ui.js';
import { orgBox, orgGrid } from './org-chart.js';
import { personnelCategory } from './personnel-roster.js';

// 국가 지도에서 지역(admin1)을 누르면 그 지역 수장이 뜬다 -- 미국 주 → 주지사, 중국 성 → 서기·성장과
// 같은 그림을 나머지 나라에도 쓴다. 자료는 국가별 인사 명단(public/data/personnel)이다.
//
// 짝짓는 순서:
//   1. 명단의 region_leaders: [{ code: 'TR-34', name, title_ko, ... }] -- ISO 3166-2 코드로 직접 (권장 계약)
//   2. 명단 안의 사람 줄 중 지역 칸(region·prefecture·sido·province·state …)이 있는 줄을
//      지역 이름으로 맞춘다. 영문·현지 표기는 악센트를 지우고 비교하고, 한·일·사우디처럼
//      문자가 다른 나라는 아래 표로 코드에 잇는다.
// 맞는 줄이 없는 지역도 눌리고, '명단 수집 전'이라고 말한다 -- 아무 반응 없는 지도가 가장 나쁘다.

const REGION_KEYS = ['region', 'prefecture', 'sido', 'province', 'state', 'uf', 'jurisdiction', 'emirate', 'governorate', 'land', 'oblast', 'department'];

const KOR = {
    서울특별시: ['KR-11'], 부산광역시: ['KR-26'], 대구광역시: ['KR-27'], 인천광역시: ['KR-28'], 광주광역시: ['KR-29'],
    대전광역시: ['KR-30'], 울산광역시: ['KR-31'], 세종특별자치시: ['KR-50'], 경기도: ['KR-41'], 강원특별자치도: ['KR-42'],
    강원도: ['KR-42'], 충청북도: ['KR-43'], 충청남도: ['KR-44'], 전북특별자치도: ['KR-45'], 전라북도: ['KR-45'],
    전라남도: ['KR-46'], 경상북도: ['KR-47'], 경상남도: ['KR-48'], 제주특별자치도: ['KR-49'],
    // 2026년 출범한 통합 광역단체는 경계 자료에서 아직 둘로 나뉘어 있다.
    전남광주통합특별시: ['KR-29', 'KR-46'],
};
const JPN = ['北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県', '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県',
    '東京都', '神奈川県', '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県', '静岡県', '愛知県', '三重県', '滋賀県',
    '京都府', '大阪府', '兵庫県', '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県', '徳島県', '香川県', '愛媛県',
    '高知県', '福岡県', '佐賀県', '長崎県', '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県']
    .reduce((acc, name, i) => ({ ...acc, [name]: [`JP-${String(i + 1).padStart(2, '0')}`] }), {});
const SAU = {
    الرياض: ['SA-01'], 'مكة المكرمة': ['SA-02'], 'المدينة المنورة': ['SA-03'], الشرقية: ['SA-04'], 'المنطقة الشرقية': ['SA-04'],
    القصيم: ['SA-05'], حائل: ['SA-06'], تبوك: ['SA-07'], 'الحدود الشمالية': ['SA-08'], جازان: ['SA-09'], نجران: ['SA-10'],
    الباحة: ['SA-11'], الجوف: ['SA-12'], عسير: ['SA-14'],
};
const ALIASES = { KOR, JPN, SAU };

// 지역 수장의 기본 직함(줄에 직함이 없을 때).
const HEAD_TITLE = {
    KOR: '광역단체장', JPN: '지사', SAU: '지역 아미르', BRA: '주지사', MEX: '주지사', ARG: '주지사', CAN: '주 총리', DEU: '주 총리',
    AUS: '주 총리', IND: '주 총리', RUS: '지역 수장', TUR: '도지사(vali)', ITA: '주 대표', ESP: '자치지방 수반', NGA: '주지사',
    IDN: '주지사', PHL: '주지사', COL: '주지사', CHL: '주지사', PAN: '주지사', EGY: '주지사', IRQ: '주지사', KWT: '주지사',
};

const fold = (s) => String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9\u0080-￿]/g, '');
const NAME_KEYS = ['name_ko', 'name', 'name_en', 'name_as_signed'];
const nameOf = (row) => NAME_KEYS.map((k) => row[k]).find((v) => typeof v === 'string' && v.trim());
const regionOf = (row) => REGION_KEYS.map((k) => row[k]).find((v) => typeof v === 'string' && v.trim());

const collectRows = (node, out = []) => {
    if (Array.isArray(node)) node.forEach((x) => collectRows(x, out));
    else if (node && typeof node === 'object') {
        if (nameOf(node) && regionOf(node)) out.push(node);
        Object.values(node).forEach((x) => { if (x && typeof x === 'object') collectRows(x, out); });
    }
    return out;
};

const cache = new WeakMap();

// code -> [row]. features 는 그 나라 admin1 경계(public/data/admin1/<ISO3>.json)의 features.
export const regionLeaderIndex = (country, features) => {
    const data = country?.personnel;
    if (!data || !Array.isArray(features)) return new Map();
    if (cache.has(data)) return cache.get(data);
    const index = new Map();
    const add = (code, row) => index.set(code, [...(index.get(code) || []), row]);
    (data.region_leaders || []).forEach((row) => { if (row?.code) add(row.code, row); });
    const byName = new Map();
    features.forEach((f) => {
        const p = f.properties || {};
        [p.name, p.name_ko, p.region].filter(Boolean).forEach((n) => {
            const key = fold(n);
            byName.set(key, [...(byName.get(key) || []), p.code]);
        });
    });
    const aliases = ALIASES[country.iso3] || {};
    // 지방 갈래(주지사·지사·지역 수장 명단)만 본다. 의원 명부에도 '지역구·주' 칸이 있어서,
    // 전부 훑으면 그 지역 의원이 수장으로 잘못 뜬다. 독일 연방상원은 주 정부 대표라 예외.
    const localRoots = Object.entries(data).filter(([k]) => personnelCategory(k) === 'local' || k === 'bundesrat').map(([, v]) => v);
    collectRows(localRoots).forEach((row) => {
        if (data.region_leaders?.includes(row)) return;
        const region = regionOf(row);
        const codes = aliases[region] || byName.get(fold(region)) || [];
        [...new Set(codes)].forEach((code) => add(code, row));
    });
    cache.set(data, index);
    return index;
};

const safeUrl = (url) => (typeof url === 'string' && /^https?:\/\//.test(url) ? url : null);

export const regionCardHtml = (country, feature, leaders) => {
    const p = feature?.properties || {};
    const place = p.name_ko || p.name || p.code || '지역';
    const head = HEAD_TITLE[country.iso3] || '지역 수장';
    if (!leaders?.length) {
        return `<p class="section-title">1 · ${escapeHtml(place)}</p>
            <p class="elections-muted">이 지역의 수장 명단은 아직 수집되지 않았습니다.</p>
            <p class="elections-panel-note">${escapeHtml([p.type, p.region, p.code].filter(Boolean).join(' · '))}</p>`;
    }
    const boxes = leaders.map((row) => orgBox({
        ko: row.title_ko || row.role_ko || row.title || row.role || head,
        person: nameOf(row),
        personUrl: safeUrl(row.source_url || row.url || row.profile_url),
        note: [row.party, row.since && `취임 ${row.since}`, row.elected && `선출 ${row.elected}`, row.term_count && `${row.term_count}선`]
            .filter(Boolean).join(' · '),
    }));
    const notes = leaders.map((row) => row.note_ko || row.note || row.term_note_ko).filter((n) => typeof n === 'string' && n);
    return `<p class="section-title">1 · ${escapeHtml(place)} ${escapeHtml(head)}</p>
        ${orgGrid(boxes)}
        ${notes.length ? `<p class="elections-panel-note">${escapeHtml(notes[0])}</p>` : ''}
        <p class="elections-panel-note">인사 기준일 ${escapeHtml(country.personnel?.as_of || '')} · 국가별 인사 명단에서 이 지역 이름으로 찾은 줄입니다.</p>`;
};
