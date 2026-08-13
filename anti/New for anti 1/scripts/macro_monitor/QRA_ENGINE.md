# QRA Causal Engine

재무부 Quarterly Refunding 아카이브를 받아 **문장 + Sources&Uses 표 + TBAC 만기표**를
정형 JSON으로 내고, Fiscal Data로 TGA·관세를 붙인다.

## 발표일 워크플로

```bash
cd "New for anti/scripts/macro_monitor"
python3 build_qra_engine.py --download --from-year 2020
```

산출물: `New for anti/public/data/qra_engine_v1.json`  
캐시: `cache/qra/html/**`, `cache/qra/pdf/**` (gitignore)

기사 URL을 맞출 필요 없음. Estimates 페이지에 달린 공식 PDF를 따라간다.

## 표 재현

| 기사에 보이던 표 | JSON 경로 |
|------------------|-----------|
| Sources & Uses (Need / Marketable / Other / Cash / SOMA) | `events[].sources_uses.rows` · `latest.sources_uses_latest_estimates` |
| TBAC 만기별 월 스케줄 | `events[].tbac_financing.rows` · `latest.tbac_recommendation_months` |
| 순발행·기말현금 문장 | `events[].estimates.quarters` |
| Bill/Coupon 스탠스 | `events[].policy.bill_stance` / `coupon_stance` |
| 순발행 비교 (전분실적·직전예측·당기) | `events[].compare` · `latest.compare` · 칩 `qra_issuance.compare` |
| 만기 바 (칩 보조) | `latest.qra_issuance_components` |
| 실TGA vs QRA 가정 | `tga_vs_qra` |
| 관세(Customs Duties) | `fiscal.customs` |

## 모듈

- `qra/fetch.py` — 아카이브 HTML
- `qra/parse.py` — Estimates/Policy 문장
- `qra/tables_pdf.py` — Sources&Uses · TBAC PDF 표
- `qra/fiscaldata.py` — TGA · Customs
- `qra/causal.py` — 고정 인과 체크리스트
- `build_qra_engine.py` — CLI

`engine_version` ≥ `0.2.0` 이면 표 레이어 포함.
