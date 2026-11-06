// Reviewed source receipts. These are dated observations, not live legal status.
export const cases = [{
  case_id: 'coupang-korea-data-and-trade',
  title: '쿠팡의 한국 개인정보 규제와 미국 통상 대응',
  countries: ['KR', 'US'], reviewed_at: '2026-11-05',
  note: '각 문서의 발표·제출 사실을 연결한 사례입니다. 최신 불복·집행 상태와 로비 효과는 미확인입니다.',
  events: [
    { date: '2026-01-22', type: 'petition', actor: 'Greenoaks Capital Partners · Altimeter Capital Management',
      title: '투자자들의 USTR 301조 청원',
      description: '투자자들이 쿠팡 관련 한국 조치를 문제 삼으며 관세·서비스 제한 등을 요청했습니다. 청원 게재와 조사 개시·관세 결정은 별도입니다.',
      url: 'https://ustr.gov/sites/default/files/files/Issue_Areas/Enforcement/Section%20301/Coupang/2026.01.22%20Section%20301%20Petition.pdf',
      evidence: '표지, 원문 인쇄 28쪽 요청 조치', link_strength: 'explicit' },
    { date: '2026-06-11', type: 'agency_decision', actor: '대한민국 개인정보보호위원회',
      title: '개인정보 유출·침해 제재처분 의결 발표',
      description: '한국 규제기관의 처분 의결과 시정명령 발표입니다. 후속 법원 판단·집행 상태는 별도 확인 대상입니다.',
      url: 'https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=B030020000&nttId=12171',
      evidence: '2026-06-11 보도자료', link_strength: 'explicit' },
  ],
  contextual_records: [{
    record_id: 'lda:f852f554-8c83-404b-8e79-309613e03c66',
    title: '쿠팡의 2025년 통상·경제협력 로비 신고', link_strength: 'contextual',
    note: '특정 법안 없음. 이 신고만으로 개인정보 분쟁 대응 로비라고 확인할 수 없습니다.',
    url: 'https://lda.gov/filings/public/filing/f852f554-8c83-404b-8e79-309613e03c66/print/'
  }],
}];
