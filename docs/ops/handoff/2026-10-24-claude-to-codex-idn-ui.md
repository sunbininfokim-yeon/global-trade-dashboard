# 2026-10-24 Claude → Codex: 인도네시아 정책 화면 변경 인수인계

## 운영 반영 완료 (모두 main 병합 + Cloudflare 배포 성공)

| PR | 내용 |
|---|---|
| #668 | IDN 메일 활성화 절차 문서 (`2026-10-22-claude-to-codex-idn-mail-enable.md`) |
| #671 | 메인 상단 메뉴 공용화(`site-nav.js/css`), 구독 세션 우선 확인, `deploy.yml`에 `Coal reference prices` 연결 |
| #673 | `/policy/indonesia` 라우팅, 별표 즐겨찾기, 미국 정책 화면과 같은 틀 |

## 지금 구조

- **주소:** `/policy/indonesia`
  - `_worker.js`가 `indonesia-policy/` 정적 페이지를 이 주소로 내준다.
  - `/indonesia-policy`, `/indonesia-policy/`, `/indonesia-policy/index.html`, `/policy/indonesia/`는 301로 넘긴다. 쿼리는 유지한다.
  - 이 경로들은 `wrangler.jsonc`의 `run_worker_first`에 정확히 등록돼 있다. 빼면 SPA 폴백이 메인 index.html을 돌려준다.
  - 페이지 자산은 모두 절대경로(`/indonesia-policy/...`, `/site-nav.*`, `/auth-config.js`)다. 상대경로로 되돌리면 새 주소에서 깨진다.
- **상단 메뉴:** `New for anti/site-nav.js`가 `/`(메인 index.html)에서 `header.top-nav`를 읽어 붙인다.
  - 메인 메뉴를 고치면 인도네시아에도 자동으로 반영된다. 별도 복사본이 없다.
  - 스타일은 `site-nav.css`에 있고, style.css 규칙을 복사한 것이다. 메인 메뉴 모양을 바꾸면 같이 맞춘다.
  - 메뉴를 불러오지 못하면 간단한 대체 헤더가 남는다.
- **페이지 틀:** 미국 정책 화면(`.policy-head`)과 같은 모양이다. 국가 라벨, pill 버튼, 경로 표시가 있다. 검색은 가운데에 그대로 둔다.
- **즐겨찾기:** 키워드 예시 아래의 `<details id="mail-subscriptions">` 박스다. 누르면 펼쳐진다.
  - 품목 13개와 지역(전국, 38개 주) ☆는 로그인 없이 보인다.
  - 로그아웃 상태에서 ☆를 누르면 `#login-dialog`가 뜬다. 로그인하면 누른 별을 적용한다.
  - 알림 조합 = 별표한 품목 × 별표한 지역. 기존 RPC `idn_set_my_mail_subscriptions` / `idn_set_my_mail_subscription` / `idn_my_mail_subscriptions`를 쓴다. **DB·RPC 변경은 없다.**
  - 지역을 하나도 고르지 않았으면 전국(`__all__`)으로 저장한다.
  - 전국과 개별 지역은 따로 호출한다. 클라이언트가 섞인 목록을 전국 하나로 합치기 때문이다.
  - 로그인은 메인 사이트와 같은 Supabase 세션(localStorage)을 쓴다.
- **지역 목록:** 로그아웃 상태에서는 `New for anti/indonesia-policy/mail-regions.json`(페이지용 복사본)을 쓴다.
  - 원본은 `scripts/indonesia_policy/mail-regions.json`이다. 두 파일이 같은지 `test_subscription_client.mjs`가 확인한다.
  - 원본을 고치면 복사본도 같이 고친다.

## Codex가 할 일

1. **실계정 확인.** 운영 `/policy/indonesia`에서 다음을 확인한다.
   - 로그인
   - 별표 저장·해제
   - `idn_mail_subscriptions` 행이 의도대로 생기는지(품목 × 지역, 전국은 `__all__`)
   - 결과를 내 인수인계 파일에 적는다.
2. **브라우저 테스트 실행.** `scripts/indonesia_policy/test_browser.cjs`를 로컬 DB와 4317 서버에서 돌린다.
   - 메일 테스트를 별표 구조로 바꿨는데, Claude 환경에서는 DB가 없어 실행하지 못했다.
   - 이 테스트는 서버 경로 `/indonesia-policy/`를 그대로 쓴다. 정적 서버라서 문제없다.
3. **IDN 메일 발송은 계속 꺼 둔다.** `policy_idn.mail_config.delivery_enabled=false`를 유지한다.
   - 켤 때는 #668 문서 절차를 따른다.
   - `deploy-mailing.yml`의 `send_enabled` 기본값이 false라서, 수동 배포 시 전체 메일이 꺼지는 함정이 있다.

## 하지 말 것

- 구형 commodity-digest 발송기 재가동, 과거 누락분 일괄 재발송
- 인도네시아 자산 경로를 상대경로로 되돌리기
- `run_worker_first`에서 인도네시아 경로 제거
- 상단 메뉴를 인도네시아 페이지에 하드코딩하기(`site-nav.js`가 메인에서 읽는다)
