import { loadAdmin1 } from '../data/geo-service.js?v=2';
import { classColors, stateClass2024 } from '../data/usa-election-context.js?v=2';

const neutral = [51, 65, 85, 235];
const selected = [14, 116, 144, 245];
const partyColor = (abbr) => abbr === 'DEM' ? [37, 99, 235, 220]
    : abbr === 'GOP' ? [220, 38, 38, 220] : neutral;

const eachCoordinate = (node, visit) => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === 'number') visit(node);
    else node.forEach((child) => eachCoordinate(child, visit));
};

const mapCoordinates = (node, project) => (typeof node[0] === 'number' ? project(node) : node.map((child) => mapCoordinates(child, project)));

const unwrapLon = (lon) => (lon < 0 ? lon + 360 : lon);
const wrapLon = (lon) => ((lon + 540) % 360) - 180;

// Exclaves (a country's own territory, geographically detached from its
// mainland) break the country map two ways: at true position they can
// straddle the antimeridian (Alaska's Aleutians), and at true scale their
// bounding box can be as wide as the mainland's, which drags the auto-fit
// viewport out until the mainland reads as a sliver -- exactly what made
// Alaska look oversized here. Scaling each one down around its own centroid
// and relocating that centroid next to the mainland is the same composite-
// inset trick paper atlases use for AK/HI; it is a coordinate transform on
// the GeoJSON alone, so it needs no second deck.gl view (this app is one
// _GlobeView -- see CLAUDE.md). Add an entry per country as its exclaves
// come up; codes match the `code` property in public/data/admin1/<ISO3>.json.
//
// AK sits in the Pacific off WA/OR with the panhandle pointing at the WA
// coast; HI sits off northern California, below AK. anchor = where the
// shape's bounding-box centre lands. dropWestOf removes island polygons
// lying wholly west of that longitude -- HI's admin1 shape carries the
// Northwestern Hawaiian atolls out to -178°, which otherwise trail across
// the inset and pull its centre off the eight main islands. rotate (degrees,
// counter-clockwise) turns the shape about its centre: on the globe a
// meridian away from the view centre leans, so AK's straight 141°W border
// read as tilted; 22° stands it upright at the USA view's centre (~103°W).
const EXCLAVES = {
    USA: [
        { code: 'US-AK', scale: 0.38, anchorLon: -133.9, anchorLat: 46.5, rotate: 22 },
        { code: 'US-HI', scale: 1, anchorLon: -128, anchorLat: 37.5, dropWestOf: -161 },
    ],
};

const boundsOf = (geometry) => {
    let west = Infinity; let east = -Infinity; let south = Infinity; let north = -Infinity;
    eachCoordinate(geometry?.coordinates, ([lon, lat]) => {
        const u = unwrapLon(lon);
        west = Math.min(west, u); east = Math.max(east, u);
        south = Math.min(south, lat); north = Math.max(north, lat);
    });
    return { west, east, south, north };
};

const withoutFarWestIslands = (geometry, dropWestOf) => {
    if (dropWestOf == null || geometry?.type !== 'MultiPolygon') return geometry;
    const limit = unwrapLon(dropWestOf);
    const kept = geometry.coordinates.filter((polygon) => {
        let east = -Infinity;
        eachCoordinate(polygon, ([lon]) => { east = Math.max(east, unwrapLon(lon)); });
        return east >= limit;
    });
    return kept.length ? { ...geometry, coordinates: kept } : geometry;
};

const DEG = Math.PI / 180;

