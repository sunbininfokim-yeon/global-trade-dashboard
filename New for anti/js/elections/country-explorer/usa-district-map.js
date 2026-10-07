import { loadCongressionalDistricts } from '../data/geo-service.js?v=2';
import { pollSignal, pollSourceReady } from '../data/usa-election-context.js?v=2';

import { electionRatingSummary } from '../data/election-overview.js?v=2';

const partyColor = (party) => party === 'DEM' ? [37, 99, 235, 225]
    : party === 'GOP' ? [220, 38, 38, 225] : [71, 85, 105, 230];

export const districtElectionColor = (raceId, rating, board, health, days = 7, now = Date.now()) => {
    const signal = pollSignal(board?.races?.[raceId] || {election_date:'2026-11-03'},board,health,days,now);
    if (signal.status === 'certified_result') return partyColor(signal.party === 'REP' ? 'GOP' : signal.party);
    if (signal.status === 'awaiting_certified_result') return [71,85,105,230];
    const r = rating?.races?.find((row) => row.race_id === raceId);
    if (['solid_dem','likely_dem'].includes(r?.effective_rating)) return [96,165,250,115];
    if (['solid_rep','likely_rep'].includes(r?.effective_rating)) return [248,113,113,115];
    if (signal.party === 'DEM' || signal.party === 'REP') return partyColor(signal.party === 'REP' ? 'GOP' : signal.party);
    return [71,85,105,230];
};

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
//
// 반환값: true = 그렸다 · false = 도형이 없거나 못 받았다 · null = 기다리는 사이 사용자가
// 이미 다른 화면으로 갔다(그래서 아무것도 그리지 않았다).
//
// `isStale` 이 이 함수의 핵심이다. 도형(캘리포니아는 16MB)이 느리게 도착하는 동안 사용자가
// "← 미국 주 지도"로 나가면, 늦게 온 이 함수가 setElectionMap 으로 **미국 지도를 덮어쓰고 클릭
// 핸들러를 null 로 만들었다**. 그러면 지도가 캘리포니아 선거구로 바뀐 채 아무리 눌러도 반응이
// 없었다 ("나갔다 들어와도 클릭이 안 된다"). 도형을 기다린 뒤, 지도를 건드리기 직전에 확인한다.
//
// `geo` 를 넘기면 도형을 다시 읽지 않는다. 호출한 쪽이 이미 도형을 받아 패널을 갱신했다면, 여기서
// 또 읽다가 (실패 직후에는 캐시가 비어 있어서) 몰래 재요청이 나가고, 패널은 "도형 못 받음"인데
// 지도는 그려지는 어긋남이 생긴다.
export const renderUsaDistrictMap = async ({ host, stateId, highlightDistrict = null, fitView = true,
    electionMode = false, pollBoard = null, pollHealth = null, windowDays = 7, ratings = null, country = null, onDistrictSelect = null, isStale = null, geo: loaded }) => {
    let geo = loaded;
    try {
        if (geo === undefined) geo = await loadCongressionalDistricts(stateId);
    } catch (error) {
        // 받다가 실패했다. 예외로 화면 전체를 멈추지 않고 "도형 없음"으로 돌려보낸다 -- 도형 읽기는
        // 실패를 캐시하지 않으므로 다음 진입이 다시 시도한다.
        console.warn(`선거구 도형을 불러오지 못했습니다 (${stateId}):`, error?.message || error);
        return isStale?.() ? null : false;
    }
    if (isStale?.()) return null;
    if (!geo) return false;
    const rating = electionMode ? electionRatingSummary(ratings,'house',country,stateId) : null;
    host.setElectionMap([
        ...host.worldBaseLayers({ id: `elections-usa-${stateId}-district-base`, landColor: [22, 32, 48, 255], lineColor: [71, 85, 105, 110] }),
        new host.layers.GeoJsonLayer({
            id: `elections-usa-${stateId}-districts`, data: geo, stroked: true, filled: true, pickable: true, lineWidthMinPixels: 1.2,
            // deck.gl caches accessor results, so the highlight has to be part
            // of the layer's update trigger or the repaint keeps the old fill.
            updateTriggers: { getFillColor: [highlightDistrict, electionMode, pollBoard?.fetched_at,
                pollSourceReady(pollBoard, pollHealth), rating?.asOf, country?.ui_ready?.congress?.swing_seats, windowDays, Math.floor(Date.now() / 3600000)],
                getLineColor: highlightDistrict, getLineWidth: highlightDistrict },
            getLineColor: (feature) => (isHighlighted(feature, highlightDistrict) ? [255, 255, 255, 255] : [226, 232, 240, 205]),
            getLineWidth: (feature) => (isHighlighted(feature, highlightDistrict) ? 3 : 1),
            lineWidthUnits: 'pixels',
            getFillColor: (feature) => {
                if (isHighlighted(feature, highlightDistrict)) return [255, 255, 255, 235];
                if (!electionMode) return partyColor(feature.properties?.party_abbr);
                const district = String(feature.properties?.district ?? '');
                return districtElectionColor(`USA:${stateId}:house:${district}`,rating,pollBoard,pollHealth,windowDays);
            },
        }),
    ], onDistrictSelect ? (info) => {
        const district = info?.object?.properties?.district;
        if (district != null && geo.features.some((f) => String(f.properties?.district) === String(district))) onDistrictSelect(String(district));
    } : null, fitView ? viewForGeometry(geo) : null);
    return true;
};
