// Signup/login for ChokePoint Monitor, backed by Supabase Auth.
// Depends on auth-config.js (window.SUPABASE_URL / SUPABASE_ANON_KEY) and the
// Supabase JS CDN script being loaded before this file. Exposes window.Auth
// so other feature modules (favorites, alerts, portfolio) can check
// Auth.currentUser() without each re-deriving the session.

const Auth = (() => {
    const client = window.supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);

    let session = null;
    const listeners = [];

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

    function currentUser() {
        return session ? session.user : null;
    }

    function onChange(fn) {
        listeners.push(fn);
    }

    async function signUp(email, password) {
        const { data, error } = await client.auth.signUp({ email, password });
        if (error) throw error;
        return data;
    }

    async function signIn(email, password) {
        const { data, error } = await client.auth.signInWithPassword({ email, password });
        if (error) throw error;
        return data;
    }

    async function signOut() {
        await client.auth.signOut();
    }

    // --- UI: nav button + modal -----------------------------------------

    function renderAuthButton() {
        const container = document.getElementById('auth-container');
        if (!container) return;
        const user = currentUser();
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

        function setMode(next) {
            mode = next;
            tabs.forEach((t) => t.classList.toggle('active', t.dataset.tab === mode));
            submitBtn.textContent = mode === 'signin' ? '로그인' : '회원가입';
            errorEl.classList.add('hidden');
            noticeEl.classList.add('hidden');
        }

        tabs.forEach((t) => t.addEventListener('click', () => setMode(t.dataset.tab)));

        modal.querySelector('.auth-modal-close').addEventListener('click', closeModal);
        modal.querySelector('.auth-modal-backdrop').addEventListener('click', closeModal);

        modal.querySelector('#auth-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            errorEl.classList.add('hidden');
            noticeEl.classList.add('hidden');
            const email = modal.querySelector('#auth-email').value.trim();
            const password = modal.querySelector('#auth-password').value;
            submitBtn.disabled = true;
            try {
                if (mode === 'signin') {
                    await signIn(email, password);
                    closeModal();
                } else {
                    await signUp(email, password);
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

    function openModal() {
        ensureModal();
        document.getElementById('auth-modal').classList.remove('hidden');
    }

    function closeModal() {
        const modal = document.getElementById('auth-modal');
        if (modal) modal.classList.add('hidden');
    }

    init();

    return { currentUser, onChange, signUp, signIn, signOut };
})();
