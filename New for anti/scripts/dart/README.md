# KFA-Engine — Korean Filing Analytics

> **문서 입구 (읽기 순서):** [`START_HERE.md`](./START_HERE.md)

DART 사업보고서/재무제표에서 **결정론적으로** 재무 지표를 뽑는 엔진입니다.  
LLM·GPU·토큰 과금 없음. 계정 없으면 `null` + `reason` (가짜 0 금지).

레포 패턴은 `shipping_capacity` / `macro_intel` 과 동일:  
`config/*.json` → Python 엔진 → `public/data/dart_universe_v1.json`.

## 층

| 층 | 역할 | 상태 |
|----|------|------|
| L0 | OpenDART `fnlttSinglAcntAll.json` 수집 (+ 로컬 캐시) | API 키 대기 · fixture로 개발 |
| L1 | `accounts.map.json` 정규화 + 자산=부채+자본 검산 | ✅ |
| L2 | `metrics.spec.json` 지표 엔진 | ✅ |
| L2b | 산업 키트·M&A 지표·가정 DCF (base/bull/bear) | ✅ phase2 |
| L3 | 업종 벤치·부실스코어·매크로 β 계수 JSON | 다음 |
| L4 | 템플릿 NLG | ✅ |
| L5 | Worker `/api/dart` + `dart.js` UI | Claude 소유 — 별도 티켓 |

포트폴리오 샤프·분산은 형제 모듈 `scripts/portfolio/` → `portfolio_risk_v1.json`.  
당신이 줄 것: `USER_INPUTS.md`.

산업 키트 **왜 이렇게 짰는지(전제·이유·출처):** `INDUSTRY_RATIONALE.md`.  
**15·20대 수출 × 한은 KSIC 매핑:** `EXPORT_BOK_COVERAGE.md` (`tools/gen_industry_kits.py`로 재생성).

**한은 업종 평균 벤치:** `config/bok_peer_benchmarks.json` → 분석 결과에 `industry.bok_peer` (유동·부채 vs 업종평균).  
**산업 배경(신평·도메인):** `config/industry_background.json`.


## 실행 (키 없이)

```bash
cd "New for anti/scripts/dart"
python3 -m unittest discover -s tests -v
python3 build_universe.py --print-stats
# → ../../public/data/dart_universe_v1.json
```

## 실행 (OpenDART 키 발급 후)

```bash
export DART_API_KEY='발급키'
python3 build_universe.py \
  --corp 00126380:2024:11011:CFS \
  --print-stats
```

환경변수 별칭: `OPENDART_API_KEY`, `DART_KEY`.

확정 공시는 `cache/fnltt__*.json` 에 TTL 없이 캐시합니다.

## 지표 (v1)

유동비율 · 당좌비율 · 현금비율 · 부채비율 · ROE · ROA · ROIC ·  
영업/순이익률 · 이자보상배율 · 자산·재고·매출채권 회전 · 이익의 질(CFO/NI) · FCF

## UI 연동 (이 브랜치에서 안 함)

`app.js` / `index.html` / `_worker.js` 는 Claude 소유.  
스냅샷만 준비해 두면 스크리너·기업 카드는 shipping 패턴으로 붙이면 됩니다.

## 면책

산출물은 **계산된 재무 지표**이며 투자 권유가 아닙니다.
