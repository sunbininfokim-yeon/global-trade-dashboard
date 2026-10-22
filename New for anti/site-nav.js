// The main site's top navigation on a standalone page (indonesia-policy/).
// The menu is read from the site's own index.html, so a menu added there shows
// up here with no second copy to keep in step. Its in-app links
// (data-target, handled by app.js on the main page) become real paths, which
// the Worker's single-page fallback opens directly. If the fetch fails, the
// page keeps its plain fallback header.
(() => {
    const host = document.querySelector('header[data-site-nav]');
    if (!host) return;
    const pathFor = (target) => (target === 'home' ? '/' : target === 'us-policy-hub' ? '/policy/us' : `/${encodeURIComponent(target)}`);
    const sessionKey = () => {
        try {
            const ref = new URL(window.SUPABASE_URL).hostname.split('.')[0];
            return `sb-${ref}-auth-token`;
        } catch { return null; }
    };
    const signedInEmail = () => {
        const key = sessionKey();
        if (!key) return null;
        try {
            const raw = JSON.parse(localStorage.getItem(key) || 'null');
            const s = raw?.currentSession || raw;
            return s?.user ? (s.user.email || '로그인됨') : null;
        } catch { return null; }
    };

    function renderAuth(header) {
        const box = header.querySelector('#auth-container');
        const mypage = header.querySelector('#mypage-nav-item');
        if (!box) return;
        const email = signedInEmail();
        mypage?.classList.toggle('hidden', !email);
        box.replaceChildren();
        if (email) {
            const span = document.createElement('span');
            span.className = 'auth-email';
            span.textContent = email;
            box.append(span);
        } else {
            // A page with its own login form (the mail subscription card) signs
            // in right here; otherwise the main site's login.
            const local = document.querySelector('form[data-login-form]');
            const btn = document.createElement('a');
            btn.className = 'auth-btn';
            btn.textContent = '로그인';
            btn.href = local ? '#mail-subscriptions' : '/mypage';
            if (local) btn.addEventListener('click', (e) => {
                e.preventDefault();
                local.scrollIntoView({ behavior: 'smooth', block: 'center' });
                local.elements.email?.focus();
            });
            box.append(btn);
        }
    }

    async function mount() {
        const res = await fetch('/', { headers: { Accept: 'text/html' } });
        if (!res.ok) return;
        const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
        const header = doc.querySelector('header.top-nav');
        if (!header) return;
        header.querySelectorAll('script, .date-picker-container').forEach((n) => n.remove());

        const logo = header.querySelector('#home-logo');
        if (logo) {
            const a = document.createElement('a');
            a.className = 'logo';
            a.id = 'home-logo';
            a.href = '/';
            a.textContent = logo.textContent;
            logo.replaceWith(a);
        }
        header.querySelectorAll('a[data-target]').forEach((a) => {
            a.href = pathFor(a.dataset.target);
            a.removeAttribute('data-target');
        });
        const here = window.location.pathname.replace(/\/+$/, '/');
        header.querySelectorAll('.dropdown a[href]').forEach((a) => {
            if (a.getAttribute('href').replace(/\/+$/, '/') === here) a.classList.add('active');
        });

        const live = document.importNode(header, true);
        live.removeAttribute('id');
        // A top-level item opens its own default screen when clicked, as on the main page.
        live.querySelectorAll('.menu-item[data-nav-default]').forEach((item) => {
            const go = () => { window.location.href = pathFor(item.dataset.navDefault); };
            const parent = item.querySelector(':scope > .menu-parent');
            parent?.addEventListener('click', go);
            parent?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
            });
            const dropdown = item.querySelector(':scope > .dropdown');
            if (dropdown) item.addEventListener('mouseenter', () => {
                const rect = item.getBoundingClientRect();
                const left = Math.max(8, Math.min(rect.left, window.innerWidth - dropdown.offsetWidth - 8));
                dropdown.style.left = `${Math.round(left)}px`;
                dropdown.style.top = `${Math.round(rect.bottom)}px`;
            });
        });
        renderAuth(live);
        host.replaceWith(live);
        const refresh = () => renderAuth(live);
        window.addEventListener('storage', refresh);
        document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refresh(); });
        window.addEventListener('site-auth-changed', refresh);
    }

    mount().catch((err) => console.warn('[site-nav] main menu unavailable, keeping fallback header', err));
})();
