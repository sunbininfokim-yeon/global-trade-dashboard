// 일본은 미국과 같은 대시보드를 쓰되 대통령제가 아니라 의원내각제다. 탭 이름이
// 그 차이를 먼저 말한다: 행정부가 아니라 내각이고, 상원·하원이 아니라 국회다.
export const jpnSections = [
    ['지도', 'subnational_map'],
    ['내각', 'executive'],
    ['국회', 'legislature'],
    ['자민당 파벌', 'factions'],
    ['일정', 'calendar'],
];

// 회파(원내 교섭단체) 약칭 → 한국어 표기. 여기 없는 약칭은 원문 그대로 둔다 --
// 모르는 회파에 이름을 지어 붙이는 것보다 약칭이 낫다.
export const JPN_PARTY_KO = {
    LDP: '자민당',
    CDP: '입헌민주당',
    Ishin: '일본유신회',
    Komeito: '공명당',
    DPP: '국민민주당',
    JCP: '일본공산당',
    Reiwa: '레이와신선조',
    SDP: '사민당',
    Sanseito: '참정당',
    CPJ: '일본보수당',
    Mirai: '팀미라이',
    Okinawa: '오키나와의 바람',
    IND: '무소속',
};

// 정당색은 각 당 공식색을 쓰되, 겹치는 붉은 계열(자민·공산)은 톤을 갈라 둔다.
// 표에 없는 회파는 순서대로 중립 램프를 받는다 -- 색이 겹쳐 두 회파가 한 덩어리로
// 보이는 것이 이름 없는 회색보다 나쁘다.
const JPN_PARTY_COLOR = {
    LDP: '#c0392b',
    CDP: '#2563eb',
    Ishin: '#16a34a',
    Komeito: '#d97706',
    DPP: '#0891b2',
    JCP: '#be123c',
    Reiwa: '#db2777',
    SDP: '#7c3aed',
    Sanseito: '#ea580c',
    CPJ: '#0f766e',
    Mirai: '#4f46e5',
    Okinawa: '#0d9488',
    IND: '#94a3b8',
};
const FALLBACK_RAMP = ['#64748b', '#78716c', '#6b7280', '#57534e', '#525252'];

export const jpnPartyKo = (abbr) => JPN_PARTY_KO[abbr] || abbr || '불명';
export const jpnPartyLabel = (abbr) => {
    const ko = JPN_PARTY_KO[abbr];
    return ko ? `${ko}(${abbr})` : (abbr || '불명');
};

export const jpnColorScale = () => {
    const assigned = new Map();
    let cursor = 0;
    return (abbr) => {
        if (JPN_PARTY_COLOR[abbr]) return JPN_PARTY_COLOR[abbr];
        if (!assigned.has(abbr)) {
            assigned.set(abbr, FALLBACK_RAMP[cursor % FALLBACK_RAMP.length]);
            cursor += 1;
        }
        return assigned.get(abbr);
    };
};

export const CHAMBER_KO = {
    house_of_representatives: '중의원',
    house_of_councillors: '참의원',
};
export const chamberKo = (key) => CHAMBER_KO[key] || key || '소속 원 불명';

// name_ja 가 있으면 그것이 본명이다. 로마자 표기는 파이프라인이 대문자 성으로
// 주기 때문에 (TAKAICHI Sanae) 한자 이름을 앞세우고 로마자를 괄호에 넣는다.
export const jpnPerson = (row) => {
    if (!row) return '';
    const primary = row.name_ko || row.name_ja || row.name_en;
    if (!primary) return '';
    const secondary = row.name_ja && row.name_en ? row.name_en : '';
    return secondary ? `${primary} (${secondary})` : primary;
};
