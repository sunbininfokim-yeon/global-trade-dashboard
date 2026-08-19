# election_watch 이관 핸드오프 (Grok 세션 축적분)

**as_of:** 2026-08-13
**용도:** 사용량 한도로 채팅 이전 시 **파이프 + 축적 데이터 + 정책** 전부 복원
**소유:** 데이터/파이프 = **Grok** · UI/`app.js` = **Claude** (절대 수정 금지)

관련 문서:
- `HANDOFF_GROK.md` (초기 이관)
- `HANDOFF_CLAUDE_ELECTIONS_UI_V2.md` (현재 UI 데이터 계약)
- `HANDOFF_CLAUDE_ELECTIONS_UI.md` (08-08 P0 범위 기록; v2로 대체)
- `README.md`, `LEARNING.md`
- 본 파일 = **2026-08-09~13 세션에서 추가·확정된 내용 정본**

---

## 0. 경로·산출물

| 구분 | 경로 |
|------|------|
| 엔진 루트 | `scripts/election_watch/**` |
| 패키지 | `scripts/election_watch/election_watch/*.py` |
| 설정·팩 | `scripts/election_watch/config/**` |
| 원본 캐시 | `scripts/election_watch/raw/**` |
| public | `public/data/elections_*.json`, `race_progress_*.json`, `race_aggregation_compare_v1.json`, `invest_lens_elections.json` |

### 파이프 명령

```bash
cd "New for anti/scripts/election_watch"

python3 run_refresh_cycle.py --build-derived  # 계파→보드→캘린더→UI manifest 인수 빌드
python3 build_board.py --print-stats
python3 build_board.py --no-betting

python3 -m election_watch.build_race_progress
python3 -m election_watch.build_china_pla_bios
python3 -m election_watch.extract_kor
python3 -m election_watch.extract_gbr_isr
python3 -m election_watch.extract_tier2_fill
python3 -m election_watch.extract_rosters
python3 -m election_watch.build_factions
python3 refresh_monthly_factions.py   # 매월 1일 계파 메타
```

철학: **숫자·명단 = 공개 소스만**. null + reason. LLM 발명 금지.

---

## 1. 등급·국가 현황 (2026-08-13)

### 1급 (deep) — active
| ISO | 깊이 | 핵심 산출 | remaining |
|-----|------|-----------|-----------|
| **USA** | congress + governors + state leg(정당만) + House factions + DSA 비공식 | `usa_house_factions.json`, calendars/usa_2026 | TX-23/FL-20 special 날짜, NCSL 크로스체크 |
| **JPN** | 중의 465 + 참의 + 지사47 + 자민 파벌 | `jpn_ldp_factions.json` | 참의 공식 HTML, 도의회 의석 |
| **CHN** | 정치국/PSC + PLA + 안보 + 실각 strikethrough + 월간 리뷰 | `china_leadership_extracted.json`, `china_pla_bios.json` | CMC 신규·전구 공개소스 재확인 |
| **RUS** | 푸틴/미슈스틴 + 안보회의 + 통합러시아 + 두마 2026-09 | `russia_leadership_extracted.json` | **2026-09-20 이후 의석 확정** |

### 2급 deep (1순위) — 계파·전대 포함
| ISO | 팩 | 메모 |
|-----|-----|------|
| **GBR** | `tier2_priority1_snapshot.json` | PM **Andy Burnham** (스티커). Labour 계파 소프트 |
| **KOR** | 동 + 전당 | 대통령 이재명 / 총리 **한성숙** + **8/17 전당**. 국민의힘 계파 메모는 있으나 공개 UI 정본은 아직 없음 |
| **ISR** | `isr_knesset_factions.json` | **2026-10-27** 총선. 전시. 리쿠드 4갈래 + 극우 연정 + 야권(아이젠콧 Yashar 등). 병역 쟁점 |

### 2급 light (수장·집권·야당만) — `tier2_remaining_light.json`
BRA, DEU, FRA, TWN, IND, TUR, **IDN, ZAF, NGA**

