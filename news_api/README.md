# news_api — 뉴스·지정학 인텔 (기후/수율과 분리)

이 트리는 **글로벌 트레이드 대시보드의 수율·NASA·training 파이프와 독립**이다.  
같은 GitHub repository 안에 두되, 코드·설정·학습 신호 경로를 섞지 않는다.

| | 이 패키지 (`news_api/`) | 기존 (`New for anti/scripts/yield_model` 등) |
|--|-------------------------|-----------------------------------------------|
| 주제 | 언론 RSS, 공식 공표, 유동성 언론 지표, 선거·배팅 | 기상·수확·Ridge 예측 |
| 산출(예정) | 티커·보드 JSON, 라벨 JSONL | `*_yield_forecast.json` |
| 공유 | **repository / Cloudflare 배포 경로만** | DATA_LAYOUT 계약은 사이트 쪽이 읽을 때 링크 |

구현 마이그레이션: 현재 초안 로직은 `New for anti/scripts/commodity_news` 등에 있을 수 있음.  
**정본 정책·티어 표는 여기 `config/`** 를 따른다. 실행 코드를 옮길 때는 이 트리를 루트로 한다.

## 매핑 코드 (A/B/C → 1–4)

```bash
cd news_api
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

```python
from news_api import map_legacy_scored_fields, NewsTier

# 옛 문자 티어만
map_legacy_scored_fields(country_tier_letter="B", info_grade_old=2)

# 본문/ISO 우선 (정본)
NewsTier().resolve(text="Rotterdam port delays", iso3="NLD", info_grade=2)
```

| 함수 | 역할 |
|------|------|
| `legacy_geo_letter_to_int` | A→1 B→2 C→3 |
| `NewsTier.resolve` | ISO·허브·전쟁 승격·pair_rank |
| `map_legacy_scored_fields` | commodity_news 브리지 한 방 |

## 아프리카·남미 소스 추천

`config/sources_africa_latam_v1.json` — URL 후보 + 왜 넣는지.  
헬스체크 후 `enabled_suggested` 참고해 레지스트리에 편입.

## 문서

| 파일 | 내용 |
|------|------|
| [`docs/STRATEGY.md`](docs/STRATEGY.md) | 국가 1–4급, 정보 1–4급, 권역·주기, 학습 뜻풀이 |
| `config/*.json` | 기계가 읽는 표 |

## 원칙

1. 국가급(geo)과 정보급(event)을 **곱하지 않고 분리**한 뒤, 표시 순위에서만 결합한다.  
2. **4급 국가라도** 전쟁·전염병 등 전염성 글로벌 재난이면 **승격 규칙**으로 올린다.  
3. 유동성 기사는 6시간 전용 크론이 아니라 **일 1회** + 일반 언론 배치에 편입.  
4. 수집은 30분 슬롯이지만 **권역별 분(offset) 분산**.  
5. “학습”은 뉴럴넷 재학습이 아니라 **라벨 키로 가중치를 고치는 일** (STRATEGY에 풀이).
