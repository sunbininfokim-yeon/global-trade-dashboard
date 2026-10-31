import { escapeHtml as e } from '../../ui.js';
import { partyProfile } from '../../data/israel-context.js?v=2';
import { sourceHref } from '../../data/israel-analysis.js';

const link = (url, label) => sourceHref(url) ? `<a href="${e(sourceHref(url))}" target="_blank" rel="noopener noreferrer">${e(label)} ↗</a>` : '출처 미확인';
export const israelResultsHtml = (board) => {
    const data = board.post_election;
    if (!data) return '';
    const row = data.result_record;
    const sources = new Map(data.sources.map((s) => [s.id, s]));
    const refs = (ids) => ids.map((id) => sources.get(id)).filter((s) => s?.body_opened).map((s) => link(s.url, ({'i24-count':'i24NEWS 보도','acri-procedure':'ACRI 해설','wipo-law':'기본법 재수록 · 2016년'}[s.id] || s.id))).join(' · ');
    const values = [...row.values].sort((a,b) => b.seats-a.seats);
    const blocs = [
        {label:'기존 집권 진영', seats:row.bloc_as_published.current_coalition, color:'#f6b85a'},
        {label:'야권 정당', seats:row.bloc_as_published.opposition, color:'#73b7ff'},
        {label:'아랍계 정당', seats:row.bloc_as_published.arab, color:'#5bd8b3'},
    ];
    const number = (n) => Number.isFinite(n) ? new Intl.NumberFormat('ko-KR').format(n) : '미확인';
    return `<header class="israel-heading israel-results-heading"><p class="israel-eyebrow">이스라엘 · 26대 크네세트</p><h4>선거 결과와 다음 단계</h4><p>120석의 분포를 확인하고, 새 정부가 출범하기까지의 절차를 살펴보세요.</p><div class="israel-status-line"><span>개표 보도 ${e(data.result_as_of)}</span><span>자료 검토 ${e(data.evidence_as_of)}</span><span>자동 갱신 미설치</span></div></header>
    <nav class="israel-section-nav" aria-label="선거 결과 바로가기"><a href="#israel-results">개표 결과</a><a href="#israel-next-steps">앞으로의 절차</a><a href="#israel-history" data-israel-history-link>선거 전 자료</a></nav>
    <section id="israel-results" class="israel-results" aria-labelledby="israel-results-title">
        <div class="israel-result-topline"><h5 id="israel-results-title">보도로 확인한 개표 결과</h5><span class="israel-result-badge">공식 표 확인 보류</span></div>
        <p class="israel-data-note">${e(data.status_note_ko)}</p>
        <div class="israel-result-metrics"><div><span>전체 의석</span><strong>120<small>석</small></strong></div><div><span>1위 · ${e(partyProfile(board,values[0].list_id).name)}</span><strong>${values[0].seats}<small>석</small></strong></div><div><span>투표율 · 보도값</span><strong>${number(row.votes.turnout_pct)}<small>%</small></strong></div></div>
        <div class="israel-result-blocs"><div class="israel-seat-bar" role="img" aria-label="기사 분류: ${e(blocs.map((b)=>`${b.label} ${b.seats}석`).join(', '))}">${blocs.map((b)=>`<span style="flex:${b.seats};background:${b.color}"></span>`).join('')}</div><div class="israel-result-legend">${blocs.map((b)=>`<span style="--group-color:${b.color}"><i class="israel-party-dot"></i>${e(b.label)} <b>${b.seats}석</b></span>`).join('')}</div><p class="israel-data-note">기사의 진영 분류입니다. 61석은 산술 과반이며, 진영 합계나 정당 순위가 정부 구성 합의를 뜻하지 않습니다.</p></div>
        <div class="israel-result-grid">${values.map((v)=>{const p=partyProfile(board,v.list_id);return `<article class="israel-result-party"><div><b>${e(p.name)}</b><small>${e(p.leader)}</small></div><span class="israel-result-party-track" aria-hidden="true"><i style="width:${v.seats/120*100}%"></i></span><strong>${v.seats}<small>석</small></strong></article>`;}).join('')}</div>
        <p class="israel-data-note">인물 소개는 기존 검토 자료 기준입니다. 득표율·미확인 명부의 0석을 생성하지 않습니다.</p><p class="israel-source-line">${refs(['i24-count'])} · ${link(sources.get('inn-flash').url,'교차 확인 보도')}</p>
        <details class="israel-details" data-israel-details="result-evidence"><summary>투표 집계·검토 출처와 확인 공백</summary><p>집계 ${number(row.votes.counted)}표 · 유효 ${number(row.votes.valid)}표 · 무효 ${number(row.votes.invalid)}표</p><p>봉쇄선 보도값 ${e(row.votes.threshold_pct_as_published)}% · ${number(row.votes.threshold_votes_as_published)}표. 공식 법문 확인과 별개입니다.</p>${data.sources.map((s)=>`<p>${link(s.url,s.id)} · ${s.body_opened?'본문 확인':'접근·확인 보류'} · ${e(s.note_ko)}</p>`).join('')}</details>
    </section>
    <section id="israel-next-steps" class="israel-section" aria-labelledby="israel-next-title"><div class="israel-section-heading"><span>다음으로 볼 것</span><h5 id="israel-next-title">대통령 지명에서 의회 신임까지</h5><p>총리 지명자·지명일·새 정부 출범은 이번 검토에서 확인하지 못했습니다.</p></div>
        <ol class="israel-next-steps">${data.steps.map((step,index)=>`<li><span class="israel-step-number" aria-hidden="true">${index+1}</span><div><span class="israel-step-when">${e(step.when_ko)}</span><h6>${e(step.title_ko)}</h6><p>${e(step.description_ko)}</p><footer>${refs(step.source_ids)}</footer></div></li>`).join('')}</ol>
        <details class="israel-details" data-israel-details="formation-fallback"><summary>정부 구성에 실패하면 어떻게 되나요?</summary>${data.fallback.map((step)=>`<p><b>${e(step.title_ko)}</b> · ${e(step.description_ko)}</p>`).join('')}<p>${refs(['wipo-law'])}</p></details><p class="israel-data-note">${e(data.procedure_note_ko)}</p>
    </section>`;
};
