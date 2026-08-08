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

`config/calendars/{usa,jpn,rus}_2026.json` 에 연도 일정을 넣고 `build_board.py`가 병합.  
시드·프로필의 `events_2026` 는 캘린더 파일이 우선. 교차 로그: `config/extracted/calendars_2026.json`.

## 학습 (문서/텍스트)

숫자 API 페인팅이 아님. → **`LEARNING.md`**

- 스펙트럼 규칙: `config/spectrum_rules.json` (공화·자민 = conservative → 지도 빨강)
- 중국 보고서: `config/china_report_sources.json` + `raw/china/CMPR_2025.{pdf,txt}`
- PLA 한국어 바이오: `python3 -m election_watch.build_china_pla_bios` → `config/china_pla_bios.json` (LLM 아님)
- Anti 문헌만: `HANDOFF_ANTIGRAVITY_CHINA_LIT.md` — JSON/파이프는 Cursor

## 1급 상태 · 파벌 (언론 교차)

| 파일 | 내용 |
|------|------|
| `config/tier1_status.json` | 뭐가 됐고 뭐가 남았는지 |
| `config/official_sources.json` | 선관위·공식 포털 |
| `config/usa_house_factions.json` | 하원 파벌 + HFC 119대 스냅샷(언론 교차) |
| `config/jpn_ldp_factions.json` | 자민 파벌/旧파벌 (読売·日経·연합 등) |

**2급 deep:** `GBR`·`ISR` (`extract_gbr_isr`) · `KOR` (`extract_kor`).  
**2급 composition:** `DEU`·`FRA`·`BRA` (`extract_tier2_fill`) — 여론 숫자 todo.  
**2급 scaffold:** `TWN`·`TUR`·`IND`.  
**3급 간략:** `SAU`·`ARE` — 선거 `없음`. `IRN` 미작성. → `tier3_leadership_briefs.json`.  
**학습 분석 정본:** `LEARNING.md` + `config/extracted/learning_analysis_v1.json` + `human_labels.jsonl`.

미국: 당대표 선거 없음 → 원내대표만. HFC는 공식 명단 없음 → NADA(2025-04) + Ballotpedia/Pew/CDC 교차로 32명 스냅샷 남김.

일본: 공식 파벌은 아소파만 존속(読売·47NEWS). 旧아베·모테기·기시다·니카이 등은 해산 후에도 회동 블록으로 언론 추적 → `ex_*`로 남김. 전체 명단은 변동 심해 count+출처만.

## UI 스케치 (나중)

```
[2026 선거 맵/리스트]
  국가 · 체제 · 집권당
  다가오는 일정 (D-day)
  예측시장 스트립 (US cycle)
  통치지지율 헤드라인
  개각 / 관련 속보
```
