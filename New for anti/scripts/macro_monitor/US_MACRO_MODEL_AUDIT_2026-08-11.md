# US Macro Monitor — Existing Model Audit (2026-08-11)

대상: `main`의 Macro Monitor 엔진 (`engine_version: 0.31.0`)

범위: 코드·설정·현재 공개 JSON의 **정적 감사**. 네트워크 수집, 빌더 실행, 성과 백테스트는 하지 않았다.

## 결론

현재 구현은 국가별 지표를 같은 UI 계약으로 보여 주는 **데모/프로토타입 엔진**으로는 잘 구조화되어 있다. 특히 QRA 문서 파서, 파생값(순유동성·금리 스프레드), 국가 키트와 명시적 limitation은 강점이다.

그러나 공개 스냅샷은 `fixture_synth`이고, `--live`도 다수 지표에서 **합성 과거 시계열에 실제 최신값 하나만 덮어쓴다**. 따라서 현 상태에서 차트 추세, 선행성, 신호 성능을 판단하거나 백테스트 근거로 쓰면 안 된다. 데이터 신뢰성 기준으로는 "연구용 프로토타입", 실시간 매크로 모델 기준으로는 "아직 미완성"이다.

## 확인된 강점

- 미국을 benchmark kit로 두고 liquidity/rates/fx/equity/growth/inflation 6탭 계약이 일관됨.
- `Net Liquidity = Fed assets - TGA - ON RRP`의 단위 변환과 파생식은 테스트됨.
- QRA는 Treasury archive·Sources & Uses PDF를 파싱하고, 행사·만기별 컴포넌트를 별도 출력함.
- NFP의 개정·계절조정 한계, QT와 QRA의 단순 인과 해석 위험을 문서와 limitation에 이미 표기함.
- JSON 직렬화 시 NaN/Infinity를 거부하는 보호장치와 fixture 기반 회귀 테스트가 있음.

## 우선 수정 사항

### P0 — 실제 최신값이 합성 과거 차트의 출처를 덮어쓴다

`live_overlay._pin_latest()`은 5년·10년 history의 마지막 값만 실제값으로 바꾸고, indicator 전체를 `source=fred_worker:*`, `quality=live_latest`로 표시한다. 나머지 history는 `fixture_synth`로 생성된 값이다.

영향:

- UI에서 FRED source로 보이는 5년·10년 추세가 실제 FRED 시계열이 아닐 수 있다.
- 변화율, 이동평균, 파생값과 이후 백테스트가 합성 데이터에 오염된다.
- source/quality가 "현재값"인지 "전체 history"인지 구별되지 않는다.

근거: `macro_monitor/live_overlay.py` 149–159, 210–219; `macro_monitor/engine.py` 1822–1828.

수정 요구:

1. `history_source`, `latest_source`, `history_quality`, `latest_quality`를 분리한다.
2. 실제 history가 없으면 fixture history를 유지한 live indicator로 표기하지 않는다. 카드에는 latest-only로 표시하거나 `history_unavailable`을 준다.
3. 원칙적으로 미국 핵심 FRED series는 최소 10년의 실제 관측값을 한번에 수집해 history 전체를 교체한다.
4. `source.kind=hybrid_live`는 전체 모델의 품질이 아니라 backend 결과일 뿐이라는 문구를 명시한다.

완료 기준:

- 실제 history가 없는 indicator는 차트에 합성선이 나타나지 않는다.
- 한 indicator의 source가 여러 개인 경우 source 범위가 JSON에 명시된다.
- `test_no_fixture_history_marked_live`가 통과한다.

### P1 — 관측일·발표일을 버리고 생성월 말일을 as_of로 기록한다

FRED fetch는 실제 관측일 `d`를 가져오지만 `_pin_latest(..., dates[-1])`에 전달하지 않는다. `dates[-1]`은 빌더가 만든 월말이며 FRED 관측일, BLS/BEA 발표일과 다를 수 있다.

영향:

- 지표가 언제 관측됐는지, 언제 투자자/정책 담당자가 알 수 있었는지 알 수 없다.
- 시차 분석·백테스트에서 look-ahead bias를 막을 수 없다.

근거: `macro_monitor/live_overlay.py` 171–173, 210–212, 224–239.

수정 요구:

```json
{
  "reference_period": "2026-07",
  "observed_at": "2026-07-31",
  "published_at": "2026-08-12T12:30:00Z",
  "retrieved_at": "2026-08-12T12:35:00Z",
  "vintage": "first"
}
```

시장 일별 series는 `observed_at`만, BLS·BEA·FOMC·QRA는 네 필드를 모두 사용한다. 단순 수정으로 `d.isoformat()`을 쓰는 것은 필요하지만 충분하지 않다.

### P1 — 미국 성장·물가 핵심은 live path에 연결되지 않았다

`FRED_WORKER_LATEST`에는 CPI index가 정의돼 있지만 `FRED_WORKER_OK`에서 의도적으로 제외되어 있다. index 하나로 YoY를 계산할 수 없기 때문이다. NFP(`PAYEMS`), GDP/BEA 기여도, core CPI/PCE, ADP, 산업별 CES도 live 수집 대상이 아니다.

영향:

- 현 `--live`는 금리·유동성의 일부 최신값에는 유용하지만 성장·물가 모델의 실측 평가가 불가능하다.
- CPI/GDP/NFP 카드와 구성요소는 설정 파일의 synthetic base/components에 의존한다.

근거: `macro_monitor/live_catalog.py` 36–75; `config/series.spec.json` USA `gdp`, `nfp`, `cpi_yoy` 설정; 현재 `public/data/macro_monitor_v1.json`의 `source.kind=fixture_synth`.

