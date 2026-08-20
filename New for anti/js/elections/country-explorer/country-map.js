import { loadAdmin1 } from '../data/geo-service.js';

const neutral = [51, 65, 85, 235];
const selected = [14, 116, 144, 245];
const partyColor = (abbr) => abbr === 'DEM' ? [37, 99, 235, 220]
    : abbr === 'GOP' ? [220, 38, 38, 220] : neutral;

const eachCoordinate = (node, visit) => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === 'number') visit(node);
    else node.forEach((child) => eachCoordinate(child, visit));
};

const viewForGeometry = (geo) => {
    const longitudes = [];
    let south = Infinity;
    let north = -Infinity;
    (geo?.features || []).forEach((feature) => eachCoordinate(feature.geometry?.coordinates, ([lon, lat]) => {
        longitudes.push((lon + 360) % 360);
        south = Math.min(south, lat); north = Math.max(north, lat);
    }));
    if (!longitudes.length) return null;
    // Find the smallest longitude arc containing every boundary point. This
    // keeps Alaska's Aleutian Islands from making the USA view span the world.
    longitudes.sort((a, b) => a - b);
    let widestGap = -1;
    let gapIndex = 0;
    for (let index = 0; index < longitudes.length; index += 1) {
        const next = index === longitudes.length - 1 ? longitudes[0] + 360 : longitudes[index + 1];
        const gap = next - longitudes[index];
        if (gap > widestGap) { widestGap = gap; gapIndex = index; }
    }
    const longitudeSpan = 360 - widestGap;
    const arcStart = longitudes[(gapIndex + 1) % longitudes.length];
    let longitude = (arcStart + longitudeSpan / 2) % 360;
    if (longitude > 180) longitude -= 360;
    const span = Math.max(longitudeSpan, (north - south) * 1.45, 4);
    return {
        longitude,
        latitude: (south + north) / 2,
        zoom: Math.max(1.2, Math.min(5.2, Math.log2(360 / span) + 0.7)),
        bearing: 0,
        pitch: 0,
    };
};

const stateIndex = (country) => new Map(
    (country?.ui_ready?.state_drilldown?.states || []).map((state) => [state.map_feature_code, state]),
);

export const renderCountryMap = async ({ host, country, selectedStateId = null, onStateOpen }) => {
    const geo = await loadAdmin1(country.iso3);
    const usaStates = country.iso3 === 'USA' ? stateIndex(country) : null;
    const layer = new host.layers.GeoJsonLayer({
        id: `elections-country-${country.iso3}`,
        data: geo,
        stroked: true,
        filled: true,
        pickable: country.iso3 === 'USA',
        lineWidthMinPixels: 1,
        getLineColor: [203, 213, 225, 190],
        getFillColor: (feature) => {
            const state = usaStates?.get(feature.properties?.code);
            if (state?.id === selectedStateId) return selected;
            return state ? partyColor(state.governor?.abbr) : neutral;
        },
    });
    host.setElectionMap([
        ...host.worldBaseLayers({ id: `elections-${country.iso3}-base`, landColor: [22, 32, 48, 255], lineColor: [71, 85, 105, 110] }),
        layer,
    ], country.iso3 === 'USA' ? (info) => {
        const state = usaStates.get(info?.object?.properties?.code);
        if (state) onStateOpen(state.id);
    } : null, viewForGeometry(geo));
};
