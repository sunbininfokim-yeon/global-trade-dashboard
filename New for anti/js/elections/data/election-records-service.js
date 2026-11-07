// 국가별 선거 기록 (build_election_records.py 가 낸 public/data/election_records/*).
// 인사 명단과 같은 방식: 목록은 한 번, 나라 파일은 그 나라를 열 때. 실패하면 null --
// '선거' 블록이 '기록 수집 전'으로 남을 뿐 나머지 화면은 그대로다.
let indexPromise = null;
const countryPromises = new Map();

const getJson = (path) => fetch(path, { cache: 'no-cache' })
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);

export const loadElectionRecordsIndex = () => {
    if (!indexPromise) indexPromise = getJson('/public/data/election_records/index.json');
    return indexPromise;
};

export const loadElectionRecords = async (iso3) => {
    const index = await loadElectionRecordsIndex();
    if (!index?.countries?.[iso3]) return null;
    if (!countryPromises.has(iso3)) {
        countryPromises.set(iso3, getJson(`/public/data/election_records/${iso3}.json`)
            .then((data) => (data?.country === iso3 ? data : null)));
    }
    return countryPromises.get(iso3);
};
