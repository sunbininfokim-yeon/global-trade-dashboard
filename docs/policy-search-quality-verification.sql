-- 조회 전용: 새 검색 인덱스·서비스 전용 권한·색인 진행률 확인
select jsonb_build_object(
 'ann_function_installed',position('nearest as materialized' in pg_get_functiondef('public.search_policy_vectors_for_type(extensions.vector,text,text,integer)'::regprocedure))>0,
 'proof_pool_limited',position('limit greatest(50,least(p_limit*2,200))' in pg_get_functiondef('public.search_policy_document_terms_for_type(jsonb,text,integer)'::regprocedure))>0,
 'anon_allowed',has_function_privilege('anon','public.search_policy_vectors_for_type(extensions.vector,text,text,integer)','execute'),
 'authenticated_allowed',has_function_privilege('authenticated','public.search_policy_balanced_terms(jsonb,integer)','execute'),
 'indexes',(select jsonb_agg(jsonb_build_object('name',indexname,'size',pg_size_pretty(pg_relation_size(('public.'||indexname)::regclass)))) from pg_indexes where schemaname='public' and indexname like 'policy_search_passages_%_ann'),
 'building',(select jsonb_agg(phase) from pg_stat_progress_create_index where relid='public.policy_search_passages'::regclass),
 'settings',(select jsonb_object_agg(proname,proconfig) from pg_proc where proname in ('search_policy_vectors_for_type','search_policy_legacy_vectors_for_type')),
 'documents',(select jsonb_object_agg(source_type,total) from (select source_type,count(*) total from policy_search_documents group by source_type) t),
 'status',policy_search_status()) search_verification;
-- 실제 자료의 유형별 후보는 서비스 RPC를 개별 호출해 검증한다.
-- 유형별 병렬 호출 Worker와 SQL 합산 실행의 시간 제한은 별도로 검증한다.
