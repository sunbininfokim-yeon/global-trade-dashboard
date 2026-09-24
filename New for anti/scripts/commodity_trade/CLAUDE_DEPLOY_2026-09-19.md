# Claude 배포 인수인계 — 월별 원자재 무역

> 2026-09-23 후속: `CLAUDE_DEPLOY_2026-09-23.md` 우선. 아래 P0 단위 오류는 로컬 교정·검증 완료했으나 원천 최신 재수집/full rebuild는 아님. 본 문서의 인증 경로와 배포 경계는 계속 참고한다.

## 반드시 같은 로컬 작업물을 사용

작업 루트는 `/Users/yeoninair/Documents/New for anti-dart`.
`pwd`와 `git rev-parse --show-toplevel`이 이 경로인지 먼저 확인한다.
해운 데이터 레포나 원격 main만 보고 구현 완료 파일이 없다고 판단하지 않는다.
현재 원자재 스크립트·공개 데이터·일부 workflow는 **untracked** 상태다.
별도 worktree에는 저절로 전달되지 않으므로 변경 파일을 먼저 확인하고 선별 이관한다.
기존 다른 업무의 수정, `.DS_Store`, Obsidian 파일 등을 포함하는 `git add .`는 금지한다.

먼저 읽을 파일(레포 루트 기준):

1. `AGENTS.md`, `docs/ops/OWNERS.md`
2. `New for anti/scripts/commodity_trade/CLAUDE_MONTHLY_BILATERAL_HANDOFF_2026-09-09.md`
3. `New for anti/scripts/commodity_trade/BILATERAL_PROGRESS_2026-09-10.md`
4. 이 문서 — 아래 배포 전 결함이 앞 문서의 준비 완료 표현보다 우선한다.

## 상태를 혼동하지 말 것

- 9월 19일 재개: 인도·노르웨이·태국의 관측 월/품목을 무료 Preview로 24회 조회, 모두 빈 응답.
- 추가로 사우디 원유 HS2709의 2026-07·08 수출입을 4회 조회했으며 모두 빈 응답이었다.
- 총 28회에는 새 HTTP 429/인증 중단이 없었다. 과거 `rate_limited` 항목은 이력으로 남아 있다.
- 재개용 seed는 보존·갱신했다. 총량 우선 패널 14개국, 상대국별 12개국, 합집합 15개국.
- 41개 상대국별 묶음 / 329개 상대국 행. 전체 상품·월·방향 완성을 뜻하지 않는다.
- 사우디의 기존 상세 확보 상품은 2025-09 철광석 HS2601. 사우디 원유 목적국별 확보로 소개하지 말 것.
- 로컬에 원천 API 키/게이트웨이 env가 없어서 무료 Preview를 사용했다. Cloudflare에 저장된 키의 존재/권한은 아직 검증하지 않았다.
- UI, 실제 Worker route, 실제 bilateral Actions 설치, 운영 배포는 Codex가 하지 않았다.
- 이번 재수집 후 기존 41묶음의 상대국·수치·비중·순위가 그대로 보존됐음을 대조했다.
- 사우디 원유 총량: 확인 당시 JODI 홈페이지는 2026-06 하이라이트를 제시한다.
  이는 목적국별 자료도, 원본 DB 전체의 최신 월 검증도 아니다. 로컬 JODI 파일은 2026-05까지다.
  JODI 공식 달력의 다음 정기 업데이트는 2026-09-22다.
  참고: https://www.jodidata.org/ 및 https://www.jodidata.org/oil/support/update-calendar.aspx

## P0 — 기존 JODI 파일은 수정 전 새로 배포하지 말 것

대상: `New for anti/public/data/commodity_trade_monthly_v1.json`.

1. `KTONS`의 기존 `normalized.value`가 원값 × 1,000인 불일치가 **429개**다.
   공식 정의는 천 metric tons이므로 kg는 원값 × 1,000,000이다.
   현재 `world_link.py`의 계수는 이미 맞지만, 생성 파일은 과거 잘못된 환산이 남아 있다.
   원본 `value`/`unit`을 보존하고 정규화와 파생 합계·비중을 재생성한다.
2. `CONVBBL`을 관측 포인트로 담은 경우가 **580개**다.
   이것은 부피 실측값이 아니라 barrels/ktons **환산계수**다.
   `sources/jodi_oil.py`의 `PREFERRED_UNITS`에 포함돼 있다.
   거래량 후보에서 제외하고, 필요하면 별도 metadata로 보존한다.
   대체 실측값이 없으면 미확보/null로 표시하고 국가 커버리지를 다시 계산한다.
3. 단위 변환과 환산계수 배제에 대해 실제 생성 JSON을 검사하는 회귀 검증을 추가한다.
   단위 테스트 89개와 Node 테스트 10개가 통과해도 이 레거시 파일 품질을 보증하지 않는다.

공식 정의: https://www.jodidata.org/_resources/files/downloads/oil-data/jodi-wdb-short-long-names.pdf
새 `commodity_trade_bilateral_v1`은 이 JODI 파일과 별도다. 해당 레거시 파일을 교정/제외할 때까지 전체 월별 완성 배포로 선언하지 않는다.

## P1 — Cloudflare의 기존 키를 사용하는 인증 경로

기존 원천 키를 브라우저나 공개 JSON으로 꺼내지 않는다.
`gateway/handler.mjs`를 `_worker.js`의 정확한 `/api/trade-pipeline/query` POST 경로에 연결한다.
구체 import/route 코드는 9월 9일 인수인계서에 있다. 기존 공개 `/api/comtrade`의 축약 응답을 새 파이프라인에 재사용하지 않는다.

