import { createElectionState } from './state.js';
import { loadElectionBundle } from './data/core-service.js';
import { initialMonth } from './data/selectors.js';
import { createCountryExplorer } from './country-explorer/index.js';
import { renderTimeline } from './timeline/index.js';

const state = createElectionState();
let host = null;
let bundle = null;
let explorer = null;
let opening = null;

const render = async () => {
    if (!host || !bundle || !explorer) return;
    const current = state.get();
    if (current.mode === 'country' && current.iso3) {
        host.setPanels({ timeline: false, country: true, left: false, right: true });
        explorer.showCountry(current.iso3);
        return;
    }
    host.setPanels({ timeline: true, country: false, left: true, right: false });
    renderTimeline(host.roots.timeline, {
        calendar: bundle.calendar,
        countries: bundle.countries,
        month: current.month,
        onMonthChange: (month) => state.set({ month }),
    });
    await explorer.showWorld();
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
        });
        state.set({ mode: 'world', iso3: null, month: state.get().month || initialMonth(bundle.calendar) });
        await opening;
        await render();
    } catch (error) {
        host.setPanels({ timeline: true, country: false, left: true, right: false });
        host.roots.timeline.innerHTML = `<div class="panel-header"><h2>선거 데이터 연결 대기</h2><p>${String(error.message || error)}</p></div>`;
    }
};

const unmount = () => {
    host?.roots?.timeline?.classList.add('hidden');
    host?.roots?.country?.classList.add('hidden');
};

window.ElectionApp = { openWorld, unmount };
window.dispatchEvent(new Event('electionapp:ready'));
