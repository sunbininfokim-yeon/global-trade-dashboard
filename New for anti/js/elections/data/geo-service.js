const DATA_ROOT = '/public/data';
const admin1Promises = new Map();
const districtPromises = new Map();

// priority:'low' 는 지원하는 브라우저에서만 효과가 있고, 모르는 브라우저는 무시한다. 선거구 도형은
// 수 MB 라서, 같은 순간에 받는 금액·폴 파일(패널이 기다리는 것)과 대역폭을 다투면 패널이 밀린다 --
// 지도는 선택한 주를 먼저 칠해 두므로 도형은 조금 늦어도 된다.
const loadJson = async (filename, { priority } = {}) => {
    const response = await fetch(`${DATA_ROOT}/${filename}`, { cache: 'force-cache', ...(priority ? { priority } : {}) });
    if (!response.ok) throw new Error(`${filename} (${response.status})`);
    return response.json();
};

// 실패한 읽기는 기억하지 않는다. 이전에는 거절된 promise 가 그대로 캐시에 남아서, 네트워크가
// 한 번 끊기면(16MB 짜리 캘리포니아 도형을 받는 도중이 가장 흔하다) 그 뒤로는 나갔다
// 들어와도 같은 실패가 즉시 되돌아왔다. 지금은 실패하면 캐시에서 빼서, 다음 진입이 새로
// 시도한다. 성공한 결과와 "파일 없음(404 → null)"은 그대로 오래 간직한다.
const remember = (cache, key, load) => {
    if (!cache.has(key)) {
        const promise = load().catch((error) => {
            if (cache.get(key) === promise) cache.delete(key);
            throw error;
        });
        cache.set(key, promise);
    }
    return cache.get(key);
};

// Boundary-only assets; political party/member fields must already be baked
// into a derived GeoJSON by the data pipeline before the browser sees it.
export const loadAdmin1 = (iso3) => remember(admin1Promises, iso3, () => loadJson(`admin1/${iso3}.json`));

export const loadCongressionalDistricts = (stateId) => remember(districtPromises, stateId,
    () => loadJson(`congressional_districts/USA/${stateId}.json`, { priority: 'low' }).catch((error) => {
        if (String(error.message).includes('(404)')) return null;
        throw error;
    }));

// 사용자가 주를 누르기 전에 도형을 데워 둔다. 실패해도 조용히 넘어간다 -- 진짜 클릭이 새로
// 시도하므로, 여기서 에러를 올릴 이유가 없다.
export const prefetchCongressionalDistricts = (stateId) => {
    loadCongressionalDistricts(stateId).catch(() => {});
};
