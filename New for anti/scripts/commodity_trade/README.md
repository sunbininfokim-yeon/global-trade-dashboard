# commodity_trade — 월별 무역 파이프

## 2026-09-23 사우디 검토·배포 인수인계

먼저 [최신 Claude 인수인계](CLAUDE_DEPLOY_2026-09-23.md)를 읽는다.
사우디 석유류 수출액과 HS2709 원유 총량/목적국별 데이터는 별개다.
`validate_release.py`로 교정된 월별 JSON과 사우디 데이터 의미, bilateral/coverage를 검증한다.
이 PR에는 실제 `.github/workflows/**` 변경이나 UI 연결을 포함하지 않는다.
아래 과거 자동화 설명은 로컬 이관 자료의 설계 기록이며 활성화 증거가 아니다.

## 2026-09-09 양국 간 월별 데이터 연결

새 국가·상품·상대국·방향별 경로는 [Claude 인수인계](CLAUDE_MONTHLY_BILATERAL_HANDOFF_2026-09-09.md)를 먼저 읽는다.
최신 확장·국가 수 집계·관측 월 기반 수집은 [9월 10일 진행 기록](BILATERAL_PROGRESS_2026-09-10.md)을 따른다.
`python3 'New for anti/scripts/commodity_trade/monthly_coverage.py'`가 총량/상대국별 국가 수를 분리해 공개 커버리지 파일을 재생성한다.
`build_bilateral.py`, 인증 조회 모듈, 화면용 데이터 로더, 수출통제 후보 검사 및 실제 초기 스냅샷을 제공한다.
기존 아래 World 총계 경로와 별도이며, 인증 gateway·실제 Actions·UI·배포는 아직 연결되지 않았다.
`deployment/monthly.yml.example`은 비활성 템플릿이다. 아래의 기존 자동 갱신 설명 역시 파일 설정 설명이지 현재 운영 성공 증거가 아니다.

**순서:** energy → minerals → agri_trade

**원칙:** 기본은 출처별 무료 월별 시리즈다. Comtrade는 키·명시적 보고국·요청 상한이 있을 때만 선택적으로 덮어쓴다. 숫자 발명·단위 없는 합산 금지.

## HS / 코드 매칭 (`hs_match.py`)

| relation | 의미 | 병합 |
|----------|------|------|
| same | 동일 코드 | OK |
| parent / child | HS 계층 (2709 ⊃ 270900) | 상위 버킷으로 정렬 OK |
| alias | JODI `CRUDEOIL` ↔ HS 2709 | 명시 별칭만 |
| sibling_under | 같은 챕터 다른 헤딩 | **자동 합산 금지** |
| incompatible | 무관 | 폐기 |

## 소스

| 소스 | 키 | 용도 |
|------|-----|------|
| JODI-Oil CSV | 불필요 | 원유·석유제품 월별 수출 |
| UN Comtrade | `COMTRADE_SUBSCRIPTION_KEY` | 전 상품 HS 월별 (옵션) |
| India TradeStat | 불필요 | 인도 월별 ITC-HS 가치(USD million), 공개 폼·캐시 기반 |
| USDA PSD | 불필요 | 농산물 **연도** (russia_export_pulse) |

## 실행

```bash
cd "New for anti/scripts/commodity_trade"
python3 build_monthly.py --sectors energy,minerals,agri_trade
```

산출: `public/data/commodity_trade_monthly_v1.json`

보드 갱신: energy 상품 `stage2_data_status=monthly_available`

부분 섹터 실행은 기존의 다른 섹터를 보존한다. 전체 산출을 의도적으로 교체할 때만 모든 섹터와 함께 `--replace-output`을 쓴다.

```bash
# 네트워크 없이 기존 결과의 계약·커버리지만 점검
python3 build_monthly.py --no-fetch --print-stats

# Comtrade는 국가·호출 수를 명시해 쿼터를 통제한다.
COMTRADE_SUBSCRIPTION_KEY=... python3 build_monthly.py \
  --comtrade-reporters USA=842,CHN=156 --comtrade-max-requests 20
```

Comtrade가 요청되지 않았거나 키가 없으면 무료 소스 결과를 유지하며, 결과 JSON에 그 실행 상태를 남긴다.

## GitHub Actions 자동 갱신·배포