수정 요구:

1. FRED는 latest endpoint가 아니라 observation range endpoint로 수집한다.
2. BLS CES/CPI와 BEA GDP는 원문 release + 시계열을 별도 collector로 저장한다.
3. YoY, QoQ, 기여도는 raw observed history에서 재계산한다.
4. observed data가 없는 구성요소는 `null`/`missing`으로 두고 synthetic fallback을 금지한다.

### P2 — QRA의 TGA 가정과 실제 결과를 선택적으로 사후 설명할 수 있다

QRA engine은 archive/PDF parsing에 성공한 부분이 있지만, 현재 output은 `fiscaldata: false`, `fiscal: null`, `tga_vs_qra: null`이다. TBAC parse도 현재 snapshot 통계상 0건이다. live overlay는 QRA bar를 표시하지만 `tga_vs_qra`가 있을 때만 붙인다.

이는 QRA 파서의 결함이나 "QRA만으로 TGA를 예측해야 한다"는 뜻이 아니다. QRA의 기말 현금은 Treasury의 당시 **계획·가정**이고, 실제 TGA는 세입·지출·부채한도·특별조치·발행 실행 등 정부 현금흐름에 따라 달라질 수 있다. 차이는 정상일 수 있으며 예측 실패로 라벨링하면 안 된다.

선택적으로 사후 기록하면 좋은 정보:

- 당시 QRA가 제시한 기말 현금 목표와 실제 해당 기준일 TGA
- 차이가 난 경우 Treasury의 이후 공식 설명·수정 QRA·재정 이벤트
- QRA 발표 직후에 시장에 알려진 발행 구성과, 사후에만 알 수 있는 실제 결과의 구분

근거: `public/data/qra_engine_v1.json` 6–27; `macro_monitor/live_overlay.py` 305–345.

수정 요구:

1. 필요할 때만 Fiscal Data 또는 동등한 공식 Treasury daily cash balance series를 추가한다.
2. 각 QRA에 `planned_end_cash`, `actual_end_cash`, `difference_bn`, `actual_available_at`를 저장할 수 있다. `forecast_error`라는 명칭은 사용하지 않는다.
3. `tga_vs_qra`는 예측 점수나 자동 매매 신호가 아니라 사후 설명용 `plan_vs_actual`로 이름을 바꾸고, 비교 가능한 분기·기준일을 명시한다.
4. TBAC PDF가 없거나 parse 불가하면 bar components를 "official recommendation unavailable"로 표시한다.

### P2 — 실제 성능 평가·시차 검증 체계가 없다

기존 테스트는 fixture 구조, 수식, QRA parser에 집중한다. 성장·물가·정책 신호가 이후 결과를 설명하는지, 데이터가 발표 당시 사용 가능했는지는 검증하지 않는다.

수정 요구:

- `US_MACRO_QUALITY_DESIGN.md` §9의 walk-forward protocol을 별도 artifact로 구현한다.
- 목표별 baseline, OOS 표본 수, lag별 결과, confidence interval, leakage audit을 JSON으로 보관한다.
- 결과가 없으면 UI는 "가설 / 검증 전"이라고 표시한다.

### P2 — FOMC·공식 문서·위원 구성은 정적 메타데이터에 머문다

현재 `officials.json`은 중앙은행장과 재정장관 수준의 현재 인물 메타데이터다. FOMC 표결·투표권 roster·SEP·Beige Book·회의록의 release timeline은 데이터 모델에 없다.

수정 요구:

- `US_MACRO_QUALITY_DESIGN.md` §4, §8의 release envelope와 `policy_committee`/`official_documents` 모듈을 추가한다.
- 문서 요약은 source URL·페이지·발표시간과 분리해 보관한다.

### P2 — 운영 품질 테스트가 부족하다

현재 macro test는 country kit·fixture 수식·JSON safe 여부를 광범위하게 검증한다. 반면 live overlay에 대한 source provenance, freshness, FRED/BLS/BEA 계산, collector 실패 격리 테스트는 없다.

추가 테스트:

1. `test_live_latest_preserves_history_provenance`
2. `test_release_timestamp_not_builder_month_end`
3. `test_cpi_yoy_from_observed_13_months`
4. `test_nfp_and_ces_components_share_same_release_vintage`
5. `test_qra_actual_tga_only_after_actual_available_at`
6. `test_missing_official_source_never_falls_back_to_synth`

## 수정 권장 순서

1. **P0 source/provenance 분리** — synthetic history를 live로 보이게 하는 문제 차단
2. **P1 point-in-time release envelope** — 날짜·vintage 기반을 먼저 고정
3. **P1 미국 FRED/BLS/BEA observed collectors** — 수집 범위를 유동성뿐 아니라 성장·물가로 확대
4. **P2 필요 시 QRA 계획–TGA 실제 결과의 사후 설명 레이어**
5. **P2 FOMC·SEP·Beige Book과 고용/GDP/CPI quality layer**
6. **P2 lag backtest + UI**

## 구현 역할 분리

- Cursor/Grok: collector, schema, fixtures, tests, UI wiring, PDF cache pipeline
- Codex review: source provenance, unit/date contract, QRA–TGA reconciliation definition, leakage test acceptance
- Claude deploy: UI integration, build/publish and deployed artifact check

## 배포 전 게이트

다음 셋 중 하나라도 충족하지 못하면 UI에 "실시간/관측"으로 표시하지 않는다.

1. 카드 value와 history 전체의 source/quality가 구분돼 있다.
2. BLS·BEA·QRA indicator에 `published_at`과 `vintage`가 있다.
3. derived value의 모든 입력이 관측값이거나, 입력 누락을 명시적으로 표시한다.
