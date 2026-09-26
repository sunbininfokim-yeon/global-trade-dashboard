// Signup/login for ChokePoint Monitor, backed by Supabase Auth.
// Depends on auth-config.js (window.SUPABASE_URL / SUPABASE_ANON_KEY) and the
// Supabase JS CDN script being loaded before this file. Exposes window.Auth
// so other feature modules (favorites, alerts, portfolio) can check
// Auth.currentUser() without each re-deriving the session.

// Draft only -- not legal review. Covers what this project actually does
// today (email/password auth, favorites, digest email) so it doesn't
// promise anything the code doesn't do; update it if that scope changes.
const PRIVACY_POLICY_HTML = `
    <h4>수집하는 개인정보</h4>
    <p>이메일 주소, 비밀번호(Supabase Auth가 해시로 변환해 저장하며, 운영자를 포함해
    누구도 원문을 볼 수 없습니다), 닉네임(선택), 즐겨찾기·알림 설정 내역.
    실명은 수집하지 않습니다.</p>
    <h4>이용 목적</h4>
    <p>로그인 및 계정 식별, 즐겨찾기한 정책·원자재 리포트 변경사항의 이메일 알림 발송.</p>
    <h4>보유 기간</h4>
    <p>회원 탈퇴 시까지 보관하며, 탈퇴 시 지체 없이 삭제합니다.</p>
    <h4>제3자 제공</h4>
    <p>계정 인증·데이터 저장은 Supabase, 이메일 발송은 Resend를 이용하며, 이 목적 외
    제3자에게 제공하지 않습니다.</p>
    <h4>이용자 권리</h4>
    <p>마이페이지에서 언제든 본인 정보를 열람·수정할 수 있고, 회원 탈퇴로 즉시
    삭제를 요청할 수 있습니다.</p>
`;

