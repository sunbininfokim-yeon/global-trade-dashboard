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
    authoritarian_ur: [100, 116, 139, 185],
    authoritarian_monarchy: [110, 90, 60, 185],
};
const neutral = [43, 52, 66, 255];

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
    host.setWorldMap([
        ...host.worldBaseLayers({ id: 'elections-world', landColor: [30, 41, 59, 255], lineColor: [100, 116, 139, 140] }),
        politicalLayer,
    ], (info) => {
        const iso3 = host.resolveIso3(info?.object);
        if (countries.has(iso3)) onCountryOpen(iso3);
    });
};
