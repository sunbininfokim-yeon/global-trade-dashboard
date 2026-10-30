# Claude 인수인계 — 월별 양국 간 무역 + 수출통제 후보

> 2026-09-10 업데이트: 상대국별 데이터 **12개국·41묶음·329행**, 월별 총량과 합집합 **15개국**.
> 아래 6개국·30묶음 표는 9월 9일 기록이다. 최신 확보 범위·재개 조건은
> [BILATERAL_PROGRESS_2026-09-10.md](BILATERAL_PROGRESS_2026-09-10.md)와 공개 `commodity_trade_coverage_v1.json`을 우선한다.

작업 루트: `/Users/yeoninair/Documents/New for anti-dart`.
UI·`_worker.js`·`wrangler.jsonc`·실제 `.github/workflows/`는 수정하지 않았다.
기존 `commodity_trade_*_v1.json`, 수정 중인 `export_controls_v1.json`도 덮어쓰지 않았다.
**코드·초기 공개 스냅샷은 준비했지만 운영 배포·인증 통합 검증은 아직 아니다.**

### 이번 실행의 실측 결과

무료 Preview 48회 수집: 30개 정상 source/reporter/HS/period/flow 묶음, 빈 응답 18건. 별도의 최초 스키마 확인 1회가 있었다.
공개 인덱스가 참조하는 상대국 행은 291개다. 연속 기간 전체나 전세계 완전 커버리지가 아니다.

| 신고국 | 실제 확보 기간 | HS | 묶음 수 |
|---|---|---|---:|
| 칠레 | 2026-06, 2026-07 | 2603·7403 | 8 |
| 브라질 | 2026-06, 2026-07 | 2603·7403 | 8 |
| 호주 | 2026-07 | 2603·7403 | 4 |
| 캐나다 | 2026-07 | 2603·7403 | 4 |
| 미국 | 2026-06 | 2603·7403, 일부 방향만 | 3 |
| 인도네시아 | 2026-06 | 2603·2604·2709, 확보된 방향만 | 3 |

사우디의 이번 6월 조회와 남아공의 이번 7월 조회는 빈 응답이었다. 미국도 이번 7월 조회는 비어 있었다.
이는 해당 월 무역이 없거나 각국 공식 통계에 자료가 없다는 뜻이 아니다. 키 기반 Comtrade·국가 원천·상대국 신고 보완 대상이다.
한국은 키 인증 실조회 미실행이다.

인도네시아 니켈광·구리 정광 2개 국가×품목 조합에 기존 통제 seed 후보가 연결됐다. 현재 법적 효력은 검토 대기다.
공식 원문 접속 확인 2회 중 보크사이트 발표 페이지는 baseline 확보, 니켈광 발표 페이지는 접속 실패로 기록했다.

검증: Python 단위 테스트 **78개**, Node 테스트 **10개** 통과.
`validate_bilateral_public.py`로 30개 파일의 내용 해시·인덱스 일치·분모/비중/순위 재계산을 확인했다.
실제 Workers 런타임, GitHub Actions, 자동 merge·배포는 실행하지 않았다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'New for anti/scripts/commodity_trade/validate_bilateral_public.py' \
  'New for anti/public/data/commodity_trade_bilateral_v1'
```

## 1. 전달물과 바로 연결할 경로

| 전달물 | 용도 |
|---|---|
| `public/data/commodity_trade_bilateral_v1/index.json` | 공개 인덱스. 확보된 국가·HS·연/월·방향 및 부분 파일 경로 |
| `public/data/commodity_trade_bilateral_v1/parts/<hash>.json` | 불변 내용 주소형 관측치 파일. 키/원본 API 에러 없음 |
| `scripts/commodity_trade/build_bilateral.py` | 명시적 `--fetch`, 요청 상한, 재개·출판 CLI |
| `bilateral_provider.py` | `preview` / `gateway` / `direct` 공통 파서. Comtrade, 한국 Itemtrade/nitemtrade |
| `bilateral.py`, `bilateral_jobs.py`, `pipeline_store.py` | 정확성 계산, 누락 방어, 원자적 저장·단일 작성자 잠금 |
| `gateway/handler.mjs` | 비밀키를 Worker 내부에 두는 인증 조회 모듈. 루트 Worker에는 아직 미연결 |
| `client/bilateral-loader.mjs` | DOM 변경 없는 화면용 데이터 로더. 직접/상대국 신고 구분 |
| `deployment/monthly.yml.example` | Claude가 검토 후 설치할 비활성 Actions 템플릿 |
| `deployment/seed_checkpoint.json` | 초기 실제 수집의 정규화 재개 상태. 키/원본 응답 캐시 아님 |
| `export_control_screen.py` | 수출국·HS·상품 형태·기간·목적국 조건으로 통제 후보 연결 |
| `check_export_policy_sources.py` | 공식 정책 원문 접속/변경 감지. 법적 효력 자동 판정 아님 |

위 `public/`, `scripts/`는 레포 안의 **`New for anti/` 기준**이다.

## 2. UI 연결 계약 (Claude 담당)

```javascript
import { loadBilateral } from './scripts/commodity_trade/client/bilateral-loader.mjs';