const Auth = (() => {
    const client = window.supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);

    let session = null;
    const listeners = [];
    // Assigned when the modal is first built, so openModal('signup') can land
    // on the signup tab instead of the default signin one.
    let setModalMode = null;

    function notify() {
        listeners.forEach((fn) => fn(session));
    }

    client.auth.onAuthStateChange((event, newSession) => {
        session = newSession;
        renderAuthButton();
        notify();
        // Fires when the visitor lands back here from the reset-password
        // email link (Supabase parses the recovery token in the URL hash
        // and signs them into a session scoped for exactly this). Send
        // them straight to "set a new password" rather than the plain
        // login tab, which would otherwise leave them stuck not knowing
        // they're already authenticated.
        if (event === 'PASSWORD_RECOVERY') openModal('recovery');
    });

    async function init() {
        const { data } = await client.auth.getSession();
        session = data.session;
        renderAuthButton();
    }

    function currentUser() {
        return session ? session.user : null;
    }

    function onChange(fn) {
        listeners.push(fn);
    }

    // termsAgreedAt travels in options.data (-> auth.users.raw_user_meta_data)
    // rather than a follow-up write to profiles, because a signup that
    // requires email confirmation has no authenticated session yet for a
    // second call to run under. handle_new_user() reads it from there.
    async function signUp(email, password, termsAgreedAt) {
        const { data, error } = await client.auth.signUp({
            email,
            password,
            options: { data: { terms_agreed_at: termsAgreedAt } },
        });
        if (error) throw error;
        // Supabase deliberately returns 200 with no error for an email
        // that's already registered and confirmed -- no new mail goes out,
        // and the only tell is an empty identities array on the returned
        // user. Surfacing that here is a small, common enumeration
        // trade-off most sites accept for the much better "you already
        // have an account" UX instead of a silent, confusing no-op.
        if (data.user && data.user.identities && data.user.identities.length === 0) {
            throw new Error('이미 가입된 이메일입니다. 로그인해주세요.');
        }
        return data;
    }

    async function changePassword(newPassword) {
        const { error } = await client.auth.updateUser({ password: newPassword });
        if (error) throw error;
    }

    // 회원 탈퇴. Re-checks the password with the same call signIn uses -- so a
    // stolen/left-open session alone can't delete the account -- then hands a
    // fresh access token to the Worker, the only place holding the
    // service_role key needed to remove the auth.users row itself. Every
    // per-user table added this project (profiles, user_favorites,
    // commodity_digest_source_prefs, commodity_report_notifications)
    // references it `on delete cascade`, so that one deletion clears all of it.
    async function deleteAccount(password) {
        const user = currentUser();
        if (!user || !user.email) throw new Error('로그인이 필요합니다.');
        const { data, error } = await client.auth.signInWithPassword({ email: user.email, password });
        if (error) throw new Error('비밀번호가 올바르지 않습니다.');
        const token = data.session && data.session.access_token;
        if (!token) throw new Error('세션이 만료되었습니다. 다시 로그인해주세요.');

        const res = await fetch('/api/account/delete', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.error || '탈퇴 처리 중 오류가 발생했습니다.');

        await signOut();
    }

    // Sends a reset-password email; the link in it brings them back here
    // with a recovery session already established (see the
    // 'PASSWORD_RECOVERY' handler above), which is what actually lets
    // changePassword() run without knowing the old password.
    async function resetPasswordForEmail(email) {
        const { error } = await client.auth.resetPasswordForEmail(email, {
            redirectTo: window.location.origin + '/',
        });
        if (error) throw error;
    }

    async function myProfile() {
        const user = currentUser();
        if (!user) return null;
        const { data, error } = await client
            .from('profiles')
            .select('email,member_no,nickname,terms_agreed_at')
            .eq('id', user.id)
            .single();
        if (error) throw error;
        return data;
    }

    async function updateNickname(nickname) {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        const { error } = await client
            .from('profiles')
            .update({ nickname })
            .eq('id', user.id);
        if (error) throw error;
    }

    // --- bill/EO notification pause ---------------------------------------

    // A single account-wide flag rather than a per-favorite one: pausing
    // stops notify-favorites.js from emailing this user without touching
    // user_favorites, so favorites (and their change tracking) are untouched
    // and resuming doesn't dump a backlog of everything missed.
    async function billNotificationsPaused() {
        const user = currentUser();
        if (!user) return false;
        const { data, error } = await client
            .from('profiles')
            .select('bill_notifications_paused')
            .eq('id', user.id)
            .single();
        if (error) throw error;
        return !!(data && data.bill_notifications_paused);
    }

    async function setBillNotificationsPaused(paused) {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        const { error } = await client
            .from('profiles')
            .update({ bill_notifications_paused: paused })
            .eq('id', user.id);
        if (error) throw error;
    }

    async function signIn(email, password) {
        const { data, error } = await client.auth.signInWithPassword({ email, password });
        if (error) throw error;
        return data;
    }

    async function signOut() {
        await client.auth.signOut();
    }

    // --- favorites (즐겨찾기) --------------------------------------------

    // These go through the same anon-key client the session belongs to, so
    // Postgres sees the caller's JWT and RLS scopes every row to auth.uid().
    // The Worker is deliberately not in this path: it holds the service_role
    // key, which would bypass that filter entirely.

    async function listFavorites() {
        if (!currentUser()) return [];
        const { data, error } = await client
            .from('user_favorites')
            .select('item_kind,item_id,title,created_at,notify_enabled')
            .order('created_at', { ascending: false });
        if (error) throw error;
        return data || [];
    }

    async function addFavorite(itemKind, itemId, title) {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        const { error } = await client
            .from('user_favorites')
            .upsert({ user_id: user.id, item_kind: itemKind, item_id: itemId, title: title || null });
        if (error) throw error;
    }

    async function removeFavorite(itemKind, itemId) {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        const { error } = await client
            .from('user_favorites')
            .delete()
            .match({ user_id: user.id, item_kind: itemKind, item_id: itemId });
        if (error) throw error;
    }

    // Per-favorite mail mute, separate from the account-wide
    // billNotificationsPaused switch above -- this keeps the item favorited
    // (still shown, still tracked) while notify-favorites.js skips just it.
    async function setFavoriteNotifyEnabled(itemKind, itemId, enabled) {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        const { error } = await client
            .from('user_favorites')
            .update({ notify_enabled: enabled })
            .match({ user_id: user.id, item_kind: itemKind, item_id: itemId });
        if (error) throw error;
    }

    // --- commodity digest source filter -----------------------------------

    // A row here means that source is turned OFF, not on -- so a user who
    // never opens this settings screen gets every source by default, and a
    // source id can't disappear from someone's mail just because the My
    // Page checkbox list forgot to render it. Build the checkbox list from
    // commodity_reports_v1.json's own source ids and check every box that
    // ISN'T in listDisabledCommoditySources().
    async function listDisabledCommoditySources() {
        if (!currentUser()) return [];
        const { data, error } = await client
            .from('commodity_digest_source_prefs')
            .select('source_id');
        if (error) throw error;
        return (data || []).map((r) => r.source_id);
    }

    function escSourceLabel(value) {
        return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    // groups: [{key, label, sources: [{source_id, agency, agency_ko}]}], built
    // by the caller from commodity_reports_v1.json's own items (never a fixed
    // list, so a commodity or source added/dropped from the pipeline shows up
    // -- or disappears -- here without a UI change). One wide box per
    // commodity; the same source can appear in more than one box (e.g. EIA
    // covers both oil and gas), so its checkbox state is kept in sync across
    // every box it shows up in by bindCommoditySourceFilter below.
    //
    // favoritedKeys: Set of commodity keys with a user_favorites row
    // (item_kind 'commodity'). notify-commodity-digest.js only mails
    // favorited commodities in the first place -- the source checkboxes
    // inside a box only matter once that box's own commodity is favorited --
    // so each header gets its own checkbox for that, not just a static label.
    function commoditySourceFilterHtml(groups, disabledIds, favoritedKeys) {
        const disabled = new Set(disabledIds);
        const favorited = favoritedKeys || new Set();
        return groups.map(({ key, label, sources }) => {
            // Two sources under the same commodity can share one agency code
            // (e.g. two different EIA feeds both covering oil) -- append the
            // source id itself as a generic, always-correct tie-breaker
            // rather than hand-maintaining a feed-name lookup per source.
            const codeCounts = new Map();
            sources.forEach(({ agency, agency_ko, source_id }) => {
                const code = agency || agency_ko || source_id;
                codeCounts.set(code, (codeCounts.get(code) || 0) + 1);
            });
            const rows = sources.map(({ source_id, agency, agency_ko }) => {
                const code = agency || agency_ko || source_id;
                const text = codeCounts.get(code) > 1 ? `${code} (${source_id})` : code;
                return `
                <label class="commodity-source-check" title="${escSourceLabel(agency_ko || agency || source_id)}">
                    <input type="checkbox" class="source-filter-checkbox" data-source-id="${escSourceLabel(source_id)}" ${disabled.has(source_id) ? '' : 'checked'}>
                    <span class="source-filter-label">${escSourceLabel(text)}</span>
                </label>`;
            }).join('');
            return `
            <div class="commodity-source-group">
                <div class="commodity-source-header">
                    <label class="commodity-fav-check" title="즐겨찾기하지 않은 원자재는 다이제스트에 포함되지 않습니다">
                        <input type="checkbox" class="commodity-fav-checkbox" data-commodity-key="${escSourceLabel(key)}" data-commodity-label="${escSourceLabel(label)}" ${favorited.has(key) ? 'checked' : ''}>
                        ${escSourceLabel(label)}
                    </label>
                </div>
                <div class="commodity-source-checks">${rows}</div>
            </div>`;
        }).join('');
    }

    // Attach once; toggling favorites this commodity for the weekly digest
    // (notify-commodity-digest.js reads user_favorites where item_kind is
    // 'commodity' and mails nothing for a commodity that isn't in it).
    function bindCommodityFavoriteFilter(container) {
        container.addEventListener('change', async (e) => {
            const checkbox = e.target.closest('.commodity-fav-checkbox');
            if (!checkbox) return;
            const key = checkbox.dataset.commodityKey;
            const label = checkbox.dataset.commodityLabel;
            checkbox.disabled = true;
            try {
                if (checkbox.checked) await addFavorite('commodity', key, label);
                else await removeFavorite('commodity', key);
            } catch (err) {
                checkbox.checked = !checkbox.checked; // roll back the click on a failed write
                console.error('Failed to update commodity favorite:', err);
            } finally {
                checkbox.disabled = false;
            }
        });
    }

    // Attach once to the list's container; delegates so re-rendering the
    // rows (e.g. after commoditySourceFilterHtml runs again) never leaves a
    // stale listener on a removed checkbox. The same source_id can appear in
    // several commodity boxes, so a click also syncs every other checkbox
    // sharing that source_id -- otherwise toggling it in one box would leave
    // a stale, contradictory state showing in the others.
    function bindCommoditySourceFilter(container) {
        container.addEventListener('change', async (e) => {
            const checkbox = e.target.closest('.source-filter-checkbox');
            if (!checkbox) return;
            const sourceId = checkbox.dataset.sourceId;
            const siblings = [...container.querySelectorAll(`.source-filter-checkbox[data-source-id="${CSS.escape(sourceId)}"]`)];
            siblings.forEach((box) => { box.checked = checkbox.checked; });
            try {
                await setCommoditySourceEnabled(sourceId, checkbox.checked);
            } catch (err) {
                siblings.forEach((box) => { box.checked = !checkbox.checked; }); // roll back the click on a failed write
                console.error('Failed to update commodity source preference:', err);
            }
        });
    }

    async function setCommoditySourceEnabled(sourceId, enabled) {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        if (enabled) {
            const { error } = await client
                .from('commodity_digest_source_prefs')
                .delete()
                .match({ user_id: user.id, source_id: sourceId });
            if (error) throw error;
        } else {
            const { error } = await client
                .from('commodity_digest_source_prefs')
                .upsert({ user_id: user.id, source_id: sourceId });
            if (error) throw error;
        }
    }

    // --- UI: nav button + modal -----------------------------------------

    function renderAuthButton() {
        const container = document.getElementById('auth-container');
        if (!container) return;
        const user = currentUser();
        document.getElementById('mypage-nav-item')?.classList.toggle('hidden', !user);
        if (user) {
            container.innerHTML = `
                <span class="auth-email" title="${user.email}">${user.email}</span>
                <button type="button" class="auth-btn" id="auth-logout-btn">로그아웃</button>
            `;
            document.getElementById('auth-logout-btn').addEventListener('click', async () => {
                await signOut();
            });
        } else {
            container.innerHTML = `<button type="button" class="auth-btn" id="auth-open-btn">로그인 / 회원가입</button>`;
            document.getElementById('auth-open-btn').addEventListener('click', () => openModal());
        }
    }

    function ensureModal() {
        if (document.getElementById('auth-modal')) return;
        const modal = document.createElement('div');
        modal.id = 'auth-modal';
        modal.className = 'auth-modal hidden';
        modal.innerHTML = `
            <div class="auth-modal-backdrop"></div>
            <div class="auth-modal-box">
                <button type="button" class="auth-modal-close" aria-label="닫기">&times;</button>
                <div class="auth-tabs" id="auth-tabs">
                    <button type="button" class="auth-tab active" data-tab="signin">로그인</button>
                    <button type="button" class="auth-tab" data-tab="signup">회원가입</button>
                </div>
                <p class="auth-modal-title hidden" id="auth-modal-title"></p>
                <form id="auth-form" class="auth-form">
                    <label data-modes="signin,signup,forgot">이메일<input type="email" id="auth-email" autocomplete="email"></label>
                    <label data-modes="signin,signup,recovery"><span id="auth-password-label">비밀번호</span><input type="password" id="auth-password" autocomplete="current-password" minlength="6"></label>
                    <label data-modes="signup,recovery">비밀번호 확인<input type="password" id="auth-password-confirm" autocomplete="new-password" minlength="6"></label>
                    <p class="auth-hint" data-modes="signup,recovery">다른 사이트에서 쓰시는 비밀번호는 재사용하지 않는 걸 권장드립니다.</p>
                    <div class="auth-consent-row" data-modes="signup">
                        <input type="checkbox" id="auth-consent">
                        <label for="auth-consent">(필수) 이용약관 및 개인정보처리방침에 동의합니다</label>
                        <button type="button" class="auth-policy-link" id="auth-policy-toggle">보기</button>
                    </div>
                    <div class="auth-policy-text hidden" id="auth-policy-text">${PRIVACY_POLICY_HTML}</div>
                    <button type="button" class="auth-policy-link" data-modes="signin" id="auth-forgot-link">비밀번호를 잊으셨나요?</button>
                    <button type="button" class="auth-policy-link" data-modes="forgot" id="auth-back-link">← 로그인으로 돌아가기</button>
                    <p class="auth-error hidden" id="auth-error"></p>
                    <p class="auth-notice hidden" id="auth-notice"></p>
                    <button type="submit" class="auth-submit-btn" id="auth-submit-btn">로그인</button>
                </form>
            </div>
        `;
        document.body.appendChild(modal);

        let mode = 'signin';
        const tabs = modal.querySelectorAll('.auth-tab');
        const submitBtn = modal.querySelector('#auth-submit-btn');
        const errorEl = modal.querySelector('#auth-error');
        const noticeEl = modal.querySelector('#auth-notice');

        const modeEls = modal.querySelectorAll('[data-modes]');
        const consentCheckbox = modal.querySelector('#auth-consent');
        const passwordConfirm = modal.querySelector('#auth-password-confirm');
        const policyText = modal.querySelector('#auth-policy-text');
        const tabsBar = modal.querySelector('#auth-tabs');
        const titleEl = modal.querySelector('#auth-modal-title');
        const passwordLabel = modal.querySelector('#auth-password-label');

        const SUBMIT_LABEL = { signin: '로그인', signup: '회원가입', forgot: '재설정 메일 보내기', recovery: '비밀번호 재설정' };
        const TITLE = { forgot: '비밀번호 재설정', recovery: '새 비밀번호 설정' };

        function setMode(next) {
            mode = next;
            tabs.forEach((t) => t.classList.toggle('active', t.dataset.tab === mode));
            tabsBar.classList.toggle('hidden', mode === 'forgot' || mode === 'recovery');
            if (TITLE[mode]) {
                titleEl.textContent = TITLE[mode];
                titleEl.classList.remove('hidden');
            } else {
                titleEl.classList.add('hidden');
            }
            passwordLabel.textContent = mode === 'recovery' ? '새 비밀번호' : '비밀번호';
            submitBtn.textContent = SUBMIT_LABEL[mode];
            modeEls.forEach((el) => el.classList.toggle('hidden', !el.dataset.modes.split(',').includes(mode)));
            policyText.classList.add('hidden');
            errorEl.classList.add('hidden');
            noticeEl.classList.add('hidden');
        }

        tabs.forEach((t) => t.addEventListener('click', () => setMode(t.dataset.tab)));
        setModalMode = setMode;

        modal.querySelector('.auth-modal-close').addEventListener('click', closeModal);
        modal.querySelector('.auth-modal-backdrop').addEventListener('click', closeModal);
        modal.querySelector('#auth-policy-toggle').addEventListener('click', () => {
            policyText.classList.toggle('hidden');
        });
        modal.querySelector('#auth-forgot-link').addEventListener('click', () => setMode('forgot'));
        modal.querySelector('#auth-back-link').addEventListener('click', () => setMode('signin'));

        modal.querySelector('#auth-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            errorEl.classList.add('hidden');
            noticeEl.classList.add('hidden');
            const email = modal.querySelector('#auth-email').value.trim();
            const password = modal.querySelector('#auth-password').value;

            if (mode === 'forgot' && !email) {
                errorEl.textContent = '이메일을 입력해주세요.';
                errorEl.classList.remove('hidden');
                return;
            }
            if (mode === 'recovery' && password.length < 6) {
                errorEl.textContent = '6자 이상 입력해주세요.';
                errorEl.classList.remove('hidden');
                return;
            }
            if ((mode === 'signup' || mode === 'recovery') && password !== passwordConfirm.value) {
                errorEl.textContent = '비밀번호가 서로 다릅니다.';
                errorEl.classList.remove('hidden');
                return;
            }
            if (mode === 'signup' && !consentCheckbox.checked) {
                errorEl.textContent = '이용약관 및 개인정보처리방침에 동의해주세요.';
                errorEl.classList.remove('hidden');
                return;
            }

            submitBtn.disabled = true;
            try {
                if (mode === 'signin') {
                    await signIn(email, password);
                    closeModal();
                } else if (mode === 'signup') {
                    await signUp(email, password, new Date().toISOString());
                    noticeEl.textContent = '가입 확인 메일을 보냈습니다. 메일함을 확인해주세요.';
                    noticeEl.classList.remove('hidden');
                } else if (mode === 'forgot') {
                    await resetPasswordForEmail(email);
                    noticeEl.textContent = '비밀번호 재설정 메일을 보냈습니다. 메일함을 확인해주세요.';
                    noticeEl.classList.remove('hidden');
                } else if (mode === 'recovery') {
                    await changePassword(password);
                    noticeEl.textContent = '비밀번호를 변경했습니다.';
                    noticeEl.classList.remove('hidden');
                }
            } catch (err) {
                errorEl.textContent = err.message || '오류가 발생했습니다.';
                errorEl.classList.remove('hidden');
            } finally {
                submitBtn.disabled = false;
            }
        });
    }

    // mode: 'signin' (the nav button), 'signup' (a gated feature sends a
    // logged-out user straight there), or 'recovery' (the reset-password
    // email link lands back here already authenticated -- see the
    // PASSWORD_RECOVERY handler above).
    function openModal(mode = 'signin') {
        ensureModal();
        if (setModalMode) setModalMode(mode);
        document.getElementById('auth-modal').classList.remove('hidden');
    }

    function closeModal() {
        const modal = document.getElementById('auth-modal');
        if (modal) modal.classList.add('hidden');
    }

    init();

    return {
        currentUser, onChange, signUp, signIn, signOut, openModal,
        listFavorites, addFavorite, removeFavorite, setFavoriteNotifyEnabled,
        listDisabledCommoditySources, setCommoditySourceEnabled,
        commoditySourceFilterHtml, bindCommoditySourceFilter, bindCommodityFavoriteFilter,
        changePassword, deleteAccount, myProfile, updateNickname, resetPasswordForEmail,
        billNotificationsPaused, setBillNotificationsPaused,
    };
})();

// A bare `const` in a classic script stays in script scope and never reaches
// window, so feature modules asking for window.Auth (the contract this file's
// header promises) would have found undefined.
window.Auth = Auth;
