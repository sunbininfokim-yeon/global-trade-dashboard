# Election watch — 학습 방식 (문서/텍스트, 숫자 API 아님)

## 한 줄

선거·인물·파벌·지지율은 **시계열 숫자 API를 바르는 문제**가 아니다.  
**공개 문서·명단 HTML/PDF·공식 발표문**을 가져와 필드로 정규화하고, 틀린 추출·스펙트럼·출처 등급만 스티커로 고친다.

뉴스 `LEARNING_PLAIN` 과 같은 철학: 딥러닝 재학습이 아니라 **규칙+출처+교정 키**.

## 왜 이렇게 가나

| 데이터 | 성격 | 수집 |
|--------|------|------|
| 대통령/총리 | 공개 현직 1명 | 공식 사이트·외교 발표문 파싱 |
| 의회 정당·의원 | 공개 명단 | congress.gov / 중의원·참의원 / TSE 등 |
| 지자체장·주의원 | 공개 명단 | NGA·주 SOS·都道府県 |
| 파벌 | 비공식 | 언론 교차 (이미 `*_factions.json`) |
| 국정 지지율 | 여론조사 표 | Gallup·NHK·리얼미터 등 **거버넌스 지지율만** |
| 중국 고위·PLA | 보고서·양회·당대회 | DoD CMPR / USCC / 新华·人大 PDF 텍스트 추출 |
| 지도색 | 수장 `spectrum` | progressive→파랑, conservative→빨강 (기존 글로브) |

## 파이프라인 (목표)

```
sources.yaml / official_sources.json
        │
        ├─ fetch_html / fetch_pdf  →  raw/ (캐시, 커밋 금지 가능)
        ├─ extract_rules.py        →  entities (head, party, seat, governor…)
        ├─ spectrum_rules.json     →  party_id|iso3 → progressive|conservative|…
        ├─ human_labels.jsonl      →  promote/demote/drop on extract keys
        └─ build_board.py          →  elections_board_v1.json
```

### 학습 키 예시 (교정용)

| key | 의미 |
|-----|------|
| `spectrum:USA:gop` | 공화=보수 확정 |
| `spectrum:JPN:ldp` | 자민=보수 확정 |
| `extract:usa_house_party` | 하원 정당 라벨 파싱 |
| `extract:jpn_pm` | 관저 총리명 |
| `source:dod_cmpr` | 중국 PLA 인물 추출 신뢰 |
| `poll:governance_only` | 경마형 제외·국정지지도만 |

## 스펙트럼 (지도용) — 즉시 규칙

수장(대통령/PM)의 소속 정당 `spectrum`을 국가 지도색에 쓴다.

- `conservative` → 빨강  
- `progressive` → 파랑  
- `centrist` / `other` / `authoritarian_*` / `authoritarian_monarchy` → 별도 팔레트 (UI)

이미 확실한 것 (`config/spectrum_rules.json` + 교정 키):

| iso | party/head | spectrum |
|-----|------------|----------|
| USA | gop / Trump | conservative |
| USA | dem | progressive |
| JPN | ldp / Takaichi | conservative |
| JPN | cdp | progressive |
| KOR | dpk / Lee | progressive |
| KOR | ppp | conservative |
| GBR | lab / Burnham | progressive |
| ISR | likud / Netanyahu | conservative |
| DEU | cdu / Merz | conservative |
| FRA | renaissance / Macron | **centrist** |
| BRA | pt / Lula | progressive |
| CHN | cpc | authoritarian_cpc |
| RUS | ur | authoritarian_ur |
| SAU | Al Saud / MbS | authoritarian_monarchy |
| ARE | Al Nahyan | authoritarian_monarchy |

### 교정 스티커 (human_labels)

정본 머신 스냅샷: `config/extracted/human_labels.jsonl`  
분석 전체: `config/extracted/learning_analysis_v1.json`

치명 교정:

| key | 액션 |
|-----|------|
| `head:GBR:pm` | **Andy Burnham** (2026-07-20~). Starmer incumbent 추출 폐기 |
| `head:KOR:pm` | **Han Seong-sook / 한성숙** (2026-07-01~, OPM) |
| `poll:reject_horserace` | 전국 대선 경마 헤드라인 drop |
| `null:없음_vs_불명` | 없음=해당없음 · 불명=미확정 |

## 19국 학습 스코어카드 (2026-08-14 보드 기준)

차원 8: head · spectrum · legislature_live · subnational · calendar · governance_poll · factions/pla/power · extract_pipe  
상세 수치: `learning_analysis_v1.json`.

### deep (의회+수장+캘린더+지지율)

| ISO | head | 의회 | 하위 | poll | 비고 |
|-----|------|------|------|------|------|
| **USA** | Trump | Congress + floor | 주지사50·주의회 | Gallup 41 | specials 일부 불명 |
| **JPN** | Takaichi | 중의+참의(wiki) | 지사47 | NHK 内閣 58 | 10월 재보궐구 TBD |
| **GBR** | **Burnham** 07-20 | Commons Lab405 | — | net+19 + Starmer exit | 의장 불명 |
| **ISR** | Netanyahu | Knesset 120 | — | preferred-PM 38 (job 아님) | 10-27 총선 |
| **KOR** | Lee 06-04 + **PM 한성숙** | 22대 300 DPK161 | 6·3 광역 12/4 | Gallup 51 / Realmeter 45.9 | 강릉 보궐 불명 |