const result = await loadBilateral({
  baseUrl: '/public/data/commodity_trade_bilateral_v1/',
  countryCode: '152', // Comtrade source country code, not ISO numeric assumption
  hs: '2603',        // copper ore/concentrates; refined copper is 7403
  frequency: 'M', period: '202606', signal: abortController.signal,
});
```

- `result.rows`: `focus_flow=X|M`, `counterparty`, 실제 `reporter`, `source_flow`, `reporting_basis`, `metrics`, `analysis`, `export_control`.
- `metrics.net_weight_kg`, `trade_value_usd`는 개별 지표다. kg→톤 표시 환산은 /1,000, kg→배럴 환산은 하지 않는다.
- `analysis.<metric>.share_pct`와 `rank` 사용. `rank_scope=observed_partner_codes`는 확보 상대국 내 순위이며 전국 전체 순위가 아니다.
- `null`은 ‘미확보/비교 불가’, 명시적 숫자 `0`만 0. `failures`가 있으면 부분 응답 배지.
- `periods`는 실제 확보 기간만 제공한다. 빈 월에 이전 월이나 연간 자료를 자동 대입하지 않는다.
- `frequency=A`로 연도 조회도 같은 규격이다. 기존 연도 데이터와 자동 혼합하지 않는다.
- **정제 구리 7403 vs 구리광·정광 2603**, **니켈광 2604 vs 정제/괴 7502**, LNG 271111 vs 넓은 가스 2711을 구분한다.
- 직접 신고와 상대국 신고는 대안 관측치다. 동일 거래를 두 번 더하거나 큰 금액을 진실로 선택하지 않는다. 상대국 신고로 전환하면 분모·순위를 null 처리한다.
- 미확인 국가 코드는 숫자 코드를 보존한다. 모르는 ISO3·국가명을 만들어내지 않는다.
- 출처 문자열/기사 제목은 신뢰할 수 없는 텍스트다. UI에 `innerHTML`로 삽입하지 않는다.

## 3. Worker 연결 (Claude 담당, 아직 배포 안 됨)

기존 공개 `/api/comtrade`는 필드를 줄이며 일부 청크 실패를 성공으로 반환할 수 있다.
**새 파이프라인에 그 응답을 사용하지 말 것.** 별도 경로를 먼저 분기한다:

```javascript
import { handleTradePipeline } from './New for anti/scripts/commodity_trade/gateway/handler.mjs';
// 기존 fetch 핸들러 내부, 공개 catch-all 앞:
if (url.pathname === '/api/trade-pipeline/query') {
  return handleTradePipeline(request, env);
}
```

필요 설정:

- Worker secrets: 기존 `COMTRADE_API_KEY`, `KOREA_CUSTOMS_SERVICE_KEY` + 신규 전용 `TRADE_PIPELINE_TOKEN`.
- 수집기: `TRADE_GATEWAY_URL=https://<배포주소>/api/trade-pipeline/query`, 같은 `TRADE_PIPELINE_TOKEN`.
- 토큰은 브라우저/정적 자산/로그/URL에 넣지 않는다. 키를 반환하는 API를 만들지 않는다.
- exact POST 경로, 토큰 인증, 파라미터 제한, 고정 원천 호스트, 리다이렉트 거부, 30초 타임아웃, 최대 응답 4MiB, 원천 요청 1회, no-store가 구현되어 있다.
- 모듈은 Cloudflare의 `crypto.subtle.timingSafeEqual`을 사용한다. Node 테스트는 해당 primitive만 shim한다. **실제 Workers 런타임·배포 검증은 Claude가 수행해야 한다.**
- 적절한 WAF/Access 호출 제한 및 실패 관측 설정은 배포 담당자가 적용한다. 이 모듈만으로 계정 전체 쿼터 조정까지 제공하지 않는다.

나중에 GitHub Secrets를 준비하면 `--mode direct`로 전환한다. 원천 키 이름은 동일하고 정규화/체크포인트/화면 형식은 유지된다.
`GITHUB_TOKEN`은 Actions가 제공한다. 일반 코드 체크아웃·artifact·PR용 토큰을 사용자가 새로 발급받을 필요는 없다. 외부 API 키와는 별개다.

## 4. 실행 및 배포 순서

