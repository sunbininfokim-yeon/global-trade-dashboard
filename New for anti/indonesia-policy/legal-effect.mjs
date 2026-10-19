const labels={unverified:'현행 효력 미확인',fully_repealed:'전부 폐지 조항 확인',partially_repealed:'일부 조항 폐지 확인',amended:'개정 조항 확인 · 통합본 검토 필요',expired:'명시된 효력기간 종료',not_yet_effective:'확인된 시행일 전',effective_date_unverified:'효력 조항 확인 · 적용일 미확인',commenced_review_needed:'시행일 확인 · 후속 개폐 미확인',conflicting_evidence:'효력 근거 상충 · 재검토 필요'};
export function effectLabel(effect){return labels[effect?.status]||labels.unverified;}
export const findingLabels={commencement:'시행',amendment:'개정',full_repeal:'전부 폐지',partial_repeal:'일부 폐지',expiry:'효력기간 종료',transition:'경과조치'};