### composition (의회 배선 · 여론 todo)

| ISO | seats 스냅샷 | 다음 승급 |
|-----|-------------|----------|
| **DEU** | BT 630 (CDU164 AfD152… CDU/CSU208) | 총리 지지율 시리즈 |
| **FRA** | AN 교섭단체 577 | PM 이름 + IFOP 등 |
| **BRA** | 하/원 midyear 언론 등급 | TSE open data + Datafolha |

### thin / leadership / scaffold

| ISO | 깊이 | 학습 메모 |
|-----|------|----------|
| **RUS** | thin + Duma light 430/450 | 9월 후 CIKRF 교체 전 hold |
| **CHN** | PLA doc (bios 21) | 선거 캘린더 비움 = 정상 |
| **SAU/IRN** | 2급 geopolitical core | SAU는 왕실·에너지·승계·안보, IRN은 최고지도자·행정부·마줄리스·전문가회의·IRGC/SNSC·계파 팩 연결 |
| **ARE** | 3급 power·leadership brief | 7개 토후국·연방 지도자 카드 중심 |
| **TWN/TUR/IND** | scaffold | 수장만; KOR 템플릿 재사용 대기 (특히 TWN) |
| **IDN/ZAF/NGA** | light connected | 수장·정당·캘린더 연결 완료; KPU/IEC/INEC 원문 수집 후 승급 |

`capture_sources.py`는 원문 캐시만 만들며, 검토 전에는 숫자·명단·날짜를 자동 반영하지 않는다.

### 교차 교훈 (L1–L7)

1. **수장 churn** — GBR 사례: `since` 없는 PM 필드 금지  
2. **poll kind 분리** — job / preferred / exit favourability  
3. **null 규약** — 없음 vs 불명  
4. **출처 등급** — official > media > wiki > approximate (BRA·RUS 승급 대기)  
5. **비선거 모드** — CHN·Gulf는 빈 이벤트가 정상  
6. **KOR 딥 템플릿** — assembly+floor+local highlight+이중 poll house+calendar null  
7. **승급 레버** — composition국은 여론 숫자 → roster 공식 승급

### 다음 학습 큐

1. DEU/FRA/BRA **governance poll 숫자 채움**  
2. FRA **PM** · BRA **TSE**  
3. TWN **입법원 deep** (KOR 파이프 복제)  
4. RUS **9월 후 CIKRF**  
5. IND·TUR 캘린더 공식 발표 시 채움  

재생성: `python3 -m election_watch.extract_*` 후 `build_board.py --no-betting`.

## 중국 PDF 출처 (레포에 파일 없음)

사용자가 말한 `generated/PLA_Commanders_Report_2026.pdf` 패턴은 **미국이 쓰는 연례 PLA/중국군 보고서** 계열이다.  
워크스페이스·Downloads에서 동명 PDF는 **아직 발견되지 않음**. 대신 공식 원천:

1. **DoD China Military Power Report (CMPR)**  
   - 2025: `https://media.defense.gov/2025/Dec/23/2003849070/-1/-1/1/ANNUAL-REPORT-TO-CONGRESS-MILITARY-AND-SECURITY-DEVELOPMENTS-INVOLVING-THE-PEOPLES-REPUBLIC-OF-CHINA-2025.PDF`  
   - 내용: CMC·전구(Eastern/Southern 등)·PLARF 인사·숙청 서술 (이름 추출 대상)
2. **USCC Annual Report** (미중경제안보검토위)
3. **양회·당대회**: npc.gov.cn / 新华社 명단·자격심사 공고
4. 로컬 캐시 권장 경로: `election_watch/raw/china/PLA_Commanders_Report_YYYY.pdf` (gitignore)  
   → 추출 결과는 `config/china_leadership_extracted.json` 만 커밋

## 여론조사

**거버넌스(국정) 지지율만** — 전국 대선 경마·RCP 평균 배제 (`reject_horserace`).

| ISO | kind | 1순위 출처 | 보드 (as_of 분석) |
|-----|------|-----------|------------------|
| USA | presidential_job_approval | Gallup | 41 |
| JPN | cabinet_approval | NHK | 58 |
| KOR | presidential_job_approval | **Gallup Korea** (1순위) + Realmeter 부차 | 51 / 45.9 |
| GBR | pm_approval / exit snapshot | More in Common / Ipsos | net+19 / Starmer 22 |
| ISR | pm_preferred | Midgam | 38 (job approval 아님) |
| DEU/FRA/BRA | *slot* | todo | null + status todo |

### 중국 문서 체인

1. [USNI News index](https://news.usni.org/2025/12/24/pentagon-annual-report-on-chinese-military-and-security-developments-2) (사용자 제공)  
2. DoD CMPR PDF/TXT → `raw/china/CMPR_2025.*`  
3. 슬롯 추출 → `config/china_leadership_extracted.json`  
4. 한국어 바이오 → `python3 -m election_watch.build_china_pla_bios` → `config/china_pla_bios.json`  
5. 보드 병합 → `elections_board_v1.json` 의 `countries[CHN].pla` (+ `pla.bios`)