모든 명령은 총괄 프로젝트 루트에서 실행한다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s 'New for anti/scripts/commodity_trade/tests' -v
node --test 'New for anti/scripts/commodity_trade/gateway/handler.test.mjs' 'New for anti/scripts/commodity_trade/client/bilateral-loader.test.mjs'

# 수집 전 예상 작업량만 확인 (파일 생성·네트워크 없음)
python3 'New for anti/scripts/commodity_trade/build_bilateral.py' --plan-only \
  --reporters all --hs all --months 3 --checkpoint /private/tmp/trade-state/checkpoint.json

# 최초 상태는 deployment/seed_checkpoint.json으로 시작하고 이후 반드시 최신 checkpoint 복원.
# 예시 경로: /private/tmp/trade-state/checkpoint.json
python3 'New for anti/scripts/commodity_trade/build_bilateral.py' --fetch --mode gateway \
  --reporters all --hs all --months 3 --max-requests 120 \
  --checkpoint /private/tmp/trade-state/checkpoint.json

# 한국: nitemtrade 개별 상대국 + Itemtrade World를 동일 갱신 회차 내에서 결합
python3 'New for anti/scripts/commodity_trade/build_bilateral.py' --fetch --mode gateway \
  --source korea_customs --reporters KOR --hs 2709,2603,2604,2607,2608 \
  --hs-version HSK --months 3 --max-requests 60 \
  --checkpoint /private/tmp/trade-state/checkpoint.json
```

한국 파서는 공식 명세 `nitemtrade`의 `hsCd`, `statCd`, `expWgt/impWgt`, `expDlr/impDlr`를 사용한다.
Itemtrade는 `hsCode`. 정확 한 달·한 HS·한 상대국 응답만 받으며 총계 행 제외, 중복·다른 기간·다른 상대국은 거부한다.
API 인증 오류/쿼터 소진은 중단 상태를 남긴다. 실제 한국 인증 통합 응답 검증 전에는 완료로 표시하지 않는다.
`HSK`는 통계 연도의 한국 품목 분류라는 출처 태그(`HSK2026` 등)이며, Comtrade `H6`와 동일하다고 자동 합치지 않는다. Comtrade의 향후 HS 개정은 `--hs-version`과 원문 일치를 별도 검증한다.
국가 코드 매핑은 현재 우선국 27개 기반이며 한국 전체 상대국 커버리지를 의미하지 않는다.

### 반복 실행과 PR

- `deployment/monthly.yml.example`을 검토하고 실제 workflow에 설치한다. 이 작업에서는 설치/활성화하지 않았다.
- 매월 16–28일 갱신 예시. 기본 최근 3개월을 재확인해 정정 자료를 반영한다.
- 27국×27 HS×3개월×2방향 = **4,374개 작업**. 예시의 120회×13일은 1,560회뿐이므로 전체 완료를 보장하지 않는다. 운영 쿼터와 국가·품목별 제공 여부를 검증한 후 실행 횟수/범위를 조정해야 한다. 처음에는 핵심 조합으로 시작할 것.
- `--max-requests`는 이 provider에서 실제 원천 1회/작업과 대응한다. 재시도 루프/페이지 추가 요청은 숨겨져 있지 않다.
- 500행 상한 도달·잘림 신호는 부분 응답으로 보류한다. 공개 Preview로 모든 국가·상품을 확보한다는 보장은 없다.
- 빈 응답·방향/상대국/지표 누락은 기존 정상 값을 삭제하지 않는다. 정당한 삭제/재분류 정정은 별도 검토 필요.
- 같은 `--cycle`의 완료 작업은 건너뛰고 실패/미완료를 먼저 진행한다. 다른 cycle에서 같은 관측월을 재확인한다.
- 매 요청 원자적 checkpoint 저장 + 단일 작성자 잠금. Actions는 실패한 실행의 artifact도 복원한다.
- artifact는 정상 후처리가 가능한 실패에 대비한다. **VM 강제 종료/전체 job 강제 취소 시 마지막 artifact 업로드 이후 작업은 재요청될 수 있다.** 원천 값이 손상되지는 않지만 무손실 진행 기록이 필요한 운영에는 R2 등 매 요청 원격 checkpoint가 추가로 필요하다.
- 공개 파일은 내용 주소형으로 먼저 쓰고 `index.json`을 마지막에 교체한다. 예전 부분 파일을 이 빌드에서 자동 삭제하지 않는다.
- 인증 실패 상태 exit 2, 계약/저장 오류 exit 1. 429/빈 응답은 인덱스 상태에 표시되며 거래 0으로 바뀌지 않는다.
- 템플릿은 main 직접 push/배포를 하지 않고 데이터 PR을 만든다. 최종 자동 merge·배포는 Claude가 저장소 승인된 검사/권한에 연결한다. `GITHUB_TOKEN`으로 만든 PR이 다른 workflow를 자동 기동한다고 가정하지 말 것.
- 기존 `commodity_trade_monthly.yml`의 main 직접 push 정책은 별도 조정 대상이다. 기존 파일을 이 작업에서 수정하지 않았다.

## 5. 수출통제 — 어느 정도 자동화됐나

- 수집 결과의 **실제 수출국**을 기준으로 검사한다. 한국 수입 화면이라도 인도네시아산이면 인도네시아 정책을 본다.
- 기존 seed 22건 중 안전하게 형태/HS 후보 매칭을 명시한 9건을 사용한다. 나머지 13건은 `unmapped_rule_ids`에 남긴다. 기술 통제·광산 정책·수입 금지·품질 한정 품목을 넓은 HS 전체에 강제 적용하지 않는다.
- 원광 금지를 정제 니켈에 적용하지 않는다. 월중 시행·과거 종료·미래 시행·특정 목적지 조건을 구분한다.
- 기본 표시: `potential_control_match` / `requires_review` / `not_assessed`. **어느 것도 통관 허가나 ‘통제 없음’ 판정이 아니다.**
- 과거 발표가 오늘 접속된다는 사실만으로 현재 법적 효력을 갱신하지 않는다. 정밀한 공식 문서·시행/종료일·검토 유효기간·품목 범위가 모두 확인될 때만 검증된 조치 범위로 표시한다.
- 정책 원문 체크는 통계 수집과 별도 실행:

```bash
python3 'New for anti/scripts/commodity_trade/check_export_policy_sources.py' \
  --out /private/tmp/trade-state/policy-source-checks.json --max-requests 2
