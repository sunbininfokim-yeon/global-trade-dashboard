import { escapeHtml } from '../../ui.js';

// 중국 우측 대시보드의 블록. 셋 다 미국 행정부 화면과 같은 조직도로 열리며,
// 그리는 쪽은 chn-org.js 다. 이 파일에는 세 화면이 같이 쓰는 사람·상태 표기만 남는다.
//
// 매니페스트는 CHN 화면을 party / state_council / military 로 선언한다. 범용
// executive/power_structure 짝이 아니다 -- 두 탭을 한 키에 걸었더니 공산당과 군이
// 같은 블록을 그리고 같이 켜졌다.
// 행정부 탭이 앞에 붙는다: 당·국가·군을 한 장의 조직도로 보여 주는 화면이고,
// 뒤의 세 탭은 그 각 단의 전체 명부다 (조직도는 책임자만, 탭은 명단 전부).
export const chinaSections = [
    ['공산당', 'party'],
    ['군부', 'military'],
    ['국무원', 'state_council'],
];

// `_internal` carries the pipeline's private faction tags; display_rules says
// they stay out of the UI.  Reading only the fields named here keeps them out
// by construction rather than by remembering to strip them.
export const personName = (person) => person?.name_ko || person?.name_en || '불명';

// status 는 파이프라인의 토큰(expelled_2025-10, investigating_2026-01_de_facto_fallen
// ...)이라 화면에 그대로 나오면 한국어 화면에 영문 코드가 박힌다. 동사만 옮기고
// 날짜는 원문 그대로 둔다 -- 날짜를 고쳐 쓰면 그게 새로운 주장이 된다. 표에 없는
// 코드는 번역하지 않고 그대로 보여, 새 코드가 조용히 사라지지 않게 한다.
const STATUS_VERBS = [
    ['acting_or_provisional', () => '대리·잠정'],
    ['expelled_', (rest) => `제명 ${rest}`],
    ['investigating_', (rest) => `조사 중 ${rest.replace('_de_facto_fallen', '')} · 사실상 실각`],
    ['likely_removed_', (rest) => `해임 추정 ${rest}`],
    ['removed_sentenced_death_reprieve_', (rest) => `해임 · 사형집행유예 선고 ${rest}`],
];
export const statusKo = (status) => {
    if (!status || status === 'incumbent') return '';
    const hit = STATUS_VERBS.find(([prefix]) => status === prefix || status.startsWith(prefix));
    return hit ? hit[1](status.slice(hit[0].length)) : status;
};
export const isFallen = (person) => person?.fallen === true || person?.display === 'strikethrough';

export const personLine = (person, fallbackTitle = '') => {
    if (!person) return '<div><span>직책</span><strong>불명</strong></div>';
    const title = person.title_ko || person.role_ko || fallbackTitle || '직책';
    const name = escapeHtml(personName(person));
    const marks = [statusKo(person.status), person.confidence ? `신뢰도 ${person.confidence}` : '']
        .filter(Boolean).map((mark) => escapeHtml(mark)).join(' · ');
    return `<div>
        <span>${escapeHtml(title)}</span>
        <strong class="${isFallen(person) ? 'elections-fallen' : ''}">${name}</strong>
        ${marks ? `<em class="elections-person-mark">${marks}</em>` : ''}
    </div>`;
};
