export const BASIS_LABELS = {
  official_reference: '공식 공표·통계 근거', literature_range_midpoint: '문헌 추정값',
  literature_review_midpoint: '문헌 추정값', literature_proxy: '산업·시점 대용값',
  historical_sector_proxy: '산업·시점 대용값', editable_example: '계산 예시', user_assumption: '사용자 가정',
};
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function basisMarkup(rows) {
  return `<div class="ts-basis" data-input-basis>${rows.map(r=>`<p><b>${esc(r.label)} · ${esc(BASIS_LABELS[r.kind] || '사용자 가정')}</b><br><small>${esc(r.note)}</small></p>`).join('')}</div>`;
}
export function marketCalibration(product, snapshot) {
  const observed = snapshot.products?.[product];
  return {
    status: 'not_calibrated', applied: false, purchase_basis: 'unverified_user_scenario',
    domestic_supply: null, comparable_market_shares: null,
    supplier_reference: observed ? { year: snapshot.year, hts6: observed.hts6, measure: snapshot.measure, url: snapshot.url } : null,
    blockers: ['미국 국내 공급과 수입을 동일 품목·기간으로 맞춘 자료 미확보',
      '수입 통관가액은 관세 포함 구매액과 다름',
      ...(observed ? ['HS6 집계와 대표 HTS·제품 범위의 일치 확인 필요'] : ['이 품목의 공급국 통계 미수록'])],
    note: '50/25/25 초기값과 편집한 구매액은 실측 시장 비중으로 검증되지 않았습니다.',
  };
}
