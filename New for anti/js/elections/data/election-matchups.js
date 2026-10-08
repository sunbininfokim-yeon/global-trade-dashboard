import { normalizeParty } from './usa-election-context.js?v=2';

export const ballotPartyLabel = (party) => normalizeParty(party) === 'REP' ? 'GOP' : normalizeParty(party) || '정당 미확인';
export const ballotPartyClass = (party) => normalizeParty(party) === 'DEM' ? 'is-dem' : normalizeParty(party) === 'REP' ? 'is-gop' : 'is-other';
const nameKey = (v) => String(v || '').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9 ]/g,' ').split(/\s+/).filter(Boolean).sort().join(' ');
export const pollMatchesMatchup = (pollRace, matchup) => !matchup || !!pollRace?.required_candidates?.length
    && pollRace.required_candidates.every((name) => matchup.candidates.some((candidate) =>
        [candidate.name, ...(candidate.poll_name_aliases || [])].some((alias) => nameKey(alias) === nameKey(name))
        && normalizeParty(candidate.party) === normalizeParty(pollRace.candidates?.[name]?.party)));

export const usaStateNameKo = (id, fallback = id) => ({
    AL:'앨라배마',AK:'알래스카',AZ:'애리조나',AR:'아칸소',CA:'캘리포니아',CO:'콜로라도',CT:'코네티컷',DE:'델라웨어',FL:'플로리다',GA:'조지아',
    HI:'하와이',ID:'아이다호',IL:'일리노이',IN:'인디애나',IA:'아이오와',KS:'캔자스',KY:'켄터키',LA:'루이지애나',ME:'메인',MD:'메릴랜드',
    MA:'매사추세츠',MI:'미시간',MN:'미네소타',MS:'미시시피',MO:'미주리',MT:'몬태나',NE:'네브래스카',NV:'네바다',NH:'뉴햄프셔',NJ:'뉴저지',
    NM:'뉴멕시코',NY:'뉴욕',NC:'노스캐롤라이나',ND:'노스다코타',OH:'오하이오',OK:'오클라호마',OR:'오리건',PA:'펜실베이니아',RI:'로드아일랜드',SC:'사우스캐롤라이나',
    SD:'사우스다코타',TN:'테네시',TX:'텍사스',UT:'유타',VT:'버몬트',VA:'버지니아',WA:'워싱턴',WV:'웨스트버지니아',WI:'위스콘신',WY:'와이오밍',
}[id] || fallback);

// Ballot identities must be available even when a race has no polling feed.
// Display-only reviewed rosters never authorize a new poll or an election call.
export const electionMatchup = (state, raceId, pollRace = null, now = Date.now()) => {
    const roster = state?.election_matchups?.[raceId];
    const reviewed = Date.parse(`${roster?.reviewed_on}T00:00:00Z`);
    if (roster?.race_id === raceId && ['certified_ballot', 'reported_general_matchup'].includes(roster.status)
        && Number.isFinite(reviewed) && reviewed <= now && roster.election_date === '2026-11-03'
        && roster.candidates?.length) return roster;
    if (pollRace?.schedule_status === 'reported_general_matchup' && pollRace.required_candidates?.length >= 2) return {
        race_id: raceId, status: 'reported_general_matchup', coverage: 'reviewed_poll_matchup',
        candidates: pollRace.required_candidates.map((name) => ({ name, ...pollRace.candidates?.[name] })),
        absent_parties: [],
    };
    return null;
};

export const senateTenureLabel = (member) => {
    const history = member?.senate_election_history;
    if (!history?.source_url || !Array.isArray(history.election_years)
        || !history.election_years.every((y) => Number.isInteger(y) && y <= 2026)) return '선수 확인 필요';
    return history.election_years.length ? `${history.election_years.length}선` : '임명';
};

export const displayPersonName = (name) => {
    const parts = String(name || '').split(',').map((p) => p.trim());
    return parts.length === 2 ? `${parts[1]} ${parts[0]}` : String(name || '현직 명부 확인 필요');
};
