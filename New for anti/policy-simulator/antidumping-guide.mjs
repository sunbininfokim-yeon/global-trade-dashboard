import { AD_CATALOG } from './antidumping-catalog.mjs';
import { lookupAD } from './antidumping-model.mjs';

// Demonstration transaction totals, not estimated industry averages or company sales.
export const AD_EXAMPLES = {
  'A-580-914': { label: '고흡수성 수지 · SAP', value: '100000', note: '10만 USD의 SAP 거래 총액 예시입니다. LG화학 실제 거래가나 산업 평균이 아닙니다.' },
  'A-580-883': { label: '철강 · 열연강판', value: '100000', note: '10만 USD의 열연강판 거래 총액 예시입니다. 산업 평균이나 현대제철·포스코의 실제 거래가가 아닙니다.' },
  'A-580-897': { label: '강관 · 대구경 용접강관', value: '100000', note: '10만 USD의 강관 거래 총액 예시입니다. 강관 1개 가격·산업 평균·회사 실제 거래가가 아닙니다.' },
  'A-580-867': { label: '대형 전력용 변압기', value: '1000000', note: '100만 USD 규모의 거래를 비교하는 예시입니다. 변압기 1대의 평균 가격이나 효성·LS의 실제 거래가가 아닙니다.' },
  'A-580-908': { label: '승용차·경트럭 타이어', value: '100000', note: '10만 USD 규모의 여러 타이어 수입 거래를 비교하는 예시입니다. 타이어 1개 가격이나 한국타이어의 실제 거래가가 아닙니다.' },
};
export const AD_GUIDE_FIELDS = ['entered_value_usd', 'scenario_rate_pct', 'annual_finance_pct', 'holding_days', 'entry_date'];

export function createADExample(input) {
  const published = input.reference_mode !== 'manual';
  const preset = published ? AD_EXAMPLES[input.case_id] : null;
  if (published && !preset) throw new Error('예시가 등록된 품목을 선택하세요.');
  let reference = null;
  if (published) {
    try { reference = lookupAD(input); } catch { /* Invalid date remains a form error. */ }
  }
  // A +5 percentage-point sensitivity, never a prediction or another firm's actual rate.
  const rate = reference?.rate_pct == null ? '' : (Number(reference.rate_pct) + 5).toFixed(2);
  return {
    id: published ? input.case_id : 'manual_transaction',
    label: preset?.label || '다른 사건 · 일반 거래 예시',
    values: { entered_value_usd: preset?.value || '100000', scenario_rate_pct: rate, annual_finance_pct: '5', holding_days: '365', entry_date: input.entry_date },
    basis: { case_id: input.case_id, company_id: input.company_id, entry_date: input.entry_date, reference_rate_pct: reference?.rate_pct ?? null, document_id: reference?.document?.document_id ?? null, increment_percentage_points: rate ? 5 : null },
    notes: {
      entered_value_usd: preset?.note || '10만 USD의 예시 거래 총액입니다. 실제 계약·통관 신고가격으로 바꾸세요.',
      scenario_rate_pct: rate ? `선별 공표 참고율 ${reference.rate_pct}%에 5%p를 더한 민감도 가정입니다. 예상 판정이나 산업 평균이 아닙니다.` : '기준 예치율을 확인하지 못해 비교율은 비워 두었습니다. 출처 확인 후 직접 입력하세요.',
      annual_finance_pct: '연 5%는 계산을 시작하기 위한 단리 자금비용 가정입니다. 시장금리·업종 평균·회사 차입금리·CBP 법정 이자가 아닙니다.',
      holding_days: '365일은 자금이 묶이는 기간의 비교 가정입니다. 법정 재심 기간·환급일·정산 완료일이 아닙니다.',
      entry_date: `자료 확인 기준일은 ${AD_CATALOG.checked_on}입니다. 이 입력은 통관 가정일이며 실제 선적일·POR·재심 종료일이 아닙니다.`,
    },
  };
}

