// 선거 전망(여론조사 기반) 로더.
//
// 이 파일은 **아직 없는 데이터**를 읽는다. 없으면 null 로 떨어지고 화면은 전망 칸을
// "여론조사 연동 예정"으로 남긴다 -- 없는 수치를 지어내는 것보다 빈 칸이 낫다.
//
// 의석·대진표와 **다른 파일**로 둔 이유: 전망은 여론조사가 들어올 때마다 바뀌고
// 의석·대진은 선거일까지 거의 안 바뀐다. 한 파일에 섞으면 여론조사 한 번 갱신할
// 때마다 의석 데이터까지 새로 받아야 하고, 캐시 정책도 하나로 묶인다.
//
// 그래서 이쪽만 `no-store` 다. 의석은 `force-cache` 로 읽는다.

const FORECAST_PATH = '/public/data/usa_midterms_forecast_v1.json';

let inflight = null;

// 매번 새로 읽는다(메모이즈하지 않는다). 여론조사가 갱신되면 같은 URL 의 내용이
// 바뀌므로, 한 번 캐시해 두면 새 전망이 영영 안 보인다. 동시에 여러 번 부르면
// 하나로 합친다.
export const loadUsaMidtermsForecast = () => {
    if (inflight) return inflight;
    inflight = fetch(FORECAST_PATH, { cache: 'no-store' })
        .then((response) => (response.ok ? response.json() : null))
        .catch(() => null)
        .finally(() => { inflight = null; });
    return inflight;
};

// 전망이 갱신되는 주기를 아는 것은 데이터 쪽이다. 파일이 `refresh_seconds` 를
// 선언하면 그 주기로 다시 읽고, 없으면 다시 읽지 않는다 -- UI 가 임의로 폴링 간격을
// 정하면 파이프라인이 바뀔 때마다 코드를 고쳐야 한다.
export const watchUsaMidtermsForecast = (onForecast) => {
    let timer = null;
    let stopped = false;

    const tick = async () => {
        const forecast = await loadUsaMidtermsForecast();
        if (stopped) return;
        onForecast(forecast);
        const seconds = Number(forecast?.refresh_seconds);
        if (Number.isFinite(seconds) && seconds >= 30) {
            timer = setTimeout(tick, seconds * 1000);
        }
    };
    tick();

    return () => { stopped = true; if (timer) clearTimeout(timer); };
};
