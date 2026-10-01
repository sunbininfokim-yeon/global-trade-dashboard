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
            if (isStale()) return;
            onRoute?.({ country: iso3 });
            shell = renderCountryShell(host.roots.country, {
                country, manifest: bundle.manifest, onBack, modal, host,
                onRoute: (patch) => onRoute?.({ country: iso3, ...patch }),
            });
            await mapReady;
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
