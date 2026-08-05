# Election watch — 세계 선거 창 (scaffold)

이후 UI에 **「선거」패널**을 붙일 때 읽는 계약입니다.

## 제품 목표 (사용자 요구)

1. **올해 어디서** 선거가 있는지 (대선·총선·지선·재보궐·당대표)
2. **집권 정당** / 추적 정당
3. 당대표 선거 범위  
   - **대통령제**: 여당 + 제1야당  
   - **의원내각제**: 주요 정당 **최대 4개**
4. 재보궐 포함
5. **여론조사**: 전국 대선 경마형 배제 · **통치(국정) 지지율** 유지
6. **미국 예측시장**(Polymarket 등)을 선거 사이클 중 참고 확률 파이프라인으로
7. **주요 개각**은 속보·보드 모두 가치 있음 (1급)

## 지금 하는 일 / 안 하는 일

| 함 | 안 함 |
|----|--------|
| `country_seed.json` 골격 + 시스템·정당 캡 정책 | 전 세계 자동 캘린더 완성 |
| 속보 RSS 선거·개각·통치지지율 (commodity_news) | app.js 선거 창 UI (T01 이후) |
| Polymarket Gamma API → `betting_markets` | 도박 UX / PredictIt(지역 제한 시 보류) |
| `elections_board_v1.json` 스냅샷 | LLM 전량 요약 |

## 실행

```bash
cd "New for anti/scripts/election_watch"
python3 build_board.py --print-stats
# ticker_v1.json 이 있으면 election / cabinet / governance 헤드라인 live 부착
# --no-betting 으로 Polymarket 호출 생략
```

산출: `public/data/elections_board_v1.json`

## 속보 연동 (commodity_news)

통과:

- 대통령/총선/지선/재보궐/당대표
- **개각·외교/재무/국방 장관 교체** (`cabinet_reshuffle`)
- **국정·통치 지지율** (`governance_poll`)

배제:

- 전국 대선 경마형 여론조사·RCP 평균 등

중요도 과다 속보는 `importance.json` (주요국 3급 > 비주요 2급 가능).

## 배팅 시장

`config/betting.json` → `election_watch.betting.fetch_us_election_markets`  
공개 Polymarket 검색/목록만 사용. `betting_markets.markets[]` 에 question·outcome 가격·volume.

## 데이터 채우기

`config/country_seed.json` 의 `events_2026[]` 에 날짜를 계속 추가.

## UI 스케치 (나중)

```
[2026 선거 맵/리스트]
  국가 · 체제 · 집권당
  다가오는 일정 (D-day)
  예측시장 스트립 (US cycle)
  통치지지율 헤드라인
  개각 / 관련 속보
```
