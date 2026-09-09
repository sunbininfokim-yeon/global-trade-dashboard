import { escapeHtml } from './ui.js';

// A centred window over the map, for the country blocks whose contents are too
// long for the right pane -- cabinets, chamber rosters, the CMC and theatre
// commands.  It mounts inside .map-pane rather than the viewport so it covers
// the map and nothing else: the nav, the ticker and the right pane stay usable.
const FOCUSABLE = 'button, [href], summary, input, select, textarea, [tabindex]:not([tabindex="-1"])';

// The legacy shell rebuilds its adapter every time the user returns to this
// view, so createModal runs again against the same element.  One controller per
// element, cached here, keeps the key and click handlers from stacking up.
const controllers = new WeakMap();

export const createModal = (hostEl) => {
    if (!hostEl) return null;
    if (controllers.has(hostEl)) return controllers.get(hostEl);

    let lastFocus = null;
    let onCloseHook = null;
    let onActionHook = null;

    const isOpen = () => !hostEl.classList.contains('hidden');

    const close = () => {
        if (!isOpen()) return;
        hostEl.classList.add('hidden');
        hostEl.innerHTML = '';
        // Returning focus to the block that opened the window keeps keyboard
        // users where they were instead of dropping them at the top of the page.
        if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
        lastFocus = null;
        onActionHook = null;
        const hook = onCloseHook;
        onCloseHook = null;
        hook?.();
    };

    const onKeyDown = (event) => {
        if (!isOpen()) return;
        if (event.key === 'Escape') {
            event.stopPropagation();
            close();
            return;
        }
        if (event.key !== 'Tab') return;
        const focusable = [...hostEl.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    };

    hostEl.addEventListener('keydown', onKeyDown);
    hostEl.addEventListener('click', (event) => {
        // Body content is inserted as an HTML string, so anything inside it
        // that needs to act announces itself with data-election-action and is
        // handled here rather than by wiring listeners per render.
        const action = event.target.closest?.('[data-election-action]');
        if (action && hostEl.contains(action)) {
            onActionHook?.(action.dataset.electionAction, action.dataset);
            return;
        }
        if (event.target === hostEl || event.target.hasAttribute?.('data-election-modal-close')) close();
    });

    const open = ({ title, subtitle = '', status = '', body = '', footnote = '', onClose = null, onAction = null }) => {
        lastFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        onCloseHook = onClose;
        onActionHook = onAction;
        hostEl.innerHTML = `
            <div class="elections-modal" role="dialog" aria-modal="true" aria-labelledby="elections-modal-title">
                <header class="elections-modal-head">
                    <div class="elections-modal-heading">
                        <h3 id="elections-modal-title">${escapeHtml(title)}</h3>
                        ${subtitle || status ? `<p class="elections-modal-sub">${escapeHtml([subtitle, status].filter(Boolean).join(' · '))}</p>` : ''}
                    </div>
                    <button class="elections-modal-close" type="button" data-election-modal-close aria-label="닫기">✕</button>
                </header>
                <div class="elections-modal-body">
                    ${body}
                    ${footnote ? `<p class="elections-panel-note">${escapeHtml(footnote)}</p>` : ''}
                </div>
            </div>`;
        hostEl.classList.remove('hidden');
        hostEl.querySelector('.elections-modal-close')?.focus();
    };

    const api = { open, close, isOpen };
    controllers.set(hostEl, api);
    return api;
};
