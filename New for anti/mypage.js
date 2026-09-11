// My Page: 즐겨찾기 / 메일링 서비스 / 포트폴리오 / 개인정보수정.
// Basic scaffold -- structure, routing, and the backend calls are wired up;
// depth (richer favorite cards, spreadsheet upload for the portfolio tab,
// other richer account features) is left for follow-up work. Mailing preference
// toggles are live through the mailing_preferences contract. Reads window.Auth (auth.js), window.USPolicy
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
        const others = favorites.filter((f) => f.item_kind !== 'bill');

        el.innerHTML = `
            ${bills.length ? '<p class="mypage-section-title">법안</p><div class="policy-bill-list" id="mypage-fav-bills"></div>' : ''}
            ${others.length ? '<p class="mypage-section-title">그 외</p><div class="policy-bill-list" id="mypage-fav-others"></div>' : ''}
        `;

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
            const container = el.querySelector('#mypage-fav-bills');
            container.innerHTML = bills.map((f) => `<div class="policy-fav-bill-card" data-bill-id="${esc(f.item_id)}"><p class="mypage-empty">불러오는 중…</p></div>`).join('');
            // One request per favorited bill -- fine at favorites-list scale;
            // revisit with a batch endpoint if this list grows large.
            bills.forEach(async (f) => {
                const card = container.querySelector(`[data-bill-id="${CSS.escape(f.item_id)}"]`);
                try {
                    const bill = await window.USPolicy.loadBillById(f.item_id);
                    if (token !== renderToken || !card) return;
                    card.outerHTML = window.USPolicy.favoriteBillCardHtml(bill);
                } catch (err) {
                    if (card) card.innerHTML = `<p class="mypage-empty">불러오지 못함: ${esc(f.title || f.item_id)}</p>`;
                }
            });
        }
    }

    /* -------------------------------------------------------- 메일링 서비스 */

    async function renderMailing() {
        const el = panel('mailing');
        el.innerHTML = `
            <p class="mypage-section-title">법안·행정명령</p>
            <label><input type="checkbox" data-mail-kind="policy" disabled> 정책 변경 메일 수신</label>
            <p class="mypage-empty">즐겨찾기한 법안의 단계 변경을 서비스에서 확인하면 다음 날 오전 6시부터 발송하며, 오전 7시 전까지 재시도합니다(한국 시간). 행정명령의 공식 요약 변경도 포함됩니다. 원문 수집이나 메일 서비스가 지연되면 늦게 도착할 수 있습니다.</p>
            <p class="mypage-section-title">원자재</p>
            <label><input type="checkbox" data-mail-kind="commodity" disabled> 주간 원자재 보고서 메일 수신</label>
            <p class="mypage-empty">즐겨찾기한 원자재의 새 보고서를 매주 월요일 오전 8시부터 발송합니다(한국 시간).</p>
            <p id="mypage-mail-status" role="status" aria-live="polite">수신 설정을 불러오는 중…</p>
            <div id="mypage-source-filter"><p class="mypage-empty">불러오는 중…</p></div>
            <p class="mypage-section-title">시장 미시구조</p>
            <p class="mypage-empty">준비 중입니다.</p>
        `;
        const token = renderToken;
        const container = el.querySelector('#mypage-source-filter');
        // Settings stay usable even if the independent report/source request fails.
        const status = el.querySelector('#mypage-mail-status');
        window.Auth.mailingPreferences().then((prefs) => {
            if (token !== renderToken) return;
            status.textContent = '인증을 완료한 로그인 이메일로 발송됩니다.';
            el.querySelectorAll('[data-mail-kind]').forEach((input) => {
                input.checked = prefs[`${input.dataset.mailKind}_enabled`];
                input.disabled = false;
                input.addEventListener('change', async () => {
                    const desired = input.checked;
                    input.disabled = true;
                    try {
                        await window.Auth.setMailingPreference(input.dataset.mailKind, desired);
                        if (token === renderToken) status.textContent = '수신 설정을 저장했습니다.';
                    } catch (_) {
                        input.checked = !desired;
                        if (token === renderToken) status.textContent = '저장하지 못했습니다. 다시 시도해주세요.';
                    } finally {
                        input.disabled = false;
                    }
                });
            });
        }).catch(() => {
            if (token === renderToken) status.textContent = '수신 설정을 불러오지 못했습니다. 잠시 후 다시 열어주세요.';
        });
        try {
            const [reportsRes, disabled] = await Promise.all([
                fetch('/public/data/commodity_reports_v1.json', { cache: 'no-cache' }).then((r) => r.json()),
                window.Auth.listDisabledCommoditySources(),
            ]);
            if (token !== renderToken) return;
            const bySource = new Map();
            (reportsRes.items || []).forEach((item) => {
                if (!bySource.has(item.source_id)) bySource.set(item.source_id, item.agency_ko || item.agency || item.source_id);
            });
            const sources = [...bySource.entries()].map(([source_id, agency_ko]) => ({ source_id, agency_ko }));
            if (!sources.length) {
                container.innerHTML = '<p class="mypage-empty">현재 연동된 원자재 소스가 없습니다.</p>';
                return;
            }
            container.innerHTML = window.Auth.commoditySourceFilterHtml(sources, disabled);
            window.Auth.bindCommoditySourceFilter(container);
        } catch (err) {
            if (token !== renderToken) return;
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

        // A login/logout elsewhere while this screen is open should not
        // leave a stale signed-out (or wrong account's) view up.
        if (!authSubscribed) {
            authSubscribed = true;
            window.Auth?.onChange?.(() => {
                if (host === surface) render(_target, surface);
            });
        }
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
