import { createElectionState } from './state.js';
import { loadElectionBundle } from './data/core-service.js?v=2';
import { initialMonth } from './data/selectors.js';
import { createCountryExplorer } from './country-explorer/index.js?v=23';
import { renderTimeline } from './timeline/index.js?v=2';
import { briefKeyFor, openBrief } from './briefs/index.js?v=2';

const state = createElectionState();
let host = null;
// Restoring a deep link walks through showCountry/showUsaState, each of
// which reports its own route; letting those writes through would truncate
// the URL to whatever step it had reached. The final route is written once,
// replacing rather than stacking a history entry for a link already open.
let restoring = false;
let bundle = null;
let explorer = null;
let opening = null;

const render = async () => {
    if (!host || !bundle || !explorer) return;
    const current = state.get();
    if (current.mode === 'country' && current.iso3) {
        host.setPanels({ timeline: false, country: true, left: false, right: true });
        // showCountry() is async (USA/CHN fetch a chart before building the
        // shell) -- missing this await let openWorld()'s `await render()`
        // resolve before `shell` existed, so a fresh load at a country+screen
        // URL (/politics/USA/executive) called explorer.openScreen() while
        // shell was still null and silently no-opped, dropping the screen.
        await explorer.showCountry(current.iso3);
        return;
    }
    host.setPanels({ timeline: true, country: false, left: true, right: false });
    renderTimeline(host.roots.timeline, {
        calendar: bundle.calendar,
        countries: bundle.countries,
        // 브리핑을 그릴 수 있는 일정만 버튼이 된다. 창은 지도 위에 열리므로 왼쪽
        // 일정 목록은 그대로 보인다 -- 누른 줄과 창이 같이 보인다.
        briefFor: (event) => briefKeyFor(event, bundle),
        onBriefOpen: (key, event) => openBrief(key, { bundle, modal: explorer.modal, event }),
        shortcuts: SHORTCUTS.filter(({ key }) => bundle.countries.get(key)),
        onShortcut: openShortcut,
    });
    await explorer.showWorld();
};

// 세계 일정 칩 줄의 국가 바로가기. 딥링크 복원(openWorld)과 같은 순서로 연다:
// 국가 모드로 바꾼 뒤 그 나라의 선거 화면을 띄운다. state.set 이 부른 render 는
// 뒤따르는 호출이 navSeq 로 덮는다.
const SHORTCUTS = [
    { key: 'USA', ko: '미국', title: '미국 선거·슈퍼팩 화면으로 이동' },
    { key: 'ISR', ko: '이스라엘', title: '이스라엘 선거 분석 탭으로 이동' },
];
const openShortcut = async (iso3) => {
    if (!explorer || !bundle?.countries.get(iso3)) return;
    state.set({ mode: 'country', iso3 });
    if (iso3 === 'USA') {
        await explorer.showCountry('USA', { electionMode: true });
        return;
    }
    await render();
    if (state.get().iso3 === iso3) explorer.openScreen('election_analysis');
};

state.subscribe(() => { render(); });

const openWorld = async (nextHost) => {
    host = nextHost;
    try {
        if (!opening) opening = loadElectionBundle();
        bundle = await opening;
        // The legacy shell creates a fresh adapter when a user returns to this
        // view, so bind the explorer to the current adapter every time.
        explorer = createCountryExplorer({
            host,
            bundle,
            onCountryOpen: (iso3) => state.set({ mode: 'country', iso3 }),
            onBack: () => state.set({ mode: 'world', iso3: null }),
            onRoute: (route) => { if (!restoring) host.writeRoute?.(route); },
        });
        const month = state.get().month || initialMonth(bundle.calendar);
        const route = host.readRoute?.() || {};
        if (route.country && bundle.countries.get(route.country)) {
            restoring = true;
            try {
                state.set({ mode: 'country', iso3: route.country, month });
                if (route.country === 'USA' && route.view === 'finance' && !route.state) {
                    await explorer.showCountry('USA', { electionMode: true });
                } else {
                    await render();
                }
                if (route.state) {
                    await explorer.showUsaState(route.state, {
                        financeMode: route.view === 'finance',
                        district: route.district || null,
                    });
                } else if (route.screen) {
                    explorer.openScreen(route.screen);
                }
            } finally {
                restoring = false;
            }
            host.writeRoute?.(route, { replace: true });
            return;
        }
        state.set({ mode: 'world', iso3: null, month });
        await opening;
        await render();
    } catch (error) {
        host.setPanels({ timeline: true, country: false, left: true, right: false });
        host.roots.timeline.innerHTML = `<div class="panel-header"><h2>선거 데이터 연결 대기</h2><p>${String(error.message || error)}</p></div>`;
    }
};

const unmount = () => {
    explorer?.modal?.close();
    host?.roots?.timeline?.classList.add('hidden');
    host?.roots?.country?.classList.add('hidden');
};

window.ElectionApp = { openWorld, unmount };
window.dispatchEvent(new Event('electionapp:ready'));