| 위치 | 이름 | 용도 |
|---|---|---|
| Cloudflare Worker Secret | `COMTRADE_API_KEY` | 기존 Comtrade 키. 저장/권한만 확인하고 값 출력 금지 |
| Cloudflare Worker Secret | `KOREA_CUSTOMS_SERVICE_KEY` | 기존 관세청 키 |
| Cloudflare Worker Secret | `TRADE_PIPELINE_TOKEN` | 수집기 전용 신규 인증 토큰 |
| GitHub Actions Secret | `TRADE_PIPELINE_TOKEN` | Worker와 같은 토큰 |
| GitHub Actions Variable | `TRADE_GATEWAY_URL` | 실제 배포 도메인 + `/api/trade-pipeline/query` |
| GitHub Actions Variable | `TRADE_ACQUISITION_MODE` | `gateway` |

원천 키는 Cloudflare에 두어도 된다. GitHub 수집기는 전용 gateway 토큰으로 원천을 조회한다.
이 토큰은 Cloudflare 계정 관리 API 토큰과 다르다. 실제 배포 권한에는 별도 Cloudflare/GitHub 인증이 필요하다.
과거 채팅에 노출된 원천 키는 운영 전 재발급/교체를 사용자에게 안내하고, 값은 다시 채팅으로 받지 않는다.
없는 인증/Secret은 사용자에게 설정을 요청하고 해당 단계에서 중단한다.

## P2 — 자동수집 및 안전한 배포

`New for anti/scripts/commodity_trade/deployment/monthly.yml.example`은 비활성 템플릿이다.
실제 `.github/workflows/commodity_trade_bilateral.yml`로 검토 후 설치한다.
관측 월 백필 + 최근 월 탐색, request budget, 단일 writer, checkpoint artifact 복원/항상 저장을 유지한다.
월별 기존 workflow와 새 workflow가 같은 산출물을 동시에 쓰지 않게 역할/동시성을 정리한다.
기존 `commodity_trade_monthly.yml`에는 직접 `git push`와 배포 명령이 있으므로 PR 기반 경로와 충돌하지 않게 정리한다.

스케줄 자동수집 → 검증 → 데이터 PR → 승인된 merge → Cloudflare 배포로 연결한다.
현재 템플릿은 PR 생성까지만 준비돼 있으며, 승인/auto-merge/후속 배포는 아직 연결 검증 전이다.
GITHUB_TOKEN으로 발생한 이벤트의 후속 workflow 제한을 확인하고 필요한 검증/배포 트리거를 명시적으로 구성한다.
모든 scope를 매달 완료할 만큼 예산이 충분하다고 가정하지 말고 핵심 상품/국가 우선순위를 설정한다.
요청 제한 exit 3, 인증/네트워크 exit 2 이후 억지로 반복하거나 빈 값으로 기존 자료를 덮지 않는다.

## P3 — 데이터 파일과 화면 연결

정적 데이터와 핵심 코드(레포 루트 기준):

- `New for anti/public/data/commodity_trade_bilateral_v1/index.json` 및 참조 `parts/*.json`
- `New for anti/public/data/commodity_trade_coverage_v1.json`
- `New for anti/public/data/commodity_trade_comtrade_priority_v1.json`
- `New for anti/public/data/commodity_trade_national_priority_v1.json`
- 필요한 board/통제 catalogue 등은 import 및 빌드 의존성을 확인해 선별 포함한다. 기존 통제 파일은 사용자 수정 상태이므로 덮어쓰지 않는다.
- `New for anti/scripts/commodity_trade/**` 중 코드·config·tests·문서·배포 seed/template
- 캐시, 임시 상태, `__pycache__`, `.env`, 키는 제외한다.

DOM-free `client/bilateral-loader.mjs`가 준비돼 있다. 코드 업로드만으로 기존 UI가 자동 연결되는 것은 아니다.
국가→상품→연/월→상대국·방향·수량·금액·비중·순위에 연결한다.
UI는 기존 디자인과 연간 기능을 유지하며 필요한 변경 범위는 사용자에게 확인한다.
확보된 달만 선택 가능하게 하고, 빈 월에 연간/과거 값을 대입하지 않는다.
직접 신고와 상대국 신고는 별도 관측이며 합산 금지. 배럴·kg·금액을 혼합하지 않는다.
수출통제는 후보/검토 대기로 표시하며 `legal_clearance=null`을 법적 허용으로 바꾸지 않는다.

## 배포 완료 판정

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s 'New for anti/scripts/commodity_trade/tests' -q
node --test 'New for anti/scripts/commodity_trade/gateway/handler.test.mjs' 'New for anti/scripts/commodity_trade/client/bilateral-loader.test.mjs'
PYTHONDONTWRITEBYTECODE=1 python3 'New for anti/scripts/commodity_trade/validate_bilateral_public.py' 'New for anti/public/data/commodity_trade_bilateral_v1'
```

추가 필수: P0 JODI 생성물 검증, 실제 Worker 런타임 테스트, 무인증 접근 거부,
소량 한국/Comtrade 인증 실조회, Actions 중단/재개 실증, 운영 URL에서 index와 참조 part 일치,
화면에서 확보 월·방향·단위·부분 커버리지·통제 불확실성 확인.
키/원문 인증 URL/헤더가 로그와 정적 파일에 없는지도 확인한다.
코드 push, PR, merge, 실제 배포 URL 검증을 각각 별도 완료 항목으로 보고한다.

참고 공식 문서:
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
