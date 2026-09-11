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
    <p>이메일 주소, 비밀번호(암호화 저장), 닉네임(선택), 즐겨찾기·알림 설정 내역.
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

    client.auth.onAuthStateChange((_event, newSession) => {
        session = newSession;
        renderAuthButton();
        notify();
    });

    async function init() {
        const { data } = await client.auth.getSession();
        session = data.session;
        renderAuthButton();
    }

    async function mailingPreferences() {
        const user = currentUser();
        if (!user) throw new Error('로그인이 필요합니다.');
        const { data, error } = await client.from('mailing_preferences')
            .select('policy_enabled,commodity_enabled').eq('user_id', user.id).maybeSingle();
        if (error) throw error;
        return data || { policy_enabled: true, commodity_enabled: true };
    }

    async function setMailingPreference(kind, enabled) {
        if (!currentUser()) throw new Error('로그인이 필요합니다.');
        if (!['policy', 'commodity'].includes(kind) || typeof enabled !== 'boolean') {
            throw new Error('수신 설정 값이 올바르지 않습니다.');
        }
        const { error } = await client.rpc('set_my_mailing_preference', { p_kind: kind, p_enabled: enabled });
        if (error) throw error;
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
        return data;
    }

    async function changePassword(newPassword) {
        const { error } = await client.auth.updateUser({ password: newPassword });
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
            .select('item_kind,item_id,title,created_at')
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

    // sources: [{source_id, agency_ko}], deduped from commodity_reports_v1.json's
    // own items -- never a fixed list, so a source added or dropped from the
    // pipeline shows up (or disappears) here without a UI change.
    function commoditySourceFilterHtml(sources, disabledIds) {
        const disabled = new Set(disabledIds);
        return sources.map(({ source_id, agency_ko }) => `
            <label class="source-filter-row">
                <input type="checkbox" class="source-filter-checkbox" data-source-id="${escSourceLabel(source_id)}" ${disabled.has(source_id) ? '' : 'checked'}>
                <span class="source-filter-label">${escSourceLabel(agency_ko || source_id)}</span>
            </label>`).join('');
    }

    // Attach once to the list's container; delegates so re-rendering the
    // rows (e.g. after commoditySourceFilterHtml runs again) never leaves a
    // stale listener on a removed checkbox.
    function bindCommoditySourceFilter(container) {
        container.addEventListener('change', async (e) => {
            const checkbox = e.target.closest('.source-filter-checkbox');
            if (!checkbox) return;
            try {
                await setCommoditySourceEnabled(checkbox.dataset.sourceId, checkbox.checked);
            } catch (err) {
                checkbox.checked = !checkbox.checked; // roll back the click on a failed write
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
            document.getElementById('auth-open-btn').addEventListener('click', openModal);
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
                <div class="auth-tabs">
                    <button type="button" class="auth-tab active" data-tab="signin">로그인</button>
                    <button type="button" class="auth-tab" data-tab="signup">회원가입</button>
                </div>
                <form id="auth-form" class="auth-form">
                    <label>이메일<input type="email" id="auth-email" required autocomplete="email"></label>
                    <label>비밀번호<input type="password" id="auth-password" required autocomplete="current-password" minlength="6"></label>
                    <label class="signup-only hidden">비밀번호 확인<input type="password" id="auth-password-confirm" autocomplete="new-password" minlength="6"></label>
                    <p class="auth-hint signup-only hidden">다른 사이트에서 쓰시는 비밀번호는 재사용하지 않는 걸 권장드립니다.</p>
                    <div class="auth-consent-row signup-only hidden">
                        <input type="checkbox" id="auth-consent">
                        <label for="auth-consent">(필수) 이용약관 및 개인정보처리방침에 동의합니다</label>
                        <button type="button" class="auth-policy-link" id="auth-policy-toggle">보기</button>
                    </div>
                    <div class="auth-policy-text hidden" id="auth-policy-text">${PRIVACY_POLICY_HTML}</div>
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

        const signupOnlyEls = modal.querySelectorAll('.signup-only');
        const consentCheckbox = modal.querySelector('#auth-consent');
        const passwordConfirm = modal.querySelector('#auth-password-confirm');
        const policyText = modal.querySelector('#auth-policy-text');

        function setMode(next) {
            mode = next;
            tabs.forEach((t) => t.classList.toggle('active', t.dataset.tab === mode));
            submitBtn.textContent = mode === 'signin' ? '로그인' : '회원가입';
            signupOnlyEls.forEach((el) => el.classList.toggle('hidden', mode !== 'signup'));
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

        modal.querySelector('#auth-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            errorEl.classList.add('hidden');
            noticeEl.classList.add('hidden');
            const email = modal.querySelector('#auth-email').value.trim();
            const password = modal.querySelector('#auth-password').value;

            if (mode === 'signup') {
                if (password !== passwordConfirm.value) {
                    errorEl.textContent = '비밀번호가 서로 다릅니다.';
                    errorEl.classList.remove('hidden');
                    return;
                }
                if (!consentCheckbox.checked) {
                    errorEl.textContent = '이용약관 및 개인정보처리방침에 동의해주세요.';
                    errorEl.classList.remove('hidden');
                    return;
                }
            }

            submitBtn.disabled = true;
            try {
                if (mode === 'signin') {
                    await signIn(email, password);
                    closeModal();
                } else {
                    await signUp(email, password, new Date().toISOString());
                    noticeEl.textContent = '가입 확인 메일을 보냈습니다. 메일함을 확인해주세요.';
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

    // mode: 'signin' (the nav button) or 'signup' -- a gated feature sends a
    // logged-out user straight to the signup tab rather than making them find
    // it themselves.
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
        listFavorites, addFavorite, removeFavorite,
        listDisabledCommoditySources, setCommoditySourceEnabled,
        commoditySourceFilterHtml, bindCommoditySourceFilter,
        changePassword, myProfile, updateNickname,
        mailingPreferences, setMailingPreference,
    };
})();

// A bare `const` in a classic script stays in script scope and never reaches
// window, so feature modules asking for window.Auth (the contract this file's
// header promises) would have found undefined.
window.Auth = Auth;