const relocateExclave = (feature, { scale, anchorLon, anchorLat, dropWestOf, rotate = 0 }) => {
    const geometry = withoutFarWestIslands(feature.geometry, dropWestOf);
    const { west, east, south, north } = boundsOf(geometry);
    const centerLon = (west + east) / 2;
    const centerLat = (south + north) / 2;
    const anchorU = unwrapLon(anchorLon);
    // A degree of longitude is cos(lat) wide on the globe, so moving a shape
    // to another latitude stretches or squeezes it sideways. Rescale longitude
    // by the ratio so AK (61°N → ~47°N) keeps its true proportions instead of
    // coming out ~1.4x too wide.
    const anchorCos = Math.cos(anchorLat * DEG);
    const lonScale = scale * Math.cos(centerLat * DEG) / anchorCos;
    const cos = Math.cos(rotate * DEG);
    const sin = Math.sin(rotate * DEG);
    // Rotate in ground units (longitude times cos(lat)) so the turn doesn't
    // shear the shape, then convert back to degrees of longitude.
    const project = ([lon, lat, ...rest]) => {
        const x = (unwrapLon(lon) - centerLon) * lonScale * anchorCos;
        const y = (lat - centerLat) * scale;
        return [
            wrapLon(anchorU + (x * cos - y * sin) / anchorCos),
            anchorLat + x * sin + y * cos,
            ...rest,
        ];
    };
    return { ...feature, geometry: { ...geometry, coordinates: mapCoordinates(geometry.coordinates, project) } };
};

// Applied before viewForGeometry runs, so the auto-fit viewport is computed
// from the relocated (small, mainland-adjacent) shapes, not the true ones.
const withRelocatedExclaves = (geo, iso3) => {
    const configs = EXCLAVES[iso3];
    if (!configs?.length) return geo;
    const byCode = new Map(configs.map((config) => [config.code, config]));
    return {
        ...geo,
        features: (geo.features || []).map((feature) => {
            const config = byCode.get(feature.properties?.code);
            return config ? relocateExclave(feature, config) : feature;
        }),
    };
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

// fitView:false 는 카메라를 건드리지 않고 색만 바꾼다. 주를 누른 직후 "눌렀다"는 표시를 지도에
// 먼저 주려고 같은 지도를 다시 칠할 때 쓴다 -- 사용자가 확대해 둔 시점이 되돌아가면 안 된다.
export const renderCountryMap = async ({ host, country, selectedStateId = null, electionMode = false, isStale = null, fitView = true, onStateOpen }) => {
    let raw;
    try {
        raw = await loadAdmin1(country.iso3);
    } catch (error) {
        // 경계 도형을 못 받았다. 예외를 올리면 이 지도를 기다리는 화면 전체가 멈춘다. 실패는
        // 캐시되지 않으므로 나갔다 들어오면 다시 시도한다.
        console.warn(`국가 경계 도형을 불러오지 못했습니다 (${country.iso3}):`, error?.message || error);
        return false;
    }
    const geo = withRelocatedExclaves(raw, country.iso3);
    if (isStale?.()) return false;
    const usaStates = country.iso3 === 'USA' ? stateIndex(country) : null;
    const layer = new host.layers.GeoJsonLayer({
        id: `elections-country-${country.iso3}`,
        data: geo,
        stroked: true,
        filled: true,
        pickable: country.iso3 === 'USA',
        lineWidthMinPixels: 1,
        updateTriggers: { getFillColor: [selectedStateId, electionMode] },
        getLineColor: [203, 213, 225, 190],
        getFillColor: (feature) => {
            const state = usaStates?.get(feature.properties?.code);
            if (state?.id === selectedStateId) return selected;
            if (country.iso3 === 'USA' && electionMode) {
                const stateId = feature.properties?.code?.replace(/^US-/, '');
                return classColors[stateClass2024(stateId)];
            }
            return state ? partyColor(state.governor?.abbr) : neutral;
        },
    });
    host.setElectionMap([
        ...host.worldBaseLayers({ id: `elections-${country.iso3}-base`, landColor: [22, 32, 48, 255], lineColor: [71, 85, 105, 110] }),
        layer,
    ], country.iso3 === 'USA' ? (info) => {
        const state = usaStates.get(info?.object?.properties?.code);
        if (state) onStateOpen(state.id);
    } : null, fitView ? viewForGeometry(geo) : null);
    return true;
};
