# Macro Monitor — 실데이터 vs 데모

## 왜 처음에 전부 데모였나

1. **키트·JSON 계약·UI 핸드오프를 먼저 고정**하기 위해 `fixture_synth`로 전체 국가를 채웠다.  
2. 실데이터는 소스마다 키·쿼터·히스토리 길이가 달라 **어댑터를 나중에** 붙이는 편이 안전했다.  
3. 로컬에 `FRED_API_KEY`가 없고, Worker FRED는 **`limit=1`(최신 1점)** 만 준다. FRED CSV 대량 다운로드는 이 환경에서 자주 타임아웃한다.

## 지금 라이브 빌드

```bash
cd "New for anti/scripts/macro_monitor"
python3 build_macro_monitor.py --live --print-stats
# → public/data/macro_monitor_v1.json  (source.kind = hybrid_live)
```

| 백엔드 | 용도 |
|--------|------|
| Yahoo chart API | 주가·FX 등 **월봉 시계열** |
| Worker `/api/macro?source=fred` | 미국 금리·Fed BS 등 **최신값** |
| Worker `/api/macro?source=bok` | 한국 기준금리·환율·코스피 **최신값** |

## 아직 못 끌어오거나 부분만 되는 것

| 데이터 | 이유 |
|--------|------|
| FRED **장기 히스토리** | Worker `limit=1` + CSV 타임아웃 |
| **FedWatch** | CME **사이트 스크래핑 금지**(ToS·IP 차단). → FF 선물 정산 기반 **자체 스코어링**(주1회 / FOMC D-7 매일) |
| **ISM / S&P PMI** | 스킵 (요청). 한국은 BOK 쪽만 |
| **국채 CDS** | 스킵 (요청·유료) |
| **S&P/Moody's/Fitch 등급** | **Wikipedia 표**로 `--live` 오버레이 (`ratings_wiki.py`) |
| **QRA 만기별 발행** | 환급발표 표 파서 확장 가능 — 수동 정답 매분기 불필요 |
| **KOSIS** | 스킵 |
| **BOJ ETF/JGB** | [BOJ Time-Series Search](https://www.stat-search.boj.or.jp/index_en.html) CSV 매핑 예정 |

정본 판단: [`ADAPTER_JUDGMENT.md`](./ADAPTER_JUDGMENT.md)


## 품질 플래그

- `quality: live` — 시계열까지 실데이터  
- `quality: live_latest` — 최신 포인트만 실데이터 (히스토리는 fixture일 수 있음)  
- `quality: demo` — 여전히 합성
