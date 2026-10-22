# 인계 2026-10-22 — claude → codex (메일 보관: 브랜치 유입 사고)

Supabase·메일링은 Codex 담당이다. Claude가 사고를 발견해 사용자 확인 하에 긴급 조치만 했고, 검증과 후속 판단은 Codex에게 넘긴다.

## 무슨 일이 있었나

- `commodity_reports.yml`의 "Archive report metadata for mailing" 단계(`scripts/archive-mailing-reports.js` → `mailing_reports` upsert → `mail_capture_report` 트리거 → `mailing_outbox`)가 **작업 브랜치 `claude/reports-user-feeds`에서 수동 실행한 수집(2026-10-21 run 219~223)**에서도 운영 키로 실행됐다.
- 그 결과 미병합 소스 33곳(`int_mining_*`, `gn_*`, `id_antara_*` 등)의 381행이 `mailing_reports`/`mailing_report_editions`에 들어갔다(구글 리다이렉트 URL 157행 포함). `mailing_outbox`에는 47건(수신자 1명, `due_at` 2026-10-25 23:00 UTC = 10/26 08:00 KST)이 생겼다.

## Claude가 한 긴급 조치 (2026-10-22 04:0x UTC, 사용자 승인)

한 트랜잭션에서 건수를 검증했다(381/47/발송 0건이 아니면 중단).
1. 47건 `mailing_outbox.suppressed_at = now()` (delivery_id 없음, 미발송).
2. 해당 33개 source_id의 `mailing_reports` 381행 DELETE → `mailing_report_editions` CASCADE.
3. 사후 확인: 남은 행 0, editions 0, 같은 due_at의 미차단 1건은 main에서 온 정상 건이라 그대로 둠.

## Codex에게 부탁할 것

1. 위 조치가 메일링 설계(trigger·receipts·edition 판별)에 맞는지 검증하고, 필요하면 바로잡기. 예: suppress 대신 다른 정리 방식이 맞는지, 지운 report_id가 다른 곳(통계·감사 로그)에 남아 있는지.
2. PR #665에 넣은 두 변경을 검토하기(Codex 소유 파일 포함):
   - `scripts/archive-mailing-reports.js`: `publisher_type: "news"` 항목은 보관하지 않음(`skipped_news`). 테스트는 `scripts/lib/policy-mailing-archive.test.cjs`에 있다.
   - `.github/workflows/commodity_reports.yml`: 보관 단계를 `refs/heads/main`에서만 실행.
   뉴스를 메일에서 아예 뺄지, 다른 방식(예: 상품별 상한)이 맞을지는 메일링 담당 판단으로 바꿔도 된다.
3. 브랜치 실행이 운영 DB에 닿는 경로가 이 단계 말고도 있는지 점검하기.

Claude는 앞으로 Supabase 쓰기를 하지 않는다. 필요한 경우 이 디렉터리에 인계 문서를 남긴다.
