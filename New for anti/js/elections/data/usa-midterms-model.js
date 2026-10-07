// 미국 중간선거 브리핑이 읽는 값만 골라 담는 순수 모듈. DOM 을 모르고 렌더도 하지
// 않으므로 노드에서 실데이터로 그대로 돌려 볼 수 있다 -- 일본·중국 화면을 만들 때
// 쓴 방식과 같다.
//
// 두 축을 한 곳에서 맞춘다:
//   현재 의석  ui_ready.congress.summary        (DEM / GOP / IND)
//   본선 대진  state_drilldown[].primary_2026   (party: "D" / "R")
// 정당 코드가 서로 다르므로 여기서 한 번만 정규화하고, 화면은 DEM/GOP 만 본다.

const PARTY_ALIAS = { D: 'DEM', DEM: 'DEM', R: 'GOP', GOP: 'GOP', I: 'IND', IND: 'IND' };
export const normalizeParty = (value) => PARTY_ALIAS[String(value || '').toUpperCase()] || null;

export const PARTY_KO = { DEM: '민주당', GOP: '공화당', IND: '무소속' };
export const PARTY_COLOR = { DEM: '#2563eb', GOP: '#dc2626', IND: '#94a3b8' };

// "house CA-01" 에서 선거구만 떼어 낸다. 마지막 대시 뒤가 선거구 번호이고, 주 코드는
// 이미 행이 속한 주에서 안다.
const districtOf = (office) => {
    const text = String(office || '');
    const dash = text.lastIndexOf('-');
    return dash === -1 ? null : text.slice(dash + 1).trim() || null;
};

const seatEntries = (byParty) => Object.entries(byParty || {})
    .map(([abbr, seats]) => [normalizeParty(abbr) || abbr, seats])
    .filter(([, seats]) => Number.isFinite(seats) && seats > 0)
    .sort((a, b) => b[1] - a[1]);

// 무소속을 어느 코커스로 셀지는 데이터가 말하지 않는다. 상원 무소속 2인을 민주 쪽에
// 더하면 45가 47이 되는데, 그건 이 화면의 판정이지 수집된 사실이 아니다. 그래서
// 더하지 않고 따로 세운다.
const currentOf = (byParty, extra = {}) => {
    const entries = seatEntries(byParty);
    return {
        entries,
        dem: entries.find(([abbr]) => abbr === 'DEM')?.[1] ?? null,
        gop: entries.find(([abbr]) => abbr === 'GOP')?.[1] ?? null,
        others: entries.filter(([abbr]) => abbr !== 'DEM' && abbr !== 'GOP'),
        ...extra,
    };
};

// 한 주의 한 선거 종류에 걸린 대진. 같은 자리에 D·R 이 한 명씩이면 맞대결이고,
// 한쪽만 있으면 상대가 아직 없다는 뜻이지 무투표라는 뜻이 아니다.
const matchupsFor = (state, kind) => {
    const primary = state.primary_2026 || {};
    const contests = (primary.contests || []).filter((row) => row.office_kind === kind);
    const bySeat = new Map();
    contests.forEach((row) => {
        const seat = kind === 'house' ? (districtOf(row.office) || row.office || '?') : kind;
        if (!bySeat.has(seat)) bySeat.set(seat, { seat, district: kind === 'house' ? districtOf(row.office) : null, runners: [] });
        bySeat.get(seat).runners.push({
            party: normalizeParty(row.party),
            name: row.winner,
            status: row.status,
        });
    });
    return [...bySeat.values()]
        .map((entry) => ({
            ...entry,
            runners: entry.runners.sort((a, b) => (a.party === 'DEM' ? -1 : b.party === 'DEM' ? 1 : 0)),
        }))
        .sort((a, b) => String(a.seat).localeCompare(String(b.seat), undefined, { numeric: true }));
};

const stateRows = (states, kind) => states
    .map((state) => {
        const primary = state.primary_2026 || {};
        return {
            id: state.id,
            name: state.state,
            primaryDate: primary.date,
            primaryStatus: primary.status,
            matchups: matchupsFor(state, kind),
        };
    })
    .filter((row) => row.matchups.length || row.primaryStatus === 'scheduled')
    .sort((a, b) => String(a.id).localeCompare(String(b.id)));

const governorCurrent = (states) => {
    const counts = {};
    states.forEach((state) => {
        const abbr = normalizeParty(state.governor?.abbr) || state.governor?.abbr;
        if (abbr) counts[abbr] = (counts[abbr] || 0) + 1;
    });
    return currentOf(counts, { total: states.length });
};

// 화면이 쓰는 모양 하나로 묶는다. 세 열(주지사·하원·상원)이 완전히 같은 구조라,
// 렌더러는 열 하나를 그리는 함수 하나만 가지면 된다.
export const usaMidtermsModel = (country) => {
    const congress = country?.ui_ready?.congress;
    const states = country?.ui_ready?.state_drilldown?.states;
    if (!congress?.summary || !Array.isArray(states)) return null;
    const summary = congress.summary;

    return {
        columns: [
            {
                key: 'governor',
                label: '주지사',
                current: governorCurrent(states),
                contestedKo: '주별 임기에 따름',
                seatNoteKo: `${states.length}개 주 현직 기준`,
                states: stateRows(states, 'governor'),
            },
            {
                key: 'house',
                label: '하원',
                current: currentOf(summary.house_by_party, {
                    total: summary.house_voting_seats,
                    seated: summary.house_voting_members,
                    vacancies: summary.house_vacancies,
                }),
                contestedKo: Number.isFinite(summary.house_voting_seats)
                    ? `${summary.house_voting_seats}석 전원 개선` : '',
                seatNoteKo: Number.isFinite(summary.house_vacancies) && summary.house_vacancies > 0
                    ? `공석 ${summary.house_vacancies}석 · 표결권 ${summary.house_voting_seats}석 중 현원 ${summary.house_voting_members}명`
                    : '',
                states: stateRows(states, 'house'),
            },
            {
                key: 'senate',
                label: '상원',
                current: currentOf(summary.senate_by_party, { total: 100 }),
                contestedKo: Number.isFinite(summary.senate_up_in_2026)
                    ? `${summary.senate_up_in_2026}석 선거${Number.isFinite(summary.senate_special_up_in_2026) ? ` · 정기 ${summary.senate_regular_up_in_2026} + 특별 ${summary.senate_special_up_in_2026}` : ""}` : '',
                seatNoteKo: '',
                states: stateRows(states, 'senate'),
            },
        ],
        // 경선이 아직인 주가 남아 있으면 대진표가 덜 찬 것이지 비어 있는 것이 아니다.
        primaryPending: states.filter((state) => state.primary_2026?.status === 'scheduled').length,
        statesTotal: states.length,
    };
};
