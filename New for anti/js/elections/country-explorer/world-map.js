const spectrumColors = {
    conservative: [220, 38, 38, 185],
    nationalist_conservative: [234, 88, 12, 185],
    progressive: [37, 99, 235, 185],
    centrist: [126, 34, 206, 185],
    catch_all_governing_party: [161, 98, 7, 185],
    authoritarian_personalist: [100, 116, 139, 185],
    authoritarian_party_state: [71, 85, 105, 185],
    theocratic_authoritarian: [20, 83, 45, 185],
    // CHN/SAU/ARE/RUS carry these three instead of the generic
    // authoritarian_* keys above, so without an entry here they fell through
    // to `neutral` -- indistinguishable from a country with no spectrum data
    // at all (reported 2026-09-12: "중국은 왜 색깔이 없는거야?").
    // authoritarian_cpc: user asked for CCP red specifically (2026-09-12).
    // This is the party's own flag color (PRC flag red, 中国红), not the
    // US conservative-party red reused for `conservative` above -- picked a
    // visibly different red (more vermilion/orange-leaning) so the two don't
    // collide as the same hue on the map. Still distinct from putting China
    // on the conservative/progressive axis, which CLAUDE.md rules out.
    authoritarian_cpc: [222, 41, 16, 195],
    // authoritarian_ur = United Russia (Единая Россия, Putin's party
    // vehicle) -- user asked for "Putin's color" (2026-09-12). This is the
    // party's own official brand blue, #2056AE, not `progressive`'s brighter
    // blue [37,99,235] -- distinct enough not to collide as the same hue.
    authoritarian_ur: [32, 86, 174, 195],
    authoritarian_monarchy: [110, 90, 60, 185],
};
const neutral = [43, 52, 66, 255];

// 분쟁국 X 표시. 권력이 둘 이상으로 갈린 나라(board 의 mode: divided_authority -- 리비아·예멘)
// 위에 국경 상자의 대각선 두 줄을 긋는다. _GlobeView 에서 LineLayer 는 그려지지 않으므로
// (CLAUDE.md) GeoJSON 선으로 만들어 GeoJsonLayer(내부 PathLayer)로 그리고, 지구면을 따라
// 휘도록 선마다 점을 촘촘히 찍는다.
export const isConflictCountry = (country) => country?.mode === 'divided_authority';

const ringsOf = (geometry) => (geometry?.type === 'Polygon' ? [geometry.coordinates]
    : geometry?.type === 'MultiPolygon' ? geometry.coordinates : []);

// 가장 큰 덩어리의 상자만 쓴다 -- 먼 섬까지 넣으면 X 가 바다 위로 뻗는다.
const mainBox = (geometry) => {
    let best = null;
    ringsOf(geometry).forEach((polygon) => {
        const ring = polygon[0] || [];
        const lons = ring.map((p) => p[0]); const lats = ring.map((p) => p[1]);
        const box = [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
        const area = (box[2] - box[0]) * (box[3] - box[1]);
        if (!best || area > best.area) best = { box, area };
    });
    return best?.box || null;
};

const densify = (a, b, steps = 24) => Array.from({ length: steps + 1 }, (_, i) => [
    a[0] + ((b[0] - a[0]) * i) / steps, a[1] + ((b[1] - a[1]) * i) / steps]);

export const conflictCrosses = (features, isConflict) => ({
    type: 'FeatureCollection',
    features: features.filter(isConflict).map((feature) => {
        const box = mainBox(feature.geometry);
        if (!box) return null;
        const [w, s, e, n] = box;
        const dx = (e - w) * 0.18; const dy = (n - s) * 0.18;
        const sw = [w + dx, s + dy]; const ne = [e - dx, n - dy];
        const nw = [w + dx, n - dy]; const se = [e - dx, s + dy];
        return { type: 'Feature', properties: { conflict: true }, geometry: { type: 'MultiLineString', coordinates: [densify(sw, ne), densify(nw, se)] } };
    }).filter(Boolean),
});

export const renderWorldElectionMap = async (host, countries, onCountryOpen) => {
    const geo = await host.loadWorldGeo();
    const politicalLayer = new host.layers.GeoJsonLayer({
        id: 'elections-political-spectrum',
        data: geo,
        stroked: true,
        filled: true,
        pickable: true,
        lineWidthMinPixels: 0.8,
        getLineColor: [148, 163, 184, 145],
        getFillColor: (feature) => {
            const country = countries.get(host.resolveIso3(feature));
            return country ? (spectrumColors[country.map_spectrum] || neutral) : neutral;
        },
    });
    const crosses = conflictCrosses(geo?.features || [], (feature) => isConflictCountry(countries.get(host.resolveIso3(feature))));
    const crossLayer = crosses.features.length ? new host.layers.GeoJsonLayer({
        id: 'elections-conflict-x',
        data: crosses,
        stroked: true,
        filled: false,
        pickable: false,
        lineWidthUnits: 'pixels',
        lineWidthMinPixels: 3,
        getLineWidth: 3,
        getLineColor: [248, 113, 113, 235],
    }) : null;
    host.setWorldMap([
        ...host.worldBaseLayers({ id: 'elections-world', landColor: [30, 41, 59, 255], lineColor: [100, 116, 139, 140] }),
        politicalLayer,
        ...(crossLayer ? [crossLayer] : []),
    ], (info) => {
        const iso3 = host.resolveIso3(info?.object);
        if (countries.has(iso3)) onCountryOpen(iso3);
    });
};
