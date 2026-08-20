import { renderCountryShell } from './country-shell.js';
import { renderWorldElectionMap } from './world-map.js';
import { renderCountryMap } from './country-map.js';
import { renderUsaStateDashboard } from './usa-state-dashboard.js';
import { renderUsaDistrictMap } from './usa-district-map.js';

export const createCountryExplorer = ({ host, bundle, onCountryOpen, onBack }) => ({
    async showWorld() {
        await renderWorldElectionMap(host, bundle.countries, onCountryOpen);
    },
    async showCountry(iso3) {
        const country = bundle.countries.get(iso3);
        if (!country) return;
        renderCountryShell(host.roots.country, { country, manifest: bundle.manifest, onBack });
        await renderCountryMap({ host, country, onStateOpen: (stateId) => this.showUsaState(stateId) });
    },
    async showUsaState(stateId) {
        const usa = bundle.countries.get('USA');
        const state = usa?.ui_ready?.state_drilldown?.states?.find((row) => row.id === stateId);
        if (!usa || !state) return;
        const districtMapReady = await renderUsaDistrictMap({ host, stateId });
        renderUsaStateDashboard(host.roots.country, {
            state,
            districtMapReady,
            onBackToUsa: () => this.showCountry('USA'),
        });
        if (!districtMapReady) {
            await renderCountryMap({ host, country: usa, selectedStateId: stateId, onStateOpen: (nextStateId) => this.showUsaState(nextStateId) });
        }
    },
});
