import { escapeHtml } from '../../ui.js';

// 중국 '공산당' 화면의 세 갈래 토글 -- 중앙 인사 / 지방 지도부 / 기업·기타.
// 자료는 public/data/elections_cn_leaders_v1.json (scripts/election_watch/
// build_cn_leaders_public.py 가 config/china_leader_appointments.json 에서 만든다).
//
// 토글은 라디오 + CSS 형제 선택자다. 화면이 innerHTML 로 통째로 다시 그려지는
// 구조라 클릭 핸들러를 따로 걸 곳이 없고, 걸 필요도 없다.
//
// 원칙: 날짜 옆에는 반드시 그 날짜를 말한 원문 링크를 붙인다. 원문 없이 날짜만
// 남은 값(null url)은 '원문 미확인'으로 적고, 검색 결과 본문으로만 본 것은
// '검색 본문'이라고 밝힌다. 날짜가 없는 값은 지어내지 않고 note_ko 를 그대로 낸다.

// 성 이름(region_ko) -> public/data/admin1/CHN.json 의 code. 지도 클릭과 색칠이 둘을 잇는다.
export const CN_REGION_CODES = {
    '베이징': 'CN-BJ', '톈진': 'CN-TJ', '허베이': 'CN-HE', '산시(山西)': 'CN-SX', '네이멍구': 'CN-NM',
    '랴오닝': 'CN-LN', '지린': 'CN-JL', '헤이룽장': 'CN-HL', '상하이': 'CN-SH', '장쑤': 'CN-JS',
    '저장': 'CN-ZJ', '안후이': 'CN-AH', '푸젠': 'CN-FJ', '장시': 'CN-JX', '산둥': 'CN-SD',
    '허난': 'CN-HA', '후베이': 'CN-HB', '후난': 'CN-HN', '광둥': 'CN-GD', '광시': 'CN-GX',
    '하이난': 'CN-HI', '충칭': 'CN-CQ', '쓰촨': 'CN-SC', '구이저우': 'CN-GZ', '윈난': 'CN-YN',
    '시짱': 'CN-XZ', '산시(陕西)': 'CN-SN', '간쑤': 'CN-GS', '칭하이': 'CN-QH', '닝샤': 'CN-NX', '신장': 'CN-XJ',
};
const REGION_BY_CODE = new Map(Object.entries(CN_REGION_CODES).map(([region, code]) => [code, region]));
export const cnRegionForCode = (code) => REGION_BY_CODE.get(code) || null;

// 지도 색. 배지 색과 같은 계열이고, 한 성에 여러 사정이 겹치면 앞의 것이 이긴다
// (공석 > 대리 > 서기 겸임 > 2026 서기 교체). 아무 일 없는 성은 기본 회색.
export const CN_MAP_KINDS = [
    ['vacant', '수반 공석', [203, 213, 225, 230]],
    ['acting', '수반 대리', [217, 119, 6, 230]],
    ['secretary_concurrent', '서기 겸임', [124, 58, 237, 225]],
    ['changed', '2026 서기 교체', [5, 150, 105, 215]],
];
export const cnRegionKind = (leaders, region) => {
    const head = (leaders?.government_heads || []).find((h) => h.region_ko === region);
    const sec = (leaders?.provincial_secretaries || []).find((r) => r.region_ko === region);
    if (head && head.status !== 'elected') return head.status;
    return sec?.changed_in_2026 ? 'changed' : null;
};
export const cnRegionColor = (leaders, code) => {
    const kind = cnRegionKind(leaders, cnRegionForCode(code));
    return CN_MAP_KINDS.find(([id]) => id === kind)?.[2] || null;
};

// 지도에서 성을 누르면 다음 한 번의 렌더가 그 성을 펼친 지방 탭으로 열린다.
let focusRegion = null;
export const focusCnRegion = (region) => { focusRegion = region || null; };

export const cnMapLegendHtml = (leaders) => (leaders ? `<div class="cn-lead-legend">
    <span>지도에서 성을 누르면 서기·성장이 열립니다</span>
    ${CN_MAP_KINDS.map(([id, label, [r, g, b]]) => `<i><b style="background:rgb(${r},${g},${b})"></b>${escapeHtml(label)}</i>`).join('')}
</div>` : '');

