// 수출통제 모니터 (원자재 › 모니터링) and the export-control catalogue reader.
//
// The catalogue is not one document. public/data/export_controls/manifest.json
// names one module file per category (agri.json, energy.json, minerals.json);
// a new group -- precious metals, say -- is a new file plus a manifest line.
// A module that fails to load is reported on screen and the rest still draw.
//
// Curated, not live. Trade policy changes faster than a hand-maintained file,
// so every row carries a source, a start date and a confidence, and the screen
// shows the manifest's as_of rather than implying it is current. A country with
// no row has not been read yet -- it is not a clean bill of health.
//
// Everything this file needs from app.js comes through the host object passed
// to mount() (see exportControlsHost in app.js), the same way js/elections/
// is wired, so the monitor does not reach into app.js internals. The trade
// maps (trade.js) read controlsFor / renderTradeLegend / FILL / LINE from
// window.ExportControls.
(() => {
    const DIR = '/public/data/export_controls';

    let doc = null;
    let promise = null;

    const fetchJson = (path) => fetch(`${DIR}/${path}`, { cache: 'no-cache' })
        .then((r) => {
            if (!r.ok) throw new Error(`${path} ${r.status}`);
            return r.json();
        });

    /** Manifest + every module, merged into one flat `controls` list. */
    const load = () => {
        if (promise) return promise;
        promise = fetchJson('manifest.json')
            .then((manifest) => Promise.all((manifest.modules || []).map((m) => fetchJson(m.file)
                .then((body) => ({ ...m, controls: body.controls || [] }))
                .catch((err) => {
                    console.error('[ExportControls] module failed', m.file, err);
                    return { ...m, controls: [], error: true };
                })))
                .then((modules) => {
                    doc = {
                        ...manifest,
                        modules,
                        categories: Object.fromEntries(modules.map((m) => [m.category, m.label_ko || m.category])),
                        controls: modules.flatMap((m) => m.controls),
                    };
                    return doc;
                }))
            .catch((err) => {
                console.error('[ExportControls] manifest failed', err);
                return null;
            });
        return promise;
    };

    // --- Regulator notices (the 「최근 공고」 tab) -------------------------------
    //
    // A second, live list next to the curated catalogue: what export-control
    // regulators published recently -- US OFAC and BIS, China's MOFCOM export
    // control bureau. It is the commodity-reports pipeline's
    // boards.export_controls (scripts/commodity_reports/README.md, "수출통제
    // 보드"), newest first, at most 200.
    //
    // Read from the published snapshot, not /api/commodity-reports?board=...:
    // that endpoint slices this same file 100 at a time and drops its
    // country_names table, and this tab needs the whole board (for the map
    // counts and filters) plus Korean names for the targeted countries. The
    // API stays the path for the trade map's per-country box (trade.js).
    // A snapshot built before the board existed has no boards.export_controls;
    // the tab then says the feed is not collected yet instead of "none".
    const NOTICES_URL = '/public/data/commodity_reports_v1.json';
    let notices = null;
    let noticesPromise = null;

    const loadNotices = () => {
        if (noticesPromise) return noticesPromise;
        noticesPromise = fetch(NOTICES_URL, { cache: 'no-cache' })
            .then((r) => {
                if (!r.ok) throw new Error(`commodity_reports ${r.status}`);
                return r.json();
            })
            .then((d) => {
                const ids = d?.boards?.export_controls;
                const byId = new Map((d?.items || []).map((it) => [it.id, it]));
                const names = {};
                for (const [iso, n] of Object.entries(d?.country_names || {})) {
                    if (n?.name_ko) names[iso] = n.name_ko;
                }
                notices = {
                    status: Array.isArray(ids) ? 'ok' : 'none',
                    generated_at: d?.generated_at || null,
                    names,
                    items: (ids || []).map((id) => byId.get(id)).filter((it) => it && it.control),
                };
                return notices;
            })
            .catch((err) => {
                console.error('[ExportControls] notices failed', err);
                notices = { status: 'error', items: [], names: {} };
                return notices;
            });
        return noticesPromise;
    };

    // control.measure (pipeline gemini.MEASURES), same words as trade.js's box.
    const NOTICE_MEASURE_KO = {
        entity_list: '통제명단', export_restriction: '수출통제', export_ban: '수출금지',
        sanctions: '제재', countermeasure: '반제재', list_adjustment: '목록조정',
        suspension: '유예·해제', enforcement: '단속', dialogue: '대화·협의', guidance: '안내',
        other: '기타',
    };

    // A measure whose `until` date has passed is shown as "기한 경과", not as
    // the live ban it was: the file says it ended, and only a reading of the
    // source can say it was extended (India's sugar ban ran to 2026-09-30).
    // It ranks between a live watch and a lift.
    const TODAY = new Date().toISOString().slice(0, 10);
    const statusOf = (c) => (c.level !== 'lifted' && c.until && c.until < TODAY ? 'expired' : c.level);
    const rank = (level) => (level === 'expired' ? 0.5 : doc?.levels?.[level]?.rank ?? 0);
    const levelLabel = (level) => (level === 'expired'
        ? '기한 경과 (연장 여부 재확인 필요)' : doc?.levels?.[level]?.label_ko || level);
    const LEVEL_SHORT_KO = { prohibited: '금지', restricted: '제한', watch: '검토', expired: '기한 경과', lifted: '최근 해제' };
    const LEVEL_ORDER = ['prohibited', 'restricted', 'watch', 'expired', 'lifted'];

    // Korean names for the commodity slugs the catalogue uses. A slug missing
    // here still shows, in English, rather than being dropped.
    const COMMODITY_KO = {
        wheat: '밀', corn: '옥수수', barley: '보리', soybeans: '대두', sugar: '설탕', rice: '쌀',
        palm_oil: '팜유', cocoa: '코코아', rapeseed: '유채', sunflower_oil: '해바라기유',
        sunflower_seed: '해바라기씨', sunflower: '해바라기', fertilizer: '비료', urea: '요소',
        phosphate: '인산비료', coffee: '커피', rubber: '천연고무', cotton: '면화', beef: '쇠고기', fruit: '과일',
        oil: '원유', crude: '원유', gas: '천연가스', lng: 'LNG', coal: '석탄', thermal_coal: '연료탄',
        met_coal: '원료탄', petroleum_products: '석유제품', uranium: '우라늄',
        gold: '금', silver: '은', platinum: '백금', palladium: '팔라듐', diamonds: '다이아몬드',
        nickel: '니켈', bauxite: '보크사이트', aluminum: '알루미늄', copper: '구리', zinc: '아연',
        gallium: '갈륨', germanium: '게르마늄', graphite: '흑연', rare_earths: '희토류',
        cobalt: '코발트', lithium: '리튬', ferroalloys: '합금철', tin: '주석', manganese: '망간',
        chromium: '크롬', iron_ore: '철광석',
    };
    const commoditiesKo = (c) => (c.commodities || []).map((x) => COMMODITY_KO[x] || x)
        .filter((v, i, a) => a.indexOf(v) === i).join('·');

    // --- Trade maps (trade.js) ------------------------------------------------

    // A dashboard commodity maps to the terms the catalogue uses. Bauxite sits
    // under aluminium because that is the map the user is looking at when the
    // ore ban matters to them.
    const ALIASES = {
        aluminum: ['aluminum', 'bauxite'],
        copper: ['copper'],
        zinc: ['zinc'],
        gold: ['gold'],
        silver: ['silver'],
        platinum: ['platinum', 'palladium'],
        // Not petroleum_products: Russia's fuel ban is not a crude ban, and
        // this is the 원유 map. Fuels show in the monitor only.
        oil: ['oil', 'crude'],
        gas: ['gas', 'lng'],
        // The 경질유 map is HS 271012 -- naphtha and motor gasoline -- so
        // Russia's gasoline export ban (petroleum_products) belongs on it.
        light_oils: ['naphtha', 'gasoline', 'petroleum_products'],
        thermal_coal: ['coal', 'thermal_coal'],
        met_coal: ['coal', 'met_coal'],
        wheat: ['wheat'],
        corn: ['corn'],
        soybeans: ['soybeans', 'soy'],
        sugar: ['sugar'],
        coffee: ['coffee'],
        palm_oil: ['palm_oil', 'palm'],
        rubber: ['rubber'],
    };

    /** Live controls affecting `commodity`, keyed by resolved country name. */
    const controlsFor = (commodity) => {
        const out = new Map();
        const terms = ALIASES[commodity] || [commodity];
        for (const c of doc?.controls || []) {
            // "최근 해제" is listed for context, never painted as a live control.
            if (statusOf(c) === 'lifted' || statusOf(c) === 'expired') continue;
            if (!(c.commodities || []).some((x) => terms.includes(x))) continue;
            const key = window.ResolveCountry?.(c.country)?.key || c.country;
            const r = rank(c.level);
            const prev = out.get(key);
            // Several measures on one commodity: show the strongest.
            if (!prev || r > prev.rank) out.set(key, { ...c, rank: r });
        }
        return out;
    };

    /**
     * Legend for the controls on a trade map. Naming the countries makes the
     * colour readable without hovering; as_of keeps a hand-maintained file from
     * reading as a live feed.
     */
    const renderTradeLegend = (controls) => {
        const host = document.getElementById('trade-overlay');
        if (!host) return;
        host.querySelector('.to-controls-legend')?.remove();
        if (!controls || controls.size === 0) return;
        const byLevel = new Map();
        for (const [country, c] of controls) {
            if (!byLevel.has(c.level)) byLevel.set(c.level, []);
            byLevel.get(c.level).push(window.ResolveCountry?.(country)?.iso || country);
        }
        const rows = ['prohibited', 'restricted', 'watch'].filter((l) => byLevel.has(l)).map((l) => `
            <div class="to-scale-row">
                <i class="ctl ctl-${l}"></i>${levelLabel(l)}
                <span class="ctl-iso">${byLevel.get(l).join(' · ')}</span>
            </div>`).join('');
        const el = document.createElement('div');
        el.className = 'to-controls-legend';
        el.innerHTML = `<span class="to-label">수출 통제</span>${rows}
            <div class="to-hint ctl-asof">${doc?.as_of || ''} 기준 · 수기 정리본 · 수출통제 모니터에서 상세</div>`;
        host.insertBefore(el, host.querySelector('.to-hint'));
    };

    const FILL = {
        prohibited: [248, 113, 113, 70],
        restricted: [251, 146, 60, 62],
        watch: [250, 204, 21, 48],
    };
    const LINE = {
        prohibited: [252, 165, 165, 190],
        restricted: [253, 186, 116, 175],
        watch: [253, 224, 71, 160],
    };

    // --- Monitor --------------------------------------------------------------

    // The monitor's own map is a touch stronger than the trade-map overlay:
    // here the fill is the whole message, not a layer under flow lines.
    const MAP_FILL = {
        prohibited: [248, 113, 113, 120],
        restricted: [251, 146, 60, 105],
        watch: [250, 204, 21, 90],
        expired: [148, 163, 184, 80],
        lifted: [148, 163, 184, 55],
    };
    const MAP_LINE = {
        prohibited: [252, 165, 165, 210],
        restricted: [253, 186, 116, 200],
        watch: [253, 224, 71, 190],
        expired: [251, 191, 36, 170],
        lifted: [148, 163, 184, 120],
    };
    const MEASURE_FALLBACK_KO = {
        ban: '수출 금지', quota: '쿼터', duty: '수출세', licensing: '허가제',
        state_trading: '국영 단일창구', levy: '부담금', min_price: '최저수출가',
    };
    const measureLabel = (t) => doc?.measure_types?.[t] || MEASURE_FALLBACK_KO[t] || t || '';

    // --- US tariffs (트럼프 2기) -------------------------------------------------
    //
    // The one exception to "export controls": the US is shown with its tariff
    // and trade policy, because for this dashboard's readers the US's import
    // side moves markets the way other countries' export bans do. A separate
    // hand-curated file (public/data/trade_policy/us_tariffs_v1.json), not a
    // catalogue module: it has its own shape (measures with a status and how
    // they ended, plus per-partner current rates).
    const US_TARIFFS_URL = '/public/data/trade_policy/us_tariffs_v1.json';
    let usTariffs = null;
    let usTariffsPromise = null;
    const loadUsTariffs = () => {
        if (usTariffsPromise) return usTariffsPromise;
        usTariffsPromise = fetch(US_TARIFFS_URL, { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { usTariffs = d; return d; })
            .catch(() => null);
        return usTariffsPromise;
    };
    const TARIFF_STATUS_KO = {
        active: '시행 중', expired: '만료', struck_down: '위법 판결로 무효', ended: '종료', truce: '휴전',
    };

    const ui = {
        host: null,
        tab: 'measures', // 'measures' (curated catalogue) | 'notices' (regulator feed)
        category: 'all',
        usView: 'tariffs', // USA panel: 'tariffs' (관세정책) | 'controls' (일반 수출통제)
        by: 'country', // 현행 조치 grouping: 'country' | 'commodity'
        commodity: null,
        noticeScope: 'controls', // 'controls' | 'all' (adds sanctions/enforcement)
        issuer: 'all',
        noticeMeasure: 'all',
        shown: 0,
        iso: null,
        panel: null,
        legend: null,
    };
    const NOTICE_PAGE = 40;
    const NOTICE_IN_COUNTRY = 12;

    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (ch) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '');

    const visibleControls = () => (doc?.controls || [])
        .filter((c) => ui.category === 'all' || c.category === ui.category);

    /** ISO3 -> rows, for the current category filter. */
    const byIso = () => {
        const out = new Map();
        for (const c of visibleControls()) {
            if (!c.iso) continue;
            if (!out.has(c.iso)) out.set(c.iso, []);
            out.get(c.iso).push(c);
        }
        for (const list of out.values()) list.sort((a, b) => rank(statusOf(b)) - rank(statusOf(a)));
        return out;
    };
    // Strongest level a country carries; lifted only when nothing live remains.
    const topLevel = (list) => (list && list.length ? statusOf(list[0]) : null);

    /** commodity slug -> rows, for the current category filter. */
    const byCommodity = () => {
        const out = new Map();
        for (const c of visibleControls()) {
            for (const slug of new Set(c.commodities || [])) {
                if (!out.has(slug)) out.set(slug, []);
                out.get(slug).push(c);
            }
        }
        for (const list of out.values()) list.sort((a, b) => rank(statusOf(b)) - rank(statusOf(a)));
        return out;
    };
    const commodityKo = (slug) => COMMODITY_KO[slug] || slug;

    // ISO 3166-1 alpha-3 -> alpha-2, five letters per country (ABWAW = ABW, AW),
    // generated once from pycountry. Only so the browser's Intl.DisplayNames can
    // name in Korean the countries a notice targets (Belarus, Cuba, ...) that
    // neither data file names -- no country names are kept here.
    const ISO3_TO_2 = (() => {
        const s = ''
        + 'ABWAWAFGAFAGOAOAIAAIALAAXALBALANDADAREAEARGARARMAMASMASATAAQATFTFATGAGAUSAUAUTATAZEAZBDIBIBELBEBENBJ'
        + 'BESBQBFABFBGDBDBGRBGBHRBHBHSBSBIHBABLMBLBLRBYBLZBZBMUBMBOLBOBRABRBRBBBBRNBNBTNBTBVTBVBWABWCAFCFCANCA'
        + 'CCKCCCHECHCHLCLCHNCNCIVCICMRCMCODCDCOGCGCOKCKCOLCOCOMKMCPVCVCRICRCUBCUCUWCWCXRCXCYMKYCYPCYCZECZDEUDE'
        + 'DJIDJDMADMDNKDKDOMDODZADZECUECEGYEGERIERESHEHESPESESTEEETHETFINFIFJIFJFLKFKFRAFRFROFOFSMFMGABGAGBRGB'
        + 'GEOGEGGYGGGHAGHGIBGIGINGNGLPGPGMBGMGNBGWGNQGQGRCGRGRDGDGRLGLGTMGTGUFGFGUMGUGUYGYHKGHKHMDHMHNDHNHRVHR'
        + 'HTIHTHUNHUIDNIDIMNIMINDINIOTIOIRLIEIRNIRIRQIQISLISISRILITAITJAMJMJEYJEJORJOJPNJPKAZKZKENKEKGZKGKHMKH'
        + 'KIRKIKNAKNKORKRKWTKWLAOLALBNLBLBRLRLBYLYLCALCLIELILKALKLSOLSLTULTLUXLULVALVMACMOMAFMFMARMAMCOMCMDAMD'
        + 'MDGMGMDVMVMEXMXMHLMHMKDMKMLIMLMLTMTMMRMMMNEMEMNGMNMNPMPMOZMZMRTMRMSRMSMTQMQMUSMUMWIMWMYSMYMYTYTNAMNA'
        + 'NCLNCNERNENFKNFNGANGNICNINIUNUNLDNLNORNONPLNPNRUNRNZLNZOMNOMPAKPKPANPAPCNPNPERPEPHLPHPLWPWPNGPGPOLPL'
        + 'PRIPRPRKKPPRTPTPRYPYPSEPSPYFPFQATQAREUREROURORUSRURWARWSAUSASDNSDSENSNSGPSGSGSGSSHNSHSJMSJSLBSBSLESL'
        + 'SLVSVSMRSMSOMSOSPMPMSRBRSSSDSSSTPSTSURSRSVKSKSVNSISWESESWZSZSXMSXSYCSCSYRSYTCATCTCDTDTGOTGTHATHTJKTJ'
        + 'TKLTKTKMTMTLSTLTONTOTTOTTTUNTNTURTRTUVTVTWNTWTZATZUGAUGUKRUAUMIUMURYUYUSAUSUZBUZVATVAVCTVCVENVEVGBVG'
        + 'VIRVIVNMVNVUTVUWLFWFWSMWSYEMYEZAFZAZMBZMZWEZW';
        const out = {};
        for (let i = 0; i + 5 <= s.length; i += 5) out[s.slice(i, i + 3)] = s.slice(i + 3, i + 5);
        return out;
    })();
    let koRegion = null;
    try { koRegion = new Intl.DisplayNames(['ko'], { type: 'region' }); } catch (_) { /* old browser */ }

    // Korean name for an ISO3: the catalogue's country_ko, then the reports
    // pipeline's country_names, then the browser's own Korean region name,
    // then the map's English label.
    const nameOf = (iso) => {
        if (!iso) return '';
        if (iso === 'EU') return 'EU';
        const row = (doc?.controls || []).find((c) => c.iso === iso && c.country_ko);
        let intl = '';
        try { intl = ISO3_TO_2[iso] && koRegion ? koRegion.of(ISO3_TO_2[iso]) : ''; } catch (_) { intl = ''; }
        return row?.country_ko || notices?.names?.[iso] || intl || ui.host?.isoLabel(iso) || iso;
    };
    const countryName = (iso, list) => {
        const row = list?.[0];
        return row?.country_ko || nameOf(iso) || (row && ui.host?.countryLabel(row.country)) || iso;
    };

    const periodText = (c) => {
        if (c.level === 'lifted') return `${c.since || ''} ~ ${c.lifted_at || ''} 해제`;
        if (statusOf(c) === 'expired') return `${c.since || ''} ~ ${c.until} · 기한 지남`;
        return `${c.since || ''} ~${c.until ? ` ${c.until}` : ' 현재'}`;
    };

    // withCountry: the per-commodity view lists several countries' measures,
    // so each row names its country instead of its commodities.
    const measureHtml = (c, withCountry = false) => {
        const url = safeUrl(c.url);
        const st = statusOf(c);
        return `<li class="ec-item ec-${esc(st)}">
            <div class="ec-top">
                <b>${esc(withCountry ? `${countryName(c.iso, [c])} · ${commoditiesKo(c)}` : commoditiesKo(c))}</b>
                <span class="ec-lv ctl-${esc(st)}">${esc([LEVEL_SHORT_KO[st] || st, measureLabel(c.measure_type)].filter(Boolean).join(' · '))}</span>
            </div>
            <div class="ec-measure">${esc(c.measure_ko)}</div>
            <div class="ec-meta">
                <span>${esc(doc?.categories?.[c.category] || c.category)}</span>
                <span>${esc(periodText(c))}</span>
                ${(c.hs_prefixes || []).length ? `<span>HS ${esc(c.hs_prefixes.join(', '))}</span>` : ''}
            </div>
            <div class="ec-src">
                ${esc(c.source)}${url ? ` <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">원문 ↗</a>` : ''}
                ${c.basis === 'reported' ? '· <span class="ec-recheck">보도 기반 · 공식 고시 없음</span> ' : ''}${c.basis === 'official' ? '· 정부 원문 ' : ''}· 신뢰도 ${esc(c.confidence || '—')}${c.verified_at ? ` · 확인 ${esc(c.verified_at)}` : ''}
                ${c.needs_reconfirm ? ' · <span class="ec-recheck">재확인 필요</span>' : ''}
            </div>
        </li>`;
    };

    // --- Notices ----------------------------------------------------------------

    // Notices are screened to export controls by default. OFAC's sanctions
    // and enforcement notices are mostly designations of people and firms --
    // not what this monitor is for -- so they sit behind a toggle.
    const CONTROL_NOTICE_MEASURES = new Set([
        'export_ban', 'export_restriction', 'entity_list', 'list_adjustment', 'countermeasure', 'suspension',
    ]);
    const inScope = (it) => ui.noticeScope === 'all' || CONTROL_NOTICE_MEASURES.has(it.control.measure);
    const noticeItems = () => (notices?.items || []).filter(inScope);
    const visibleNotices = () => noticeItems().filter((it) => (
        (ui.issuer === 'all' || it.control.issuer === ui.issuer)
        && (ui.noticeMeasure === 'all' || (it.control.measure || 'other') === ui.noticeMeasure)));
    const noticeDate = (it) => String(it.published_at || '').slice(0, 10);

    /** ISO3 -> { issued, targeted } counts over the filtered notices. */
    const noticeCounts = () => {
        const out = new Map();
        const bump = (iso, k) => {
            if (!out.has(iso)) out.set(iso, { issued: 0, targeted: 0 });
            out.get(iso)[k] += 1;
        };
        for (const it of visibleNotices()) {
            if (it.control.issuer) bump(it.control.issuer, 'issued');
            for (const t of it.control.targets || []) bump(t, 'targeted');
        }
        return out;
    };

    const noticeHtml = (it) => {
        const c = it.control;
        const url = safeUrl(it.url);
        const agencyUrl = safeUrl(it.agency_url);
        const body = c.issuer_body_ko || it.agency_ko || c.issuer_body || '';
        const ko = it.title?.ko || '';
        const orig = it.title?.original || '';
        const lang = it.title?.original_lang || '';
        const head = ko || orig;
        // The original stays visible under a translation: the measure is in the
        // original, and the Korean is a model's reading of one line.
        const showOrig = ko && orig && orig !== ko;
        const measure = c.measure ? (NOTICE_MEASURE_KO[c.measure] || c.measure) : '';
        const targets = (c.targets || []).map(nameOf).join(' · ');
        const items = (c.items || []).map((x) => COMMODITY_KO[x] || x).join(' · ');
        return `<li class="ec-notice">
            <div class="ec-n-meta">
                <span class="ec-n-date">${esc(noticeDate(it))}</span>
                ${agencyUrl
                    ? `<a class="ec-n-body" href="${esc(agencyUrl)}" target="_blank" rel="noopener noreferrer" title="발표 기관 사이트">${esc(body)}</a>`
                    : `<span class="ec-n-body">${esc(body)}</span>`}
                ${measure ? `<span class="ec-n-measure m-${esc(c.measure)}">${esc(measure)}</span>` : ''}
            </div>
            ${url
                ? `<a class="ec-n-title" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(head)} <span class="ec-n-go">원문 ↗</span></a>`
                : `<span class="ec-n-title">${esc(head)}</span>`}
            ${showOrig ? `<div class="ec-n-orig" lang="${esc(lang)}">${esc(orig)}</div>` : ''}
            ${targets || items ? `<div class="ec-n-tags">
                ${targets ? `<span>대상 ${esc(targets)}</span>` : ''}
                ${items ? `<span>품목 ${esc(items)}</span>` : ''}
            </div>` : ''}
        </li>`;
    };

    const scopeToggleHtml = () => {
        const hidden = (notices?.items || []).filter((it) => !CONTROL_NOTICE_MEASURES.has(it.control.measure)).length;
        if (!hidden) return '';
        const on = ui.noticeScope === 'all';
        return `<label class="ec-scope"><input type="checkbox" data-ec-scope ${on ? 'checked' : ''}>
            제재·단속·협의 공고도 보기 <span>${hidden}건 · 대부분 개인·기업 지정</span></label>`;
    };

    const noticeStatusHtml = () => {
        if (!notices || notices.status === 'error') return '<p class="ec-warn">공고 목록을 불러오지 못했습니다.</p>';
        if (notices.status === 'none') {
            return `<p class="ec-empty">규제 기관 공고 수집이 아직 이 데이터에 들어오지 않았습니다.<br>
                (보고서 파이프라인의 수출통제 보드가 배포되면 여기에 표시됩니다.)</p>`;
        }
        return '';
    };

    // The agencies named are whichever the board actually carries, so a new
    // regulator in sources.json shows up here without a UI change.
    const noticeFootHtml = () => {
        const bodies = [...new Set((notices?.items || [])
            .map((it) => it.control.issuer_body_ko || it.agency_ko || it.control.issuer_body).filter(Boolean))];
        return `<p class="ec-foot">
        ${esc(bodies.join(' · ') || '규제 기관')} 공고, 최신순 최대 200건 ·
        갱신 ${esc(String(notices?.generated_at || '').slice(0, 10) || '—')}.
        한글 제목과 조치 종류·대상국은 제목 한 줄을 Gemini가 읽은 값입니다 — 판단은 원문으로.
        EU·일본 METI는 아직 연결 전.</p>`;
    };

    const renderNoticesPanel = () => {
        const status = noticeStatusHtml();
        if (status) {
            ui.panel.innerHTML = `${tabsHtml()}${status}${noticeFootHtml()}`;
            return;
        }
        const all = noticeItems();
        const issuers = [...new Set(all.map((it) => it.control.issuer).filter(Boolean))];
        const count = (pred) => all.filter(pred).length;
        const issuerChips = ['all', ...issuers].map((iso) => {
            const on = ui.issuer === iso;
            const n = iso === 'all' ? all.length : count((it) => it.control.issuer === iso);
            return `<button type="button" class="ec-filter${on ? ' is-on' : ''}" data-ec-issuer="${esc(iso)}" aria-pressed="${on}">
                ${esc(iso === 'all' ? '전체' : nameOf(iso))} <span>${n}</span></button>`;
        }).join('');
        const scoped = all.filter((it) => ui.issuer === 'all' || it.control.issuer === ui.issuer);
        const measures = [...new Set(scoped.map((it) => it.control.measure || 'other'))]
            .sort((a, b) => scoped.filter((it) => (it.control.measure || 'other') === b).length
                - scoped.filter((it) => (it.control.measure || 'other') === a).length);
        const measureChips = ['all', ...measures].map((m) => {
            const on = ui.noticeMeasure === m;
            const n = m === 'all' ? scoped.length : scoped.filter((it) => (it.control.measure || 'other') === m).length;
            return `<button type="button" class="ec-filter ec-filter-sm${on ? ' is-on' : ''}" data-ec-nmeasure="${esc(m)}" aria-pressed="${on}">
                ${esc(m === 'all' ? '모든 조치' : (NOTICE_MEASURE_KO[m] || m))} <span>${n}</span></button>`;
        }).join('');
        const list = visibleNotices();
        const shown = list.slice(0, ui.shown || NOTICE_PAGE);
        const more = list.length - shown.length;
        ui.panel.innerHTML = `
            ${tabsHtml()}
            <div class="ec-filters" role="group" aria-label="발표국">${issuerChips}</div>
            <div class="ec-filters" role="group" aria-label="조치 종류">${measureChips}</div>
            ${scopeToggleHtml()}
            ${shown.length ? `<ul class="ec-notices">${shown.map(noticeHtml).join('')}</ul>`
                : '<p class="ec-empty">조건에 맞는 공고가 없습니다.</p>'}
            ${more > 0 ? `<button type="button" class="ec-more" data-ec-more>공고 ${Math.min(more, NOTICE_PAGE)}건 더 보기 (남은 ${more}건)</button>` : ''}
            ${noticeFootHtml()}`;
    };

    // --- Panels -------------------------------------------------------------------

    const tabsHtml = () => {
        const tab = (key, label, n) => `<button type="button" role="tab" class="ec-tab${ui.tab === key ? ' is-on' : ''}"
            data-ec-tab="${key}" aria-selected="${ui.tab === key}">${label}${n != null ? ` <span>${n}</span>` : ''}</button>`;
        const nn = notices?.status === 'ok' ? noticeItems().length : null;
        return `<div class="ec-tabs" role="tablist">
            ${tab('measures', '현행 조치', (doc?.controls || []).length)}
            ${tab('notices', '최근 공고', nn)}
        </div>`;
    };

    const filterHtml = () => {
        const all = doc?.controls || [];
        const chips = [{ category: 'all', label_ko: '전체' }, ...(doc?.modules || [])].map((m) => {
            const n = m.category === 'all' ? all.length : all.filter((c) => c.category === m.category).length;
            const on = ui.category === m.category;
            return `<button type="button" class="ec-filter${on ? ' is-on' : ''}" data-ec-category="${esc(m.category)}"
                aria-pressed="${on}">${esc(m.label_ko)}${m.error ? ' ⚠' : ''} <span>${n}</span></button>`;
        }).join('');
        return `<div class="ec-filters" role="group" aria-label="분류">${chips}</div>`;
    };

    const footerHtml = () => {
        const failed = (doc?.modules || []).filter((m) => m.error);
        return `${failed.length ? `<p class="ec-warn">불러오지 못한 분류: ${esc(failed.map((m) => m.label_ko).join(', '))}</p>` : ''}
            <p class="ec-foot">${esc(doc?.as_of || '')} 기준 수기 정리본 · 원문을 확인한 조치만 싣는다.
            목록에 없는 나라는 아직 확인하지 않은 것이지, 통제가 없다는 뜻이 아니다.</p>`;
    };

    const byToggleHtml = () => {
        const b = (key, label) => `<button type="button" class="ec-by${ui.by === key ? ' is-on' : ''}" data-ec-by="${key}"
            aria-pressed="${ui.by === key}">${label}</button>`;
        return `<div class="ec-bys" role="group" aria-label="묶어 보기">${b('country', '국가별')}${b('commodity', '품목별')}</div>`;
    };

    const levelKeyHtml = () => `<div class="ec-levelkey">
        <span><i class="ctl-prohibited"></i>금지 — 수출 자체를 막음</span>
        <span><i class="ctl-restricted"></i>제한 — 쿼터·허가·수출세·국영 창구</span>
        <span><i class="ctl-watch"></i>검토 — 통제 논의·경고 단계</span>
        <span><i class="ctl-expired"></i>기한 경과 — 연장 여부 재확인 필요</span>
    </div>`;

    const statusChip = (c, label) => `<span class="ec-chip ctl-${esc(statusOf(c))}">${esc(label)} · ${esc(LEVEL_SHORT_KO[statusOf(c)] || statusOf(c))}</span>`;

    const renderWorldPanel = () => {
        let rows;
        if (ui.by === 'commodity') {
            const groups = [...byCommodity().entries()]
                .sort(([, a], [, b]) => rank(statusOf(b[0])) - rank(statusOf(a[0])) || b.length - a.length);
            rows = groups.map(([slug, list]) => `<button type="button" class="ec-country" data-ec-commodity="${esc(slug)}">
                <span class="ec-name">${esc(commodityKo(slug))}</span>
                <span class="ec-chips">${list.map((c) => statusChip(c, countryName(c.iso, [c]))).join('')}</span>
            </button>`).join('');
        } else {
            const groups = [...byIso().entries()]
                .sort(([, a], [, b]) => rank(statusOf(b[0])) - rank(statusOf(a[0])) || b.length - a.length);
            rows = groups.map(([iso, list]) => `<button type="button" class="ec-country" data-ec-iso="${esc(iso)}">
                <span class="ec-name">${esc(countryName(iso, list))}<span class="ec-iso">${esc(iso)}</span></span>
                <span class="ec-chips">${list.map((c) => statusChip(c, commoditiesKo(c))).join('')}</span>
            </button>`).join('');
        }
        ui.panel.innerHTML = `
            ${tabsHtml()}
            <button type="button" class="ust-entry" data-ec-iso="USA">
                <b>미국 관세·통상 정책</b><span>트럼프 2기 · 232조·301조 · 한·일·대만·중·독 세율</span></button>
            ${byToggleHtml()}
            ${filterHtml()}
            ${levelKeyHtml()}
            <div class="ec-list">${rows || '<p class="ec-empty">이 분류에 정리된 조치가 없습니다.</p>'}</div>
            ${footerHtml()}`;
    };

    const renderCommodityPanel = (slug) => {
        // Every country's measure on one commodity, strongest first, whatever
        // the category filter.
        const list = (doc?.controls || []).filter((c) => (c.commodities || []).includes(slug))
            .sort((a, b) => rank(statusOf(b)) - rank(statusOf(a)));
        const top = list.length ? statusOf(list[0]) : null;
        ui.panel.innerHTML = `
            <button type="button" class="ec-back" data-ec-back>← 전체 품목</button>
            <div class="ec-country-head">
                <h3>${esc(commodityKo(slug))} 수출통제</h3>
                ${top ? `<span class="ec-lv ctl-${esc(top)}">최고 단계 · ${esc(LEVEL_SHORT_KO[top] || top)}</span>` : ''}
            </div>
            ${list.length ? `<ul class="ec-items">${list.map((c) => measureHtml(c, true)).join('')}</ul>`
                : '<p class="ec-empty">정리된 조치가 없습니다.</p>'}
            ${levelKeyHtml()}
            ${footerHtml()}`;
    };

    const tariffSources = (list) => (list || []).map((x) => {
        const url = safeUrl(x.url);
        return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(x.label)} ↗</a>` : esc(x.label);
    }).join(' · ');

    const tariffMeasureHtml = (m) => `<li class="ust-item ust-${esc(m.status)}">
        <div class="ust-top">
            <span class="ust-auth">${esc(m.authority === 'IEEPA' ? 'IEEPA' : `${m.authority}조`)}</span>
            <b>${esc(m.name_ko)}</b>
            <span class="ust-status">${esc(TARIFF_STATUS_KO[m.status] || m.status)}</span>
        </div>
        <div class="ust-when">${esc(m.started || '')} ~ ${esc(m.ended || '현재')}</div>
        <div class="ust-rate">${esc(m.rate_ko)}</div>
        ${m.how_ended_ko ? `<div class="ust-ended"><b>어떻게 끝났나</b> ${esc(m.how_ended_ko)}</div>` : ''}
        ${m.scope_ko ? `<div class="ust-scope">${esc(m.scope_ko)}</div>` : ''}
        <div class="ec-src">${tariffSources(m.sources)}</div>
    </li>`;

    const partnerHtml = (iso, p, { link = false } = {}) => `<div class="ust-partner">
        <div class="ust-top">
            ${link ? `<button type="button" class="ust-pname" data-ec-iso="${esc(iso)}">${esc(p.name_ko)} →</button>`
                : `<b>미국이 ${esc(p.name_ko)}에 매기는 관세 (현재)</b>`}
        </div>
        <div class="ust-scope">${esc(p.summary_ko)}</div>
        <table class="ust-table"><tbody>
            ${(p.lines || []).map((l) => `<tr><th>${esc(l.label_ko)}</th><td>${esc(l.rate_ko)}</td>
                <td class="ust-auth-cell">${esc(/^\d/.test(l.authority) ? `${l.authority}조` : l.authority)}</td></tr>`).join('')}
        </tbody></table>
        ${link ? '' : `<div class="ec-src">${tariffSources(p.sources)}</div>`}
    </div>`;

    // The US's own panel: what is in force, how the struck-down and expired
    // layers ended, and the current rate on the main manufacturing partners.
    const usTariffSectionHtml = () => {
        if (!usTariffs) return '<p class="ec-warn">미국 관세 자료를 불러오지 못했습니다.</p>';
        const live = usTariffs.measures.filter((m) => m.status === 'active' || m.status === 'truce');
        const gone = usTariffs.measures.filter((m) => !(m.status === 'active' || m.status === 'truce'));
        const partners = Object.entries(usTariffs.partners || {});
        return `<section class="ust">
            <h4 class="ec-sect">${esc(usTariffs.title_ko)}</h4>
            <p class="ust-lead">미국은 예외로 수출통제 대신 관세·통상 정책을 붙였다. 2026-02-20 대법원이 IEEPA 관세를 무효로 하면서
                지금은 <b>232조(품목별)</b>와 <b>301조(국가별)</b>가 두 축이다.</p>
            <h4 class="ec-cat">주요 제조국에 지금 매기는 관세</h4>
            ${partners.map(([iso, p]) => partnerHtml(iso, p, { link: true })).join('')}
            <h4 class="ec-cat">시행 중인 제도 <span class="ec-cat-n">${live.length}건</span></h4>
            <ul class="ust-list">${live.map(tariffMeasureHtml).join('')}</ul>
            <details class="ust-gone"><summary>끝난 조치 — 어떻게 끝났나 <span class="ec-cat-n">${gone.length}건</span></summary>
                <ul class="ust-list">${gone.map(tariffMeasureHtml).join('')}</ul>
            </details>
            <p class="ec-foot">${esc(usTariffs.as_of)} 기준 · ${esc(usTariffs.note_ko)}</p>
        </section>`;
    };

    // A partner's panel: the US's current rates on it, above its own measures.
    const usPartnerSectionHtml = (iso) => {
        const p = usTariffs?.partners?.[iso];
        if (!p) return '';
        return `<section class="ust">${partnerHtml(iso, p)}
            <button type="button" class="ec-more" data-ec-iso="USA">미국 관세 정책 전체 보기 (트럼프 2기)</button></section>`;
    };

    // The US panel splits in two: its tariff policy, and the export-control
    // notices its regulators (OFAC, BIS) issue -- which otherwise sat below a
    // long tariff section.
    const usToggleHtml = () => {
        const n = noticeItems().filter((it) => it.control.issuer === 'USA').length;
        const b = (key, label) => `<button type="button" class="ec-by${ui.usView === key ? ' is-on' : ''}" data-ec-usview="${key}"
            aria-pressed="${ui.usView === key}">${label}</button>`;
        return `<div class="ec-bys ust-toggle" role="group" aria-label="미국 보기">${b('tariffs', '관세 정책')}${b('controls', `일반 수출통제 <span>${n}</span>`)}</div>`;
    };

    const renderCountryPanel = (iso) => {
        // The detail ignores every filter: a reader who clicked a country
        // wants everything on it -- its standing measures, the notices its
        // regulators issued, and the notices aimed at it.
        const list = (doc?.controls || []).filter((c) => c.iso === iso)
            .sort((a, b) => rank(statusOf(b)) - rank(statusOf(a)));
        const name = countryName(iso, list);
        const sections = (doc?.modules || []).map((m) => {
            const rows = list.filter((c) => c.category === m.category);
            if (!rows.length) return '';
            return `<h4 class="ec-cat">${esc(m.label_ko)}</h4><ul class="ec-items">${rows.map(measureHtml).join('')}</ul>`;
        }).join('');
        const issued = noticeItems().filter((it) => it.control.issuer === iso);
        const aimed = noticeItems().filter((it) => (it.control.targets || []).includes(iso));
        const noticeBlock = (title, rows, allLink) => (rows.length ? `
            <h4 class="ec-cat">${esc(title)} <span class="ec-cat-n">${rows.length}건</span></h4>
            <ul class="ec-notices">${rows.slice(0, NOTICE_IN_COUNTRY).map(noticeHtml).join('')}</ul>
            ${rows.length > NOTICE_IN_COUNTRY && allLink ? `<button type="button" class="ec-more" data-ec-issuer-all="${esc(iso)}">최근 공고 탭에서 ${rows.length}건 모두 보기</button>` : ''}` : '');
        const total = list.length + issued.length + aimed.length;
        ui.panel.innerHTML = `
            <button type="button" class="ec-back" data-ec-back>← 전체 국가</button>
            <div class="ec-country-head">
                <h3>${esc(name)} <span class="ec-iso">${esc(iso)}</span></h3>
                <span class="ec-count">${list.length ? `현행 조치 ${list.length}건` : ''}</span>
            </div>
            ${iso === 'USA' ? usToggleHtml() : ''}
            ${iso === 'USA' && ui.usView === 'tariffs' ? usTariffSectionHtml() : ''}
            ${iso !== 'USA' ? usPartnerSectionHtml(iso) : ''}
            ${iso === 'USA' && ui.usView === 'tariffs' ? '' : `
            ${sections ? `<h4 class="ec-sect">현행 조치 (수기 정리)</h4>${sections}` : ''}
            ${noticeBlock(`${name} 규제 기관이 낸 공고`, issued, true)}
            ${noticeBlock(`${name}을(를) 겨냥한 공고`, aimed, false)}`}
            ${total || (iso === 'USA' && ui.usView === 'tariffs') || usTariffs?.partners?.[iso] ? '' : `<p class="ec-empty">정리된 수출통제 조치도, 최근 공고도 없습니다.<br>
                아직 원문을 확인하지 않은 것일 수 있습니다 — 통제가 없다는 뜻은 아닙니다.</p>`}
            ${footerHtml()}`;
    };

    const renderPanel = () => {
        if (!ui.panel) return;
        if (ui.iso) renderCountryPanel(ui.iso);
        else if (ui.commodity) renderCommodityPanel(ui.commodity);
        else if (ui.tab === 'notices') renderNoticesPanel();
        else renderWorldPanel();
        ui.panel.scrollTop = 0;
    };

    // --- Map ------------------------------------------------------------------------

    // Notices tab: the issuing countries in teal, the countries notices aim
    // at in violet, deeper with more notices.
    const ISSUER_FILL = [45, 212, 191, 95];
    const ISSUER_LINE = [94, 234, 212, 210];
    const targetFill = (n) => [167, 139, 250, Math.min(60 + n * 22, 150)];
    const TARGET_LINE = [196, 181, 253, 190];

    const swatch = (c) => `<span class="swatch" style="background:rgb(${c[0]},${c[1]},${c[2]})"></span>`;

    const renderLegend = () => {
        if (!ui.legend) return;
        if (ui.tab === 'notices' && !ui.iso) {
            const eu = visibleNotices().filter((it) => (it.control.targets || []).includes('EU')).length;
            ui.legend.innerHTML = `<div class="mini-leg-head">최근 수출통제 공고</div>
                <div class="mini-leg-row">${swatch(ISSUER_FILL)}발표국</div>
                <div class="mini-leg-row">${swatch(targetFill(3))}공고가 겨냥한 나라 (진할수록 많음)</div>
                ${eu ? `<div class="mini-leg-note">EU 대상 ${eu}건은 지도 밖</div>` : ''}
                <div class="mini-leg-note">국가 클릭 시 공고·원문</div>`;
        } else {
            const present = new Set([...mapGroups().values()].map(topLevel));
            const rows = LEVEL_ORDER.filter((l) => present.has(l))
                .map((l) => `<div class="mini-leg-row">${swatch(MAP_FILL[l])}${esc(levelLabel(l))}</div>`).join('');
            const head = ui.commodity ? `${commodityKo(ui.commodity)} 수출통제` : '수출 통제 · 국가별 최고 단계';
            ui.legend.innerHTML = `<div class="mini-leg-head">${esc(head)}</div>${rows}
                <div class="mini-leg-note">${esc(doc?.as_of || '')} 기준 · 국가 클릭 시 상세</div>
                <div class="mini-leg-row">${swatch([45, 212, 191])}미국 — 관세·통상 정책</div>`;
        }
        ui.legend.classList.remove('hidden');
    };

    // Measures map: one commodity's countries when a commodity is open,
    // otherwise every country under the category filter.
    const mapGroups = () => {
        if (!ui.commodity) return byIso();
        const out = new Map();
        for (const c of (byCommodity().get(ui.commodity) || [])) {
            if (!out.has(c.iso)) out.set(c.iso, []);
            out.get(c.iso).push(c);
        }
        return out;
    };

    const layers = () => {
        const h = ui.host;
        const noticeMode = ui.tab === 'notices' && !ui.commodity;
        const groups = mapGroups();
        const counts = noticeMode ? noticeCounts() : null;
        const fill = (iso) => {
            if (noticeMode) {
                const c = counts.get(iso);
                if (!c) return [0, 0, 0, 0];
                return c.issued ? ISSUER_FILL : targetFill(c.targeted);
            }
            const lv = topLevel(groups.get(iso));
            if (lv) return MAP_FILL[lv];
            // The US carries tariff policy, not export controls (see usTariffs).
            return iso === 'USA' && usTariffs ? [45, 212, 191, 75] : [0, 0, 0, 0];
        };
        const line = (iso) => {
            if (iso && iso === ui.iso) return [240, 249, 255, 240];
            if (noticeMode) {
                const c = counts.get(iso);
                if (!c) return [0, 0, 0, 0];
                return c.issued ? ISSUER_LINE : TARGET_LINE;
            }
            const lv = topLevel(groups.get(iso));
            return lv ? MAP_LINE[lv] : [0, 0, 0, 0];
        };
        const key = [ui.tab, ui.category, ui.commodity, ui.issuer, ui.noticeMeasure, ui.noticeScope].join('|');
        return [
            ...h.worldBaseLayers({ id: 'export-controls' }),
            new h.GeoJsonLayer({
                id: 'export-controls-countries',
                data: h.worldGeo(),
                stroked: true,
                filled: true,
                pickable: true,
                autoHighlight: true,
                highlightColor: [255, 255, 255, 50],
                lineWidthMinPixels: 1,
                getFillColor: (f) => fill(h.resolveIso3(f)),
                getLineColor: (f) => line(h.resolveIso3(f)),
                getLineWidth: (f) => (h.resolveIso3(f) === ui.iso ? 3 : 1),
                lineWidthUnits: 'pixels',
                updateTriggers: {
                    getFillColor: [key],
                    getLineColor: [key, ui.iso],
                    getLineWidth: [ui.iso],
                },
            }),
        ];
    };

    const redraw = () => {
        renderPanel();
        renderLegend();
        ui.host?.updateLayers(layers());
    };

    const select = (iso) => {
        ui.iso = iso || null;
        redraw();
    };

    const onMapClick = (info) => {
        const iso = info?.object ? ui.host.resolveIso3(info.object) : '';
        select(iso || null);
    };

    const onMapHover = (info) => {
        const h = ui.host;
        if (!info?.object) { h.hideTooltip(); return; }
        const iso = h.resolveIso3(info.object);
        const name = nameOf(iso) || info.object.properties?.name || iso;
        let body;
        if (ui.tab === 'notices') {
            const c = noticeCounts().get(iso);
            body = c
                ? `${c.issued ? `<div class="tooltip-stat"><span>발표한 공고</span><span>${c.issued}건</span></div>` : ''}
                   ${c.targeted ? `<div class="tooltip-stat"><span>겨냥된 공고</span><span>${c.targeted}건</span></div>` : ''}`
                : '<div class="tooltip-stat"><span>최근 공고 없음</span></div>';
        } else {
            const list = mapGroups().get(iso);
            body = list
                ? list.map((c) => `<div class="tooltip-stat"><span>${esc(commoditiesKo(c))}</span>
                    <span class="ec-lv ctl-${esc(statusOf(c))}">${esc(LEVEL_SHORT_KO[statusOf(c)] || statusOf(c))}</span></div>`).join('')
                : '<div class="tooltip-stat"><span>정리된 조치 없음</span></div>';
        }
        h.showTooltip(info, `<div class="tooltip-title">${esc(name)}</div>${body}
            <div style="margin-top:6px;font-size:10px;color:#64748b;">클릭하여 조치·공고·원문 보기</div>`);
    };

    const onPanelClick = (e) => {
        const t = e.target instanceof Element ? e.target : null;
        if (!t) return;
        const attr = (name) => t.closest(`[${name}]`)?.getAttribute(name);
        let v;
        if ((v = attr('data-ec-tab'))) {
            ui.tab = v; ui.iso = null; ui.commodity = null; ui.shown = 0; redraw(); return;
        }
        if ((v = attr('data-ec-usview'))) {
            ui.usView = v; renderPanel(); return;
        }
        if ((v = attr('data-ec-by'))) {
            ui.by = v; ui.iso = null; ui.commodity = null; redraw(); return;
        }
        if ((v = attr('data-ec-commodity'))) {
            ui.commodity = v; ui.iso = null; redraw(); return;
        }
        if (t.matches('[data-ec-scope]')) {
            ui.noticeScope = t.checked ? 'all' : 'controls';
            ui.noticeMeasure = 'all'; ui.shown = 0; redraw(); return;
        }
        if ((v = attr('data-ec-category'))) {
            ui.category = v; ui.iso = null; redraw(); return;
        }
        if ((v = attr('data-ec-issuer'))) {
            ui.issuer = v; ui.noticeMeasure = 'all'; ui.shown = 0; redraw(); return;
        }
        if ((v = attr('data-ec-nmeasure'))) {
            ui.noticeMeasure = v; ui.shown = 0; redraw(); return;
        }
        if ((v = attr('data-ec-issuer-all'))) {
            ui.tab = 'notices'; ui.issuer = v; ui.noticeMeasure = 'all'; ui.shown = 0; ui.iso = null; redraw(); return;
        }
        if (t.closest('[data-ec-more]')) {
            const top = ui.panel.scrollTop;
            ui.shown = (ui.shown || NOTICE_PAGE) + NOTICE_PAGE;
            renderNoticesPanel();
            ui.panel.scrollTop = top;
            return;
        }
        if ((v = attr('data-ec-iso'))) { select(v); return; }
        if (t.closest('[data-ec-back]')) {
            // Back from a country opened inside a commodity returns to it.
            if (ui.iso) select(null);
            else { ui.commodity = null; redraw(); }
        }
    };

    const mount = async (host) => {
        ui.host = host;
        ui.panel = document.getElementById('export-controls-content');
        ui.legend = document.getElementById('export-controls-legend');
        if (ui.panel && !ui.panel.dataset.wired) {
            ui.panel.addEventListener('click', onPanelClick);
            ui.panel.dataset.wired = '1';
        }
        host.setHeader('수출통제 모니터', '현행 조치(수기 정리)와 규제 기관 최근 공고 · 국가를 클릭하면 조치·공고·원문');
        host.setPanels();
        if (ui.panel) ui.panel.innerHTML = '<p class="ec-empty">불러오는 중…<span class="inline-spinner" aria-hidden="true"></span></p>';
        host.setMap([], onMapClick, onMapHover);
        await Promise.all([load(), loadNotices(), loadUsTariffs(), host.loadWorldGeo()]);
        if (!host.isActive()) return;
        if (!doc) {
            if (ui.panel) ui.panel.innerHTML = '<p class="ec-warn">수출통제 목록을 불러오지 못했습니다.</p>';
            return;
        }
        redraw();
    };

    const unmount = () => {
        ui.legend?.classList.add('hidden');
        ui.host?.hideTooltip();
        ui.iso = null;
    };

    window.ExportControls = {
        load,
        loadNotices,
        doc: () => doc,
        levelLabel,
        commoditiesKo,
        controlsFor,
        renderTradeLegend,
        FILL,
        LINE,
        mount,
        unmount,
        select,
    };
})();