export function describeADInputs(input, example, editedKeys = []) {
  return AD_GUIDE_FIELDS.map(key => {
    const contextMatches = key !== 'scenario_rate_pct' || (input.reference_mode !== 'manual' && example.basis.case_id === input.case_id && example.basis.company_id === input.company_id && example.basis.entry_date === input.entry_date);
    const fromExample = contextMatches && !editedKeys.includes(key) && String(input[key]) === example.values[key];
    return { key, value: String(input[key]), origin: fromExample ? 'editable_example' : 'user_input', note: fromExample ? example.notes[key] : '사용자가 입력·수정한 거래 또는 시나리오 값입니다. 실제 공표·산업 평균값으로 검증되지 않았습니다.' };
  });
}

export const AD_PROCESS_SOURCES = {
  commerce: { label: '상무부 · 조사와 행정재심 절차', url: 'https://www.trade.gov/antidumping-and-countervailing-duty-frequently-asked-questions' },
  injury: { label: 'USITC · 덤핑과 산업피해 판단의 역할', url: 'https://www.usitc.gov/press_room/usad.htm' },
  assessment: { label: '19 CFR §351.212 · 사후 관세 확정', url: 'https://www.ecfr.gov/current/title-19/section-351.212' },
  judicial: { label: '19 U.S.C. §1516a · 사법심사·정산 금지·환송', url: 'https://www.cit.uscourts.gov/sites/cit/files/19U.S.C.1516a.pdf' },
  remand: { label: 'CIT Rule 56.2 · 기록심사·환송 후 절차', url: 'https://www.cit.uscourts.gov/sites/cit/files/Rule%2056.2.pdf' },
  appeal: { label: '28 U.S.C. §1295(a)(5) · Federal Circuit 관할 · 2024 법전', url: 'https://www.govinfo.gov/content/pkg/USCODE-2024-title28/pdf/USCODE-2024-title28-partIV-chap83-sec1295.pdf' },
  supreme: { label: '미 연방대법원 · 2026 규칙 Rule 10', url: 'https://www.supremecourt.gov/filingandrules/2026RulesoftheCourt_WEB.pdf' },
};

