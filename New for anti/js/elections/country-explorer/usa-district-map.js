import { loadCongressionalDistricts } from '../data/geo-service.js';

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

export const renderUsaDistrictMap = async ({ host, stateId }) => {
    const geo = await loadCongressionalDistricts(stateId);
    if (!geo) return false;
    host.setElectionMap([
        ...host.worldBaseLayers({ id: `elections-usa-${stateId}-district-base`, landColor: [22, 32, 48, 255], lineColor: [71, 85, 105, 110] }),
        new host.layers.GeoJsonLayer({
            id: `elections-usa-${stateId}-districts`, data: geo, stroked: true, filled: true, pickable: true, lineWidthMinPixels: 1.2,
            getLineColor: [226, 232, 240, 205],
            getFillColor: (feature) => partyColor(feature.properties?.party_abbr),
        }),
    ], null, viewForGeometry(geo));
    return true;
};