| ISO | 수장 | 집권 | 야당/반대 |
|-----|------|------|-----------|
| BRA | 룰라 (PT) | PT 소수+Centrão | PL(볼소나루) |
| DEU | **메르츠** (CDU, 2025-05~) | CDU/CSU+SPD | AfD 등 |
| FRA | 마크롱 / PM **레코르누** | Ensemble 소수 | RN · LFI |
| TWN | 라이칭더 (DPP) | DPP 행정·입법원 과반X | KMT+TPP |
| IND | 모디 (BJP) | NDA | INC·INDIA |
| TUR | 에르도안 (AKP) | AKP+MHP | CHP 분열(외젤 신당 등) |
| IDN | 프라보워 (Gerindra) | 거대 연정 | 의회 약세·거리 항의 |
| ZAF | 라마포사 (ANC) | **GNU**(ANC+DA 등) | EFF 등 GNU 밖 |
| NGA | 티누부 (APC) | APC | PDP·Labour·ADC (**유동**) |

### 2급 지정학 핵심
| ISO | 모드 | 팩 |
|-----|------|-----|
| SAU | leadership·energy·security core | 살만 / **MbS** 실질 · 전국 경쟁선거 없음 |
| **IRN** | **china_style party-state-security core** | `iran_leadership_extracted.json` |

### 3급
| ISO | 모드 | 팩 |
|-----|------|-----|
| ARE | emirates brief | MbZ / MbR · 7 토후국 |

**IRN 핵심 (2026):**
- ~~알리 하메네이~~ 사망(2026-02말) → **모주타바 하메네이** 최고지도자 (2026-03-08)
- 대통령: **페제슈키안**
- 실무 안보: **IRGC + SNSC** 집단 비중 확대 (분석 medium)
- 마줄리스 의장: 갈리바프
- 선거: 관리형(감시평의회 사전심사)

---

## 2. 정책·UI 계약 (세션에서 확정)

1. **실각/조사:** 이름 **strikethrough** 필드 (하이픈 접두 아님). 태그는 **`_internal` only** — 공개 UI 금지.
2. **정치 호칭:** 가장 대중적·높은 직급 하나만 display_title.
3. **주의회:** 정당 의석만 (계파 금지). **연방 하원**만 계파 + 비공식 DSA/Mamdani 가능.
4. **계파 월간 보조:** `refresh_monthly_factions.py`는 날짜·메타데이터만 갱신한다. 실제 명단·숫자는 공개 원문 검토 후 `usa_house_factions.json` / `jpn_ldp_factions.json`에 반영한다.
5. **지도:** 1단계 대통령 정당색 / 2단계 주지사 정당색. 의회 = 반원(상·하원).
6. **캘린더:** invest-lens 스타일 전역 날짜순. **전당대회 필수** (예: 민주 8/17).
7. **깊이:** USA만 연방+주 deep. 다른 1급은 국가별 특수 구조, tier2는 국가수반+국가의회 여야 구도+캘린더와 선택적 광역 요약, tier3는 국가 권력 브리프. 지방의원 개별 명단은 기본 범위 밖.
8. **희소 데이터:** 분석 문구만 근거와 confidence를 붙여 제한적으로 허용. 인명·의석·날짜·명단은 추정 금지, `불명` 유지.
9. **외부 데이터 평가:**
   - `civicaatlas.org/parties` → 이념·의석 **보조 교차**만. 다운로드 제한·V-Party 2019. 본선 금지.
   - `country-factbook.vercel.app` → CIA Factbook **아카이브**. 인물 낡음(이란 등). 체제 유형 참고만. 스크랩 본선 금지.
   - 의석 본선: **IPU Parline / Wikidata / 공식 선관위**.

정본 정책 파일:
- `config/depth_and_calendar_policy.json`
- `config/ui_display_policy.json`
- `config/spectrum_rules.json`

---

## 3. 스티커 (틀리면 안 됨)

| 키 | 값 |
|----|-----|
| 영국 총리 | **Andy Burnham** (2026-07-20~). Starmer 현직 금지 |
| 한국 대통령 | 이재명 |
| 한국 총리 | **한성숙** |
| 미국 2026 | **중간선거** (대선 경선=2028) |
| 이스라엘 총선 | **2026-10-27** |
| 러시아 두마 | **2026-09-18~20** (확인 후 의석 갱신) |
| 일본 공식 파벌 | 아소파 존속; 구 아베·모테기 등은 ex_* 블록 |

