import { renderCountryShell } from './country-shell.js?v=2';
import { renderWorldElectionMap } from './world-map.js';
import { renderCountryMap } from './country-map.js?v=2';
import { renderUsaStateDashboard } from './usa-state-dashboard.js';
import { renderUsaDistrictMap } from './usa-district-map.js';
import { createModal } from '../modal.js';
import { loadUsCommittees, loadEopChart } from '../data/us-congress-service.js';
import { loadStateFinance, loadFinanceDisplayContract } from '../data/finance-service.js';
import { loadCongressionalDistricts } from '../data/geo-service.js';
import { applyEopChart } from './special/usa-executive.js';
import { applyCnPartyChart } from './special/chn-org.js';
import { loadCnPartyChart } from '../data/chn-service.js';

export const createCountryExplorer = ({ host, bundle, onCountryOpen, onBack, onRoute }) => {
    const modal = createModal(host.roots.modal);
    let shell = null;
    // Bumped on every navigation, so a map that finishes loading after the
    // user has already moved on (back to world, another country) is dropped
    // instead of painting over the screen they're now on.
    let navSeq = 0;
    return {
        modal,
        openScreen(key) { shell?.openSection(key); },
        async showWorld() {
            modal?.close();
            shell = null;
            navSeq += 1;
            onRoute?.({});
            await renderWorldElectionMap(host, bundle.countries, onCountryOpen);
        },
        async showCountry(iso3) {
            const country = bundle.countries.get(iso3);
            if (!country) return;
            const seq = ++navSeq;
            const isStale = () => seq !== navSeq;
            // The map only needs admin1 geometry, so it starts now, in parallel
            // with the panel's data below -- it used to wait for the committee /
            // EOP fetches first, which left the world map up (and a state click
            // landing on whatever country was under it) for the first second
            // after opening USA ("미국 들어가서 바로 주 누르면 클릭이 안돼").
            const mapReady = renderCountryMap({ host, country, isStale, onStateOpen: (stateId) => this.showUsaState(stateId) });
            // The 의회 screen's 상임위 chips need the policy overview's
            // committee list before the panel is built; only the USA screen
            // reads it, so it is fetched once, lazily, here.
            if (iso3 === 'USA' && !country.us_committees) {
                country.us_committees = await loadUsCommittees();
                applyEopChart(await loadEopChart());
            }
            // 중국 당 주요 직위 골격도 같은 방식이다 -- 화면이 그려지기 전에 한 번만
            // 읽고, 못 읽으면 모듈 내장 골격으로 그린다.
            if (iso3 === 'CHN') applyCnPartyChart(await loadCnPartyChart());
            // Wait for the map's own layers/click handler to actually land
            // before painting the shell -- not just for the committee/EOP
            // fetch above. admin1 geometry is cached after a country's first
            // visit (loadAdmin1 memoizes the promise), so a repeat visit (e.g.
            // USA -> a state -> back to USA) skips the committee fetch too
            // (country.us_committees is already set) and reaches this point
            // almost immediately -- before renderCountryMap's continuation
            // after its own admin1 fetch had a chance to call
            // host.setElectionMap. The shell looked ready, but a click still
            // landed on the previous screen's stale layers/handler until
            // something else forced a redraw ("두번째로 다른 주 클릭할 때 바로
            // 안 되고 더블 클릭하거나 지도 크기가 바뀐 뒤에야 됨", 2026-10-02).
            await mapReady;
            if (isStale()) return;
            onRoute?.({ country: iso3 });
            shell = renderCountryShell(host.roots.country, {
                country, manifest: bundle.manifest, onBack, modal, host,
                onRoute: (patch) => onRoute?.({ country: iso3, ...patch }),
            });
        },
        async showUsaState(stateId, { financeMode = false, district = null } = {}) {
            // The state dashboard replaces the right pane wholesale, so any
            // country block still open would be describing the wrong screen.
            modal?.close();
            const usa = bundle.countries.get('USA');
            const state = usa?.ui_ready?.state_drilldown?.states?.find((row) => row.id === stateId);
            if (!usa || !state) return;
            shell = null;
            const seq = ++navSeq;
            const isStale = () => seq !== navSeq;
            const route = { country: 'USA', state: stateId, view: financeMode ? 'finance' : null, district: financeMode ? district : null };
            onRoute?.(route);
            // Every race file for the state, plus the district ids the map can
            // actually draw, only once the 선거 toggle is on.
            const financeRaces = financeMode ? await loadStateFinance(stateId) : null;
            const financeContract = financeMode ? await loadFinanceDisplayContract() : null;
            const districtGeo = financeMode ? await loadCongressionalDistricts(stateId).catch(() => null) : null;
            const mappedDistricts = districtGeo
                ? new Set((districtGeo.features || []).map((feature) => String(feature.properties?.district ?? '')))
                : null;
            const districtMapReady = await renderUsaDistrictMap({ host, stateId, highlightDistrict: financeMode ? district : null });
            if (isStale()) return;
            renderUsaStateDashboard(host.roots.country, {
                state,
                districtMapReady,
                financeMode,
                financeRaces,
                financeContract,
                mappedDistricts,
                openDistrict: financeMode ? district : null,
                onBackToUsa: () => this.showCountry('USA'),
                onToggleFinance: () => this.showUsaState(stateId, { financeMode: !financeMode }),
                // Only the map is redrawn, and only its colours: fitView stays
                // off so clicking a district never moves the camera.
                onHighlightDistrict: (next) => {
                    onRoute?.({ ...route, district: next });
                    return renderUsaDistrictMap({ host, stateId, highlightDistrict: next, fitView: false });
                },
            });
            if (!districtMapReady) {
                await renderCountryMap({ host, country: usa, selectedStateId: stateId, isStale, onStateOpen: (nextStateId) => this.showUsaState(nextStateId) });
            }
        },
    };
};
