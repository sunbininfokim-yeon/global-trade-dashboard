-- A distinct Indonesian category; no US search/lifecycle changes.
begin;
set local lock_timeout='3s';
alter table policy_idn.documents drop constraint if exists idn_policy_documents_primary_stage_check;
alter table policy_idn.documents add constraint idn_policy_documents_primary_stage_check
  check(primary_stage in ('coal','nickel_mining','palm_oil','biofuel'));
comment on table policy_idn.documents is '인도네시아 석탄·니켈광산·팜유·바이오연료 공식 문서. 중앙·지방 구분, 현행 효력·완전성 미확인.';
commit;
