# Claude 배포 인수인계 — 사우디 월별 상품무역 패널

> 최신 배포 판단은 `CLAUDE_DEPLOY_2026-09-23.md`가 우선한다. 본 문서의 과거 카운트/배포 예시는 현재 준비 완료를 뜻하지 않는다.

**수신:** Claude Code (배포·UI 소유자)

**저장소 루트:** `/Users/yeoninair/Documents/New for anti-dart`

**배포 대상:** Cloudflare Worker `global-trade-dashboard` + 정적 자산 `New for anti/`

**이 티켓의 목적:** 사우디 공식 월별 상품무역 JSON을 정적 자산으로 배포하고, 배포 후 데이터 계약을 확인한다.

> 이번 작업은 UI 연동 티켓이 아니다. 사우디 데이터는 이미 `public/data`에 생성됐지만, 현재 `app.js`가 이 국가 원천 패널을 읽어 화면에 표시하도록 수정되지는 않았다. 배포는 JSON을 공개하는 단계이며 UI 노출은 별도 승인 후 진행한다.

---

## 1. 배포 판단 표

| 항목 | 확정 상태 | Claude가 할 일 | 하지 말 것 |
|---|---|---|---|
| 배포 방식 | 루트 `wrangler.jsonc`: `main: _worker.js`, `assets.directory: "New for anti"` | 저장소 루트에서 Worker 정적 자산 배포 | `New for anti/` 외 별도 build output을 임의 지정하지 말 것 |
| Worker/라우트 | 변경 없음 | 기존 `_worker.js`와 KV/cron 설정을 그대로 유지 | `_worker.js`, `wrangler.jsonc`, KV binding, cron 수정 금지 |
| 새 API 키 | 필요 없음 | GASTAT 키·TOTP·Cloudflare Secret을 만들지 않음 | `SAUDI_GASTAT_API_KEY`를 요구·저장하지 말 것 |
| 배포 데이터 | `public/data/commodity_trade_national_priority_v1.json` | 이 JSON이 정적 자산에 포함되는지 확인 | 수집기 캐시(`/tmp/commodity_trade_cache`)를 배포/커밋하지 말 것 |
| UI | 미연동 | 배포 뒤 JSON만 smoke test | `app.js`, `data.js`, `style.css`, `index.html`, `shipping.js` 수정 금지 |
| 데이터 최신성 | 사우디 상세 Tableau의 검증 최신 행은 `2025-09` | stale 상태를 그대로 보여줄 준비만 함 | 최신 2026 보도자료로 HS4·국가 상세값을 추정·덮어쓰기 금지 |

## 2. 실제 변경물

| 경로 | 배포/검토 목적 |
|---|---|
| `New for anti/public/data/commodity_trade_national_priority_v1.json` | **배포 필수.** 국가 원천 패널에 SAU를 추가한 결과물 |
| `New for anti/scripts/commodity_trade/sources/saudi_gastat_tableau.py` | 공개 GASTAT Tableau CSV 수집기. 배포 런타임에서는 실행하지 않음 |
| `New for anti/scripts/commodity_trade/build_national_priority_monthly.py` | `--reporters SAU` 실행 경로 |
| `New for anti/scripts/commodity_trade/national_source_registry.py` | SAU 공개 원천·품질 계약 |
| `New for anti/scripts/commodity_trade/world_link.py` | JODI `KTONS` → kg 환산계수 수정 (`1 KTONS = 1,000,000 kg`) |
| `New for anti/scripts/commodity_trade/tests/test_saudi_gastat_tableau.py` | Tableau 파서·stale fallback·단위 회귀 테스트 |
| `New for anti/scripts/commodity_trade/README.md` | 실행·원천 문서 |
| `New for anti/scripts/commodity_trade/CURSOR_TRANSFER_INVENTORY.md` | 최신 인벤토리/제약 |

## 3. 사우디 데이터 계약

| 필드 | 값/규칙 |
|---|---|
| 보고국 | `SAU` (사우디아라비아) |
| 원천 | GASTAT 공개 Tableau 월별 HS·국가 표. API 키 없음 |
| 자동 수집 범위 | 상대국 `WORLD` 합계, 정확한 HS4 heading |
| 수출 확보 | `crude_oil` HS2709, `petroleum_products` HS2710, `coal` HS2701, `iron_ore` HS2601 |
| 수입 확보 | `petroleum_products`, `coal`, `iron_ore` |
| 원유 수입 | 공식 표가 빈 응답. **0이 아니라 `no_data_in_saudi_gastat_tableau_response`** |
| 단위 | 기본 `metric_tons` (공식 net weight tons); `primary_value_sar_million` 보조 필드 |
| 최신월 | SAU 상세 표에서 `2025-09`; `series_quality.flags`의 stale 경고를 보존 |
| HS6 미수집 | LNG HS271111·우라늄 HS284410은 `not_collected_by_saudi_public_hs4_adapter` |
| 양자 흐름 | 사우디→미국은 미구현. Country 레이블 계약을 확인하기 전에는 양자 0을 만들지 않음 |

