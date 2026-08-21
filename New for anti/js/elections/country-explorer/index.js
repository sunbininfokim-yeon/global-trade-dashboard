import { renderCountryShell } from './country-shell.js';
import { renderWorldElectionMap } from './world-map.js';
import { renderCountryMap } from './country-map.js';
import { renderUsaStateDashboard } from './usa-state-dashboard.js';
import { renderUsaDistrictMap } from './usa-district-map.js';
import { createModal } from '../modal.js';

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
            renderCountryShell(host.roots.country, { country, manifest: bundle.manifest, onBack, modal });
            await renderCountryMap({ host, country, onStateOpen: (stateId) => this.showUsaState(stateId) });
        },
        async showUsaState(stateId) {
            // The state dashboard replaces the right pane wholesale, so any
            // country block still open would be describing the wrong screen.
            modal?.close();
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
    };
};
