/* Pure policy contract shared by the collector, Worker and browser. No network. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PolicyEvidence = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const CHAMBERS = { house: '하원', senate: '상원' };
  const chamber = (v) => /^(house|h)$/i.test(v || '') ? 'house' : /^(senate|s)$/i.test(v || '') ? 'senate' : null;
  function parseBillQuery(input) {
    const text = String(input || '').trim();
    const canonical = text.match(/^(\d{1,3})-(hr|s|hjres|sjres|hconres|sconres|hres|sres)-(\d{1,6})$/i);
    const citation = text.match(/^(h\s*\.?\s*(?:con\s*\.?\s*res|j\s*\.?\s*res|res|r)|s\s*\.?\s*(?:con\s*\.?\s*res|j\s*\.?\s*res|res)?)\s*\.?\s*(\d{1,6})(?:\s*\(\s*(\d{1,3})(?:th)?\s*\))?$/i);
    if (!canonical && !citation) return null;
    const congressText = canonical?.[1] || citation?.[3];
    const congress = congressText ? Number(congressText) : null;
    if (congressText && congress < 1) return null;
    const type = (canonical?.[2] || citation[1]).replace(/[.\s]/g, '').toLowerCase();
    const number = Number(canonical?.[3] || citation[2]);
    return number > 0 && (!congress || congress > 0) ? { type, number, congress } : null;
  }
  function billUrl(congress, type, number) {
    const names = { hr: 'house-bill', s: 'senate-bill', hjres: 'house-joint-resolution', sjres: 'senate-joint-resolution', hres: 'house-resolution', sres: 'senate-resolution', hconres: 'house-concurrent-resolution', sconres: 'senate-concurrent-resolution' };
    const n = Number(congress);
    if (!Number.isInteger(n) || n < 1 || !names[type] || !Number.isInteger(Number(number)) || Number(number) < 1) return null;
    const ordinal = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th');
    return `https://www.congress.gov/bill/${n}${ordinal}-congress/${names[type]}/${Number(number)}`;
  }
  function officialSource(url) {
    const legacy = String(url || '').match(/^https:\/\/www\.congress\.gov\/bill\/(\d+)\/([a-z]+)\/(\d+)$/i);
    return legacy ? billUrl(legacy[1], legacy[2].toLowerCase(), legacy[3]) : url;
  }
  function actionChamber(a) {
    if (chamber(a.chamber)) return chamber(a.chamber);
    const code = a.sourceSystem?.code;
    if (code !== null && code !== undefined && String(code) === '0') return 'senate';
    if (['1', '2'].includes(String(code))) return 'house';
    const system = a.sourceSystem?.name || a.action_type || '';
    if (/^House(?: committee| floor)?(?: actions)?$/i.test(system)) return 'house';
    if (/^Senate$/i.test(system)) return 'senate';
    const text = a.text || a.action_text || '';
    const match = text.match(/(?:^Passed(?:\/agreed to in)?\s+(?:the\s+)?|^Received in |^Introduced in |^Referred to (?:the )?)(House|Senate)\b/i);
    return chamber(match?.[1]);
  }
  const count = (v) => v === null || v === undefined || v === '' ? null : Number.isInteger(Number(v)) && Number(v) >= 0 ? Number(v) : null;
  function voteEvidence(v) {
    const text = String(v.question || v.text || v.action_text || '');
    const kind = /\bcloture\b/i.test(text) ? 'cloture' : /motion to proceed/i.test(text) ? 'motion_to_proceed'
      : /(?:^|:\s*)on passage\b|^passage\b|^passed(?:\/agreed to in)? (?:the )?(?:house|senate)\b/i.test(text) ? 'passage' : 'other';
    const resultText = [v.result, text].filter(Boolean).join(' ');
    const failed = /\bnot (?:invoked|agreed to|passed)\b|\b(?:failed|rejected|defeated)\b/i.test(resultText);
    const explicitPass = /\bpassed\b|\bagreed to\b|\binvoked\b/i.test(resultText);
    // Postponed debate, a motion to reconsider and an amendment are not a final vote on this bill.
    const uncertain = /POSTPONED PROCEEDINGS|motion to reconsider|^On (?:agreeing to )?(?:the )?amendment/i.test(text);
    const result = uncertain ? 'unknown' : failed ? 'failed' : explicitPass ? 'passed' : 'unknown';
    const tally = text.match(/(?:Yea-Nay Vote\.|Yeas and Nays:|recorded vote:)\s*(\d+)\s*-\s*(\d+)/i);
    return { kind, result, yea_count: count(v.yea_count ?? v.yeaCount) ?? count(tally?.[1]),
      nay_count: count(v.nay_count ?? v.nayCount) ?? count(tally?.[2]),
      present_count: count(v.present_count), not_voting_count: count(v.not_voting_count),
      tally_source: tally ? 'official_action_text' : count(v.yea_count) !== null ? 'recorded_vote' : null };
  }
  function classifyAction(a) {
    const text = String(a.text || a.action_text || '');
    const vote = voteEvidence({ ...a, question: text });
    let kind = 'other';
    if (/\bbecame (?:public|private) law\b|^signed by (?:the )?president\b/i.test(text)) kind = 'enacted';
    else if (/^presented to (?:the )?president\b/i.test(text)) kind = 'presented_to_president';
    else if (/^vetoed by|returned to (?:the )?(?:house|senate).*veto/i.test(text)) kind = 'vetoed';
    else if (vote.kind === 'cloture' || vote.kind === 'motion_to_proceed') kind = 'procedural_vote';
    else if (vote.kind === 'passage' && vote.result === 'passed') kind = 'passage';
    else if (vote.kind === 'passage' && vote.result === 'failed') kind = 'passage_failed';
    else if (/^(?:House|Senate) agreed to (?:the )?(?:Senate|House) amendment(?:s)?(?: to .*?)? (?:without amendment|by|on)|^Cleared for White House|^Passed both (?:House|chambers)/i.test(text)) kind = 'passed_both_chambers';
    else if (/conference.*(?:appointed|requested|agreed)|disagreeing votes|resolving differences/i.test(text)) kind = 'resolving_differences';
    else if (/^Referred\b|^Received in (?:the )?(?:House|Senate)\b.*referred/i.test(text)) kind = 'referred';
    else if (/ordered to be reported|committee.*(?:markup|hearings|consideration)|^Committee Consideration/i.test(text)) kind = 'committee_consideration';
    else if (/^(?:Reported(?: \(| by| to| with| without)|Committee on .+\. Reported)/i.test(text)) kind = 'reported';
    else if (/^Introduced\b/i.test(text)) kind = 'introduced';
    return { kind, chamber: actionChamber(a), date: a.action_date || (a.actionDate ? `${a.actionDate}T${a.actionTime || '00:00:00'}Z` : null),
      text, source_url: a.source_url || null, action_id: a.bill_action_id || null, vote: ['procedural_vote', 'passage', 'passage_failed'].includes(kind) ? vote : null };
  }
  function buildLifecycle(bill) {
    const type = String(bill.bill_type || '').toLowerCase();
    const origin = chamber(bill.origin_chamber) || (/^h(?:r|jres|res|conres)$/.test(type) ? 'house' : /^s(?:jres|res|conres)?$/.test(type) ? 'senate' : null);
    const other = origin === 'house' ? 'senate' : origin === 'senate' ? 'house' : null;
    const sourceUrl = billUrl(bill.congress_number, type, bill.bill_number) || officialSource(bill.congress_url) || null;
    const supported = ['hr', 's'].includes(type);
    const events = (bill.bill_actions || []).map(classifyAction);
    for (const v of bill.bill_votes || []) {
      const vote = voteEvidence(v);
      if (!['passage', 'cloture', 'motion_to_proceed'].includes(vote.kind)) continue;
      events.push({ kind: vote.kind === 'passage' ? (vote.result === 'passed' ? 'passage' : vote.result === 'failed' ? 'passage_failed' : 'other') : 'procedural_vote',
        chamber: chamber(v.chamber), date: v.vote_date || null, text: v.question || '', source_url: v.source_url || null, action_id: v.vote_id || null, vote });
    }
    if (!events.some(e => e.kind === 'introduced') && bill.introduced_date) events.push({ kind: 'introduced', chamber: origin, date: bill.introduced_date, source_url: sourceUrl, text: 'Introduced', vote: null });
    events.sort((a, b) => (Date.parse(a.date) || 0) - (Date.parse(b.date) || 0));
    const specs = origin ? [
      [`${origin}_introduced`, `${CHAMBERS[origin]} 발의`, origin, ['introduced'], ['bill_id', 'introduced_date', 'sponsor']],
      [`${origin}_referred`, `${CHAMBERS[origin]} 위원회 회부·심사`, origin, ['referred', 'committee_consideration'], ['committee_id', 'activity_date', 'action_text']],
      [`${origin}_reported`, `${CHAMBERS[origin]} 상임위 보고`, origin, ['reported'], ['committee_id', 'report_date', 'report_url']],
      [`${origin}_passage`, `${CHAMBERS[origin]} 본회의 통과`, origin, ['passage'], ['vote_question', 'vote_result', 'vote_date', 'source_url']],
      ...(supported ? [
        [`${other}_referred`, `${CHAMBERS[other]} 회부·심사`, other, ['referred', 'committee_consideration'], ['committee_id', 'activity_date', 'action_text']],
        [`${other}_reported`, `${CHAMBERS[other]} 상임위 보고`, other, ['reported'], ['committee_id', 'report_date', 'report_url']],
        [`${other}_passage`, `${CHAMBERS[other]} 본회의 통과`, other, ['passage'], ['vote_question', 'vote_result', 'vote_date', 'source_url']],
        ['resolving_differences', '양원 이견 조정(필요시)', null, ['resolving_differences'], ['amendment_or_conference_text', 'concurrence_actions']],
        ['passed_both_chambers', '양원 동일안 확정', null, ['passed_both_chambers'], ['concurrence_action_or_unamended_passage']],
        ['presented_to_president', '대통령 송부', null, ['presented_to_president'], ['presentation_date', 'enrolled_text_url']],
        ['enacted', '법률 제정', null, ['enacted'], ['enactment_date', 'law_type', 'law_number', 'official_law_url']],
      ] : []),
    ] : [];
    const steps = specs.map(([id, label, c, kinds, required_data]) => ({ id, label, chamber: c, kinds, required_data, state: 'unconfirmed', evidence: [] }));
    let current = { stage: 'other', chamber: null, step_id: null, label: '단계 확인 필요' };
    let terminal = false;
    for (const e of events) {
      e.source_url = officialSource(e.source_url) || sourceUrl;
      const step = steps.find(s => s.kinds.includes(e.kind) && (!s.chamber || e.chamber === s.chamber));
      if (step) { step.state = 'observed'; step.evidence.push(e); }
      if (terminal || !step) continue;
      // A late re-referral does not erase that chamber's passage milestone.
      const passed = steps.find(s => s.id === `${e.chamber}_passage`)?.state === 'observed';
      if (passed && ['referred', 'reported', 'committee_consideration'].includes(e.kind)) continue;
      const stage = e.kind === 'passage' ? (e.chamber === origin ? 'passed_origin_chamber' : 'second_chamber')
        : e.chamber === other && ['referred', 'reported', 'committee_consideration'].includes(e.kind) ? 'second_chamber' : e.kind;
      if (steps.findIndex(s => s.id === current.step_id) > steps.indexOf(step)) continue;
      current = { stage, chamber: e.chamber, step_id: step.id, label: step.label };
      if (supported && e.kind === 'passage' && e.chamber === other && /without amendment/i.test(e.text)
        && steps.find(s => s.id === `${origin}_passage`)?.state === 'observed') {
        const agreed = steps.find(s => s.id === 'passed_both_chambers');
        agreed.state = 'observed'; agreed.evidence.push({ ...e, kind: 'passed_both_chambers', basis: 'other_chamber_passage_without_amendment' });
        current = { stage: 'passed_both_chambers', chamber: e.chamber, step_id: agreed.id, label: agreed.label };
      }
      terminal = e.kind === 'enacted';
    }
    // Passage of both chambers alone does not prove agreement on the same text.
    const latestEvent = [...events].reverse().find(e => e.kind !== 'other') || null;
    const latestVote = [...events].reverse().find(e => e.vote && e.vote.result !== 'unknown') || null;
    if (!terminal && latestEvent?.kind === 'vetoed') current = { stage: 'vetoed', chamber: 'executive', step_id: null, label: '대통령 거부권 행사' };
    const alert = !terminal && latestVote && latestEvent && latestVote.date === latestEvent.date && ['procedural_vote', 'passage_failed'].includes(latestVote.kind)
      ? { chamber: latestVote.chamber, kind: latestVote.vote.kind, result: latestVote.vote.result,
        label: `${CHAMBERS[latestVote.chamber] || '원 미확인'} ${latestVote.vote.kind === 'cloture' ? '토론 종결' : latestVote.vote.kind === 'passage' ? '법안 통과' : '심의 개시'} 표결 ${latestVote.vote.result === 'failed' ? '부결' : '가결'}`, evidence: latestVote } : null;
    const index = steps.findIndex(s => s.id === current.step_id);
    return { version: 1, origin_chamber: origin, current, latest_event: latestEvent, procedural_alert: alert, steps,
      next: terminal ? null : steps.slice(index + 1).find(s => s.state !== 'observed') || null,
      coverage: { actions: (bill.bill_actions || []).length, votes: (bill.bill_votes || []).length, chamber_unknown: events.filter(e => !e.chamber && !['other', 'enacted', 'presented_to_president'].includes(e.kind)).length,
        pathway: supported ? 'bill' : 'partial_resolution_or_unknown' },
      note: '미확인 단계는 미발생을 뜻하지 않습니다. 절차 표결은 법안 통과와 다르며 양원 동일안 여부는 별도 근거가 필요합니다.' };
  }
  function notificationSnapshot(lifecycle) {
    const e = lifecycle.latest_event;
    return { version: 1, origin_chamber: lifecycle.origin_chamber, current: lifecycle.current,
      latest_event: e ? { kind: e.kind, chamber: e.chamber, date: e.date, text: e.text, source_url: e.source_url, vote: e.vote } : null,
      procedural_alert: lifecycle.procedural_alert ? { label: lifecycle.procedural_alert.label, kind: lifecycle.procedural_alert.kind, result: lifecycle.procedural_alert.result } : null,
      next: lifecycle.next ? { id: lifecycle.next.id, label: lifecycle.next.label, required_data: lifecycle.next.required_data } : null };
  }
  return { parseBillQuery, billUrl, actionChamber, classifyAction, voteEvidence, buildLifecycle, notificationSnapshot };
});
