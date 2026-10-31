import { escapeHtml as e } from '../../ui.js';
import { partyProfile, koreanText, selectionRelationships } from '../../data/israel-context.js?v=2';
import { sourceHref } from '../../data/israel-analysis.js';
import { cooperationPartners } from '../../data/israel-cooperation.js';
const kinds={talks:'협의·회동 확인',refusal:'공동 연정 거부 발언',joint_principles:'공동 원칙 발표'};
const families=[['left','좌파 계열','#e999af'],['center','중도 계열','#73b7ff'],['right','우파 계열','#f6b85a'],['far-right','극우 계열','#e78c69'],['plural','복수 성향 명부','#ba9bf7'],['unplaced','단일 좌우 배치 보류','#5bd8b3']];
const link=(url,label)=>sourceHref(url)?`<a href="${e(sourceHref(url))}" target="_blank" rel="noopener noreferrer">${e(label)} ↗</a>`:'출처 미확인';
export const israelCooperationHtml=(board,anchor='k26:עם')=>{
 const data=board.cooperation_review;if(!data)return '';
 const refs=(ids)=>ids.map(id=>data.sources[id]).filter(s=>s?.body_opened).map(s=>link(s.url,s.publisher)).join(' · ');
 const profile=data.profiles.find(p=>p.list_id===anchor)||data.profiles[0];anchor=profile.list_id;
 const name=id=>partyProfile(board,id).name;
 const identity=p=>`<div class="israel-feature-tags"><span>${e(p.spectrum_ko)}</span><span>${e(p.religion_ko)}</span></div>`;
 const historical=(id)=>selectionRelationships(board,[anchor,id]);
 const partners=cooperationPartners(board,anchor).sort((a,b)=>(a.records.length?a.priority:historical(a.list_id).length?2:3)-(b.records.length?b.priority:historical(b.list_id).length?2:3));
 return `<section id="israel-cooperation" class="israel-section" aria-labelledby="israel-cooperation-title"><div class="israel-section-heading"><span>협력 근거 · ${e(data.reviewed_on)} 검토</span><h5 id="israel-cooperation-title">누구와, 무엇을 함께할 수 있나</h5><p>선거 후 확인 → 선거 전 발표 → 과거 검토 → 미확인 순서입니다. 성사 가능성 순위나 추천 조합이 아닙니다.</p></div>
 <div class="israel-arab-comparison">${['k26:עם','k26:ודם'].map(id=>{const p=data.profiles.find(p=>p.list_id===id);if(!p)return '';return `<article><h6>${e(name(id))}</h6>${identity(p)}<p>${id==='k26:עם'?'독립 명부 · 2021년 베넷–라피드 연정 참여 사례가 있습니다. 이번 연정 참여 합의와는 별도입니다.':'하다시·타알·발라드가 함께 출마한 명부입니다. 구성당의 노선과 외부 지지·정부 참여 입장은 같다고 보지 않습니다.'}</p>${(p.components||[]).map(c=>`<details><summary>${e(c.name_ko)} · ${e(c.spectrum_ko)}</summary><p>${e(c.religion_ko)} · ${e(c.note_ko)}</p><p>구성당별 의석 미확인 · 명부 총의석을 재배분하지 않음</p><footer>${refs(c.source_ids)}</footer></details>`).join('')}<footer>${refs(p.source_ids)}</footer></article>`;}).join('')}</div>
 <details class="israel-details" data-israel-details="party-spectrum" open><summary>정당 성향 지도 · 좌우와 종교를 따로 보기</summary><p class="israel-data-note">${e(data.basis_ko)} 같은 칸 안의 정당 사이에 순위나 거리를 매기지 않습니다. 아랍 민족·국가관과 경제 좌우는 다른 축입니다.</p><div class="israel-spectrum-grid">${families.map(([id,label,color])=>`<div style="--spectrum-color:${color}"><h6>${label}</h6>${data.profiles.filter(p=>p.spectrum===id).map(p=>`<button type="button" data-israel-anchor="${e(p.list_id)}" aria-pressed="${p.list_id===anchor}">${e(name(p.list_id))}<small>${e(p.religion_ko)}</small></button>`).join('')}</div>`).join('')}</div></details>
 <div class="israel-partner-selector"><label>기준 정당<select data-israel-cooperation-anchor>${data.profiles.map(p=>`<option value="${e(p.list_id)}" ${p.list_id===anchor?'selected':''}>${e(name(p.list_id))}</option>`).join('')}</select></label><div><b>${e(name(anchor))}</b><small>${e(partyProfile(board,anchor).leader)}</small>${identity(profile)}<p>주요 의제 · ${profile.issues_ko.map(e).join(' · ')}</p><footer>${refs(profile.source_ids)}</footer></div></div>
 <div class="israel-partner-grid">${partners.map(p=>{
 const history=historical(p.list_id);
 return `<article class="israel-partner-card" data-israel-partner="${e(p.list_id)}"><header><h6>${e(name(anchor))} ↔ ${e(name(p.list_id))}</h6><span>${p.records.some(r=>r.phase==='post_election')?'선거 후 확인':p.records.length?'선거 전 발표':history.length?'과거 검토 기록':'협력 근거 미확인'}</span></header>${identity(p)}<p class="israel-data-note">상대 정당 주요 의제 · ${p.issues_ko.map(e).join(' · ')}</p>
 ${p.records.map(r=>`<div class="israel-partner-evidence israel-evidence-${e(r.kind)}"><b>${e(kinds[r.kind])}</b><time>${e(r.event_date)} · ${r.phase==='post_election'?'선거 후':'선거 전'}</time><p>${e(r.basis_ko)}</p><p class="israel-relation-condition">${e(r.limit_ko)}</p><footer>${refs(r.source_ids)}</footer></div>`).join('')}
 ${!p.records.length?'<p>이번 조사에서 두 정당의 선거 후 협의·최종 연정 합의를 확인하지 못했습니다. 성향 유사성만으로 가능·불가능을 판정하지 않습니다.</p>':''}
 ${history.length?`<details><summary>기존 입장 · ${e(board.coalition_context.reviewed_on)}까지 검토</summary>${history.map(r=>`<p><b>${e(r.label_ko)}</b> · ${e(r.event_date)}</p><p>${e(koreanText(board,r.summary))}</p><p>${e(koreanText(board,r.condition))}</p>${(r.source_ids||[]).map(id=>{const s=board.coalition_context.sources[id];return s?link(s.url,s.publisher):'';}).join(' · ')}`).join('')}<p class="israel-data-note">외부 지지 제안은 상대 수용·장관 참여와 별개이며, 선거 협약도 연정 합의가 아닙니다.</p></details>`:''}</article>`;
 }).join('')}</div><p class="israel-data-note">최종 연정 합의·지원 약속은 확인하지 못했습니다. 라암과 공동명부를 하나의 정부 참여 단위로 합산하지 않습니다.</p></section>`;
};
