# Claude → Codex: 인도네시아 규제 메일 실제 발송 켜기 (2026-10-22)

## 현재 상태
- PR #652 병합(`4e541a38`). 사이트 배포 성공 — 인니 정책 페이지에 "상품·사업지역 규제 메일 구독"(13개 품목 × 지역/전국) 노출.
- 메일 Worker 재배포 성공(run 39721314955, `send_enabled=true` = 10/11 배포와 동일 값). 법안·원자재 메일은 기존대로 발송.
- **인니 메일 실제 발송은 0건 상태.** `policy_idn.mail_config.delivery_enabled=false`라 구독 저장만 되고 큐 등록·발송은 안 됨.
- #652의 DB migration 9개는 이전에 운영 적용 완료. Claude는 이번에 Supabase를 건드리지 않았다.

## 켜기 전 확인 (Supabase 권한 필요 — Codex/사용자)
1. 실제 로그인 계정으로 인니 페이지에서 구독 저장·새로고침·해제·재구독이 되는지.
2. `idn_my_mail_subscriptions` 결과와 DB 구독 행이 일치하는지, anon/타 사용자 접근이 막혀 있는지.
3. 검토 완료(`reviewed`) 변경 1건이 매칭 구독자에게 outbox로 한 번만 들어가는지(전국+지역 중복 시에도 1건).
4. 이상 없으면 `delivery_enabled=true`. 첫 발송은 다음 날 06:00 KST 정책 메일 경로.
5. 켠 뒤 첫 발송의 provider 접수 기록·실제 수신 확인. 문제가 있으면 `delivery_enabled=false`로 되돌림(큐 삭제·재발송 금지).

## 주의
- 메일 Worker 재배포(`deploy-mailing.yml`)는 `send_enabled` 기본값이 **false**. 그대로 실행하면 법안·원자재 포함 **모든 메일이 꺼진다.** 반드시 `true`로 실행.
- 인니 스위치는 DB, 전체 발송 스위치는 Worker — 둘은 별개다.
