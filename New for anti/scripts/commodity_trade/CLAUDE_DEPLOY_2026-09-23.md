# Claude 배포 인수인계 — 사우디 검토 및 월별 데이터 안전화

이 문서가 9월 19일 문서와 `HANDOFF_CLAUDE_DEPLOY_SAUDI_MONTHLY.md`의 배포 판단보다 우선한다.
**데이터·코드 로컬 검증 완료 / UI 연결·원격 push·PR·운영 배포는 미실행.**

> 위 상태는 9월 23일 검증 시점 기록이다. 후속 PR에서는 원자재 코드·선별 데이터·이 문서를 함께 제공한다.
> PR checkout에서는 이 파일의 상대 경로를 사용하면 되며, 아래 로컬 `untracked` 안내는 원본 작업 공간에 관한 설명이다.
> 최신 main에는 `.github/workflows/deploy.yml`의 main push 배포가 존재한다. **PR 생성은 배포가 아니지만 merge는 운영 배포를 유발할 수 있다.** 검토 전 자동 머지하지 않는다.

## 1. 작업 위치와 경계

루트: `/Users/yeoninair/Documents/New for anti-dart`
자산 루트: `New for anti/`, 데이터: `New for anti/public/data/`.
이 경로는 `해운 데이터`와 다른 checkout이다. 작업 시작 시 아래 두 결과를 확인한다.

```bash
cd '/Users/yeoninair/Documents/New for anti-dart'
pwd
git rev-parse --show-toplevel
git -c core.fsmonitor=false status --short
```

현재 브랜치는 `cursor/macro-monitor-fix`이며 다른 업무 변경과 미추적 파일이 섞여 있다.
`git add .`, 현재 전체 폴더 그대로의 무검토 배포, 강제 reset 금지.
원자재 코드·데이터 대부분은 **untracked**다. 다른 worktree/원격 main에는 자동으로 들어가지 않는다.
`AGENTS.md`, `docs/ops/OWNERS.md`를 읽고 선별 이관한다.
사용자의 UI 수정 금지는 계속 유효하다. 이번 배포 대상은 데이터/수집기/검증뿐이다.
Worker·실제 Actions 설치·배포는 Claude 소유 경로이며 Codex는 변경하지 않았다.

## 2. 사우디 팩트 — 반드시 구분

| 데이터 | 직접 검증 결과 | 화면/데이터 의미 |
|---|---|---|
| GASTAT 월간 무역 엑셀 | 2026-06, 잠정치, 공식 XLSX 원본 확인 | 아래 석유류 수출 **금액** 제공 |
| 석유류 전체 수출액 | 2026-06: 63,176.984784 million SAR | 원유 HS2709 단독 아님; 배럴/톤 아님 |
| 전체 상품 수출액 | 같은 달 87,762.015822 million SAR | 석유류 금액 비중 71.9867%; 목적국별 비중 아님 |
| GASTAT 상세 Tableau HS2709 | 새 네트워크 조회도 2025-09까지 | 원유 대세계 총량, stale 표시 유지 |
| 사우디 원유 목적국별 수출 | **미확보** | 중국/미국/한국 값을 만들거나 0으로 채우지 말 것 |
| 기존 사우디 bilateral | 2025-09 HS2601 철광석 | 원유 데이터가 아님 |

공식 6월 엑셀의 `1.2!H166`은 석유류 금액, `1.2!P166`은 전체 상품 수출액이다.
`1.2!H5`, `1.2!A3`의 표제/단위를 확인했다.
`4`번 표는 전체 상품의 국가별 금액이다. `6.1`은 비석유 국가×섹션,
`11`은 비석유 수출/재수출/수입의 장별 주요 HS6이며 원유 목적국별 표가 아니다.
이 표들끼리 조인해 HS2709 목적국별 물량을 추정하지 않는다.

공식 원문:

- [6월 발표](https://www.stats.gov.sa/en/w/international-trade-in-goods-june-2026)
- [직접 확인한 XLSX](https://stats.gov.sa/documents/20117/2435267/ITR+Jun+2026+%282%29.xlsx/b5c7a705-8dd8-cf93-ab22-05cb371cfcb4?version=1.0&download=true)
- [공식 목록](https://stats.gov.sa/ar/search?category=all&delta=60&sort=createDate-&start=1)
- [공식 일정](https://www.stats.gov.sa/en/search-methodology?delta=40&start=2): 7월 무역은 2026-09-24 예정. 예정일을 실제 공개/수록 월로 취급하지 않는다.

XLSX SHA256: `afd4c7c08b22998c9e1a1005c6c1715de9bf54cffeea10152e9b3110be504907`.
자동 탐색으로 얻은 아랍어 페이지 XLSX와 수동 확인한 영어 페이지 XLSX의 해시와 추출값이 동일했다.

## 3. 이번에 구현·교정한 것

- `sources/saudi_gastat_bulletin.py`: 공식 목록 → 최신 무역 발표 → XLSX 자동 탐색. API 키 불필요.
  표제/단위/월/중복/비정상 수치 검증. 분기·연간 행 제외. 표 구조 변경 시 중단.
- `build_saudi_bulletin.py`: 아래 별도 JSON에 최근 24개월 석유류 수출액 발행.
  다운로드 실패·자료 월 역행 시 기존 파일 보존. 원본 해시와 셀 출처 보존.
  원본/값 불변이면 파일을 다시 쓰지 않아 불필요한 PR을 억제한다.
- `sources/saudi_gastat_tableau.py`: 24시간 캐시 만료, 실패 요청도 예산에 계산,
  두 지표를 파싱한 뒤 캐시 교체. 중복 월·NaN·음수 차단. 상대국별 계약을 임의 추가하지 않음.
- `sources/jodi_oil.py`: `CONVBBL`을 거래량 후보에서 제외.
- `series_quality.py`: `CONVBBL`을 부피가 아닌 환산계수로 분리.
- `repair_monthly_units.py`: 기본 dry-run, 쓰기 시 별도 백업 필수, 반복 실행 시 불변.
  기존 월별 파일의 **429개 KTONS→kg**를 ×1,000,000으로 교정하고
  **580개 환산계수**를 `points`에서 제외하여 metadata에 보존했다.
  환산계수만 존재했던 국가는 `unavailable_countries`로 옮겨 실제 관측과 구분했다.
  원유 관측 국가 109→67, 석유제품 25→19. 기존의 109/25를 실제 물량 커버리지로 소개하지 않는다.
  유효 원본 관측 **1,872개**의 국가/월/value/unit은 전부 동일하고 기존 world-link도 동일하다.
  이것은 **과거 생성물의 오프라인 교정**이지 JODI 최신 수집/full rebuild가 아니다.
- `build_monthly.py`: 실제 생성물에 환산계수 또는 잘못된 KTONS 정규화가 있으면 배포 전 검증 실패.
- `validate_release.py`: 월별 단위, 사우디 의미/비중, 기존 bilateral 해시·순위·비중, coverage 일치 검사.
- `deployment/monthly.yml.example`: 비활성 템플릿에 사우디 bulletin 갱신·release gate·JSON PR 포함 추가.
  실제 `.github/workflows/**`는 변경하지 않았다.

## 4. 새 데이터 계약

파일: `New for anti/public/data/commodity_trade_saudi_bulletin_v1.json`

```text
schema_version = commodity-trade-saudi-bulletin-v1
series_id = oil_exports_aggregate_value
reporter_iso3 = SAU
flow = X, partner = WORLD
hs = null
quantity_available = false
bilateral_available = false
points[].value / unit = 석유류 전체 수출액 / SAR_million
points[].share_of_total_goods_export_value = 전체 상품 수출금액 중 석유류 비중 (0~1)
points[].preliminary = 잠정치 여부
points[].source_cells = 원본 셀 주소
```

`crude_oil` / `HS2709` / bilateral 파티션에 넣지 않는다. 서로 대체하지 않는다.
기존 UI는 이 파일을 자동으로 읽지 않는다. **정적 파일 배포와 화면 기능 완료는 별개**다.
UI 연결은 별도 사용자 승인 후 기존 디자인 안에서 “석유류 전체 수출액” 참고 패널로 한다.

## 5. 검증 명령과 현재 기대 결과

2026-09-24 리뷰 반영: 의존성 명시·템플릿 설치 단계·README 배포 경로를 수정했다.
Preview `points[].publication.eligible_for_display=false`는 대표값·차트·비율·순위에서 보류하고,
`publication_summary.latest_eligible_month`를 사용한다. 이전 `latest_available_month`는 원본 최신 월이다.
서로 다른 단위를 한 차트 계열로 합치지 않는다. 상세 규격은 README의 Preview 게시 품질 계약을 따른다.
UI 변경은 이 PR에 없으므로 #351 담당자가 새 필드 연결 후 임시 휴리스틱을 제거해야 한다.
기존 Preview JSON은 오프라인으로 메타데이터만 갱신했으며 새로운 무역자료 수집은 하지 않았다.
24시간 캐시 TTL은 수집기가 해당 월을 다시 요청할 때만 작동하며, 스케줄 전체를 활성화하지 않는다.

리뷰 수정 검증: 별도 가상환경에 requirements만 설치 후 Python 110개 통과,
JavaScript 10개 통과, `build_monthly.py --no-fetch` 및 release gate 통과.
Preview 원본 관측 489개·기존 수집 시각·실행 이력은 변경 전과 동일하다.
보류 11개 계열-월: 브라질 2026-06 10건, 아르헨티나 밀 수입 2026-03 1건.
보류는 휴리스틱 경고이며 원천의 부분 집계가 확정되었다는 뜻이 아니다.

모든 명령은 위 레포 루트에서 실행한다. Python 3.12 가상환경을 권장한다.
ABS·USDA ERS 어댑터는 `openpyxl`이 필요하다. 사우디 bulletin 파서만 표준 라이브러리로 동작한다.

```bash
python3 -m pip install -r 'New for anti/scripts/commodity_trade/requirements.txt'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s 'New for anti/scripts/commodity_trade/tests' -q
node --test 'New for anti/scripts/commodity_trade/gateway/handler.test.mjs' 'New for anti/scripts/commodity_trade/client/bilateral-loader.test.mjs'
PYTHONDONTWRITEBYTECODE=1 python3 'New for anti/scripts/commodity_trade/build_monthly.py' --no-fetch --print-stats
PYTHONDONTWRITEBYTECODE=1 python3 'New for anti/scripts/commodity_trade/validate_release.py'
```

기대: release `status=pass`, 잘못된 환산계수/질량 정규화=0.
2026-09-23 실검증: Python 101개 / JavaScript 10개 통과, 생성물 검증 pass.
자동 공식 목록→발표→엑셀 실조회 결과가 공개 JSON의 24개 관측 및 원본 해시와 일치했다.
전체 `git diff --check`에는 기존 선거 README의 trailing whitespace가 있으나 별도 업무이므로 수정하지 않았다.
우선순위 패널: 총량 14개국 / 상대국별 12개국 / 합집합 15개국.
기존 bilateral 41묶음·329행. 국가별 모든 품목/월/방향 완전 커버라는 뜻이 아니다.
사우디: bulletin 2026-06 / HS2709 총량 2025-09 / HS2709 bilateral false.

새 사우디 수집기 라이브 실행(키 없이 공식 공개자료 GET 3회):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'New for anti/scripts/commodity_trade/build_saudi_bulletin.py'
```

목록에 인식 가능한 월별 발표가 없거나 표제가 바뀌면 종료 2, 기존 산출물 유지.
공식 목록 첫 페이지 60개 내에서만 탐색하므로 링크가 밀려나면 운영자가 목록 계약을 재확인해야 한다.
무한 재시도/추정 URL/누락값 0 대입 금지.

## 6. Claude 배포 순서

1. 현재 변경물을 분리해 깨끗한 배포 브랜치/체크아웃에 선별 이관한다.
   대상: `New for anti/scripts/commodity_trade/**`의 코드·tests·config·문서·client·gateway·deployment,
   `public/data/commodity_trade_*.json`, bilateral `index.json` 및 참조 `parts`, `comtrade_public_seed_v1.json`.
   `export_controls_v1.json`은 사용자의 기존 수정이 있으므로 검토 후 그대로 보존; 덮어쓰기 금지.
   `__pycache__`, raw CSV/XLSX, `/tmp` 캐시, .env, 키, 다른 업무 파일은 제외.
2. 위 검증 4개 통과. 이관 후 다시 실행한다.
3. 사우디 새 데이터 정적 배포는 새 Secret 불필요.
   Comtrade/한국 인증·gateway 운영 연결은 9월 19일 문서 P1을 별도 수행한다.
   원천 키를 공개 자산/브라우저로 보내지 않는다. 누락된 Secret은 사용자에게 설정 요청 후 해당 단계 중단.
4. 실제 자동화는 Claude가 `deployment/monthly.yml.example`을 검토·설치한다.
   기존 월별 workflow의 직접 push/deploy와 중복 writer를 없앤다.
   스케줄 수집 → 검증 → 데이터 PR → 승인 merge → 기존 운영 배포를 연결한다.
   템플릿의 16~28일 일일 확인은 늦은 발표/정정을 수용하기 위한 것이며, 각 관측은 월 단위다.
   GITHUB_TOKEN PR의 후속 워크플로 실행 제한, 체크포인트 복원, Secrets, 중단/재개는 운영에서 별도 검증한다.
5. 사용자 승인된 배포 범위를 확인 후 PR/merge/기존 Cloudflare 배포 절차를 진행한다.
   Wrangler는 `New for anti`의 모든 정적 자산을 업로드하므로 dirty checkout 전체 배포 금지.
6. 운영 도메인의 `/public/data/commodity_trade_saudi_bulletin_v1.json`과 수정 월별 JSON을 내려받아
   로컬 승인본과 해시를 비교한다. bilateral index/part 해시와 404 여부도 확인한다.
   코드 push, PR merge, 배포 성공, 운영 자산 일치, UI 노출을 각기 별도 완료로 보고한다.

## 7. 아직 완료가 아닌 것

- 사우디 원유 목적국별 물량/순위/비중. 총량으로 쪼개지 않는다.
- JODI 최신 원천 재수집. 이번 교정은 원본 수록 월을 바꾸지 않았다.
- 다른 국가 신규 수집 및 국가/상품 확대.
- 인증 Secret 실연결, 실제 Actions 활성화, PR, push, 운영 배포, UI 연동.
- 수출통제 법률 판정: 기존 candidate/`legal_clearance=null` 유지. 데이터로 법적 허용을 단정하지 않는다.

복구용 교정 전 파일은 이 작업 당시 `/private/tmp/saudi-review.1UA108/monthly-before-repair.json`에 저장했다.
임시 파일은 장기 보관 보장이 없으므로 운영 전 승인본을 Git에 선별 커밋한다.

## Claude 시작 문장

“`/Users/yeoninair/Documents/New for anti-dart`에서 이 문서를 먼저 읽고,
수정된 월별 데이터와 사우디 bulletin 데이터만 선별 검증·PR·배포 준비해줘.
UI는 수정하지 말고, 사우디 석유류 수출액을 원유 목적국별 물량으로 표시하지 마.
실제 배포 및 자동화 연결은 권한과 전체 자산 변경 범위를 확인하고 진행해줘.”