이 PR은 수집 자동화를 활성화하지 않는다. `deployment/monthly.yml.example`은 검토 후
`.github/workflows/commodity_trade_bilateral.yml`로 설치할 비활성 템플릿이다.
설치 시 매월 16–28일 UTC 03:20에 bilateral·사우디 bulletin을 갱신하고 데이터 PR을 만든다.
기존 월별 총량·국가 통계 전체를 갱신하는 스케줄은 이 템플릿에 포함되지 않는다.

- 테스트 전에 `python3 -m pip install -r 'New for anti/scripts/commodity_trade/requirements.txt'`를 실행한다.
- 변경은 데이터 PR → 검토·병합 → 기존 `.github/workflows/deploy.yml` 경로로 배포한다. main 직접 push나 수집기 직접 배포는 하지 않는다.
- 현행 배포 워크플로의 시크릿 이름은 `CLOUDFLARE_API_TOKEN`이다. 수집 API 키와 별개다.
- 수집 설정은 템플릿의 `TRADE_ACQUISITION_MODE`, `TRADE_GATEWAY_URL`, `TRADE_PIPELINE_TOKEN`, `COMTRADE_API_KEY`, `KOREA_CUSTOMS_SERVICE_KEY`를 따른다.
- `GITHUB_TOKEN`으로 만든 PR의 후속 CI 트리거 제약은 설치 담당자가 검증해야 한다. 무인 자동 배포 완료를 뜻하지 않는다.

키·토큰은 파일·로그·공개 JSON에 저장하지 않는다.

## 핵심국 Comtrade 월별 패널

`build_comtrade_priority_monthly.py`는 미국·브라질·아르헨티나·중국·한국·일본·호주·남아공·사우디·UAE 등을 대상으로, 수출과 수입의 World 상대 월별 시리즈를 별도 파일에 축적한다. 이는 세계 전체가 아니라 국가 클릭 2단계용 우선 보고국 패널이다.

무료 Preview는 한 요청에 한 월만 허용하므로, 23개 핵심 HS를 한 국가·흐름·월 요청으로 묶고 `/tmp/commodity_trade_cache`에 캐시한다. 기본값은 최신 완료월부터 3개월·최대 24개 네트워크 요청이다. 24시간 이내 캐시는 재사용하고, 만료된 캐시는 기존 요청 예산 안에서 재조회한다. 요청 실패·오류 응답은 기존 캐시를 덮어쓰지 않는다. 새 응답에 없는 월의 기존 공개 관측값은 보존한다. 과거 월 수정은 그 월을 요청 범위에 포함했을 때 반영된다.

### Preview 게시 품질 계약 (2026-09-24)

- 각 `points[].publication`: `status=eligible|hold`, `eligible_for_display`, `flags`, `evidence`.
- `suspected_partial_month`: 이전 최대 12개 정상 후보 월의 중앙값 대비 1% 미만. 최신 월뿐 아니라 과거 의심 월도 계속 표시한다. 부분 집계 확정이나 실제 무역 중단을 뜻하지 않는다.
- USD 금액끼리 우선 비교하고, 불가능하면 정확히 같은 원본 단위끼리만 비교한다. 한 달만 기준인 경우도 `baseline_count=1`로 증거의 한계를 노출한다. 부족한 표본·계절성으로 오탐 가능성이 있다.
- `publication_summary.latest_eligible_month`는 대표값 후보 최신 월, `held_months`는 보류 월이다. 기존 `latest_available_month`는 원본 관측 최신 월로 유지한다. `eligible`은 검증된 완전 통계라는 뜻이 아니다.
- UI는 Preview의 `eligible_for_display=false`를 차트·대표값·비율·순위에서 제외하고 보류 배지를 표시한다. 다른 단위는 한 선으로 연결하거나 직접 비교하지 않는다. 원본 값/0은 삭제·변조하지 않는다. JODI·국가 통계는 이 휴리스틱을 적용하지 않는다.
- UI 미수정: 기존 UI 휴리스틱은 소비자가 이 계약을 연결한 뒤 제거한다. 메타데이터 추가만으로 화면 수정이 완료되지는 않는다.
- 기존 파일의 오프라인 메타데이터 갱신: `python3 'New for anti/scripts/commodity_trade/build_comtrade_priority_monthly.py' --annotate-only`. 수집 시각·원본 관측은 그대로 둔다. `--no-fetch`는 여전히 읽기 전용이다.
- `validate_release.py`는 게시 메타데이터를 재계산하여 누락·변조를 차단한다. 보류 표시가 올바르게 있는 데이터는 통과시킨다.

