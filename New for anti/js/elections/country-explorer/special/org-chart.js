import { escapeHtml } from '../../ui.js';

// The box vocabulary every 행정부 org chart draws with. Built for the EOP
// screen, then shared: 일본 내각 and 중국 당·국가 체제 are the same picture with
// different tiers, and a shared box is what keeps them looking like one
// dashboard rather than three.

export const card = (label, value, note = '') => `
    <article class="elections-card">
        <div class="elections-card-label">${escapeHtml(label)}</div>
        <div class="elections-card-value">${escapeHtml(value || '명단 수집 예정')}</div>
        ${note ? `<div class="elections-event-meta">${escapeHtml(note)}</div>` : ''}
    </article>`;

// One box per body, laid out side by side like a printed org chart's rows
// rather than as full-width rows. The person line is pushed to the bottom of
// the box so it lands on the same baseline across a row of uneven name lengths.
//
// `strike` marks a name the source itself struck through (중국 실각·조사자).
// An empty person renders "명단 수집 예정" -- never a guess, and never to be
// read as "이 자리는 공석".
export const orgBox = ({
    abbr, ko, en, title, person, note, strike = false, vacant = false,
    commissar, commissarTitle, commissarStrike = false, former,
}) => `
    <article class="elections-org-box">
        <div class="elections-org-box-ko">${escapeHtml(ko)}</div>
        ${abbr ? `<div class="elections-org-box-abbr">${escapeHtml(abbr)}</div>` : ''}
        ${en ? `<div class="elections-org-box-en">${escapeHtml(en)}</div>` : ''}
        <div class="elections-org-box-person${person ? '' : ' is-empty'}${person && strike ? ' is-fallen' : ''}${person && vacant ? ' is-vacant' : ''}">
            ${person && title ? `<span class="elections-org-box-title">${escapeHtml(title)}</span>` : ''}
            ${escapeHtml(person || '명단 수집 예정')}
        </div>
        ${commissar ? `<div class="elections-org-box-person is-second${commissarStrike ? ' is-fallen' : ''}">
            ${commissarTitle ? `<span class="elections-org-box-title">${escapeHtml(commissarTitle)}</span>` : ''}
            ${escapeHtml(commissar)}
        </div>` : ''}
        ${former && former.length ? `<div class="elections-org-box-former">전임 <s>${escapeHtml(former.join(' · '))}</s></div>` : ''}
        ${note ? `<div class="elections-org-box-note">${escapeHtml(note)}</div>` : ''}
    </article>`;

export const orgGrid = (boxes) => `<div class="elections-org-grid">${boxes.join('')}</div>`;

export const rowList = (rows) => `<div class="elections-disclosure-rows">${rows.join('')}</div>`;

export const disclosure = (summary, rows) => (rows.length
    ? `<details class="elections-disclosure"><summary>${escapeHtml(summary)}</summary>${rowList(rows)}</details>`
    : '');

export const noteLine = (text) => (text ? `<p class="elections-panel-note">${escapeHtml(text)}</p>` : '');
