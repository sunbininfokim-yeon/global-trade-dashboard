// My Page: 즐겨찾기 / 메일링 서비스 / 포트폴리오 / 개인정보수정.
// Basic scaffold -- structure, routing, and the backend calls are wired up;
// depth (richer favorite cards, spreadsheet upload for the portfolio tab,
// notification-preference toggles beyond the commodity source filter) is
// left for follow-up work. Reads window.Auth (auth.js), window.USPolicy
// (policy.js), and renderPortfolioLab (portfolio.js) -- all loaded earlier
// in index.html and sharing this page's script scope.
(() => {
    const TABS = [
        { id: 'favorites', label: '즐겨찾기' },
        { id: 'mailing', label: '메일링 서비스' },
        { id: 'portfolio', label: '포트폴리오' },
        { id: 'account', label: '개인정보수정' },
    ];

    let host = null;
    let activeTab = 'favorites';
    let renderToken = 0;

    const esc = (value) => {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    };

    function shellHtml() {
        return `
            <div class="mypage-shell">
                <div class="mypage-header">
                    <h1>마이페이지</h1>
                    <p id="mypage-identity"></p>
                </div>
                <div class="mypage-tabs">
                    ${TABS.map((t) => `<button type="button" class="mypage-tab" data-tab="${t.id}">${t.label}</button>`).join('')}
                </div>
                <div class="mypage-panels">
                    ${TABS.map((t) => `<div class="mypage-panel hidden" data-panel="${t.id}"></div>`).join('')}
                </div>
            </div>`;
    }

    function setActiveTab(id) {
        activeTab = id;
        host.querySelectorAll('.mypage-tab').forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === id));
        host.querySelectorAll('.mypage-panel').forEach((panel) => panel.classList.toggle('hidden', panel.dataset.panel !== id));
        loadTab(id);
    }

    const loaded = new Set(); // tabs already fetched once this render -- avoid refetching on every tab switch

    function loadTab(id) {
        if (loaded.has(id)) return;
        loaded.add(id);
        if (id === 'favorites') renderFavorites();
        else if (id === 'mailing') renderMailing();
        else if (id === 'portfolio') renderPortfolio();
        else if (id === 'account') renderAccount();
    }

    function panel(id) {
        return host.querySelector(`.mypage-panel[data-panel="${id}"]`);
    }

    // Shared by the 즐겨찾기 tab's bill list and the 메일링 서비스 tab's "these
    // are what you're watching" list below the pause toggle -- same cards,
    // same one-request-per-bill loading pattern, two places that show them.
    function renderFavoriteBillCards(container, bills, token) {
        if (!bills.length) {
            container.innerHTML = '<p class="mypage-empty">아직 즐겨찾기한 법안이 없습니다.</p>';
            return;
        }
        container.innerHTML = bills.map((f) => `<div class="policy-fav-bill-card" data-bill-id="${esc(f.item_id)}"><div class="policy-fav-bill-title">${esc(f.title || f.item_id)}</div><p class="mypage-empty">저장됨 · 상세정보 불러오는 중…</p></div>`).join('');
        // One request per favorited bill -- fine at favorites-list scale;
        // revisit with a batch endpoint if this list grows large.
        bills.forEach(async (f) => {
            const card = container.querySelector(`[data-bill-id="${CSS.escape(f.item_id)}"]`);
            try {
                const bill = await window.USPolicy.loadBillById(f.item_id);
                if (token !== renderToken || !card) return;
                card.outerHTML = window.USPolicy.favoriteBillCardHtml(bill, f.notify_enabled);
            } catch (err) {
                if (token !== renderToken || !card) return;
                card.innerHTML = `<div class="policy-fav-bill-title">${esc(f.title || f.item_id)}</div><p class="mypage-empty">즐겨찾기는 저장돼 있습니다. 법안 상세정보를 불러오지 못했습니다.</p>`;
            }
        });
        bindFavoriteBillCardActions(container);
    }

    // Delegated so it survives the card.outerHTML swap above; safe to call
    // every render since the container itself is fresh innerHTML each time
    // (no stale listener stacks up on a removed container).
    function bindFavoriteBillCardActions(container) {
        container.addEventListener('click', async (e) => {
            const btn = e.target.closest('[data-remove-item-id]');
            if (!btn) return;
            btn.disabled = true;
            try {
                await window.Auth.removeFavorite('bill', btn.dataset.removeItemId);
                // Both tabs can be showing a bill list; force a refetch next
                // time either is opened instead of leaving a stale copy.
                loaded.delete('favorites');
                loaded.delete('mailing');
                const card = btn.closest('.policy-fav-bill-card');
                if (card) card.remove();
                if (!container.querySelector('.policy-fav-bill-card')) {
                    container.innerHTML = '<p class="mypage-empty">아직 즐겨찾기한 법안이 없습니다.</p>';
                }
            } catch (err) {
                btn.disabled = false;
                console.error('Failed to remove favorite bill:', err);
            }
        });
        container.addEventListener('change', async (e) => {
            const checkbox = e.target.closest('.policy-fav-bill-notify-checkbox');
            if (!checkbox) return;
            const next = checkbox.checked;
            checkbox.disabled = true;
            try {
                await window.Auth.setFavoriteNotifyEnabled('bill', checkbox.dataset.itemId, next);
            } catch (err) {
                checkbox.checked = !next;
                console.error('Failed to update favorite notify preference:', err);
            } finally {
                checkbox.disabled = false;
            }
        });
    }

    /* ------------------------------------------------------------ 즐겨찾기 */

    async function renderFavorites() {
        const el = panel('favorites');
        el.innerHTML = '<p class="mypage-empty">불러오는 중…</p>';
        const token = renderToken;
        let favorites = [];
        try {
            favorites = await window.Auth.listFavorites();
        } catch (err) {
            if (token !== renderToken) return;
            el.innerHTML = `<p class="mypage-empty">즐겨찾기를 불러오지 못했습니다: ${esc(err.message)}</p>`;
            return;
        }
        if (token !== renderToken) return;
        if (!favorites.length) {
            el.innerHTML = '<p class="mypage-empty">아직 즐겨찾기한 항목이 없습니다.</p>';
            return;
        }

        const bills = favorites.filter((f) => f.item_kind === 'bill');
        const commodities = favorites.filter((f) => f.item_kind === 'commodity');
        const others = favorites.filter((f) => f.item_kind !== 'bill' && f.item_kind !== 'commodity');

        el.innerHTML = `
            ${bills.length ? '<p class="mypage-section-title">법안</p><div class="policy-bill-list" id="mypage-fav-bills"></div>' : ''}
            ${commodities.length ? '<p class="mypage-section-title">원자재</p><div class="policy-bill-list" id="mypage-fav-commodities"></div>' : ''}
            ${others.length ? '<p class="mypage-section-title">그 외</p><div class="policy-bill-list" id="mypage-fav-others"></div>' : ''}
        `;

        if (commodities.length) {
            const container = el.querySelector('#mypage-fav-commodities');
            container.innerHTML = commodities.map((f) => `
                <div class="policy-fav-bill-card">
                    <div class="policy-fav-bill-title">${esc(f.title || f.item_id)}</div>
                    <div class="policy-fav-bill-actions">
                        <button type="button" class="policy-fav-star" data-remove-commodity-id="${esc(f.item_id)}" title="즐겨찾기 해제" aria-label="즐겨찾기 해제">★</button>
                    </div>
                </div>`).join('');
            container.addEventListener('click', async (e) => {
                const btn = e.target.closest('[data-remove-commodity-id]');
                if (!btn) return;
                btn.disabled = true;
                try {
                    await window.Auth.removeFavorite('commodity', btn.dataset.removeCommodityId);
                    loaded.delete('favorites');
                    loaded.delete('mailing'); // its commodity checkboxes read the same favorites
                    renderFavorites();
                } catch (err) {
                    btn.disabled = false;
                    console.error('Failed to remove commodity favorite:', err);
                }
            });
        }

        if (others.length) {
            const container = el.querySelector('#mypage-fav-others');
            container.innerHTML = others.map((f) => `
                <div class="policy-fav-bill-card">
                    <div class="policy-fav-bill-title">${esc(f.title || f.item_id)}</div>
                    <div class="policy-fav-bill-meta">
                        <span class="policy-fav-bill-code">${esc(f.item_kind)}</span>
                        <button type="button" class="auth-btn" data-remove-kind="${esc(f.item_kind)}" data-remove-id="${esc(f.item_id)}">해제</button>
                    </div>
                </div>`).join('');
            container.addEventListener('click', async (e) => {
                const btn = e.target.closest('[data-remove-kind]');
                if (!btn) return;
                btn.disabled = true;
                try {
                    await window.Auth.removeFavorite(btn.dataset.removeKind, btn.dataset.removeId);
                    loaded.delete('favorites');
                    renderFavorites();
                } catch (err) {
                    btn.disabled = false;
                    console.error('Failed to remove favorite:', err);
                }
            });
        }

        if (bills.length) {
            renderFavoriteBillCards(el.querySelector('#mypage-fav-bills'), bills, token);
        }
    }

    /* -------------------------------------------------------- 메일링 서비스 */

    // Groups commodity_reports_v1.json's items by commodity instead of by
    // RSS/source id, so the source filter reads "원유 -> EIA" instead of a
    // flat list of feed names. commodity_labels/commodities come straight
    // from that file -- a commodity or source added to the pipeline shows up
    // here without a UI change. Order follows each commodity's first
    // appearance in items (stable, not alphabetical or hardcoded).
    function groupSourcesByCommodity(reportsRes) {
        const labels = reportsRes.commodity_labels || {};
        const order = [];
        const byCommodity = new Map(); // key -> Map<source_id, {agency, agency_ko}>
        (reportsRes.items || []).forEach((item) => {
            (item.commodities || []).forEach((key) => {
                if (!byCommodity.has(key)) {
                    byCommodity.set(key, new Map());
                    order.push(key);
                }
                const sources = byCommodity.get(key);
                if (!sources.has(item.source_id)) {
                    sources.set(item.source_id, { agency: item.agency, agency_ko: item.agency_ko });
                }
            });
        });
        const allSourceIds = new Set();
        (reportsRes.items || []).forEach((item) => allSourceIds.add(item.source_id));
        const groups = order.map((key) => ({
            key,
            label: labels[key] || key,
            sources: [...byCommodity.get(key)].map(([source_id, meta]) => ({ source_id, ...meta })),
        }));
        return { groups, sourceIds: allSourceIds };
    }

    function reportQualityText(doc, now = Date.now()) {
        const feeds = Array.isArray(doc.feed_status) ? doc.feed_status : [];
        const items = Array.isArray(doc.items) ? doc.items : [];
        const generated = Date.parse(doc.generated_at || '');
        const freshness = !Number.isFinite(generated) || generated > now + 5 * 60000 ? '수집 시각 미확인'
            : now - generated > 12 * 3600000 ? '수집 자료 갱신 지연' : '최근 수집 자료';
        const failed = feeds.filter(f => !f.ok).length;
        const carried = feeds.reduce((n, f) => n + (Number(f.carried_over) || 0), 0);
        const undated = items.filter(i => !i.published_at || !Number.isFinite(Date.parse(i.published_at))).length;
        const unclassified = Number.isInteger(doc.stats?.unclassified) ? doc.stats.unclassified : '집계 미확인';
        return `${freshness} · 소스 ${feeds.length ? `${feeds.filter(f => f.ok).length}/${feeds.length} 응답` : '상태 미확인'} · 수집 실패 ${failed} · 이전 자료 보존 ${carried} · 발행일 미확인 ${undated} · 주제 미분류 ${unclassified}. 수집 실패나 미확인은 기관의 미발행을 뜻하지 않습니다.`;
    }

    async function renderMailing() {
        const el = panel('mailing');
        el.innerHTML = `
            <div class="mypage-status-strip" id="mypage-mail-status">
                <div class="mypage-status-tile"><div class="v">불러오는 중…</div><div class="k">법안 알림</div></div>
                <div class="mypage-status-tile"><div class="v">불러오는 중…</div><div class="k">원자재 다이제스트</div></div>
                <div class="mypage-status-tile"><div class="v">준비 중</div><div class="k">시장 미시구조</div></div>
            </div>

            <p class="mypage-section-title">법안</p>
            <p class="mypage-empty">법안별 변경 알림을 받을지 설정합니다. 수신 설정과 실제 발송 상태는 다릅니다. 변경이 없는 법안은 반복 발송 대상이 아닙니다. 다음날 오전 7시 이전 알림은 새 발송기로 전환 준비 중입니다.</p>
            <div class="mypage-switch-row">
                <div class="mypage-switch-label">알림 일시정지<small>즐겨찾기는 그대로 두고 메일만 끕니다</small></div>
                <label class="mypage-switch">
                    <input type="checkbox" id="mypage-bill-pause">
                    <span class="track"></span><span class="knob"></span>
                </label>
            </div>
            <p class="mypage-status hidden" id="mypage-bill-pause-status"></p>
            <div class="policy-bill-list" id="mypage-mail-bills"><p class="mypage-empty">불러오는 중…</p></div>

            <p class="mypage-section-title">원자재</p>
            <p class="mypage-empty">박스 제목을 체크한 원자재만 최근 8일 이내 리포트를 매주 월요일 오전 8시(KST) 발송 대상으로 확인합니다. 실행 지연에 따라 도착 시각은 늦어질 수 있습니다. 체크 안 한 원자재는 그 안의 기관 체크와 상관없이 메일이 가지 않습니다. 아래 기관 체크는 즐겨찾기한 원자재 안에서 어느 기관 소식만 뺄지 고르는 용도입니다.</p>
            <p class="mypage-empty" id="mypage-report-quality"></p>
            <div id="mypage-source-filter"><p class="mypage-empty">불러오는 중…</p></div>

            <p class="mypage-section-title">시장 미시구조</p>
            <p class="mypage-empty">준비 중입니다.</p>
        `;
        const token = renderToken;
        const statusStrip = el.querySelector('#mypage-mail-status');
        const [billTile, commodityTile] = statusStrip.querySelectorAll('.mypage-status-tile');

        const pauseToggle = el.querySelector('#mypage-bill-pause');
        const pauseStatus = el.querySelector('#mypage-bill-pause-status');
        try {
            const paused = await window.Auth.billNotificationsPaused();
            if (token !== renderToken) return;
            pauseToggle.checked = paused;
            billTile.querySelector('.v').textContent = paused ? '일시정지됨' : '수신 설정 켜짐';
        } catch (err) {
            if (token !== renderToken) return;
            billTile.querySelector('.v').textContent = '불러오지 못함';
        }
        pauseToggle.addEventListener('change', async () => {
            const next = pauseToggle.checked;
            pauseToggle.disabled = true;
            pauseStatus.className = 'mypage-status hidden';
            try {
                await window.Auth.setBillNotificationsPaused(next);
                billTile.querySelector('.v').textContent = next ? '일시정지됨' : '수신 설정 켜짐';
            } catch (err) {
                pauseToggle.checked = !next;
                pauseStatus.textContent = err.message || '저장하지 못했습니다.';
                pauseStatus.className = 'mypage-status is-error';
            } finally {
                pauseToggle.disabled = false;
            }
        });

        const billListEl = el.querySelector('#mypage-mail-bills');
        let favorites = [];
        try {
            favorites = await window.Auth.listFavorites();
            if (token !== renderToken) return;
            renderFavoriteBillCards(billListEl, favorites.filter((f) => f.item_kind === 'bill'), token);
        } catch (err) {
            if (token !== renderToken) return;
            billListEl.innerHTML = `<p class="mypage-empty">즐겨찾기한 법안을 불러오지 못했습니다: ${esc(err.message)}</p>`;
        }
        const favoritedCommodityKeys = new Set(favorites.filter((f) => f.item_kind === 'commodity').map((f) => f.item_id));

        const container = el.querySelector('#mypage-source-filter');
        try {
            const [reportsRes, disabled, macQuality] = await Promise.all([
                fetch('/public/data/commodity_reports_v1.json', { cache: 'no-cache' }).then((r) => r.json()),
                window.Auth.listDisabledCommoditySources(),
                fetch('/api/us/reports/quality', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null).catch(() => null),
            ]);
            if (token !== renderToken) return;
            const macDate = macQuality?.last_success_at ? new Date(macQuality.last_success_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '미확인';
            const macLabel = ({succeeded:'수집·DB 보관 완료',partial:'일부 자료만 수집·보관',failed:'마지막 시도 실패'})[macQuality?.status] || '수집 상태 미확인';
            el.querySelector('#mypage-report-quality').textContent = `맥 DB 보관: ${macLabel} · 마지막 성공 ${macDate}. 게시된 RSS 자료: ${reportQualityText(reportsRes)}`;
            const { groups } = groupSourcesByCommodity(reportsRes);
            const updateCommodityTile = () => {
                commodityTile.querySelector('.v').textContent = favoritedCommodityKeys.size
                    ? `예약 월 08:00 · ${favoritedCommodityKeys.size}개 즐겨찾기`
                    : '즐겨찾기 없음 · 발송 안 됨';
            };
            updateCommodityTile();
            if (!groups.length) {
                container.innerHTML = '<p class="mypage-empty">현재 연동된 원자재 소스가 없습니다.</p>';
                return;
            }
            container.innerHTML = window.Auth.commoditySourceFilterHtml(groups, disabled, favoritedCommodityKeys);
            window.Auth.bindCommoditySourceFilter(container);
            window.Auth.bindCommodityFavoriteFilter(container);
            container.addEventListener('change', (e) => {
                const checkbox = e.target.closest('.commodity-fav-checkbox');
                if (!checkbox) return;
                // Optimistic, same as bindCommodityFavoriteFilter's own write --
                // rolls back together with the checkbox if that write fails.
                if (checkbox.checked) favoritedCommodityKeys.add(checkbox.dataset.commodityKey);
                else favoritedCommodityKeys.delete(checkbox.dataset.commodityKey);
                updateCommodityTile();
                loaded.delete('favorites'); // 즐겨찾기 탭의 원자재 목록도 같이 바뀌었으니 다음에 열 때 새로 불러옴
            });
        } catch (err) {
            if (token !== renderToken) return;
            commodityTile.querySelector('.v').textContent = '불러오지 못함';
            container.innerHTML = `<p class="mypage-empty">소스 목록을 불러오지 못했습니다: ${esc(err.message)}</p>`;
        }
    }

    /* ------------------------------------------------------------ 포트폴리오 */

    // Same calculator as Finance›Portfolio Lab (portfolio.js, loaded earlier in
    // index.html so renderPortfolioLab shares this page's script scope) --
    // one engine, one UI, two entry points, per the T25 design. Holdings are
    // saved to the same portfolioLab.v1 localStorage key, so a list started
    // on one screen picks up on the other.
    async function renderPortfolio() {
        const el = panel('portfolio');
        if (typeof renderPortfolioLab !== 'function') {
            el.innerHTML = '<p class="mypage-empty">포트폴리오 계산기를 불러오지 못했습니다.</p>';
            return;
        }
        const token = renderToken;
        try {
            await renderPortfolioLab(el);
        } catch (err) {
            if (token !== renderToken) return;
            el.innerHTML = `<p class="mypage-empty">포트폴리오 계산기를 불러오지 못했습니다: ${esc(err.message)}</p>`;
        }
    }

    /* ------------------------------------------------------------ 개인정보 */

    async function renderAccount() {
        const el = panel('account');
        el.innerHTML = '<p class="mypage-empty">불러오는 중…</p>';
        const token = renderToken;
        let profile = null;
        try {
            profile = await window.Auth.myProfile();
        } catch (err) {
            if (token !== renderToken) return;
            el.innerHTML = `<p class="mypage-empty">불러오지 못했습니다: ${esc(err.message)}</p>`;
            return;
        }
        if (token !== renderToken || !profile) return;

        el.innerHTML = `
            <p class="mypage-section-title">계정 정보</p>
            <div class="mypage-field">
                <label>이메일 (변경 불가)</label>
                <input type="text" value="${esc(profile.email)}" disabled>
            </div>
            <div class="mypage-field">
                <label>회원번호</label>
                <input type="text" value="#${esc(profile.member_no)}" disabled>
            </div>
            <div class="mypage-field">
                <label>닉네임</label>
                <input type="text" id="mypage-nickname" value="${esc(profile.nickname || '')}" placeholder="닉네임 미설정" maxlength="30">
            </div>
            <button type="button" class="mypage-btn" id="mypage-save-nickname">닉네임 저장</button>
            <p class="mypage-status hidden" id="mypage-nickname-status"></p>

            <p class="mypage-section-title">비밀번호 변경</p>
            <div class="mypage-field">
                <label>새 비밀번호</label>
                <input type="password" id="mypage-new-password" minlength="6" autocomplete="new-password">
            </div>
            <div class="mypage-field">
                <label>새 비밀번호 확인</label>
                <input type="password" id="mypage-new-password-confirm" minlength="6" autocomplete="new-password">
            </div>
            <button type="button" class="mypage-btn" id="mypage-save-password">비밀번호 변경</button>
            <p class="mypage-status hidden" id="mypage-password-status"></p>

            <p class="mypage-section-title">회원 탈퇴</p>
            <p class="mypage-empty">회원 탈퇴 기능은 준비 중입니다. 필요하시면 문의해주세요.</p>
        `;

        const nicknameStatus = el.querySelector('#mypage-nickname-status');
        el.querySelector('#mypage-save-nickname').addEventListener('click', async (e) => {
            const btn = e.currentTarget;
            const value = el.querySelector('#mypage-nickname').value.trim();
            btn.disabled = true;
            nicknameStatus.className = 'mypage-status hidden';
            try {
                await window.Auth.updateNickname(value || null);
                nicknameStatus.textContent = '저장했습니다.';
                nicknameStatus.className = 'mypage-status is-ok';
            } catch (err) {
                nicknameStatus.textContent = err.message || '저장하지 못했습니다.';
                nicknameStatus.className = 'mypage-status is-error';
            } finally {
                btn.disabled = false;
            }
        });

        const passwordStatus = el.querySelector('#mypage-password-status');
        el.querySelector('#mypage-save-password').addEventListener('click', async (e) => {
            const btn = e.currentTarget;
            const pw = el.querySelector('#mypage-new-password').value;
            const pwConfirm = el.querySelector('#mypage-new-password-confirm').value;
            passwordStatus.className = 'mypage-status hidden';
            if (pw.length < 6) {
                passwordStatus.textContent = '6자 이상 입력해주세요.';
                passwordStatus.className = 'mypage-status is-error';
                return;
            }
            if (pw !== pwConfirm) {
                passwordStatus.textContent = '비밀번호가 서로 다릅니다.';
                passwordStatus.className = 'mypage-status is-error';
                return;
            }
            btn.disabled = true;
            try {
                await window.Auth.changePassword(pw);
                el.querySelector('#mypage-new-password').value = '';
                el.querySelector('#mypage-new-password-confirm').value = '';
                passwordStatus.textContent = '변경했습니다.';
                passwordStatus.className = 'mypage-status is-ok';
            } catch (err) {
                passwordStatus.textContent = err.message || '변경하지 못했습니다.';
                passwordStatus.className = 'mypage-status is-error';
            } finally {
                btn.disabled = false;
            }
        });
    }

    /* --------------------------------------------------------------- 진입 */

    function render(_target, surface) {
        if (!surface) return;
        renderToken += 1;
        loaded.clear();
        host = surface;
        surface.classList.remove('hidden');
        surface.innerHTML = shellHtml();

        // Subscribe before the signed-out return; initial session recovery and
        // login must also refresh a page opened before authentication finishes.
        if (!authSubscribed && window.Auth?.onChange) {
            authSubscribed = true;
            window.Auth.onChange(() => {
                if (host) render('mypage', host);
            });
        }
        const user = window.Auth?.currentUser?.();
        surface.querySelector('#mypage-identity').textContent = user
            ? user.email
            : '로그인이 필요합니다.';

        if (!user) {
            panel('favorites').classList.remove('hidden');
            panel('favorites').innerHTML = `
                <p class="mypage-empty">마이페이지를 이용하려면 로그인해주세요.</p>
                <button type="button" class="mypage-btn" id="mypage-login-btn">로그인 / 회원가입</button>`;
            surface.querySelector('#mypage-login-btn').addEventListener('click', () => window.Auth.openModal('signin'));
            return;
        }

        surface.querySelectorAll('.mypage-tab').forEach((btn) => {
            btn.addEventListener('click', () => setActiveTab(btn.dataset.tab));
        });
        setActiveTab('favorites');

    }

    let authSubscribed = false;

    function unmount(surface) {
        if (!surface) return;
        renderToken += 1;
        surface.innerHTML = '';
        host = null;
    }

    window.MyPage = { render, unmount };
})();