python3 'New for anti/scripts/commodity_trade/build_bilateral.py' \
  --checkpoint /private/tmp/trade-state/checkpoint.json \
  --policy-monitor /private/tmp/trade-state/policy-source-checks.json
```

두 번째 명령은 `--fetch`가 없어 무역 API를 재호출하지 않고 정책 표시만 재생성한다.
`index.product_policy_screens`와 로더의 같은 필드는 거래 행이 미확보인 국가·품목도 검사한 결과다. 빈 거래를 통제의 결과로 단정하지 않는다.
별도 정책 작업을 하루 1회 돌리고 결과를 보관하도록 기존 공식보고서 workflow에 연결할 수 있다. 현재 자동 설치는 하지 않았다.
원문 해시 변경은 검토 신호이며 페이지의 조회수 변경도 감지할 수 있으므로 법률 변경 확정 알림으로 쓰면 안 된다.

## 6. 남은 승인·확인

1. Claude: gateway import/route + UI loader 연결 + 실제 Workers 인증 smoke test.
2. 사용자/Claude: 신규 `TRADE_PIPELINE_TOKEN`을 Worker와 수집기 양쪽 Secret에 안전하게 등록. 기존 원천 키를 다시 채팅에 붙이지 말 것.
3. 실제 한국 nitemtrade 한 달·한 상대국 XML 검증 후 범위 확대.
4. Claude: 워크플로 설치·주기/예산 선택·artifact 복원·PR 검사·자동 merge/배포 경로 검증.
5. 정책 담당: 미매핑 13개 규칙의 정확 HS/예외/시행일·최신 공식 개정 검증.

OPEC Excel/PDF, FAPDA 및 추가 상품별 RSS는 이전 조사 후보다. **이번 구현을 해당 파서/수집기가 완성됐다는 뜻으로 해석하지 말 것.**
기존 월별 World 총계/JODI/국가별 어댑터도 유지되며, 새 양국 간 스냅샷과 근거 없이 합산하지 않는다.

## 참고한 공식 자료

- [한국 관세청 품목별 국가별 API](https://www.data.go.kr/data/15100475/openapi.do): 필드/단위/방향.
- [UN Comtrade API](https://uncomtrade.org/docs/un-comtrade-api/): 원천 접근 경로. 실제 공개 응답으로 필드 대조.
- [Cloudflare Workers 보안 지침](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/), [Secrets](https://developers.cloudflare.com/workers/configuration/secrets/): 서버 내부 키 사용·크기 제한·인증 비교에 반영.
- [GitHub 자동 토큰](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token), [Actions artifacts](https://docs.github.com/en/rest/actions/artifacts): 별도 개인 토큰 없이 재개 자료 읽기/저장.
- [인도네시아 내각사무처 보크사이트 발표](https://setkab.go.id/en/govt-to-impose-export-ban-on-bauxite-ore-june-next-year/): 과거 발표 근거이지 현재 효력 보증이 아님.
