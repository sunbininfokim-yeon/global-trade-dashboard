import { escapeHtml } from '../ui.js';

// 주 선거 당국이 공개한 비공식 개표(인증 전). public/data/usa_election_official_results_v1.json
// (scripts/election_watch/collect_official_results.py, 20분마다). 언론 집계·추정이 아니다:
// 남은 표를 추정하지 않고 당선을 판정하지 않는다. 투표구 수는 그 주가 낸 숫자 그대로다.
export const officialResult = (board, raceId) => board?.officialResults?.races?.[raceId] || null;

const PARTY = { DEM: 'D', REP: 'R', IND: 'I', LIB: 'L', GRN: 'G' };
const lastName = (name) => String(name || '').split(' ').filter(Boolean).at(-1) || '';
const fmtPct = (v) => (typeof v === 'number' ? `${v.toFixed(1)}%` : '');

export const officialLine = (result, { full = false } = {}) => {
    if (!result?.candidates?.length) return '';
    const top = result.candidates.slice(0, 2)
        .map((c) => `${full ? c.name : lastName(c.name)} ${PARTY[c.party] || c.party || ''} ${fmtPct(c.pct)}`.replace(/\s+/g, ' ').trim());
    const unit = result.reporting_unit === 'county' ? '카운티' : '투표구';
    const precincts = Number.isFinite(result.precincts_total) && result.precincts_total > 0
        ? ` · ${unit} ${result.precincts_reporting ?? 0}/${result.precincts_total} 보고` : '';
    const lead = result.leader?.party;
    const cls = lead === 'DEM' ? 'is-dem' : lead === 'REP' ? 'is-gop' : lead === 'IND' ? 'is-ind' : '';
    return `<small class="elections-official-count ${cls}" title="${escapeHtml(`${result.authority_ko || '주 선거 당국'} 공개 · ${result.fetched_at || ''}`)}">주정부 개표(비공식): ${escapeHtml(top.join(' · '))}${escapeHtml(precincts)}${result.stale ? ' · 갱신 지연' : ''}</small>`;
};
