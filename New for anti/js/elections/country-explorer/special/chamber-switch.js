import { escapeHtml } from '../../ui.js';

// A CSS-only two-chamber switch. The modal body is inserted as a static HTML
// string with no per-render listeners, so both panels ship together and the
// checked radio decides which one shows.
//
// The slots are numbered rather than named after 하원/상원, because the same
// switch now carries 중의원·참의원 too. The radios stay focusable (clipped, not
// display:none) so arrow keys move between chambers the way a native tab list
// does.
//
// `chambers` is [{ label, panel }] -- exactly two, first one open.
export const chamberSwitch = (chambers) => `
    <div class="elections-chamber-switch">
        ${chambers.map((chamber, index) => `<input class="elections-chamber-radio" type="radio" name="elections-chamber" id="elections-chamber-${index + 1}"${index === 0 ? ' checked' : ''}>`).join('')}
        <div class="elections-chamber-tabs" role="tablist">
            ${chambers.map((chamber, index) => `<label for="elections-chamber-${index + 1}">${escapeHtml(chamber.label)}</label>`).join('')}
        </div>
        ${chambers.map((chamber, index) => `<div class="elections-chamber-panel" data-chamber-slot="${index + 1}">${chamber.panel}</div>`).join('')}
    </div>`;
