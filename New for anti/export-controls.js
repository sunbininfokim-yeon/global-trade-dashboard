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

    // Independently reviewed country news; never mixed into the export-control feed.
    const ANNOUNCEMENTS_URL = '/public/data/trade_policy/country_announcements_v1.json';
    let announcements = null;
    let announcementsPromise = null;
    const loadAnnouncements = () => {
        if (!announcementsPromise) announcementsPromise = fetch(ANNOUNCEMENTS_URL, { cache: 'no-cache' })
            .then((r) => { if (!r.ok) throw new Error(`country announcements ${r.status}`); return r.json(); })
            .then((d) => { announcements = d; return d; })
            .catch(() => { announcements = { error: true }; return announcements; });
        return announcementsPromise;
    };

    // US sanctions pilot is a separate evidence snapshot, not a country risk score.
    const SANCTIONS_URL = '/public/data/trade_policy/us_sanctions_v1.json';
    let sanctions = null;
    let sanctionsPromise = null;
    const loadSanctions = () => {
        if (!sanctionsPromise) sanctionsPromise = fetch(SANCTIONS_URL, { cache: 'no-cache' })
            .then((r) => { if (!r.ok) throw new Error(`sanctions ${r.status}`); return r.json(); })
            .then((d) => { sanctions = d; return d; })
            .catch(() => { sanctions = { error: true }; return sanctions; });
        return sanctionsPromise;
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
        investigation: '조사 중 · 세율 미확정', review_required: '재확인 필요', scheduled: '시행 예정',
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
        noticePages: {},
        sanctionsViews: {},
        sanctionsPages: {},
        iso: null,
        panel: null,
        legend: null,
    };
    const NOTICE_PAGE = 5;

    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (ch) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '');

    const SANCTION_VIEWS = { banks: '은행·금융', industries: '산업', goods: '물품·예외 허가', companies: '주요 기업' };
    const SANCTION_KINDS = { blocking: 'SDN · 자산동결', sectoral: 'SSI · 특정 금융·부문 제한',
        securities: 'NS-CMIC · 특정 증권투자 제한', bank_account: 'CAPTA · 환거래 계좌 제한',
        export_license: 'Entity List · 수출허가 요건', export_denial: 'DPL · 수출권한 제한',
        verification: 'UVL · 검증 미완료', military_end_use: '군사 최종사용자 통제', menu_based: '지정별 선택적 제한', other: '별도 조치 확인' };
    const SECTORS_KO = { bank: '은행', energy: '에너지', metals: '금속', semiconductors: '반도체', electronics: '전자',
        telecom: '통신', batteries: '배터리', automotive: '자동차', power_equipment: '전력기기', manufacturing: '제조업', trading: '종합상사' };
    const sanctionsTiming = (m, now = Date.now()) => {
        if (m.status !== 'time_limited_authorization') return m.status === 'conditional_exposure' ? '거래 조건에 따른 위험' : '선택 검토한 제한·요건';
        const end = Date.parse(m.expires_at);
        if (!Number.isFinite(end)) return '허가 기한 미확인';
        return now >= end ? '허가 기한 경과 · 연장 확인 필요' : '거래 한시 허용 · 전면 해제 아님';
    };
    const sanctionsDeadline = (value) => Number.isFinite(Date.parse(value))
        ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short' }).format(new Date(value))
        : '확인 필요';
    const sanctionsMeasureHtml = (m) => `<li class="uss-card">
        <div class="uss-meta">${esc(sanctionsTiming(m))}</div><strong>${esc(m.title_ko)}</strong>
        <p>${esc(m.summary_ko)}</p><div class="uss-meta">${esc(m.legal_basis)}</div>
        ${m.expires_at ? `<p class="uss-deadline">허가 만료: ${esc(sanctionsDeadline(m.expires_at))} (미국 동부 시간)</p>` : ''}
        <a href="${esc(safeUrl(m.source_url))}" target="_blank" rel="noopener noreferrer">공식 근거 ↗</a></li>`;
    const sanctionsCompanyHtml = (c) => {
        const status = c.status === 'listed_in_snapshot' ? 'CSL 명단 일치' : c.status === 'identity_review' ? '동일 법인 확인 필요' : '입력한 이름의 정확 일치 없음';
        const hits = (c.matches || []).map((m) => `<li><strong>${esc(SANCTION_KINDS[m.restriction_kind] || '개별 제한 확인')}</strong>
            <div>${esc(m.name)}</div><div class="uss-meta">${esc(m.source)} · ID ${esc(m.source_id)}</div>
            <div>${esc(m.validity === 'expired_or_ends_today' ? '명시된 종료일 경과 또는 당일 · 현행 적용 별도 확인' : m.validity === 'future' ? '명시된 시작일 전' : m.validity === 'date_review' ? '기간 해석 확인 필요' : '명단 기재 확인 · 거래별 예외·기간 별도 확인')}</div>
            ${m.start_date || m.end_date ? `<div class="uss-meta">시작 ${esc(m.start_date || '미기재')} · 종료 ${esc(m.end_date || '미기재')}</div>` : ''}
            ${m.programs ? `<div class="uss-meta">프로그램 ${esc(m.programs)}</div>` : ''}
            ${m.license_requirement ? `<p>${esc(m.license_requirement)}</p>` : ''}
            <a href="${esc(safeUrl(m.source_list_url))}" target="_blank" rel="noopener noreferrer">원기관 명단 ↗</a></li>`).join('');
        return `<li class="uss-card"><div class="uss-meta">${esc(SECTORS_KO[c.sector] || c.sector)} · ${esc(status)}</div>
            <strong>${esc(c.name_ko)}</strong><div class="uss-meta">${esc(c.screen_names?.[0])}</div>
            ${hits ? `<details><summary>제한 종류·법인 근거 ${(c.matches || []).length}개</summary><ul class="uss-matches">${hits}</ul></details>`
                : '<p>이름 대조 결과이며 제재 면제·거래 허용 판정이 아닙니다. 별칭·자회사·소유구조·거래 조건은 추가 확인이 필요합니다.</p>'}</li>`;
    };
    const sanctionsSectionHtml = (iso) => {
        if (!['RUS', 'CHN', 'KOR', 'JPN'].includes(iso)) return '';
        if (!sanctions || sanctions.error || !sanctions.countries?.[iso] || !Array.isArray(sanctions.companies) || !Array.isArray(sanctions.measures))
            return '<section class="uss-section"><h4>미국 제재·거래 제한</h4><p class="ec-warn">제재 검토 자료를 불러오지 못했습니다.</p></section>';
        const country = sanctions.countries[iso];
        const view = ui.sanctionsViews[iso] || 'banks';
        const measures = sanctions.measures.filter((m) => m.countries.includes(iso) && m.category === view);
        const companies = sanctions.companies.filter((c) => c.country === iso &&
            (view === 'companies' || (view === 'banks' && c.sector === 'bank') || (view === 'industries' && c.sector !== 'bank')));
        const pages = Math.max(1, Math.ceil(companies.length / 5));
        const page = Math.max(1, Math.min(pages, Number(ui.sanctionsPages[iso]) || 1));
        const shown = companies.slice((page - 1) * 5, page * 5);
        const age = (Date.now() - Date.parse(sanctions.checked_on)) / 86400000;
        return `<section class="uss-section" aria-label="${esc(country.name_ko)} 관련 미국 제재">
            <h4>미국 제재·거래 제한 <span class="uss-meta">4개국 시범</span></h4>
            <p class="uss-scope">${esc(country.program_scope_ko)}</p>
            <p class="uss-meta">확인 ${esc(sanctions.checked_on)} · ${age > 7 ? '확인일 경과 · 최신 명단 재확인 필요' : '공식 자료의 선택 검토본'} · 국가 전체 제재와 개별 법인 지정은 다릅니다.</p>
            <div class="uss-tabs" role="group" aria-label="제재 구분">${Object.entries(SANCTION_VIEWS).map(([key,label]) => `<button type="button" data-ec-sanctions-view="${key}" aria-pressed="${view === key}">${label}</button>`).join('')}</div>
            ${measures.length ? `<ul class="uss-list">${measures.map(sanctionsMeasureHtml).join('')}</ul>` : ''}
            ${companies.length ? `<h5>${view === 'companies' ? '주요 기업' : view === 'banks' ? '선정 은행' : '선정 산업 기업'} · ${companies.length}개 법인</h5>
            <ul class="uss-list">${shown.map(sanctionsCompanyHtml).join('')}</ul>
            <nav class="uss-pages" aria-label="기업 페이지">${Array.from({length:pages},(_,i) => `<button type="button" data-ec-sanctions-page="${i+1}" ${page === i+1 ? 'aria-current="page"' : ''}>${i+1}</button>`).join('')}
            <span>${(page-1)*5+1}–${Math.min(page*5,companies.length)} / ${companies.length}</span></nav>` : ''}
            <details class="uss-coverage"><summary>선정·대조 범위와 한계</summary><p>${esc(sanctions.selection_ko)}</p>
            <p>${esc(sanctions.screening_scope_ko)}</p><p>조회되지 않아도 ‘제재 없음’으로 판정하지 않습니다. 자산동결 대상자의 합산 50% 소유 규칙과 계열사 검토는 별도이며 NS-CMIC에 일괄 적용하지 않습니다. DoD·UFLPA 등 CSL 밖 명단은 이번 대조에 포함하지 않았습니다.</p>
            <a href="https://www.trade.gov/consolidated-screening-list" target="_blank" rel="noopener noreferrer">미 상무부 CSL 범위 ↗</a> ·
            <a href="https://ofac.treasury.gov/faqs/401" target="_blank" rel="noopener noreferrer">OFAC 소유구조 규칙 ↗</a></details>
        </section>`;
    };

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

    const newestNotices = (rows) => [...new Map(rows.map((r) => [r.id || r.url, r])).values()]
        .sort((a, b) => noticeDate(b).localeCompare(noticeDate(a)) || String(a.id || a.url).localeCompare(String(b.id || b.url)));

    const pageNotices = (rows, key) => {
        const sorted = newestNotices(rows);
        const pages = Math.max(1, Math.ceil(sorted.length / NOTICE_PAGE));
        const requested = Number(ui.noticePages[key]) || 1;
        const page = Math.max(1, Math.min(pages, Math.floor(requested)));
        ui.noticePages[key] = page;
        return { rows: sorted.slice((page - 1) * NOTICE_PAGE, page * NOTICE_PAGE), page, pages, total: sorted.length };
    };
    const pagedNoticesHtml = (rows, key, render = noticeHtml) => {
        const p = pageNotices(rows, key);
        if (!p.total) return '<p class="ec-empty">조건에 맞는 공고가 없습니다.</p>';
        const buttons = Array.from({ length: p.pages }, (_, i) => `<button type="button"
            data-ec-notice-page="${i + 1}" data-ec-notice-key="${esc(key)}"
            ${p.page === i + 1 ? 'aria-current="page"' : ''} aria-label="${i + 1}페이지">${i + 1}</button>`).join('');
        return `<div data-ec-notice-list="${esc(key)}"><ul class="ec-notices">${p.rows.map(render).join('')}</ul>
            <nav class="ec-pagination" aria-label="공고 페이지">${buttons}
            <span>${(p.page - 1) * NOTICE_PAGE + 1}–${Math.min(p.page * NOTICE_PAGE, p.total)} / ${p.total}건</span></nav></div>`;
    };

    const announcementEligible = (r, iso) => {
        const w = announcements?.window;
        if (!w || !/^\d{4}-\d{2}-\d{2}$/.test(r.published_at || '')
            || r.published_at < w.from || r.published_at > w.through || r.published_at > TODAY) return false;
        let host;
        try { host = new URL(r.url).hostname; } catch { return false; }
        const usOfficial = host.endsWith('.gov') || host === 'content.govdelivery.com';
        const krOfficial = host.endsWith('.go.kr');
        if (r.issuer === 'USA') return usOfficial;
        return r.issuer === iso && krOfficial && r.speaker?.statement_verified === true
            && ['president', 'prime_minister', 'deputy_prime_minister', 'cabinet_minister'].includes(r.speaker.rank);
    };
    const ANNOUNCEMENT_KINDS = {
        joint_statement: '공동성명', cooperation: '협력 발표', implementation_guidance: '시행 안내',
        policy_action: '정책 조치 발표', minister_statement: '한국 장관급 발언', trade_remedy: '무역구제 공고',
    };
    const announcementHtml = (r) => `<li class="ec-notice">
        <div class="ec-n-meta"><span class="ec-n-date">${esc(r.published_at)}</span>
        <span class="ec-n-body">${esc(r.agency_ko)}</span><span class="ec-n-measure">${esc(ANNOUNCEMENT_KINDS[r.kind] || r.kind)}</span></div>
        <a class="ec-n-title" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title?.ko || r.title?.original)} <span class="ec-n-go">원문 ↗</span></a>
        <p class="ec-n-summary">${esc(r.summary_ko)}</p>
        <div class="ec-n-tags">${esc(r.relation)}${r.event_date ? ` · 행사 ${esc(r.event_date)}` : ''}
        · ${r.verification === 'official_text_checked' ? '공식 본문 확인' : '공식 제목·발행일 확인 / 본문 상세 미검증'}${r.document_number ? ` · FR ${esc(r.document_number)}` : ''}</div></li>`;
    const announcementsHtml = (iso) => {
        if (iso !== 'KOR') return '';
        const heading = '<h4 class="ec-cat">한국 관련 미국 발표·고위급 동향</h4>';
        if (!announcements || announcements.error || !announcements.countries?.[iso] || !announcements.window) {
            return heading + '<p class="ec-warn">공식 동향 자료를 불러오지 못했습니다.</p>';
        }
        const rows = newestNotices(announcements.countries[iso].filter((r) => announcementEligible(r, iso))).slice(0, 40);
        return `${heading}<p class="ec-foot">${esc(announcements.window.from)}~${esc(announcements.window.through)} · ${rows.length}건 · 확인 ${esc(announcements.checked_on)}<br>
            미국 발표 중심 · 한국은 장관급 이상 발언만 · 일부 공식 자료를 선별한 검토본입니다. 발언·협의와 규제 시행은 구분합니다.</p>
            ${pagedNoticesHtml(rows, `${iso}:announcements`, announcementHtml)}`;
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

        ui.panel.innerHTML = `
            ${tabsHtml()}
            <div class="ec-filters" role="group" aria-label="발표국">${issuerChips}</div>
            <div class="ec-filters" role="group" aria-label="조치 종류">${measureChips}</div>
            ${scopeToggleHtml()}
            ${pagedNoticesHtml(list, 'all')}
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

    const authorityLabel = (value) => /^\d+$/.test(value || '') ? `${value}조` : value || '';
    const verificationHtml = (item) => `<span class="ust-verification ${item.verification === 'primary_text_checked' ? 'ust-checked' : 'ust-review'}">${
        item.verification === 'primary_text_checked' ? '표시 원문 확인' : '기존 자료 · 재확인 필요'}</span>`;
    // A law's existence, an investigation and an effective measure are separate.
    // Classify against the snapshot date, without silently refreshing legal facts.
    const tariffPhase = (m) => {
        if (['expired', 'struck_down', 'ended'].includes(m.status)) return 'history';
        if (['active', 'truce'].includes(m.status)) {
            if (m.started && m.started > usTariffs.as_of) return 'pending';
            if (m.ended && m.ended <= usTariffs.as_of) return 'history';
            return 'live';
        }
        return 'pending';
    };

    const legalToolsHtml = (ids, note) => {
        const wanted = new Set(ids || (usTariffs?.legal_tools || []).map((t) => t.id));
        const tools = (usTariffs?.legal_tools || []).filter((t) => wanted.has(t.id));
        if (!tools.length) return '';
        return `<details class="ust-tools"><summary>법적 요건을 충족하면 검토할 수 있는 수단 · ${tools.length}개</summary>
            <p class="ust-scope">${esc(note || '국가별 발효 조치와 별개인 법률상 검토 목록입니다. 적용 가능성·발동 확률·세율을 확정하지 않습니다.')}</p>
            <ul class="ust-list">${tools.map((t) => `<li class="ust-item ust-conditional">
                <b>${esc(t.name_ko)}</b><div class="ust-when">${esc(t.legal_basis)}</div>
                <div class="ust-scope"><b>요건</b> ${esc(t.trigger_ko)}</div>
                <div class="ust-scope"><b>절차</b> ${esc(t.procedure_ko)}</div>
                <div class="ust-rate">${esc(t.effect_ko)}</div>
                <div class="ec-src">${tariffSources(t.sources)}</div></li>`).join('')}</ul></details>`;
    };

    const tariffMeasureHtml = (m) => `<li class="ust-item ust-${esc(m.status)}">
        <div class="ust-top">
            <span class="ust-auth">${esc(authorityLabel(m.authority))}</span>
            <b>${esc(m.name_ko)}</b>
            <span class="ust-status">${esc(TARIFF_STATUS_KO[m.status] || m.status)}</span>
        </div>
        <div class="ust-when">${esc(m.started || '')} ~ ${esc(m.ended || (tariffPhase(m) === 'live' ? '종료일 미지정' : '개별 일정 확인'))}</div>
        ${verificationHtml(m)}
        <div class="ust-rate">${esc(m.rate_ko)}</div>
        ${m.how_ended_ko ? `<div class="ust-ended"><b>어떻게 끝났나</b> ${esc(m.how_ended_ko)}</div>` : ''}
        ${m.scope_ko ? `<div class="ust-scope">${esc(m.scope_ko)}</div>` : ''}
        ${m.verification_note_ko ? `<div class="ust-scope">${esc(m.verification_note_ko)}</div>` : ''}
        <div class="ec-src">${tariffSources(m.sources)}</div>
    </li>`;

    const negotiationKind = (kind) => ({ framework: '기본합의', signed_agreement: '서명 확인',
        agreement_in_force: '기존 발효 협정', consensus: '합의 발표', sectoral_agreement: '분야별 합의',
        implementation: '이행 발표', implementation_pending: '발표 당시 국내 절차 필요',
        negotiation: '협상·협의', consultation: '의견수렴', recommendation: '권고 · 시행 별도 확인',
        suspension: '협상 중단 발표', statement: '공식 입장' }[kind] || '구분 확인 필요');
    const checkedDevelopments = (n) => (n.developments || []).filter((e) =>
        e.verification === 'primary_text_checked' && /^\d{4}-\d{2}-\d{2}$/.test(e.announced_on || '') &&
        e.announced_on <= n.checked_on && e.sources?.length)
        .slice().sort((a, b) => b.announced_on.localeCompare(a.announced_on));
    // Passing a scheduled date never proves that talks occurred or an agreement entered into force.
    const negotiationScheduleState = (m, now = new Date()) => {
        if (m.status === 'cancelled') return '취소 발표';
        if (m.status === 'completed' && m.completion_sources?.length) return '결과 원문 확인';
        const date = m.scheduled_for || '';
        let end = m.deadline_at ? Date.parse(m.deadline_at) : NaN;
        if (!Number.isFinite(end)) {
            if (m.date_precision === 'year' && /^\d{4}$/.test(date)) end = Date.parse(`${date}-12-31T23:59:59Z`);
            else if (m.date_precision === 'month' && /^\d{4}-(0[1-9]|1[0-2])$/.test(date)) {
                const [year, month] = date.split('-').map(Number);
                end = Date.UTC(year, month, 1) - 1;
            } else if (m.date_precision === 'day' && /^\d{4}-\d{2}-\d{2}$/.test(date)) end = Date.parse(`${date}T23:59:59Z`);
        }
        if (!Number.isFinite(end)) return '확정일 미확인';
        return now.getTime() > end ? '일정 경과 · 결과 미확인' : '공식 예고 · 변경 여부 확인 필요';
    };
    const negotiationsHtml = (p, compact = false) => {
        const n = p.negotiation;
        if (!n) return '';
        const a = n.agreement?.verification === 'primary_text_checked' && n.agreement.sources?.length ? n.agreement : null;
        const updates = checkedDevelopments(n);
        const row = (e) => `<li><div class="ust-when">${esc(e.announced_on ? `${e.announced_on} 발표` : `${e.event_on || '일자 미확인'} 기준`)} · ${esc(negotiationKind(e.kind))}</div>
            <b>${esc(e.title_ko)}</b><p class="ust-scope">${esc(e.summary_ko)}</p>
            <div class="ust-scope">${e.effective_on ? `확인한 발효일: ${esc(e.effective_on)}` : '개별 시행·발효일 별도 확인'}</div>
            <div class="ec-src">${tariffSources(e.sources)}</div></li>`;
        const summary = a ? `${a.announced_on || a.event_on || '일자 미확인'} · ${a.title_ko} (${negotiationKind(a.kind)})` : '확인한 합의 없음';
        if (compact) return `<div class="ust-negotiation-brief"><b>확인한 주요 합의·기준 협정</b> ${esc(summary)}
            ${updates[0] ? `<br><b>공식 후속 발표</b> ${esc(updates[0].announced_on)} · ${esc(updates[0].title_ko)}` : ''}</div>`;
        return `<details class="ust-negotiations"><summary>주요 합의·공식 후속 발표·일정</summary>
            <p class="ust-scope">공식 자료 확인일 ${esc(n.checked_on)} · ${esc(n.coverage_note_ko)}</p>
            ${n.jurisdiction_ko ? `<p class="ust-scope"><b>협상 관할</b> ${esc(n.jurisdiction_ko)}</p>` : ''}
            <h5>확인한 주요 합의·기준 협정</h5>${a ? `<ul class="ust-negotiation-list">${row(a)}</ul>` : '<p class="ust-scope">확인한 합의 없음</p>'}
            <h5>공식 후속 발표 · 최신 발표부터</h5>${updates.length ? `<ul class="ust-negotiation-list">${updates.map(row).join('')}</ul>` : '<p class="ust-scope">추가로 확인한 후속 발표 없음</p>'}
            <h5>공식 예고 일정</h5>${n.milestones?.length ? `<ul class="ust-negotiation-list">${n.milestones.map((m) => `<li>
                <div class="ust-when">${esc(m.scheduled_for || '확정일 미확인')} · ${esc(negotiationScheduleState(m))}</div>
                <b>${esc(m.title_ko)}</b><p class="ust-scope">${esc(m.note_ko)}</p><div class="ec-src">${tariffSources(m.sources)}</div></li>`).join('')}</ul>` : '<p class="ust-scope">확인한 원문에 다음 통상협상 확정일 없음</p>'}
            <p class="ust-scope">${esc(n.unresolved_ko)}</p>
        </details>`;
    };

    const partnerHtml = (iso, p, { link = false } = {}) => `<div class="ust-partner">
        <div class="ust-top">
            ${link ? `<button type="button" class="ust-pname" data-ec-iso="${esc(iso)}">${esc(p.name_ko)} →</button>`
                : `<b>미국 → ${esc(p.name_ko)} · 통상 조치와 검토사항</b>`}
        </div>
        <div class="ust-scope">${esc(p.summary_ko)}</div>
        ${negotiationsHtml(p, true)}
        <table class="ust-table"><tbody>
            ${(p.lines || []).map((l) => `<tr><th>${esc(l.label_ko)}</th><td>${esc(l.rate_ko)}
                ${link ? '' : `${verificationHtml(l)}${l.sources?.length ? `<details class="ust-line-detail"><summary>근거·확인 범위</summary>
                    ${(l.measure_ids || []).map((id) => (usTariffs.measures || []).find((m) => m.id === id)).filter(Boolean)
                        .map((m) => `<div class="ust-scope">${esc(TARIFF_STATUS_KO[m.status] || m.status)} · ${esc(m.name_ko)}<br>${esc(m.scope_ko || m.verification_note_ko || '')}</div>`).join('')}
                    <div class="ec-src">${tariffSources(l.sources)}</div></details>` : ''}`}</td>
                <td class="ust-auth-cell">${esc(authorityLabel(l.authority))}</td></tr>`).join('')}
        </tbody></table>
        ${link ? '' : `<p class="ust-scope">${esc(usTariffs.as_of)} 기준 · ${esc(p.coverage_ko || '')}</p><div class="ec-src">${tariffSources(p.sources)}</div>
            ${negotiationsHtml(p)}${legalToolsHtml(p.legal_tool_ids, p.legal_tools_note_ko)}`}
    </div>`;

    // The US's own panel: what is in force, how the struck-down and expired
    // layers ended, and the current rate on the main manufacturing partners.
    const usTariffSectionHtml = () => {
        if (!usTariffs) return '<p class="ec-warn">미국 관세 자료를 불러오지 못했습니다.</p>';
        const live = usTariffs.measures.filter((m) => tariffPhase(m) === 'live');
        const gone = usTariffs.measures.filter((m) => tariffPhase(m) === 'history');
        const pending = usTariffs.measures.filter((m) => tariffPhase(m) === 'pending');
        const partners = Object.entries(usTariffs.partners || {});
        return `<section class="ust">
            <h4 class="ec-sect">${esc(usTariffs.title_ko)}</h4>
            <p class="ust-lead">미국의 수입관세·수입금지와 수출·거래 제한을 구분합니다. 국가를 열면 실제 조치의 근거와
                별도의 조건부 법적 수단을 확인할 수 있습니다. 법률이 존재한다고 즉시 적용되는 것은 아닙니다.</p>
            <p class="ust-scope">${esc(usTariffs.audit?.scope_ko || usTariffs.note_ko)}</p>
            <h4 class="ec-cat">국가별 미국 통상 조치 · 확인한 범위</h4>
            ${partners.map(([iso, p]) => partnerHtml(iso, p, { link: true })).join('')}
            <h4 class="ec-cat">시행 중인 제도 <span class="ec-cat-n">${live.length}건</span></h4>
            <ul class="ust-list">${live.map(tariffMeasureHtml).join('')}</ul>
            ${pending.length ? `<details class="ust-gone"><summary>조사·시행 예정·재확인 <span class="ec-cat-n">${pending.length}건</span></summary>
                <ul class="ust-list">${pending.map(tariffMeasureHtml).join('')}</ul></details>` : ''}
            <details class="ust-gone"><summary>끝난 조치 — 어떻게 끝났나 <span class="ec-cat-n">${gone.length}건</span></summary>
                <ul class="ust-list">${gone.map(tariffMeasureHtml).join('')}</ul>
            </details>
            ${legalToolsHtml()}
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
        const noticeBlock = (title, rows, key) => (rows.length ? `
            <h4 class="ec-cat">${esc(title)} <span class="ec-cat-n">${rows.length}건</span></h4>
            ${pagedNoticesHtml(rows, `${iso}:${key}`)}` : '');
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
            ${noticeBlock(`${name} 규제 기관이 낸 공고`, issued, 'issued')}
            ${noticeBlock(`${name}을(를) 겨냥한 공고`, aimed, 'aimed')}`}
            ${total || (iso === 'USA' && ui.usView === 'tariffs') || usTariffs?.partners?.[iso] || sanctions?.countries?.[iso] ? '' : `<p class="ec-empty">정리된 수출통제 조치도, 최근 공고도 없습니다.<br>
                아직 원문을 확인하지 않은 것일 수 있습니다 — 통제가 없다는 뜻은 아닙니다.</p>`}
            ${announcementsHtml(iso)}
            ${sanctionsSectionHtml(iso)}
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
        ui.noticePages = {};
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
            ui.tab = v; ui.iso = null; ui.commodity = null; ui.noticePages = {}; redraw(); return;
        }
        if ((v = attr('data-ec-sanctions-view'))) {
            if (!ui.iso || !Object.hasOwn(SANCTION_VIEWS, v)) return;
            ui.sanctionsViews[ui.iso] = v; ui.sanctionsPages[ui.iso] = 1;
            const top = ui.panel.scrollTop; renderPanel(); ui.panel.scrollTop = top; return;
        }
        if ((v = attr('data-ec-sanctions-page'))) {
            if (!ui.iso || !/^\d+$/.test(v)) return;
            ui.sanctionsPages[ui.iso] = Number(v);
            const top = ui.panel.scrollTop; renderPanel(); ui.panel.scrollTop = top; return;
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
            ui.noticeMeasure = 'all'; ui.noticePages = {}; redraw(); return;
        }
        if ((v = attr('data-ec-category'))) {
            ui.category = v; ui.iso = null; redraw(); return;
        }
        if ((v = attr('data-ec-issuer'))) {
            ui.issuer = v; ui.noticeMeasure = 'all'; ui.noticePages = {}; redraw(); return;
        }
        if ((v = attr('data-ec-nmeasure'))) {
            ui.noticeMeasure = v; ui.noticePages = {}; redraw(); return;
        }
        if ((v = attr('data-ec-issuer-all'))) {
            ui.tab = 'notices'; ui.issuer = v; ui.noticeMeasure = 'all'; ui.noticePages = {}; ui.iso = null; redraw(); return;
        }
        if ((v = attr('data-ec-notice-page'))) {
            const key = attr('data-ec-notice-key');
            if (!key || !/^\d+$/.test(v)) return;
            const top = ui.panel.scrollTop;
            ui.noticePages[key] = Number(v);
            renderPanel();
            ui.panel.scrollTop = top;
            ui.panel.querySelector(`[data-ec-notice-key="${CSS.escape(key)}"][aria-current="page"]`)?.focus({ preventScroll: true });
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
        await Promise.all([load(), loadNotices(), loadUsTariffs(), loadAnnouncements(), loadSanctions(), host.loadWorldGeo()]);
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
