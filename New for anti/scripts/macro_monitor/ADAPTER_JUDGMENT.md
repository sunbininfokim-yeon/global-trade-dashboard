# Adapter judgment (2026-08-08)

Antigravity 제안 + 실측 기준 결정.

| 소스 | 판단 | 이유 / 다음 |
|------|------|-------------|
| **FedWatch (CME 사이트 스크래핑)** | **하지 않음** | CME Data ToS 금지. 이 IP는 이미 403 차단. 공식 API는 유료(~$25/월). |
| **FedWatch (자체 스코어링)** | **할 것** | 30D FF 선물 정산가 + FRED EFFR로 CME와 같은 확률 계산(오픈소스 FedWatch 방식). 평시 **주 1회**, FOMC **D-7부터 매일**. |
| **ISM / S&P PMI** | **스킵** | 라이선스. 한국은 BOK/민간 PMI만. |
| **CDS** | **스킵** | Markit 등 유료. |
| **신용등급** | **Wikipedia** | `pandas.read_html` + UA로 S&P/Fitch/Moody's 표 동작 확인. Trading Economics는 Cloudflare. 구글 검색 스크래핑은 비추. |
| **BOJ** | **Time-Series Search** | [stat-search](https://www.stat-search.boj.or.jp/index_en.html) CSV/다운로드. 시리즈 코드 매핑만 하면 됨 (BS·JGB·ETF). |
| **IndexErgo** | **참고만 · 데이터 API 아님** | 미국 지표 목록·카테고리 참고용(센서스튜디오와 함께). 본문은 대부분 **FRED/BOK 원천**. 공개 개발자 API 없음. UI/카피 베끼기·사이트 스크래핑 폴백 **하지 않음**. 데이터 폴백은 FRED/Worker/Yahoo 등 원천으로. |
| **QRA** | **엔진 가동** | `build_qra_engine.py` — 2020+ archives 다운로드·파싱·인과 체크리스트 → `public/data/qra_engine_v1.json`. `--live` 시 `qra_issuance` 바에 환급주 경매 규모 오버레이. |

## 이미 있는 것

- `macro_intel/qra.py` — 순차입·현금잔고 문장 파서
- `qra_issuance` 칩 — 만기 바 (지금은 fixture components)
- Wikipedia 등급 — `macro_monitor/ratings_wiki.py` → `--live` 오버레이
