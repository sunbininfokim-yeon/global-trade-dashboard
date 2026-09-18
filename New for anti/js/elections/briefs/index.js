import { usaMidtermsBrief } from './usa-midterms.js';
import { applyForecast, forecastFooter } from './forecast-panel.js';
import { watchUsaMidtermsForecast } from '../data/forecast-service.js';

// 일정 한 줄 → 브리핑 창. 어떤 일정이 어떤 브리핑을 여는지는 여기 한 곳에서만 정한다.
//
// 지금은 미국 중간선거 하나뿐이다. 나라를 늘릴 때 이 표에 줄을 더하고 렌더러를
// 하나 붙이면 되고, 타임라인·모달 쪽은 건드리지 않는다.
const BRIEFS = [
    {
        key: 'usa-midterms',
        title: '미국 중간선거',
        matches: (event) => event?.iso3 === 'USA' && event?.type === 'general',
        render: ({ bundle, event }) => usaMidtermsBrief(bundle.countries.get('USA'), { event }),
        // 전망은 본문과 따로 온다. 창이 열려 있는 동안 여론조사가 갱신되면 그 칸만
        // 갈아끼우고, 창을 닫으면 구독을 끊는다.
        watch: (root) => watchUsaMidtermsForecast((forecast) => applyForecast(root, forecast)),
    },
];

const briefFor = (key) => BRIEFS.find((brief) => brief.key === key) || null;

export const briefKeyFor = (event, bundle) => {
    const brief = BRIEFS.find((row) => row.matches(event));
    if (!brief) return null;
    // 그릴 수 있는지 실제로 확인한다. 렌더러가 null 을 내면 버튼으로 만들지 않는다 --
    // 눌러도 빈 창이 뜨는 것보다 아예 안 눌리는 편이 낫다.
    return brief.render({ bundle, event }) ? brief.key : null;
};

let stopWatch = null;

export const openBrief = (key, { bundle, modal, event = null }) => {
    const brief = briefFor(key);
    if (!brief || !modal) return;
    const body = brief.render({ bundle, event });
    if (!body) return;
    stopWatch?.();
    modal.open({
        title: brief.title,
        subtitle: '선거 개괄',
        body,
        onClose: () => { stopWatch?.(); stopWatch = null; },
    });
    // modal.open() 이 본문을 넣은 뒤라야 슬롯이 DOM 에 있다.
    const root = modal.bodyEl?.() || document.querySelector('.elections-modal-body');
    stopWatch = brief.watch ? brief.watch(root) : null;
};

export { applyForecast, forecastFooter };