// Actual progress requires a sourced event for this case AND this review period.
// Neither an event in another POR nor the passage of a deadline completes a stage.
export const AD_REVIEW_RECORDS = [
  { id: 'sap-2023-24', case_id: 'A-580-914', por_start: '2023-12-01', por_end: '2024-11-30', companies: ['lg-chem'],
    events: [{ stage: 'preliminary', date: '2026-05-22', source: '2026-19625', note: '최종 공고 Background가 인용한 예비결과 발행일입니다.' },
      { stage: 'final', date: '2026-09-25', source: '2026-19625', note: 'LG Chem, Ltd. 0.00% 최종 마진. 실제 수입 정산·법원 판단 완료를 뜻하지 않습니다.' }],
    deposit: { date: '2026-09-25', source: '2026-19625' } },
  { id: 'welded-pipe-nonselected-2024-25', case_id: 'A-580-897', por_start: '2024-05-01', por_end: '2025-04-30', companies: ['chang-won', 'dong-yang', 'eew-korea', 'histeel', 'hyundai-rb', 'nexteel'],
    events: [{ stage: 'initiation', date: '2025-06-25', source: '2026-15399', note: '예비 공고 Background가 인용한 재심 개시일입니다.' },
      { stage: 'preliminary', date: '2026-07-30', source: '2026-15399', note: 'Appendix III의 비선정 6개사에 예비 마진 0.80%를 배정했습니다. 개별조사 기업으로 선정되었다는 뜻이 아니며 미래 예치율 변경도 아닙니다.' }] },
  { id: 'welded-pipe-rescinded-2024-25', case_id: 'A-580-897', por_start: '2024-05-01', por_end: '2025-04-30',
    companies: ['aju', 'daiduck', 'dongbu', 'eew-khpc', 'geumok', 'hansol', 'husteel', 'il-jin-nts', 'kiduck', 'kum-kang', 'kumsoo', 'seonghwa', 'sin-e', 'steel-flower', 'weltech'],
    events: [{ stage: 'initiation', date: '2025-06-25', source: '2026-15399', note: '해당 POR의 재심 개시일입니다.' }],
    status: 'rescinded', status_event: { date: '2026-07-30', source: '2026-15399', note: 'Appendix II의 15개사는 이 POR에 재심 대상 거래가 없어 재심이 철회되었습니다. 0% 판정·반덤핑 명령 폐지·관세 정산 완료를 뜻하지 않습니다.' } },
  { id: 'welded-pipe-nonselected-2023-24', case_id: 'A-580-897', por_start: '2023-05-01', por_end: '2024-04-30',
    companies: AD_CATALOG.cases.find(c => c.case_id === 'A-580-897').companies.filter(c => !['hyundai-pipe', 'seah'].includes(c.id)).map(c => c.id),
    events: [{ stage: 'final', date: '2026-05-01', source: '2026-08489', note: 'Appendix II의 비선정 21개사 최종 배정 마진 0.80%. 해당 법인의 미래 통관 예치율은 별도로 확인하지 않았습니다.' }] },
  { id: 'hot-rolled-2023-24', case_id: 'A-580-883', por_start: '2023-10-01', por_end: '2024-09-30', companies: ['hyundai-steel', 'posco-pic'],
    events: [{ stage: 'preliminary', date: '2026-01-08', source: '2026-09707', note: '최종 공고 Background가 인용한 예비결과 발행일입니다.' },
      { stage: 'final', date: '2026-05-14', source: '2026-09707', note: '현대제철 1.49%, POSCO/PIC 1.22% 최종결과. CBP 정산·법원 판단의 완료를 뜻하지 않습니다.' }],
    deposit: { date: '2026-05-14', source: '2026-09707' } },
  { id: 'welded-pipe-2024-25', case_id: 'A-580-897', por_start: '2024-05-01', por_end: '2025-04-30', companies: ['hyundai-pipe', 'seah'],
    events: [{ stage: 'initiation', date: '2025-06-25', source: '2026-15399', note: '예비 공고 Background의 개시일 인용입니다.' },
      { stage: 'selection', date: '2025-08-27', source: '2026-15399', note: '예비 공고 Background에서 현대스틸파이프·세아제강의 선정일을 확인했습니다.' },
      { stage: 'preliminary', date: '2026-07-30', source: '2026-15399', note: '두 기업 모두 예비 마진 0%. 이전 POR의 최종 예치 참고율은 자동 변경하지 않습니다.' }] },
  { id: 'welded-pipe-2023-24', case_id: 'A-580-897', por_start: '2023-05-01', por_end: '2024-04-30', companies: ['hyundai-pipe', 'seah'],
    events: [{ stage: 'preliminary', date: '2025-08-29', source: '2026-08489', note: '최종 공고 Background가 인용한 예비결과 발행일입니다.' },
      { stage: 'final', date: '2026-05-01', source: '2026-08489', note: '현대스틸파이프 0%, 세아제강 0.80% 최종결과. 실제 수입자별 관세 정산과 구분합니다.' }],
    deposit: { date: '2026-05-01', source: '2026-08489' } },
  { id: 'lpt-2025-26', case_id: 'A-580-867', por_start: '2025-08-01', por_end: '2026-07-31', companies: ['hyundai', 'iljin', 'ls', 'hyosung'],
    events: [{ stage: 'initiation', date: '2026-10-01', source: '2026-20160', note: '이 공고에서 네 법인의 행정재심 개시를 확인했습니다. 새 예치율이나 개별조사 선정 결과가 아닙니다.' }] },
  { id: 'lpt-2023-24', case_id: 'A-580-867', por_start: '2023-08-01', por_end: '2024-07-31', companies: ['hyundai', 'iljin', 'ls', 'hyosung'],
    events: [
      { stage: 'initiation', date: '2024-09-20', source: '2026-02646', note: '예비 공고 Background가 이 POR의 개시일과 89 FR 77079를 인용합니다.' },
      { stage: 'selection', date: '2024-10-30', source: '2026-02646', note: '현대·일진 개별조사 선정. 예비 공고 각주 3의 Respondent Selection 메모 날짜입니다.' },
      { stage: 'preliminary', date: '2026-02-10', source: '2026-02646', note: '예비결과 공표. 이 행정재심 예비결과만으로 새 예치율이 발효하지 않습니다.' },
      { stage: 'comments', date: '2026-07-01', source: 'ACCESS-4943770-02', note: '상무부 결정문 p.2: LS·효성·일진·신청인의 case briefs 제출. 이는 법원 소장 접수와 다릅니다.' },
      { stage: 'final', date: '2026-08-14', source: '2026-16663', note: '최종결과 공표: 현대·일진 0%, LS·효성 4.32%. CBP의 실제 개별 수입 정산 완료를 뜻하지 않습니다.' },
    ], deposit: { date: '2026-08-14', source: '2026-16663' } },
  { id: 'lpt-2022-23', case_id: 'A-580-867', por_start: '2022-08-01', por_end: '2023-07-31', companies: ['hyundai', 'iljin', 'ls'],
    events: [{ stage: 'final', date: '2025-04-08', source: '2025-05960', note: '수록 최종결과: 현대 0%, 일진·LS 16.87%. 이 기록에는 앞 단계별 원문을 수록하지 않았습니다.' }], deposit: { date: '2025-04-08', source: '2025-05960' } },
  { id: 'tires-2023-24', case_id: 'A-580-908', por_start: '2023-07-01', por_end: '2024-06-30', companies: ['hankook', 'nexen', 'kumho'],
    events: [
      { stage: 'selection', date: null, source: '2026-14027', note: '최종 공고에서 한국타이어·넥센을 개별조사 기업으로 확인. 정확한 선정일은 미수록입니다.' },
      { stage: 'preliminary', date: '2026-01-08', source: '2026-14027', note: '최종 공고 Background의 예비결과 발행일. 예비 공고 세율은 수록하지 않았습니다.' },
      { stage: 'comments', date: null, source: '2026-14027', note: '최종 공고 Analysis of Comments에서 의견·반박서 검토를 확인. 제출일은 미수록입니다.' },
      { stage: 'final', date: '2026-07-13', source: '2026-14027', note: '한국타이어 13.03%, 넥센 8.02%, 금호 10.53%. 수입자별 사후 부과율과 미래 예치율을 구분해야 합니다.' },
    ], deposit: { date: '2026-07-13', source: '2026-14027' } },
];

