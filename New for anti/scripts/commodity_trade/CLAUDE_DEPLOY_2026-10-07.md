# 월별 원자재 수집·배포 인수인계 — 2026-10-07

## 현재 경계

총괄 프로젝트는 `/Users/yeoninair/Documents/New for anti-dart`다. 작업 격리본은
`/private/tmp/commodity-monthly-refresh.TCvTGA/checkout`, 브랜치는
`codex/commodity-monthly-automation`이다. UI·wrangler·공용 deploy workflow·학습 모델은
미수정이다. 이번 PR은 구현/실자료 교정이며 병합·배포·운영 한국 인증 성공을 뜻하지 않는다.

## 운영 점검에서 확인한 것

- #351/#352는 병합됐고 운영 정적 월별 파일 6종은 점검 당시 main과 일치했다.
- 운영 Comtrade 키로 캐시 MISS 조회가 성공했다. 정적 파일 갱신과 실시간 조회는 별개다.
- 종전 main에는 전체 월별 갱신 workflow가 없었다. Worker의 시간별 cron은 연도 캐시용이다.
- 관세청 키는 Cloudflare에 있고 GitHub에는 없다. `TRADE_PIPELINE_TOKEN` 및 gateway URL 연결은 미설정이다.
- KOSIS 키는 관세청 Itemtrade의 `serviceKey`를 대신하지 못한다. KOSIS 별도 통계표 접근은
  기관/표/분류/단위/월/상대국 계약을 검증한 별도 어댑터 업무다.

