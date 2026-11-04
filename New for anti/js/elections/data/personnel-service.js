// 국가별 인사 명단 (build_personnel_public.py 가 낸 public/data/personnel/*).
// 목록(index.json)은 한 번만 받고, 나라 파일은 그 나라를 열 때 받는다. 실패하면 null --
// 인사 명단 블록만 안 보이고 나머지 화면은 그대로다.
let indexPromise = null;
const countryPromises = new Map();

const getJson = (path) => fetch(path, { cache: 'no-cache' })
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);

export const loadPersonnelIndex = () => {
    if (!indexPromise) indexPromise = getJson('/public/data/personnel/index.json');
    return indexPromise;
};

export const loadPersonnel = async (iso3) => {
    const index = await loadPersonnelIndex();
    if (!index?.countries?.[iso3]) return null;
    if (!countryPromises.has(iso3)) {
        countryPromises.set(iso3, getJson(`/public/data/personnel/${iso3}.json`)
            .then((data) => (data?.country === iso3 ? data : null)));
    }
    return countryPromises.get(iso3);
};