const stage = (id, label, agency, description, source) => ({ id, label, agency, description, source });
export const AD_PROCESS_STEPS = {
  investigation: [
    stage('petition', '국내 산업 신청·조사 개시', '상무부 · USITC', '미국 국내 산업의 신청 등을 받아 덤핑 조사와 피해 조사를 시작합니다.', 'commerce'),
    stage('injury_preliminary', '산업피해 예비판정', 'USITC', '피해 또는 피해 우려의 합리적 징후를 판단합니다. 부정 판정이면 해당 조사는 종료될 수 있습니다.', 'injury'),
    stage('dumping_preliminary', '덤핑 예비판정', '상무부', '덤핑 여부와 잠정 마진을 판단합니다. 긍정 예비판정에 따른 잠정 예치가 시작될 수 있습니다. 상무부 예비 부정 판정만으로 조사 종료를 단정하지 않습니다.', 'commerce'),
    stage('dumping_final', '덤핑 최종판정', '상무부', '기업별 덤핑 여부·마진을 최종 판단합니다.', 'commerce'),
    stage('injury_final', '산업피해 최종판정', 'USITC', '미국 국내 산업의 실질적 피해·피해 우려 등을 판단합니다. 긍정 최종판정 조건을 충족해야 명령으로 이어집니다.', 'injury'),
    stage('order', '반덤핑 명령', '상무부', '필요한 긍정 최종판정을 거쳐 AD 명령을 발행합니다. 이후 수입 예치·연례 재심 경로가 이어집니다.', 'commerce'),
  ],
  review: [
    stage('initiation', '행정재심 개시', '상무부', '기존 명령의 특정 POR·기업에 대한 재심입니다. 새 조사·산업피해 재판정과 다릅니다.', 'commerce'),
    stage('selection', '조사기업 선정·자료 검토', '상무부', '개별조사 대상을 정하고 판매·원가 자료를 검토합니다. 선정 제외가 무관세를 뜻하지 않습니다.', 'commerce'),
    stage('preliminary', '예비결과', '상무부', '잠정 재심 결과를 공표합니다. 행정재심의 예비결과만으로 미래 현금예치율을 바꾸지 않습니다.', 'commerce'),
    stage('comments', '의견·반박 제출·검토', '당사자 · 상무부', '기업·신청인이 행정기록에 의견을 내고 상무부가 검토합니다. case brief는 CIT 소송과 다릅니다.', 'commerce'),
    stage('final', '최종결과', '상무부', '해당 POR의 사후 부과 근거와 향후 예치율을 정합니다. 개별조사 기업은 수입자별 사후 부과율이 공표 마진과 다를 수 있습니다.', 'assessment'),
    stage('liquidation', '수입 건별 관세 확정·정산', 'CBP · 미국 세관', '상무부 지침과 적용되는 법원 명령에 따라 실제 수입 건의 관세를 확정하고 예치금 차액을 정산합니다. 최종결과 공고만으로 완료 처리하지 않습니다.', 'assessment'),
  ],
  litigation: [
    stage('cit_filed', 'CIT 제소', '이해관계 당사자', '행정재심 최종결과 등의 적법성을 국제무역법원에 다툽니다. §1516a(a)(2)의 통상 경로는 공표 후 30일 내 summons, 그 후 30일 내 complaint이며 결정 유형·적격·예외 확인이 필요합니다. 여기서는 개인별 기한을 계산하지 않습니다.', 'judicial'),
    stage('injunction', '관세 확정 금지명령 · 필요시', 'CIT', '관련 수입 건의 liquidation을 막는 법원 명령입니다. 소송 접수만으로 기존 예치 의무나 관세 확정이 자동 중단되는 것은 아닙니다.', 'judicial'),
    stage('cit_decision', 'CIT 심리·판결', '국제무역법원', '행정기록과 법률에 따라 판단합니다. 승인·기각·일부 승소·환송 등이 있어 단순 승패 한 단계로 축약하지 않습니다.', 'remand'),
    stage('remand', '상무부 재결정·재심사 · 환송시', '상무부 ↔ CIT', '환송되면 상무부가 재결정하고 법원이 다시 심사할 수 있습니다. 환송은 즉시 환급 또는 최종 승소를 뜻하지 않습니다.', 'remand'),
    stage('appeal', 'Federal Circuit 항소 · 선택', '연방순회항소법원', '항소 가능한 CIT 최종판결 등을 항소심에서 다툽니다. 모든 사건이 자동 항소되는 것은 아닙니다.', 'appeal'),
    stage('supreme', '대법원 심리허가 신청 · 선택', '미 연방대법원', '연방항소심 이후 certiorari를 신청할 수 있습니다. 심리 허가 여부는 대법원의 재량이며 자동으로 진행되는 3심이 아닙니다.', 'supreme'),
  ],
};

