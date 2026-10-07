import { renderCountryShell } from './country-shell.js?v=3';
import { renderWorldElectionMap } from './world-map.js';
import { renderCountryMap } from './country-map.js?v=4';
import { renderUsaStateDashboard } from './usa-state-dashboard.js?v=5';
import { renderUsaDistrictMap } from './usa-district-map.js?v=4';
import { createModal } from '../modal.js';
import { loadUsCommittees, loadEopChart } from '../data/us-congress-service.js';
import { loadStateFinance, loadStateFinanceIndex, loadFinanceDisplayContract, loadUsaElectionFinance, prefetchStateFinance } from '../data/finance-service.js?v=3';
import { MAPPING_FAILED } from './special/usa-state-superpac.js?v=5';
import { loadLivePolls } from '../data/poll-service.js?v=2';
import { loadUsaElectionRatings } from '../data/rating-service.js';
import { nationalMonitoringStates, renderUsaElectionNational } from './special/usa-election-national.js?v=4';
import { loadCongressionalDistricts, prefetchCongressionalDistricts } from '../data/geo-service.js?v=2';
import { applyEopChart } from './special/usa-executive.js';
import { applyCnPartyChart } from './special/chn-org.js';
import { loadCnPartyChart } from '../data/chn-service.js';

export const createCountryExplorer = ({ host, bundle, onCountryOpen, onBack, onRoute }) => {
    const modal = createModal(host.roots.modal);
    let shell = null;
    let usaElectionMode = false;
    let pollWindowDays = 7;
    const evidenceOpen = { poll: false, finance: false };
    const rememberEvidence = () => host.roots.country.querySelectorAll('[data-evidence-section]').forEach((section) => {
        evidenceOpen[section.dataset.evidenceSection] = section.open;
    });
    // Bumped on every navigation, so a map that finishes loading after the
    // user has already moved on (back to world, another country) is dropped
    // instead of painting over the screen they're now on.
    let navSeq = 0;
    // 지금 지도가 무엇을 보여 주는지. 주를 누른 직후 "눌렀다"는 표시를 주려고 미국 지도를 다시
    // 칠하는데, 이미 그 주의 선거구 지도가 떠 있다면(7일/14일 전환, 토글 등) 되돌리지 않는다.
    let mapShows = null;
    let displayTimer = null;
    const stopDisplayRefresh = () => { if (displayTimer) clearTimeout(displayTimer); displayTimer = null; };
    const watchDisplay = (polls, seq, redraw) => {
        stopDisplayRefresh();
        const signature = (value) => [value.board?.fetched_at, value.health?.status,
            new Date().toISOString().slice(0, 10)].join('|');
        const before = signature(polls);
        const tick = async () => {
            if (seq !== navSeq) return;
            const latest = await loadLivePolls(); // memoized for 15 minutes
            if (seq !== navSeq) return;
            if (signature(latest) !== before) {
                const scroll = host.roots.country.scrollTop;
                const monitoringOpen = host.roots.country.querySelector('.elections-monitoring-list')?.open;
                await redraw();
                host.roots.country.scrollTop = scroll;
                const list = host.roots.country.querySelector('.elections-monitoring-list');
                if (list && monitoringOpen) list.open = true;
                return;
            }
            displayTimer = setTimeout(tick, 60000);
        };
        displayTimer = setTimeout(tick, 60000);
    };
    return {
        modal,
        openScreen(key) { shell?.openSection(key); },
        async showWorld() {
            stopDisplayRefresh();
            modal?.close();
            shell = null;
            mapShows = null;
            navSeq += 1;
            onRoute?.({});
            await renderWorldElectionMap(host, bundle.countries, onCountryOpen);
        },
        async showCountry(iso3, { electionMode = false } = {}) {
            rememberEvidence();
            stopDisplayRefresh();
            const country = bundle.countries.get(iso3);
            if (!country) return;
            usaElectionMode = iso3 === 'USA' && electionMode;
            const seq = ++navSeq;
            const isStale = () => seq !== navSeq;
            // The map only needs admin1 geometry, so it starts now, in parallel
            // with the panel's data below -- it used to wait for the committee /
            // EOP fetches first, which left the world map up (and a state click
            // landing on whatever country was under it) for the first second
            // after opening USA ("미국 들어가서 바로 주 누르면 클릭이 안돼").
            const mapReady = renderCountryMap({ host, country, electionMode: usaElectionMode, isStale,
                onStateOpen: (stateId) => this.showUsaState(stateId, { financeMode: usaElectionMode }) })
                .then((drawn) => { if (drawn && !isStale()) mapShows = `country:${iso3}`; return drawn; });
            if (usaElectionMode) {
                host.roots.country.innerHTML = '<div class="panel-header"><h2>미국 선거</h2><p>공개 데이터를 연결하는 중입니다.</p></div>';
                // 전국 자금 파일은 폴과 상관없이 필요하다. 폴이 와서 감시 주 목록을 알게 된 뒤에야 받기
                // 시작하면 한 번 더 기다리므로, 폴과 같이 미리 받기 시작한다.
                loadUsaElectionFinance();
                const [polls, contract, ratings] = await Promise.all([loadLivePolls(), loadFinanceDisplayContract(), loadUsaElectionRatings()]);
                const entries = await Promise.all(nationalMonitoringStates(polls.board)
                    .map(async (id) => [id, await loadStateFinanceIndex(id)]));
                if (isStale()) return;
                shell = null;
                onRoute?.({ country: iso3, view: 'finance' });
                renderUsaElectionNational(host.roots.country, {
                    country, ...polls, contract, ratings, evidenceOpen, indexes: Object.fromEntries(entries), days: pollWindowDays,
                    onBack, onToggle: () => this.showCountry('USA'),
                    onWindowChange: (days) => { pollWindowDays = days; this.showCountry('USA', { electionMode: true }); },
                    onStateOpen: (stateId, district) => this.showUsaState(stateId, { financeMode: true, district }),
                    // 목록에서 주 위에 잠깐 머물면 그 주의 자료를 미리 데운다.
                    onStatePrefetch: (stateId) => { prefetchStateFinance(stateId); prefetchCongressionalDistricts(stateId); },
                });
                await mapReady;
                if (!isStale()) watchDisplay(polls, seq, () => this.showCountry('USA', { electionMode: true }));
                return;
            }
            // The 의회 screen's 상임위 chips need the policy overview's
            // committee list before the panel is built; only the USA screen
            // reads it, so it is fetched once, lazily, here.
            if (iso3 === 'USA' && !country.us_committees) {
                country.us_committees = await loadUsCommittees();
                applyEopChart(await loadEopChart());
            }
            // 중국 당 주요 직위 골격도 같은 방식이다 -- 화면이 그려지기 전에 한 번만
            // 읽고, 못 읽으면 모듈 내장 골격으로 그린다.
            if (iso3 === 'CHN') applyCnPartyChart(await loadCnPartyChart());
            // Wait for the map's own layers/click handler to actually land
            // before painting the shell -- not just for the committee/EOP
            // fetch above. admin1 geometry is cached after a country's first
            // visit (loadAdmin1 memoizes the promise), so a repeat visit (e.g.
            // USA -> a state -> back to USA) skips the committee fetch too
            // (country.us_committees is already set) and reaches this point
            // almost immediately -- before renderCountryMap's continuation
            // after its own admin1 fetch had a chance to call
            // host.setElectionMap. The shell looked ready, but a click still
            // landed on the previous screen's stale layers/handler until
            // something else forced a redraw ("두번째로 다른 주 클릭할 때 바로
            // 안 되고 더블 클릭하거나 지도 크기가 바뀐 뒤에야 됨", 2026-10-02).
            await mapReady;
            if (isStale()) return;
            onRoute?.({ country: iso3 });
            shell = renderCountryShell(host.roots.country, {
                country, manifest: bundle.manifest, onBack, modal, host,
                onRoute: (patch) => onRoute?.({ country: iso3, ...patch }),
                onElectionMode: () => this.showCountry('USA', { electionMode: true }),
            });
        },
        async showUsaState(stateId, { financeMode = false, district = null } = {}) {
            rememberEvidence();
            stopDisplayRefresh();
            // The state dashboard replaces the right pane wholesale, so any
            // country block still open would be describing the wrong screen.
            modal?.close();
            const usa = bundle.countries.get('USA');
            const state = usa?.ui_ready?.state_drilldown?.states?.find((row) => row.id === stateId);
            if (!usa || !state) return;
            shell = null;
            const seq = ++navSeq;
            const isStale = () => seq !== navSeq;
            const route = { country: 'USA', state: stateId, view: financeMode ? 'finance' : null, district: financeMode ? district : null };
            // 사용자가 지금 고른 선거구. 7일/14일 전환이나 자동 갱신으로 화면을 다시 그려도 이 선택을 잇는다.
            let activeDistrict = district;
            onRoute?.(route);
            let polls = { board: null, health: null };
            const openState = (nextStateId) => this.showUsaState(nextStateId, { financeMode });

            // 1) 누른 즉시 우측 패널부터 바꾼다. 예전에는 금액 → 도형 → 지도를 순서대로 다 기다린
            //    뒤에야 패널이 바뀌어서, 캘리포니아는 6초 가까이 이전 화면 그대로였다.
            const view = renderUsaStateDashboard(host.roots.country, {
                state, country: usa, evidenceOpen, financeMode, loading: financeMode, districtMapReady: undefined,
                windowDays: pollWindowDays,
                openDistrict: financeMode ? district : null,
                onWindowChange: (days) => { pollWindowDays = days; this.showUsaState(stateId, { financeMode: true, district: activeDistrict }); },
                onBackToUsa: () => this.showCountry('USA', { electionMode: usaElectionMode || financeMode }),
                onToggleFinance: () => this.showUsaState(stateId, { financeMode: !financeMode }),
                // Only the map is redrawn, and only its colours: fitView stays
                // off so clicking a district never moves the camera.
                onHighlightDistrict: (next) => {
                    activeDistrict = next;
                    onRoute?.({ ...route, district: next });
                    return renderUsaDistrictMap({ host, stateId, highlightDistrict: next, fitView: false,
                        electionMode: financeMode, pollBoard: polls.board, pollHealth: polls.health, windowDays: pollWindowDays, isStale });
                },
            });

            // 2) 지도에도 "눌렀다"는 표시를 먼저 준다: 선택한 주를 칠하고 클릭도 계속 살려 둔다.
            //    도형이 올 때까지 지도가 먹통이 되지 않고, 그 사이에 다른 주를 눌러도 된다.
            //    카메라는 건드리지 않는다(fitView:false). 이미 그 주의 선거구 지도가 떠 있으면 건너뛴다.
            if (mapShows !== `districts:${stateId}`) {
                renderCountryMap({ host, country: usa, selectedStateId: stateId, electionMode: financeMode,
                    isStale, fitView: false, onStateOpen: openState })
                    .then((drawn) => { if (drawn && !isStale()) mapShows = 'country:USA'; });
            }

            // 3) 자료는 한꺼번에 받기 시작한다. 이전에는 금액이 끝난 뒤에야 도형을 받기 시작했다.
            const pollsPromise = financeMode ? loadLivePolls() : Promise.resolve(polls);
            const financePromise = financeMode
                ? Promise.all([loadStateFinance(stateId), loadFinanceDisplayContract(), loadUsaElectionRatings()]) : null;

            // 패널: 금액·폴·등급이 오면 바로 그린다. 도형을 기다리지 않는다.
            const panelDone = financeMode ? (async () => {
                const [[financeResult, contract, ratings], loaded] = await Promise.all([financePromise, pollsPromise]);
                polls = loaded;
                if (isStale()) return;
                view.setFinance({
                    financeRaces: financeResult?.races ?? null, financeFailed: financeResult?.failed ?? 0,
                    financeContract: contract, ratings, pollBoard: loaded.board, pollHealth: loaded.health,
                    windowDays: pollWindowDays, openDistrict: district,
                });
                watchDisplay(loaded, seq, () => this.showUsaState(stateId, { financeMode: true, district: activeDistrict }));
            })() : Promise.resolve();

            // 지도: 도형이 오면 패널의 하원 구획(어느 선거구가 지도에 있는지)과 부제를 먼저 갱신하고,
            // 그다음에 지도를 그린다 -- 지도를 그리는 일(deck.gl 의 도형 분할)이 무거워서, 패널 갱신이
            // 그 뒤로 밀리지 않게 한다.
            const mapDone = (async () => {
                // 일시적 끊김은 한 번 더 시도한다. 그래도 안 되면 실패로 보고하고 지도는 그리지 않는다 --
                // 실패는 캐시되지 않으므로 나갔다 다시 들어오면 새로 받는다.
                let geo;
                for (let attempt = 0; attempt < 2 && geo === undefined; attempt += 1) {
                    try {
                        geo = await loadCongressionalDistricts(stateId);
                    } catch (error) {
                        console.warn(`선거구 도형을 불러오지 못했습니다 (${stateId}, ${attempt + 1}/2):`, error?.message || error);
                        if (attempt === 0) await new Promise((resolve) => setTimeout(resolve, 700));
                        if (isStale()) return;
                    }
                }                               // geo === undefined: 받다가 실패 -- "도형이 없다"(null)와 다르다
                if (isStale()) return;
                const mapped = geo === undefined ? MAPPING_FAILED
                    : geo ? new Set((geo.features || []).map((feature) => String(feature.properties?.district ?? ''))) : null;
                view.setMapped({ mappedDistricts: mapped, districtMapReady: geo === undefined ? 'failed' : Boolean(geo) });
                const loaded = await pollsPromise;
                polls = loaded;
                if (isStale()) return;
                if (geo === undefined) return;   // 못 받았다: 지도는 선택한 주가 칠해진 미국 지도 그대로
                // `isStale` 를 넘겨서, 도형이 늦게 오는 사이 사용자가 나갔다면 지도를 건드리지 않는다.
                const drawn = await renderUsaDistrictMap({ host, stateId, highlightDistrict: financeMode ? activeDistrict : null,
                    electionMode: financeMode, pollBoard: loaded.board, pollHealth: loaded.health, windowDays: pollWindowDays, isStale, geo });
                if (drawn) mapShows = `districts:${stateId}`;
            })();

            await Promise.all([panelDone, mapDone].map((job) => job.catch((error) => {
                console.warn('주 화면을 그리는 중 오류:', error?.message || error);
            })));
        },
    };
};
