-- 조회 · 본문·인용 기반 검색 확인 (읽기 전용)
select source_type as "문서종류", source_id as "문서ID",
  '캐나다 + 관세' as "검색조건",
  (select string_agg(distinct p->>'field',', ')
   from jsonb_array_elements(evidence_parts) p) as "근거위치",
  refresh_pending as "갱신대기",
  (select count(*) from public.policy_search_documents) as "전체색인건수",
  not has_function_privilege('anon','public.search_policy_document_terms(jsonb,integer)','EXECUTE') as "익명RPC차단"
from public.search_policy_document_terms(
  '[{"key":"캐나다","aliases":["canada","canadian"]},{"key":"관세","aliases":["tariff","tariffs"]}]'::jsonb,100)
where (source_type='bill' and source_id='119-hjres-72')
   or (source_type='executive_order' and source_id='14193');

-- 전체 진행률은 아래 문장을 선택해서 따로 실행하세요.
-- select public.policy_search_status();
