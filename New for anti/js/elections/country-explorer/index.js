import { renderCountryShell } from './country-shell.js';
import { renderWorldElectionMap } from './world-map.js';
import { renderCountryMap } from './country-map.js';
import { renderUsaStateDashboard } from './usa-state-dashboard.js';
import { renderUsaDistrictMap } from './usa-district-map.js';
import { createModal } from '../modal.js';
import { loadUsCommittees } from '../data/us-congress-service.js';
import { loadStateFinance } from '../data/finance-service.js';
import { loadCongressionalDistricts } from '../data/geo-service.js';

export const createCountryExplorer = ({ host, bundle, onCountryOpen, onBack }) => {
    const modal = createModal(host.roots.modal);
    return {
        modal,
        async showWorld() {
            modal?.close();
            await renderWorldElectionMap(host, bundle.countries, onCountryOpen);
        },
        async showCountry(iso3) {
            const country = bundle.countries.get(iso3);
            if (!country) return;
            // The 의회 screen's 상임위 chips need the policy overview's
            // committee list before the panel is built; only the USA screen
            // reads it, so it is fetched once, lazily, here.
            if (iso3 === 'USA' && !country.us_committees) {
                country.us_committees = await loadUsCommittees();
            }
            renderCountryShell(host.roots.country, { country, manifest: bundle.manifest, onBack, modal, host });
            await renderCountryMap({ host, country, onStateOpen: (stateId) => this.showUsaState(stateId) });
        },
        async showUsaState(stateId, { financeMode = false } = {}) {
            // The state dashboard replaces the right pane wholesale, so any
            // country block still open would be describing the wrong screen.
            modal?.close();
            const usa = bundle.countries.get('USA');
            const state = usa?.ui_ready?.state_drilldown?.states?.find((row) => row.id === stateId);
            if (!usa || !state) return;
            // Every race file for the state, plus the district ids the map can
            // actually draw, only once the 선거 toggle is on.
            const financeRaces = financeMode ? await loadStateFinance(stateId) : null;
            const districtGeo = financeMode ? await loadCongressionalDistricts(stateId).catch(() => null) : null;
            const mappedDistricts = districtGeo
                ? new Set((districtGeo.features || []).map((feature) => String(feature.properties?.district ?? '')))
                : null;
            const districtMapReady = await renderUsaDistrictMap({ host, stateId });
            renderUsaStateDashboard(host.roots.country, {
                state,
                districtMapReady,
                financeMode,
                financeRaces,
                mappedDistricts,
                onBackToUsa: () => this.showCountry('USA'),
                onToggleFinance: () => this.showUsaState(stateId, { financeMode: !financeMode }),
                // Only the map is redrawn, and only its colours: fitView stays
                // off so clicking a district never moves the camera.
                onHighlightDistrict: (district) => renderUsaDistrictMap({ host, stateId, highlightDistrict: district, fitView: false }),
            });
            if (!districtMapReady) {
                await renderCountryMap({ host, country: usa, selectedStateId: stateId, onStateOpen: (nextStateId) => this.showUsaState(nextStateId) });
            }
        },
    };
};