공식 근거: [KOSIS 통계자료 API](https://kosis.kr/openapi/devGuide/devGuide_0201List.do),
[관세청 품목별 실적](https://www.data.go.kr/data/15101609/openapi.do).

## 이번 변경

| 구성 | 변경 | 확인/남은 한계 |
|---|---|---|
| Comtrade 총계 | partner2=0, customs=C00, mot=0를 명시; 상세 행 제외·상충 중복 거부 | 금액 최대값/마지막 행 선택 금지. 기존 유일한 legacy 행은 유지 |
| 무료 Preview | 캐시 버전 분리, 원천 오류/잘림 캐시 교체 금지, 동일 월 중복 교체 금지 | Preview 완전 통계 보증 아님; 기존 게시 보류 정책 유지 |
| 운영 월별 조회 | 총계 선택, 월별 캐시24시간·빈 결과1시간, partial 표시, 응답4MiB 제한 | 연도 캐시 키는 보존. UI의 live zero/partial 소비 개선은 별도 |
| 한국 | 보호 중계로 Cloudflare 기존 Customs 키 사용, 공통 XML 파서·24시간 캐시 | 실제 한국 응답은 배포/토큰 설정 후 확인 필요 |
| 전체 월별 갱신 | 수집 실패/누락 시 기존 나라·월 보존, 최근12개월 유지 | 보존은 새 원천 검증 성공이 아님; 상태에 명시 |
| 자동 수집 | 실제 refresh workflow, 27개국을 9개씩 3개 배치로 분할 | 국가·품목·방향 전체를 확보했다는 뜻 아님; 요청 예산/원천 공백 존재 |
| 감시 | 실행 시각과 국가별 관측 월 분리, 오래된/없는 자료 경고 | 정상 실행이 최신 자료를 보장하지 않음. 우선 패널 집계는 JODI 제외 |
| 배포 | 검증한 데이터만 별도 PR, 검토·병합 후 기존 production deploy | main 직접 push/무인 auto-merge 없음 |

소유권 예외는 이 브랜치의 `_worker.js` 및 전용 workflow 2개만 허용한다.
다른 UI/배포 파일에는 예외가 없다.

## 실제 제한 수집 결과

2026-10-07 공개 Preview 16회, USA/BRA × 수출/수입 × 2026-06~09를 요청했다.
10개 응답에서 수치를 얻었고 6개는 미공개/빈 결과였다. 쿼터 중단은 없었다.

- USA: 이번 범위에서 2026-07까지. 08/09는 0으로 채우지 않았다.
- BRA: 2026-08까지. 09는 0으로 채우지 않았다.
- BRA 대두 2026-06 수출: 잘못 선택된 상세행 245kg/$2,312 대신 공식 총계
  **14,505,018,184.774kg / $6,266,777,036**로 교정했다. 원천의 중량 추정 표시도 보존했다.
- Preview 게시 보류 월은 11→7개로 줄었지만 남은 7개를 임의 해제하지 않았다.
- 일부 월의 중량이 없으면 USD 관측으로 보존하며 kg와 합산하지 않는다.
- 현재 우선 범위 국가 수는 총량14/상대국별12/합집합15, 대상27이다.
- Saudi bulletin은 석유류 전체 수출액 2026-06, HS2709 총량은 2025-09다.
  Saudi HS2709 상대국별 확보 없음. 석유류 수출액을 원유 배럴/목적국별 수출로 표시하면 안 된다.

## 설치 순서 (Claude)

1. 이 PR을 검토·병합하고 기존 main production 배포 성공을 확인한다.
2. 안전한 비밀관리 환경에서 **새로운 중계 접근 토큰**을 생성한다.
   - Cloudflare secret: `TRADE_PIPELINE_TOKEN`
   - GitHub Actions secret: 같은 `TRADE_PIPELINE_TOKEN`
   - GitHub Actions variable `TRADE_GATEWAY_URL`:
     `https://global-trade-dashboard.sunbin-info-kim.workers.dev/api/trade-pipeline/query`
   - Cloudflare의 `KOREA_CUSTOMS_SERVICE_KEY`, `COMTRADE_API_KEY`는 기존 것을 사용한다.
     관세청 키를 GitHub에 복제할 필요 없다. 별도로 저장했다면 direct 경로도 가능하다.
   - 토큰 값을 문서·PR·채팅·명령 인자·로그·공개 JSON에 넣지 않는다.
3. 무인증 POST가401, 정당한 인증 + 관세청 HS2709 한 월 요청이 status=ok인지 확인한다.
   오류 응답을 0kg/0USD 성공으로 취급하지 않는다. 키 권한/만료는 실제 응답으로 확인한다.
4. `Monthly commodity trade refresh`를 batch0으로 수동 실행한다. 실행 출력을 보고
   source 실패, auth_required, rate_limited, unfinished_jobs를 확인한다.
5. 생성된 데이터 PR의 `commodity_trade_refresh_status_v1.json`과 release gate 결과를 검토한다.
   GITHUB_TOKEN 생성 PR은 후속 PR CI가 자동 실행되지 않을 수 있으므로 생산 workflow의
   테스트/검증 결과를 확인한다. CI 미실행을 통과로 표기하지 않는다.
6. 데이터 PR을 병합한 후 실제 배포 run과 공개 JSON의 값/생성 시각을 확인한다.
   Python 테스트·dry-run 성공은 운영 배포 증거가 아니다.
7. 이후 weekly freshness 검사에서 공개 상태를 확인한다. 첫 full run의 데이터 PR이
   배포되기 전에는 status 파일 부재로 실패할 수 있다.

## 일정과 요청 예산

- 매월16/24/28일12:37 KST에 batch0/1/2. USA~SAU / ARE~NOR / KAZ~VNM 순서.
- 매번 전체 무료 월별/JODI/브라질·공개 국가 어댑터·Saudi bulletin을 갱신한다.
- Preview: 배치 내 국가별 최근6개월, 국가당 최대12요청, 최소3초 간격.
- 국가 어댑터: 최근3개월, 국가당 최대72요청. 미공개 월·원천 실패는 기록한다.
- Bilateral: 관측된 월을 기준으로 batch당 최대60요청, 한국 추가 최대60요청.
  요청 예산으로 전체 계획을 처리하지 못하면 `unfinished_jobs` 및 partial을 남긴다.
  같은 월·배치를 수동 재실행하면 checkpoint로 이어간다. 새 월로 넘어가면 새 cycle이므로
  이 예산만으로 모든 상품의 매월 완전 확보/과거 백필을 보장하지 않는다.
- 동일 월 진행 상황은 private Actions artifact90일 보존. 공개에는 정규화된 관측·상태만 넣는다.
- 429/키 오류/빈 응답/누락은 별개. 실제 빈 공개 응답은 `empty_responses`, 원천 오류는
  `source_failures`. 보존된 데이터는 현재 관측으로 날짜를 바꾸지 않는다.
- weekly watchdog: 월요일14:19 KST. 마지막 수집35일 초과·partial/failed·smoke-only는 실패,
  국가별6개월 초과 관측/미확보는 별도 coverage warnings. 경고는 자료의 공개 시차를 나타내며
  자동으로 국가를 삭제하거나 가짜 수치를 만들지 않는다.

## 인수 시 검증

작업본에서 Python121개, Node36개, 소유권5개 검사가 통과했다.
전체 release gate·기존 월별 읽기 전용 검증·38개 기존 수집기의 deploy 연결 검사·
전용 workflow YAML 파싱·Wrangler4.141.0 dry-run 번들 검증도 통과했다.

레포 루트에서 아래를 실행한다. 원본 API 캐시/pycache/키는 커밋하지 않는다.

```bash
python3 -B -m unittest discover -s 'New for anti/scripts/commodity_trade/tests' -q
node --test 'New for anti/scripts/commodity_trade/gateway/'*.test.mjs
node --test tests/comtrade/period.test.mjs tests/comtrade/monthly-view.test.mjs
python3 -B -m unittest discover -s tools/ops/tests -p test_ownership_rules.py -q
python3 -B tools/ops/check_deploy_chain.py
python3 -B 'New for anti/scripts/commodity_trade/build_monthly.py' --no-fetch --print-stats
python3 -B 'New for anti/scripts/commodity_trade/validate_release.py'
npx wrangler deploy --dry-run
```

실행 성공 후에도 아직 필요한 확인: 운영 중계 토큰 설정, 한국 실제 인증·자료 응답,
main 정기수집→데이터 PR→병합→배포→공개값의 첫 전체 순환.
