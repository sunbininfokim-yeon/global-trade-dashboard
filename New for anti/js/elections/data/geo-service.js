const DATA_ROOT = '/public/data';
const admin1Promises = new Map();
const districtPromises = new Map();

const loadJson = async (filename) => {
    const response = await fetch(`${DATA_ROOT}/${filename}`, { cache: 'force-cache' });
    if (!response.ok) throw new Error(`${filename} (${response.status})`);
    return response.json();
};

// Boundary-only assets; political party/member fields must already be baked
// into a derived GeoJSON by the data pipeline before the browser sees it.
export const loadAdmin1 = (iso3) => {
    if (!admin1Promises.has(iso3)) admin1Promises.set(iso3, loadJson(`admin1/${iso3}.json`));
    return admin1Promises.get(iso3);
};

export const loadCongressionalDistricts = (stateId) => {
    if (!districtPromises.has(stateId)) {
        districtPromises.set(stateId, loadJson(`congressional_districts/USA/${stateId}.json`).catch((error) => {
            if (String(error.message).includes('(404)')) return null;
            throw error;
        }));
    }
    return districtPromises.get(stateId);
};
