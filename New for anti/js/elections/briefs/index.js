import { usaMidtermsBrief } from './usa-midterms.js?v=2';
import { applyForecast, forecastFooter } from './forecast-panel.js';
import { watchUsaMidtermsForecast } from '../data/forecast-service.js';
import { contestSkeleton, applyContest } from './generic-contest.js';
import { contestEntryFor, loadContest } from '../data/contest-service.js';

// 일정 한 줄 → 브리핑 창. 어떤 일정이 어떤 브리핑을 여는지는 여기 한 곳에서만 정한다.
//
// 나라를 늘릴 때 이 표에 줄을 더하고 렌더러를 하나 붙이면 되고, 타임라인·모달 쪽은
// 건드리지 않는다. 지금 둘이다:
//
//   usa-midterms  미국 중간선거 전용. 양당 대결 + 여론조사 전망 슬롯.
//   contest       그 밖의 모든 나라. 정당 수를 모른 채 그리고, 전망은 없다.
//
// 순서가 곧 우선순위다 -- 먼저 맞는 것이 이긴다.
const BRIEFS = [
    {
        key: 'usa-midterms',
        title: () => '미국 중간선거',
        subtitle: (event) => ['미국', event?.date, '선거 개괄'].filter(Boolean).join(' · '),
        matches: (event) => event?.iso3 === 'USA' && event?.type === 'general',
        render: ({ bundle, event }) => usaMidtermsBrief(bundle.countries.get('USA'), { event }),
        // 전망은 본문과 따로 온다. 창이 열려 있는 동안 여론조사가 갱신되면 그 칸만
        // 갈아끼우고, 창을 닫으면 구독을 끊는다.
        watch: (root) => watchUsaMidtermsForecast((forecast) => applyForecast(root, forecast)),
    },
    {
        key: 'contest',
        title: (event) => event?.label_ko || event?.label_en || '선거 개괄',
        subtitle: (event, bundle) => [
            bundle?.countries?.get?.(event?.iso3)?.name_ko || event?.iso3,
            event?.date,
            '선거 개괄',
        ].filter(Boolean).join(' · '),
        // 목차에 이 선거의 대진 파일이 있을 때만 열린다. 없으면 일정 줄은 버튼이
        // 되지 않는다 -- 눌러도 빈 창이 뜨는 것보다 안 눌리는 편이 낫다.
        matches: (event, bundle) => Boolean(contestEntryFor(event, bundle?.contests)),
        render: ({ event }) => contestSkeleton(event),
        // 대진 파일은 창을 열 때 읽는다. 선거구가 수백이면 첫 화면에서 받아 둘 것이 아니다.
        watch: (root, { bundle, event }) => {
            let stopped = false;
            loadContest(contestEntryFor(event, bundle?.contests)).then((contest) => {
                if (!stopped) applyContest(root, contest, event);
            });
            return () => { stopped = true; };
        },
    },
];

const briefFor = (key) => BRIEFS.find((brief) => brief.key === key) || null;

export const briefKeyFor = (event, bundle) => {
    const brief = BRIEFS.find((row) => row.matches(event, bundle));
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
        title: brief.title(event, bundle),
        subtitle: brief.subtitle ? brief.subtitle(event, bundle) : '선거 개괄',
        body,
        onClose: () => { stopWatch?.(); stopWatch = null; },
    });
    // modal.open() 이 본문을 넣은 뒤라야 슬롯이 DOM 에 있다.
    const root = modal.bodyEl?.() || document.querySelector('.elections-modal-body');
    stopWatch = brief.watch ? brief.watch(root, { bundle, event }) : null;
};

export { applyForecast, forecastFooter };