export function reviewRecords(caseId, companyId) {
  return AD_REVIEW_RECORDS.filter(r => r.case_id === caseId && r.companies.includes(companyId)).map(r => structuredClone(r));
}
export function reviewProgress(caseId, recordId) {
  const r = AD_REVIEW_RECORDS.find(r => r.case_id === caseId && r.id === recordId);
  if (!r) throw new Error('선택한 사건의 재심 기록을 확인하세요.');
  const last = AD_PROCESS_STEPS.review.findLast(s => r.events.some(e => e.stage === s.id));
  return { ...structuredClone(r), checked_on: AD_CATALOG.checked_on, latest_stage: r.status === 'rescinded' ? 'rescinded' : last.id,
    stages: AD_PROCESS_STEPS.review.map(s => {
      const event = r.events.find(e => e.stage === s.id);
      return { ...s, state: event ? (s.id === last.id && r.status !== 'rescinded' ? 'latest' : 'confirmed') : 'unknown', event: event ? { ...event, document: structuredClone(AD_CATALOG.documents[event.source]) } : null };
    }),
    // This curated dataset has no verified docket for these PORs. Empty is not proof of no lawsuit.
    litigation: AD_PROCESS_STEPS.litigation.map(s => ({ ...s, state: 'unknown', event: null })),
  };
}
