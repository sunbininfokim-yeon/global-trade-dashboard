import { loadCongressionalDistricts } from '../data/geo-service.js';
import { pollSignal, pollSourceReady } from '../data/usa-election-context.js?v=2';

const partyColor = (party) => party === 'DEM' ? [37, 99, 235, 225]
    : party === 'GOP' ? [220, 38, 38, 225] : [71, 85, 105, 230];

const eachCoordinate = (node, visit) => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === 'number') visit(node);
    else node.forEach((child) => eachCoordinate(child, visit));
};

const viewForGeometry = (geo) => {
    let west = Infinity; let east = -Infinity; let south = Infinity; let north = -Infinity;
    (geo?.features || []).forEach((feature) => eachCoordinate(feature.geometry?.coordinates, ([lon, lat]) => {
        west = Math.min(west, lon); east = Math.max(east, lon); south = Math.min(south, lat); north = Math.max(north, lat);
    }));
    if (!Number.isFinite(west)) return null;
    const span = Math.max(east - west, (north - south) * 1.45, 1.5);
    return { longitude: (west + east) / 2, latitude: (south + north) / 2, zoom: Math.max(3, Math.min(7.5, Math.log2(360 / span) - 0.1)), bearing: 0, pitch: 0 };
};

// Districts are keyed as zero-padded strings ("01") in both the geometry and
// the finance data, so the selected district is compared as a string rather
// than parsed -- "00" (at-large) would otherwise collide with a falsy 0.
const isHighlighted = (feature, highlightDistrict) => highlightDistrict != null
    && String(feature.properties?.district ?? '') === String(highlightDistrict);

// fitView is false when only the highlight changed: setElectionMap treats a
// viewState as "move the camera there", so re-fitting on every district click
// would yank the map back to the whole-state framing the user had zoomed out of.
export const renderUsaDistrictMap = async ({ host, stateId, highlightDistrict = null, fitView = true,
    electionMode = false, pollBoard = null, pollHealth = null, windowDays = 7 }) => {
    const geo = await loadCongressionalDistricts(stateId);
    if (!geo) return false;
    host.setElectionMap([
        ...host.worldBaseLayers({ id: `elections-usa-${stateId}-district-base`, landColor: [22, 32, 48, 255], lineColor: [71, 85, 105, 110] }),
        new host.layers.GeoJsonLayer({
            id: `elections-usa-${stateId}-districts`, data: geo, stroked: true, filled: true, pickable: true, lineWidthMinPixels: 1.2,
            // deck.gl caches accessor results, so the highlight has to be part
            // of the layer's update trigger or the repaint keeps the old fill.
            updateTriggers: { getFillColor: [highlightDistrict, electionMode, pollBoard?.fetched_at,
                pollSourceReady(pollBoard, pollHealth), windowDays, Math.floor(Date.now() / 3600000)],
                getLineColor: highlightDistrict, getLineWidth: highlightDistrict },
            getLineColor: (feature) => (isHighlighted(feature, highlightDistrict) ? [255, 255, 255, 255] : [226, 232, 240, 205]),
            getLineWidth: (feature) => (isHighlighted(feature, highlightDistrict) ? 3 : 1),
            lineWidthUnits: 'pixels',
            getFillColor: (feature) => {
                if (isHighlighted(feature, highlightDistrict)) return [255, 255, 255, 235];
                if (!electionMode) return partyColor(feature.properties?.party_abbr);
                const district = String(feature.properties?.district ?? '');
                const race = pollBoard?.races?.[`USA:${stateId}:house:${district}`];
                const party = pollSignal(race, pollBoard, pollHealth, windowDays).party;
                return party === 'DEM' ? partyColor('DEM') : party === 'REP' ? partyColor('GOP') : [71, 85, 105, 230];
            },
        }),
    ], null, fitView ? viewForGeometry(geo) : null);
    return true;
};