const safeUrl = (url) => (typeof url === 'string' && /^https?:\/\//.test(url) ? url : '');

const link = (url, label) => {
    const href = safeUrl(url);
    return href
        ? `<a class="elections-person-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
        : '';
};

// { date, url, search_only, note_ko } -> "2026-10-25 · 원문"
export const evidence = (ev) => {
    if (!ev) return '<span class="elections-muted">미확인</span>';
    const parts = [];
    if (ev.date) parts.push(escapeHtml(ev.date));
    if (ev.note_ko) parts.push(escapeHtml(ev.note_ko));
    if (safeUrl(ev.url)) parts.push(link(ev.url, ev.search_only ? '검색 본문' : '원문'));
    else if (ev.date) parts.push('<span class="elections-muted">원문 미확인</span>');
    return parts.join(' · ') || '<span class="elections-muted">미확인</span>';
};

const row = (label, value) => `<div><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`;
const who = (person) => escapeHtml([person?.name_ko, person?.name_zh && `(${person.name_zh})`].filter(Boolean).join(' ') || '');

const HEAD_STATUS = {
    elected: ['', ''],
    acting: ['대리', 'is-acting'],
    vacant: ['공석', 'is-vacant'],
    secretary_concurrent: ['서기 겸임', 'is-concurrent'],
};

// 성 이름으로 정부 수반을 정확히 맞춘다 -- 두 목록의 순서가 같다고 가정하지 않는다.
const headsByRegion = (leaders) => new Map((leaders.government_heads || []).map((h) => [h.region_ko, h]));
const staleByRegion = (leaders) => {
    const map = new Map();
    (leaders.stale_pages || []).forEach((s) => map.set(s.region_ko, [...(map.get(s.region_ko) || []), s]));
    return map;
};

const headLabel = (head) => {
    if (!head) return '<span class="elections-muted">미수집</span>';
    if (head.status === 'vacant') return '<em class="cn-lead-badge is-vacant">공석</em>';
    const [badge, cls] = HEAD_STATUS[head.status] || [head.status, ''];
    return `${who(head)}${badge ? ` <em class="cn-lead-badge ${cls}">${escapeHtml(badge)}</em>` : ''}`;
};

const provinceCard = (sec, head, stale, open = false) => {
    const flags = [
        sec.changed_in_2026 ? '<em class="cn-lead-badge is-new">2026 교체</em>' : '',
        sec.politburo_member ? '<em class="cn-lead-badge is-pb">정치국</em>' : '',
        head && head.status !== 'elected' ? `<em class="cn-lead-badge ${HEAD_STATUS[head.status]?.[1] || ''}">${escapeHtml(HEAD_STATUS[head.status]?.[0] || head.status)}</em>` : '',
    ].filter(Boolean).join('');
    const pages = [sec.leader_page, head?.leader_page].filter((p, i, all) => p && all.findIndex((q) => q?.url === p.url && q?.label_ko === p.label_ko) === i);
    return `<details class="cn-lead-province" data-region="${escapeHtml(sec.region_ko)}"${open ? ' open' : ''}>
        <summary>
            <b>${escapeHtml(sec.region_ko)}</b>
            <span>서기 ${escapeHtml(sec.name_ko || '')}</span>
            <span>${head ? (head.status === 'vacant' ? '수반 공석' : head.status === 'secretary_concurrent' ? '수반 서기 겸임' : `수반 ${escapeHtml(head.name_ko || '')}`) : ''}</span>
            ${flags}
        </summary>
        <div class="elections-disclosure-rows">
            ${row('당위 서기', who(sec))}
            ${row('중앙 결정', evidence(sec.central_decision))}
            ${row('전임 서기', escapeHtml(sec.predecessor_zh || sec.predecessor_note_ko || '—'))}
            ${row('성 당위 전체회의 선출', sec.plenum_election ? evidence(sec.plenum_election) : escapeHtml(sec.plenum_note_ko || '아직 없음'))}
            ${row('정부 수반', headLabel(head))}
            ${head?.acting_appointed ? row('대리 임명', evidence(head.acting_appointed)) : ''}
            ${head?.elected ? row('인대 선출', evidence(head.elected)) : ''}
            ${head?.predecessor ? row('전임 수반', escapeHtml(head.predecessor)) : ''}
            ${head?.note_ko ? row('비고', `${escapeHtml(head.note_ko)}${head.related_url ? ` · ${link(head.related_url, '원문')}` : ''}`) : ''}
            ${pages.map((p) => row('공식 지도자 페이지', safeUrl(p.url) ? link(p.url, p.label_ko || '열기') : `<span class="elections-muted">${escapeHtml(p.label_ko || '없음')}</span>`)).join('')}
            ${(stale || []).map((s) => row('낡은 페이지 주의', `${escapeHtml(s.site)} · ${escapeHtml(s.issue_ko)}`)).join('')}
        </div>
    </details>`;
};

const xpccCard = (x) => {
    if (!x) return '';
    const seat = (label, s) => (s ? row(label, `${escapeHtml(s.name_zh || '')} · ${evidence(s)}`) : '');
    return `<details class="cn-lead-province">
        <summary><b>신장생산건설병단</b><span>정위 ${escapeHtml(x.political_commissar?.name_zh || '')}</span><span>사령원 ${escapeHtml(x.commander?.name_zh || '')}</span><em class="cn-lead-badge">성급 준군사</em></summary>
        <div class="elections-disclosure-rows">
            ${row('제1정위', `${escapeHtml(x.first_secretary_zh || '')}${x.first_secretary_note_ko ? ` · ${escapeHtml(x.first_secretary_note_ko)}` : ''}`)}
            ${seat('당위 서기', x.party_secretary)}
            ${seat('정치위원', x.political_commissar)}
            ${seat('사령원', x.commander)}
            ${safeUrl(x.leader_page_url) ? row('공식 지도자 페이지', link(x.leader_page_url, '병단 지도자')) : ''}
        </div>
    </details>`;
};

export const provincesHtml = (leaders, focus = null) => {
    const heads = headsByRegion(leaders);
    const stale = staleByRegion(leaders);
    const secs = leaders.provincial_secretaries || [];
    const all = [...heads.values()];
    const count = (status) => all.filter((h) => h.status === status).length;
    const changed = secs.filter((s) => s.changed_in_2026).length;
    const names = (status) => all.filter((h) => h.status === status).map((h) => h.region_ko).join('·');
    return `
        <div class="elections-cards cn-lead-summary">
            <article class="elections-card"><div class="elections-card-label">성급 단위</div><div class="elections-card-value">${secs.length}곳</div></article>
            <article class="elections-card"><div class="elections-card-label">2026 서기 교체</div><div class="elections-card-value">${changed}곳</div></article>
            <article class="elections-card"><div class="elections-card-label">수반 대리</div><div class="elections-card-value">${count('acting')}곳</div></article>
            <article class="elections-card"><div class="elections-card-label">수반 공석·겸임</div><div class="elections-card-value">${count('vacant')} · ${count('secretary_concurrent')}</div></article>
        </div>
        ${count('acting') ? `<p class="elections-panel-note">대리: ${escapeHtml(names('acting'))}${count('vacant') ? ` · 공석: ${escapeHtml(names('vacant'))}` : ''}${count('secretary_concurrent') ? ` · 서기 겸임: ${escapeHtml(names('secretary_concurrent'))}` : ''}</p>` : ''}
        ${cnMapLegendHtml(leaders)}
        <p class="elections-panel-note">성을 누르면 서기·정부 수반의 임명일과 원문이 펼쳐집니다. 11~12월 성 당대회가 열리는 곳은 이후 다시 확인해야 합니다.</p>
        <div class="cn-lead-provinces">
            ${secs.map((sec) => provinceCard(sec, heads.get(sec.region_ko), stale.get(sec.region_ko), sec.region_ko === focus)).join('')}
            ${xpccCard(leaders.xpcc)}
        </div>
        ${(leaders.rank_conflicts || []).length ? `<details class="elections-disclosure"><summary>출처 간 직급 충돌 ${leaders.rank_conflicts.length}건</summary><div class="elections-disclosure-rows">${leaders.rank_conflicts.map((c) => row(c.name_zh, escapeHtml(c.issue_ko))).join('')}</div></details>` : ''}`;
};

export const enterprisesHtml = (leaders) => {
    const list = leaders.enterprises || [];
    if (!list.length) return '<p class="elections-muted">확보된 기업 인사가 없습니다.</p>';
    const byOrg = new Map();
    list.forEach((e) => byOrg.set(e.org_ko, [...(byOrg.get(e.org_ko) || []), e]));
    return `
        <p class="elections-panel-note">중앙 관리 기업 수장 중, 신화사가 성 지도부와의 회동을 보도한 곳만 담았습니다. 전체 중앙기업 명부가 아닙니다.</p>
        <div class="cn-lead-provinces">
        ${[...byOrg.entries()].map(([org, people]) => {
            const contacts = [...new Set(people.flatMap((p) => (p.provincial_contacts || []).map((c) => c.region_ko)))];
            return `<details class="cn-lead-province">
                <summary><b>${escapeHtml(org)}</b>${people.map((p) => `<span>${escapeHtml(p.post_ko || '')} ${escapeHtml(p.name_ko || '')}</span>`).join('')}${contacts.length ? `<em class="cn-lead-badge">접점 ${escapeHtml(contacts.join('·'))}</em>` : ''}</summary>
                <div class="elections-disclosure-rows">
                    ${people.map((p) => `
                        ${row(p.post_ko || '직책', who(p))}
                        ${row('임명', evidence(p.appointed))}
                        ${(p.provincial_contacts || []).map((c) => row(`성 회동 · ${c.region_ko}`, evidence(c))).join('')}`).join('')}
                    ${people[0]?.leader_page ? row('공식 지도자 페이지', safeUrl(people[0].leader_page.url) ? link(people[0].leader_page.url, people[0].leader_page.label_ko || '열기') : escapeHtml(people[0].leader_page.label_ko || '')) : ''}
                </div>
            </details>`;
        }).join('')}
        </div>`;
};

// 중앙 탭에 붙는 근거 -- 정치국 22인의 입국일·현직 취임일, 5중전회 중앙위원 보충.
export const centralEvidenceHtml = (leaders) => {
    const pb = leaders.politburo || [];
    const promoted = leaders.cc_promoted_2026_10_29?.members || [];
    const pbRows = pb.map((p) => `<div class="cn-lead-pb-row">
        <span>${p.standing_committee ? '<em class="cn-lead-badge is-pb">상무위</em> ' : ''}${escapeHtml(p.post_ko || '')}</span>
        <strong>${who(p)}</strong>
        <small>정치국 ${evidence(p.politburo_joined)} · 현직 ${evidence(p.current_post_appointed)}${safeUrl(p.bio_url) ? ` · ${link(p.bio_url, '약력')}` : ''}</small>
    </div>`);
    return `
        ${pbRows.length ? `<details class="elections-disclosure"><summary>정치국 ${pb.length}인 · 입국일·현직 취임일과 원문</summary><div class="elections-disclosure-rows cn-lead-pb">${pbRows.join('')}</div></details>` : ''}
        ${promoted.length ? `<details class="elections-disclosure"><summary>5중전회(10-29) 중앙위원 보충 ${promoted.length}인</summary><div class="elections-disclosure-rows">${promoted.map((m) => row(m.post_ko || '', `${who(m)} · ${evidence(m.current_post_appointed)}`)).join('')}${safeUrl(leaders.cc_promoted_2026_10_29?.source_url) ? row('발표', link(leaders.cc_promoted_2026_10_29.source_url, '공보 원문')) : ''}</div></details>` : ''}`;
};

let toggleSeq = 0;

// central: 기존 중앙 조직도 HTML. leaders 가 없으면 토글 없이 그대로 돌려준다 --
// 자료 파일을 못 읽었다고 중앙 화면까지 사라지면 안 된다.
export const chnLeadersToggle = (central, leaders) => {
    if (!leaders) return central;
    toggleSeq += 1;
    const name = `cn-lead-${toggleSeq}`;
    const focus = focusRegion;
    focusRegion = null;
    const start = focus ? 1 : 0;
    const tabs = [
        ['central', '중앙 인사', `${central}${centralEvidenceHtml(leaders)}`],
        ['provinces', `지방 지도부 ${(leaders.provincial_secretaries || []).length}`, provincesHtml(leaders, focus)],
        ['enterprises', '기업·기타', enterprisesHtml(leaders)],
    ];
    return `<div class="cn-lead">
        ${tabs.map(([id], i) => `<input class="cn-lead-radio" type="radio" name="${name}" id="${name}-${id}" data-cn-tab="${id}"${i === start ? ' checked' : ''}>`).join('')}
        <div class="cn-lead-tabs" role="group" aria-label="공산당 인사 구분">
            ${tabs.map(([id, label]) => `<label for="${name}-${id}" data-cn-tab="${id}">${escapeHtml(label)}</label>`).join('')}
        </div>
        ${tabs.map(([id, , body]) => `<div class="cn-lead-pane" data-cn-pane="${id}">${body}</div>`).join('')}
        <p class="elections-panel-note">인사 기준일 ${escapeHtml(leaders.as_of || '')} · ${escapeHtml(leaders.source_policy_ko || '')}</p>
    </div>`;
};