```bash
# 우선 4개국의 최근 3개월 수출·수입 패널을 수집
python3 build_comtrade_priority_monthly.py \
  --reporters USA,BRA,ARG,CHN --months 3 --max-requests 24 --print-stats

# 네트워크 없이 현재 패널의 통계 확인
python3 build_comtrade_priority_monthly.py --no-fetch --print-stats
```

산출: `public/data/commodity_trade_comtrade_priority_v1.json`. 각 관측치에는 Comtrade의 `isReported`, 수량 추정, 집계·추정 플래그가 보존된다.

## Comtrade 공백국의 국가 공식 패널

`build_national_priority_monthly.py`는 Comtrade Preview가 비어 있는 국가를 원천국의 공식 월간 통계로 보완한다. 이 파일은 Preview 패널과 **분리**된다. 국가 원천은 HS 단위·측정치가 다를 수 있으므로, 숫자를 자동 합산하거나 한 출처가 다른 출처를 덮어쓰지 않는다.

현재 자동 수집 가능한 나라는 인도(`IND`)·멕시코(`MEX`)·노르웨이(`NOR`)·사우디아라비아(`SAU`)·태국(`THA`)이며, 한국(`KOR`)은 실행 환경에 `KOREA_CUSTOMS_SERVICE_KEY`가 있을 때만 추가된다. 인도 TradeStat은 HS4 전체 USD 값과 HS6 특정품목 조회를 사용하며, 멕시코 INEGI 어댑터는 현재 TIGIE HS4의 USD FOB 값만 수집한다. 노르웨이 SSB는 kg로 명시된 하위 세번, 사우디 GASTAT는 공개 Tableau CSV의 정확 HS4 순중량 tons·million SAR, 태국 관세청은 HS4/HS6 직접 월의 바트 가치만 사용한다. 사우디 공개 필터의 HS6·상대국 레이블 계약은 아직 자동화하지 않는다. 따라서 이들 원천을 서로 또는 Comtrade와 자동 합산하지 않는다.

```bash
# 인도 최근 완료 3개월, 수출·수입. 한 번에 모든 요청을 하지 않으며 캐시로 재개한다.
python3 build_national_priority_monthly.py \
  --reporters IND --end-month 2026-06 --months 3 --max-requests 12

# 네트워크 없이 현재 국가 원천 패널의 통계 확인
python3 build_national_priority_monthly.py --no-fetch --print-stats
```

산출: `public/data/commodity_trade_national_priority_v1.json`.

다른 공백국의 실제 접근 조건은 `national_source_registry.py`에 명시한다. 중국은 공개 월간 주요 품목표가 있으나 정확 HS 계약의 안정적 자동 조회 경로가 아직 없고, 남아공 SARS는 월별 관세세번·상대국·수량·가치 선택까지 검증됐지만, 최종 내려받기의 비대화형 계약이 안정화되기 전에는 자동 시리즈를 만들지 않는다. UAE 공개 데이터는 현재 식별된 범위가 2023년까지이며, 인도네시아 월간 공개물은 HS2 중심이라 현 HS4/HS6 계약에 자동 배분하지 않는다.

## 파편화된 월별 데이터를 읽는 규칙

빌드는 각 원본 포인트를 그대로 보존하고 `normalized` 메타데이터를 덧붙인다. `kg`, `metric_tons`, `KTONS`처럼 질량으로 정확히 환산 가능한 값만 `normalized.value`/`normalized.unit="kg"`를 제공한다. 배럴·㎥·FOB 금액·산업 프록시는 환산하지 않으며 비교 불가 사유를 남긴다.

각 국가 시리즈에는 `series_quality`(12개월 충족률, 최신성, 원본 단위, 반복값·프록시 경고), 품목에는 `comparison_policy`(국가 간 수치 비교 허용 여부, 부분합 규칙)가 추가된다. 이 필드는 무료 원천의 차이를 숨기기 위한 점수가 아니라, UI·분석기가 잘못 합산하지 않도록 하는 계약이다.

## UI

- 1단계: 연도/롤업 + `export_controls` 관찰/주의/경계 색
- 2단계: `points[]` 최신월 기준 12개월, 기본=latest
