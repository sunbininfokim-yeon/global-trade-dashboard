import { escapeHtml } from '../../ui.js';
import { card, orgBox, orgGrid, noteLine } from './org-chart.js';
import { chamberKo, jpnPartyLabel, jpnPerson } from './jpn.js';

// 일본 내각 화면. 미국 행정부 화면과 같은 박스 격자를 쓰지만 단 구성이 다르다 --
// 대통령제가 아니기 때문이다.
//
// 미국은 대통령이 따로 뽑히고 그 밑에 위원회·실국이 달린 피라미드라 4단(대통령 →
// 위원회 → 특보 → 실국)이 그대로 조직도가 된다. 일본은 그 축이 없다: 총리는 국회가
// 지명하고 내각은 국회의 신임 위에 서며, 국무대신 과반은 국회의원이어야 한다
// (헌법 68조). 그래서 3단으로 간다:
//
//   1 · 내각의 핵      총리·관방장관
//   2 · 국무대신       부처별 박스. 각 박스에 소속 원(중의원/참의원)과 회파를 적는다.
//   3 · 내각의 의회 기반  내각이 서 있는 의석. 여기가 대통령제와 갈리는 지점이다.
//
// 특보·실국단이 없는 것은 데이터 미수집이 아니라 제도가 다른 것이므로, 빈 칸을
// 만들어 "수집 예정"을 붙이지 않는다.

const MAJORITY_NOTE = '내각총리대신은 국회에서 지명되고, 국무대신의 과반은 국회의원이어야 합니다(일본국 헌법 67·68조). 아래 의석은 그 기반을 보여 주는 것이지 내각의 표결권이 아닙니다.';

const personText = (row) => {
    const name = jpnPerson(row);
    if (!name) return '';
    return [name, row.party_abbr ? jpnPartyLabel(row.party_abbr) : ''].filter(Boolean).join(' · ');
};

const seatTotal = (byParty) => Object.values(byParty || {})
    .filter((seats) => Number.isFinite(seats))
    .reduce((sum, seats) => sum + seats, 0);

// 여당 의석은 집권 회파의 의석만 센다. 연립 상대를 데이터가 따로 표시하지 않으므로
// 연립 합계를 지어내지 않는다 -- 자민당 단독 의석이라고 분명히 적는다.
const chamberBase = (label, byParty, rulingAbbr, note) => {
    const total = seatTotal(byParty);
    if (!total) return '';
    const ruling = byParty?.[rulingAbbr];
    const line = Number.isFinite(ruling)
        ? `${ruling} / ${total}석 · 과반선 ${Math.floor(total / 2) + 1}석`
        : `집계 ${total}석`;
    return card(label, line, note);
};

const cabinetChamberSplit = (cabinet) => {
    const counts = new Map();
    cabinet.forEach((row) => {
        const key = row.chamber || 'unknown';
        counts.set(key, (counts.get(key) || 0) + 1);
    });
    return [...counts.entries()]
        .map(([key, count]) => `${key === 'unknown' ? '소속 원 미기재' : chamberKo(key)} ${count}명`)
        .join(' · ');
};

export const jpnExecutive = (country) => {
    const live = country.executive_live;
    if (!live) return null;
    const core = live.core || [];
    const cabinet = live.cabinet || [];
    const legislature = country.legislature_live || {};
    const rulingAbbr = country.ruling_party?.abbr;

    const coreCards = core.map((row) => card(row.office_ko || '직책', personText(row))).join('');
    const cabinetBoxes = cabinet.map((row) => orgBox({
        ko: row.portfolio_ko || '직책',
        title: row.chamber ? chamberKo(row.chamber) : '',
        person: personText(row),
        note: row.note_ko,
    }));

    // 참의원 합계는 공개 회파표를 더한 값이라 정수(定数)와 어긋날 수 있다. 어긋난
    // 채로 두고 그렇다고 적는 편이, 모자란 만큼을 어딘가에 얹는 것보다 정확하다.
    const sangiinTotal = seatTotal(legislature.sangiin_by_abbr);
    const shugiinTotal = seatTotal(legislature.shugiin_by_party_abbr);

    return `
        <p class="section-title">1 · 내각의 핵</p>
        <div class="elections-card-grid">
            ${coreCards || '<p class="elections-muted">확보된 공개 명부가 없습니다.</p>'}
        </div>

        <p class="section-title">2 · 국무대신 ${cabinet.length}명</p>
        ${cabinet.length ? orgGrid(cabinetBoxes) : '<p class="elections-muted">확보된 국무대신 명부가 없습니다.</p>'}
        ${cabinet.length ? `<p class="elections-panel-note">소속 원 구성: ${escapeHtml(cabinetChamberSplit(cabinet))}. 박스의 윗줄은 소속 원입니다.</p>` : ''}

        <p class="section-title">3 · 내각의 의회 기반</p>
        <div class="elections-card-grid">
            ${chamberBase('중의원', legislature.shugiin_by_party_abbr, rulingAbbr, rulingAbbr ? `${jpnPartyLabel(rulingAbbr)} 단독` : '')
            || card('중의원', '', '공개 의석 집계 없음')}
            ${chamberBase('참의원', legislature.sangiin_by_abbr, rulingAbbr, sangiinTotal ? '공개 회파표 합계' : '')
            || card('참의원', '', '공개 의석 집계 없음')}
            ${card('내각 구성', cabinet.length ? `${cabinet.length}명` : '', cabinet.length ? cabinetChamberSplit(cabinet) : '')}
        </div>
        ${noteLine(MAJORITY_NOTE)}
        ${shugiinTotal && legislature.shugiin_members && shugiinTotal !== legislature.shugiin_members
            ? noteLine(`중의원 회파 합계 ${shugiinTotal}석은 공개 정수 ${legislature.shugiin_members}석과 다릅니다. 합산 없이 원문 그대로 표시합니다.`)
            : ''}
        ${noteLine(live.party_display_rule)}
        ${noteLine(legislature.source?.note_ko)}
    `;
};