공식 원천: [수출 가치 Tableau](https://tableau.stats.gov.sa/views/Exports-Monthly-Value_17298816519090/NW-ExportsValuebyHarmonizedSystemandCountry), [수출 중량 Tableau](https://tableau.stats.gov.sa/views/Exports-Monthly-Weight_17298818154970/NW-ExportsWeightbyHarmonizedSystemandCountry), [GASTAT 월별 무역 방법론](https://www.stats.gov.sa/en/w/methodology-and-quality-report-for-international-trade-in-goods-statistics-monthly-4.1).

## 4. 배포 전 필수 점검

Cloudflare의 자산 디렉터리는 `New for anti/` 전체다. 현재 워크트리에 이 티켓과 무관한 untracked/수정 파일이 존재할 수 있으므로, **사우디 JSON만 바뀐다고 가정하고 배포하면 안 된다.**

```bash
cd "/Users/yeoninair/Documents/New for anti-dart"

# 1) 전체 정적 자산 배포 범위와 무관 변경을 먼저 검토
git -c core.fsmonitor=false status --short

# 2) 파이프라인 회귀·JSON 검증 (네트워크 없음)
PYTHONPYCACHEPREFIX=/tmp/commodity_trade_pycache \
  python3 -m unittest discover -s "New for anti/scripts/commodity_trade/tests" -v

python3 "New for anti/scripts/commodity_trade/build_national_priority_monthly.py" \
  --no-fetch --print-stats

python3 -m json.tool \
  "New for anti/public/data/commodity_trade_national_priority_v1.json" >/dev/null

# 3) SAU 계약 최소 확인
python3 - <<'PY'
import json
from pathlib import Path
p = Path("New for anti/public/data/commodity_trade_national_priority_v1.json")
d = json.loads(p.read_text())
s = d["reporters"]["SAU"]
assert s["flows"]["exports"]["commodities"]["crude_oil"]["latest_available_month"] == "2025-09"
assert not s["flows"]["imports"]["commodities"]["crude_oil"]["points"]
assert s["flows"]["exports"]["commodities"]["lng"]["status"] == "not_collected_by_saudi_public_hs4_adapter"
print("SAU static-data contract OK")
PY
```

기대 결과: 단위 테스트 32개 통과, national panel은 `reporter_count: 5`, `available_series_count: 174`, `point_count: 431` (이후 다른 작업이 추가된 경우 숫자는 달라질 수 있으나 SAU 계약은 유지되어야 함).

## 5. 배포 절차

`wrangler.jsonc`는 저장소 루트에 있고 `assets.directory`가 이미 `New for anti`를 가리킨다. 별도 Pages 프로젝트 배포가 아니다.

```bash
cd "/Users/yeoninair/Documents/New for anti-dart"

# 인증/구성 확인 후 dry run
npx wrangler whoami
npx wrangler deploy --dry-run

# 위 점검이 모두 통과하고, 정적 자산 전체 배포 범위를 검토한 경우에만
npx wrangler deploy
```

배포 중 새 시크릿을 설정하거나 기존 `COMTRADE_API_KEY`, `KOREA_CUSTOMS_SERVICE_KEY`, `API_CACHE`를 변경할 이유는 없다.

## 6. 배포 후 smoke test

```bash
curl -fsS \
  "https://global-trade-dashboard.sunbin-info-kim.workers.dev/public/data/commodity_trade_national_priority_v1.json" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["reporters"]["SAU"]; print({"crude_export_latest": s["flows"]["exports"]["commodities"]["crude_oil"]["latest_available_month"], "crude_import_points": len(s["flows"]["imports"]["commodities"]["crude_oil"]["points"])})'
```

기대값:

```json
{"crude_export_latest": "2025-09", "crude_import_points": 0}
```

`crude_import_points: 0`은 수입이 0이라는 뜻이 아니라 원천 표가 빈 응답이라는 뜻이다. UI를 연결할 때도 이 차이를 유지해야 한다.

## 7. 후속 작업 경계

| 후속 과제 | 담당/조건 |
|---|---|
| SAU 나머지 HS4 백필 | 데이터 담당. `--reporters SAU --max-requests 12` 재실행; `/tmp` 캐시 재사용 |
| SAU→미국 원유 양자 흐름 | Country 레이블·필터 계약을 별도로 검증한 뒤에만 구현 |
| LNG·우라늄 HS6 | 공개 Tableau의 HS6 필터 계약이 확인될 때만 추가 |
| `app.js` 국가 클릭 화면 연결 | 사용자 승인 후 Claude UI 티켓으로 별도 진행 |
| JODI `KTONS` 보정 반영 | 다음 `build_monthly.py --sectors energy,minerals,agri_trade` full rebuild 때 반영. 이번 배포에서는 main monthly JSON을 재생성하지 않음 |

## Claude용 시작 프롬프트

```text
Read first:
New for anti/scripts/commodity_trade/HANDOFF_CLAUDE_DEPLOY_SAUDI_MONTHLY.md

Deploy only the verified Saudi national-trade static JSON through the existing
Cloudflare Worker configuration at repository root. The Worker serves assets
from "New for anti". Do not edit app.js, data.js, style.css, index.html,
shipping.js, _worker.js, wrangler.jsonc, workflows, KV bindings, cron, or
Cloudflare Secrets.

Before deploy, inspect the entire working-tree asset scope because Wrangler
uploads all of "New for anti", not only this JSON. Run the listed offline
tests and JSON/SAU contract checks. Then use `npx wrangler deploy --dry-run`
and deploy only if the static asset scope is acceptable.

Required post-deploy assertion:
SAU crude export latest_available_month == "2025-09";
SAU crude imports have zero points because the source response is unavailable,
not because trade is numerically zero.
```