---

## 4. 핵심 config 파일 목록

```
config/
  priority_tiers.json          # 1/2/3급 정의·active
  tier1_status.json            # 완료/remaining
  tier2_priority1_snapshot.json # GBR/KOR/ISR deep
  tier2_remaining_light.json   # BRA…NGA light
  tier3_leadership_briefs.json # SAU/IRN 2급 특수팩 + ARE 3급
  china_leadership_extracted.json
  china_pla_bios.json
  russia_leadership_extracted.json
  iran_leadership_extracted.json
  isr_knesset_factions.json
  usa_house_factions.json
  jpn_ldp_factions.json
  country_seed.json
  official_sources.json
  depth_and_calendar_policy.json
  ui_display_policy.json
  calendars/{usa,jpn,rus,kor,gbr,isr,bra,deu,fra,twn,ind,tur,sau,are}_2026.json
  profiles/{usa,jpn,chn,rus,kor,...}.json
  extracted/*                  # 의회·캘린더·race 중간 산출
```

---

## 5. 다음 작업 큐 (우선순위)

1. **RUS** 2026-09 두마 결과 → 의석·통합러시아 갱신
2. **CHN** 월간 전체 검토 (CMC·전구·실각)
3. 2급 light → 필요 시 deep 승격: **BRA**(10월 대선) → DEU → FRA
4. KOR 민주 전당 **최종** 결과 반영 (8/17 이후)
5. ISR 10/27 전 여론·연정 시나리오 주기 갱신
6. `build_board.py` 돌리며 light/중국식 팩이 보드에 붙는지 확인
7. NGA 야당 문구 “유동·소송” 유지 (고정 3당처럼 쓰지 말 것)

---

## 6. 새 채팅 복붙 블록

```
election_watch 데이터/파이프 이어가기.
정본: scripts/election_watch/MIGRATION_HANDOFF_2026-08-13.md
+ HANDOFF_GROK.md / README.md
소유: 데이터=Grok, UI=Claude(app.js 금지).
숫자·명단 공개소스만. LLM 발명 금지.
UI 게이트: public/data/elections_ui_manifest_v1.json 먼저 읽기.
전체 빌드: python3 run_refresh_cycle.py --build-derived
현재 1급 USA/JPN/CHN/RUS deep 완료(러 9월 후속).
2급 deep GBR/KOR/ISR. 2급 light BRA DEU FRA TWN IND TUR IDN ZAF NGA.
2급 지정학 핵심 SAU·IRN + 3급 ARE. IRN은 최고지도자·행정부·마줄리스·전문가회의·IRGC/SNSC·계파를 중국식으로 본다.
스티커: Burnham / 한성숙 / 미 중간선거.
UI는 manifest ready/partial/disabled 준수. 클라이언트 재계산·새 데이터 파일 생성 금지.
다음 데이터: BRA deep / RUS 선거 대비.
```

---

## 7. 세션에서 한 일 (요약)

- 중국: 실각 strikethrough, 안보·당 기관, PLA-시진핑 연결, 월간 리뷰, 태그 internal
- 미국 하원 정당별 계파 + DSA/Mamdani 비공식
- 일본 자민 파벌 분리
- 러시아 중국식 리더십 팩
- 이스라엘 미국급 크네셋·리쿠드 혼전·전시
- 국힘 계파 조사 메모 축적(공개 UI 정본 미완료)
- 2급 light 9개 + IDN/ZAF/NGA
- 2급 지정학 핵심 SAU·IRN + 3급 ARE
- 정책: 주의회 정당만, 월간 계파, 전당·캘린더, 외부 Atlas/Factbook 보조만
- 팩트체크: 수장·집권 OK; NGA 야당 유동; IRGC 사령관 medium

정본 파일은 `scripts/election_watch/config/**` 및 public data에 존재한다. 단, 국민의힘 계파·각국 전체 내각·미국 부지사/법무장관·상원 임기·상임위 등은 아직 정본 파일이 없으며 UI manifest에서 `partial/disabled`다. 대화 요약만으로 복원하지 말고 위 경로와 `public/data/elections_ui_manifest_v1.json`을 읽을 것.
