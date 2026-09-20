# 작업 B 큐 — 정치 세부 조사 (대진 / 누가 나오는지)

이 파일은 **작업 B**다. 짝 문서:

- 작업 A (일정·제도, 이미 커밋/PR): `HANDOFF_CURSOR_ELECTION_INVENTORY.md`
- 작업 B 규격: `HANDOFF_CURSOR_ELECTION_CONTESTS.md`
- 공통 규칙(센티널·출처·합산 금지·`id`): `HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md` 1절

**Claude:** GitHub에서 이 경로를 연다.
`New for anti/scripts/election_watch/HANDOFF_CONTESTS_QUEUE.md`

**Cursor 「정치 세부 조사」:** 같은 경로를 연다. 한 채팅·한 턴에 **이벤트 하나**. 아래 목록의 **위부터**.

---

## 하지 말 것

- 일정·제도를 다시 만들지 말 것. 달력·`elections_system_v1.json`·`config/calendars/` 는 작업 A 산출이다. 여기서는 `event_id` 로 **참조만** 한다.
- A 에 없는 선거의 대진을 만들지 말 것.
- `date` 가 `"없음"` / `"불명"` 인 행은 이 큐에 없다. 찾지 말고 다음 번호로.
- UI (`app.js`, `js/**`, `style.css`, `index.html`) 금지.
- 기존 미국 파일 (`usa_elections_ui_ready_*`, `state_drilldown`) 을 고치지 말 것.
- 여론조사·승률·`win_prob` 넣지 말 것.
- `jpn-2026-shugiin-51` 은 PR #325 에서 `complete`. 큐에서 뺐다. 다시 만들지 말 것.

## 한 턴에 만들 것

```
New for anti/public/data/elections_contests_index_v1.json
New for anti/public/data/elections_contests/{event_id}.json
```

`event_id` = 달력 `board_tracked_all_events[].id` 와 **같은 문자열**.
필드명은 `HANDOFF_CURSOR_ELECTION_CONTESTS.md` 2절 그대로. `null` / `""` / 의미 없는 `0` 금지.
추측으로 후보·의석을 채우지 말 것. 모르면 키를 빼거나 `status: "scheduled"` + `candidates: []`.

우선: **가까운 확정 날짜 · 주요국**. 일본 중의원 형식이 이미 굳었으므로, 가까운 총선·대선부터 창이 열리게 한다.

---

## 큐 (30)

| # | event_id | iso3 | 날짜 | 종류 | 상태 |
|---|---|---|---|---|---|
| 1 | `rus-2026-duma` | RUS | 2026-09-20 | 총선 | scheduled |
| 2 | `deu-2026-berlin-ag` | DEU | 2026-09-20 | 지방 | scheduled |
| 3 | `deu-2026-mv-landtag` | DEU | 2026-09-20 | 지방 | scheduled |
| 4 | `rus-2026-single-voting-day-regions` | RUS | 2026-09-20 | 지방 | scheduled |
| 5 | `bra-2026-general-r1` | BRA | 2026-10-04 | 총선 | scheduled |
| 6 | `can-2026-quebec` | CAN | 2026-10-05 | 지방 | scheduled |
| 7 | `fra-2026-senate` | FRA | 2026-09 | 총선 | scheduled |
| 8 | `fra-2026-rn-congres-19` | FRA | 2026-10-24 | 당권 | scheduled |
| 9 | `bra-2026-general-r2` | BRA | 2026-10-25 | 총선 | tentative |
| 10 | `isr-2026-knesset` | ISR | 2026-10-27 | 총선 | scheduled |
| 11 | `zaf-2026-local-government` | ZAF | 2026-11-04 | 지방 | scheduled |
| 12 | `twn-2026-local` | TWN | 2026-11-28 | 지방 | scheduled |
| 13 | `kor-2026-dpk-convention` | KOR | 2026-08-17 | 당권 | ongoing |
| 14 | `deu-2026-st-landtag` | DEU | 2026-09-06 | 지방 | scheduled |
| 15 | `jpn-2026-gov-okinawa` | JPN | 2026-09-13 | 지방 | scheduled |
| 16 | `jpn-2026-fukushima-governor` | JPN | 2026-10-25 | 지방 | scheduled |
| 17 | `jpn-2026-gov-ehime` | JPN | 2026-11-29 | 지방 | scheduled |
| 18 | `jpn-2026-gov-saga` | JPN | 2026-12-20 | 지방 | scheduled |
| 19 | `jpn-2026-gov-miyazaki` | JPN | 2026-12-27 | 지방 | scheduled |
| 20 | `kor-2026-local` | KOR | 2026-06-03 | 지방 | completed |
| 21 | `gbr-2026-scottish-parliament` | GBR | 2026-05-07 | 지방 | completed |
| 22 | `gbr-2026-senedd` | GBR | 2026-05-07 | 지방 | completed |
| 23 | `col-2026-presidential` | COL | 2026-05-31 | 대선 | completed |
| 24 | `col-2026-presidential-r2` | COL | 2026-06-21 | 대선 | completed |
| 25 | `col-2026-congress` | COL | 2026-03-08 | 총선 | completed |
| 26 | `tha-2026-general` | THA | 2026-02-08 | 총선 | completed |
| 27 | `twn-2026-dpp-chair` | TWN | 2026-07-19 | 당권 | completed |
| 28 | `gbr-2026-labour-leadership` | GBR | 2026-07-17 | 당권 | completed |
| 29 | `usa-2026-midterms` | USA | 2026-11-03 | 총선 | scheduled |
| 30 | `usa-2026-governors` | USA | 2026-11-03 | 지방 | scheduled |

미국(#29–30)은 기존 `ui_ready` 화면이 돌아가므로 **새 형식은 뒤로**. 원 출처에서 다시 만들고 레거시 파일은 그대로 둔다. 대조 수치는 PR 본문에.

---

## 붙여넣기용 프롬프트

각 블록을 **그대로 한 턴**에 붙인다. `{event_id}` 만 해당 번호로 바뀐 상태.

### 공통 머리 (모든 프롬프트에 이미 포함됨)

아래 각 항의 본문이 머리+해당 이벤트를 합친 한 덩어리다.

---

### 1. rus-2026-duma (RUS · 2026-09-20 · 총선)

```
너는 작업 B(대진 / 누가 나오는지)만 한다. 작업 A(일정·제도)는 이미 커밋돼 있다. 달력·elections_system_v1.json·config/calendars/ 를 새로 만들지 마라.

한 턴에 이벤트 하나. 이번만 rus-2026-duma.

읽을 것:
- New for anti/scripts/election_watch/HANDOFF_CURSOR_ELECTION_CONTESTS.md
- New for anti/scripts/election_watch/HANDOFF_CURSOR_ELECTION_BRIEF_SCHEMA.md 1절
- New for anti/public/data/elections_calendar_master_v1.json 에서 id=rus-2026-duma
- system_id=rus-duma (elections_system_v1.json)

만들 것:
- New for anti/public/data/elections_contests/rus-2026-duma.json
- 목차 elections_contests_index_v1.json 에 이 event_id 한 줄 (없으면 파일을 만들고, 있으면 이 행만 추가/갱신)

내용: 러시아 제9기 국가두마(2026-09-20). contested_ko는 「국가두마 450석 전원」. 정당·현재 의석·선거구/명부 대진. 출처 필수. 추측 금지. null/빈문자열/의미없는 0 금지. UI 수정 금지. 여론조사·승률 넣지 말 것.
끝나면 파일 경로와 status(partial/complete)만 짧게.
```

### 2. deu-2026-berlin-ag (DEU · 2026-09-20 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: deu-2026-berlin-ag (독일 베를린 주의회, 2026-09-20, 지방). system_id=deu-landtag-berlin. contested_ko 「해당 주 주의회 의석 전원」.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/deu-2026-berlin-ag.json + 목차 갱신.
정당·현재 의석·후보는 출처가 있는 것만. 추측 금지. UI 금지.
```

### 3. deu-2026-mv-landtag (DEU · 2026-09-20 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: deu-2026-mv-landtag (메클렌부르크포어포메른 주의회, 2026-09-20, 지방). system_id=deu-landtag-mv. contested_ko 「해당 주 주의회 의석 전원」.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/deu-2026-mv-landtag.json + 목차 갱신.
베를린(deu-2026-berlin-ag)과 섞지 말 것. 추측 금지. UI 금지.
```

### 4. rus-2026-single-voting-day-regions (RUS · 2026-09-20 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: rus-2026-single-voting-day-regions (러시아 단일투표일 지방, 2026-09-20). 두마(rus-2026-duma)와 다른 이벤트다. 섞지 말 것.
contested_ko 「단일투표일 지방 수장·주의회」. 열이 여러 개면 columns를 나눈다. 전수를 못 채우면 확인된 주지사·주의회만 넣고 status=partial.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/rus-2026-single-voting-day-regions.json + 목차.
추측 금지. UI 금지.
```

### 5. bra-2026-general-r1 (BRA · 2026-10-04 · 총선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: bra-2026-general-r1 (브라질 2026-10-04 1차. 달력 type은 general, 내용은 대통령+연방의회+주지사). system_id=bra-president. contested_ko 「대통령 + 연방의회 + 주지사 (1차)」.
열을 성격별로 나눈다 (대통령 / 하원 / 상원 / 주지사). 결선(bra-2026-general-r2)은 이번 턴에 만들지 말 것.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/bra-2026-general-r1.json + 목차.
1MB 넘으면 열 단위로 districts_path 분리. 추측 금지. UI 금지.
```

### 6. can-2026-quebec (CAN · 2026-10-05 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: can-2026-quebec (퀘벡 주의회 총선, 2026-10-05, 지방). system_id=can-local. contested_ko 「퀘벡 주의회 127석 전원」.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/can-2026-quebec.json + 목차.
연방 총선과 섞지 말 것. 추측 금지. UI 금지.
```

### 7. fra-2026-senate (FRA · 2026-09 · 총선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: fra-2026-senate (프랑스 상원 간선, 날짜는 달력상 2026-09 월 단위). system_id=fra-senate. contested_ko 「상원 간선 (해당 series 改選분)」.
국민직접선거가 아니다. 간선 방식·改選 분·교대 그룹을 출처로 밝히고, 모르는 칸은 키를 빼라.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/fra-2026-senate.json + 목차.
추측 금지. UI 금지.
```

### 8. fra-2026-rn-congres-19 (FRA · 2026-10-24 · 당권)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: fra-2026-rn-congres-19 (국민연합 RN 제19차 전당대회, 2026-10-24, 당권). electorate는 달력 notes/electorate_ko를 따른다.
당대표·집행부 중 무엇을 뽑는지 contested_ko에 한 줄. 후보는 공천/보도 구분을 status로.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/fra-2026-rn-congres-19.json + 목차.
추측 금지. UI 금지.
```

### 9. bra-2026-general-r2 (BRA · 2026-10-25 · 총선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: bra-2026-general-r2 (브라질 대선·주지사 결선, 2026-10-25, tentative). system_id=bra-president.
1차(bra-2026-general-r1)와 다른 파일. 결선이 열리는 자리만 넣고, 1차에서 끝난 의회 총선은 넣지 말 것. 아직 1차 전이면 candidates를 비우고 status=scheduled, notes에 「1차 결과에 따라 결선 여부」.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/bra-2026-general-r2.json + 목차.
추측 금지. UI 금지.
```

### 10. isr-2026-knesset (ISR · 2026-10-27 · 총선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: isr-2026-knesset (이스라엘 제26대 크네세트, 2026-10-27, 총선). isr-2026-candidate-lists(명단 제출 기한)는 만들지 말 것.
전국 명부제이므로 선거구를 지어내지 말고, 정당 명부 열로 둔다. 현재 의석은 크네세트 원문 총계.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/isr-2026-knesset.json + 목차.
추측 금지. UI 금지.
```

### 11. zaf-2026-local-government (ZAF · 2026-11-04 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: zaf-2026-local-government (남아프리카 지방정부선거 LGE, 2026-11-04). system_id=zaf-local.
전 기초자치단체를 한 파일에 다 넣으려 하지 말 것. 확인된 광역/주요 시부터, 1MB면 분리. status=partial 허용.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/zaf-2026-local-government.json + 목차.
추측 금지. UI 금지.
```

### 12. twn-2026-local (TWN · 2026-11-28 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: twn-2026-local (대만 지방공직인원 구합일, 2026-11-28). system_id=twn-local. contested_ko 「지방공직 11,051명 (중선회 2026-08-20 공고)」 — 총원을 더해 만들지 말고 공고 원문을 따른다.
국가명·기관명은 공식 명칭 그대로. 직(직할시장·현시장·의원 등)이 다르면 columns를 나눈다.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/twn-2026-local.json + 목차.
추측 금지. UI 금지.
```

### 13. kor-2026-dpk-convention (KOR · 2026-08-17 · 당권)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: kor-2026-dpk-convention (더불어민주당 전당대회 당대표·최고위원, 2026-08-17, ongoing).
순회경선 kor-2026-dpk-convention-tour 는 이번 파일에 합치지 말 것(별 이벤트). 후보는 공천 확정분만 nominated. 권리당원·대의원 비율은 달력 rules를 옮기지 말고 대진 필드에 맞게 electorate/contested만.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/kor-2026-dpk-convention.json + 목차.
추측 금지. UI 금지.
```

### 14. deu-2026-st-landtag (DEU · 2026-09-06 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: deu-2026-st-landtag (작센안할트 주의회, 2026-09-06). system_id=deu-landtag-st.
날짜가 지났으면 당선(elected/result)을 출처로 채우고 districts status=completed. 예비 의석이면 note_ko에 예비라고 밝힌다.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/deu-2026-st-landtag.json + 목차.
추측 금지. UI 금지.
```

### 15. jpn-2026-gov-okinawa (JPN · 2026-09-13 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: jpn-2026-gov-okinawa (오키나와현 지사, 2026-09-13). system_id=jpn-prefecture-governor. contested_ko 「도도부현 지사 1인」.
다른 현 지사·중의원과 섞지 말 것. 후보는 공시 명부.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/jpn-2026-gov-okinawa.json + 목차.
추측 금지. UI 금지.
```

### 16. jpn-2026-fukushima-governor (JPN · 2026-10-25 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: jpn-2026-fukushima-governor (후쿠시마현 지사, 2026-10-25). system_id=jpn-prefecture-governor.
오키나와·에히메와 파일을 합치지 말 것.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/jpn-2026-fukushima-governor.json + 목차.
추측 금지. UI 금지.
```

### 17. jpn-2026-gov-ehime (JPN · 2026-11-29 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: jpn-2026-gov-ehime (에히메현 지사, 2026-11-29). system_id=jpn-prefecture-governor.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/jpn-2026-gov-ehime.json + 목차.
추측 금지. UI 금지.
```

### 18. jpn-2026-gov-saga (JPN · 2026-12-20 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: jpn-2026-gov-saga (사가현 지사, 2026-12-20). system_id=jpn-prefecture-governor.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/jpn-2026-gov-saga.json + 목차.
추측 금지. UI 금지.
```

### 19. jpn-2026-gov-miyazaki (JPN · 2026-12-27 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: jpn-2026-gov-miyazaki (미야자키현 지사, 2026-12-27). system_id=jpn-prefecture-governor.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/jpn-2026-gov-miyazaki.json + 목차.
추측 금지. UI 금지.
```

### 20. kor-2026-local (KOR · 2026-06-03 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: kor-2026-local (제9회 전국동시지방선거, 2026-06-03, completed). system_id=kor-local.
contested_ko 「광역단체장 17곳 + 기초단체장 226곳 등 동시」. 끝난 선거라 elected/result 필수. 광역단체장과 광역의원은 열을 나눈다. 기초 전수가 크면 광역부터 complete, 기초는 partial+분리 파일.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md (끝난 선거 필드) + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/kor-2026-local.json + 목차.
중앙선관위 원문. 추측 금지. UI 금지.
```

### 21. gbr-2026-scottish-parliament (GBR · 2026-05-07 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: gbr-2026-scottish-parliament (스코틀랜드 의회, 2026-05-07, completed). system_id=gbr-holyrood.
같은 날 세네드·잉글랜드 지방과 파일을 합치지 말 것. 당선 결과 포함.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/gbr-2026-scottish-parliament.json + 목차.
추측 금지. UI 금지.
```

### 22. gbr-2026-senedd (GBR · 2026-05-07 · 지방)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: gbr-2026-senedd (웨일스 세네드, 2026-05-07, completed). system_id=gbr-senedd.
스코틀랜드 의회 파일과 합치지 말 것.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/gbr-2026-senedd.json + 목차.
추측 금지. UI 금지.
```

### 23. col-2026-presidential (COL · 2026-05-31 · 대선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: col-2026-presidential (콜롬비아 대선 1차, 2026-05-31, completed). system_id=col-president.
결선(col-2026-presidential-r2)은 다음 턴. 1차 후보·득표·결선 진출만.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/col-2026-presidential.json + 목차.
추측 금지. UI 금지.
```

### 24. col-2026-presidential-r2 (COL · 2026-06-21 · 대선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: col-2026-presidential-r2 (콜롬비아 대선 결선, 2026-06-21, completed). system_id=col-president.
1차 파일을 덮어쓰지 말 것. 결선 두 후보와 결과만.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/col-2026-presidential-r2.json + 목차.
추측 금지. UI 금지.
```

### 25. col-2026-congress (COL · 2026-03-08 · 총선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: col-2026-congress (콜롬비아 상원·하원 총선, 2026-03-08, completed). system_id=col-chamber.
상원/하원은 columns 두 열. 대선 파일과 합치지 말 것.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/col-2026-congress.json + 목차.
추측 금지. UI 금지.
```

### 26. tha-2026-general (THA · 2026-02-08 · 총선)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: tha-2026-general (태국 하원 총선, 2026-02-08, completed). system_id=tha-house. contested_ko 「하원 500석 전원」.
끝난 선거라 elected/result. 소선거구·비례가 있으면 열을 나누고, 공시전 의석을 소·비로 지어내지 말 것(일본 중의원 형식 손본 곳과 같음).

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/tha-2026-general.json + 목차.
추측 금지. UI 금지.
```

### 27. twn-2026-dpp-chair (TWN · 2026-07-19 · 당권)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: twn-2026-dpp-chair (민진당 제22차 전당대회, 2026-07-19, completed).
달력 contested_ko: 「중앙집행위원 30인 → 중상무위원 10인 (당주석 직선 아님)」. 당주석 직선으로 쓰지 말 것.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/twn-2026-dpp-chair.json + 목차.
추측 금지. UI 금지.
```

### 28. gbr-2026-labour-leadership (GBR · 2026-07-17 · 당권)

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: gbr-2026-labour-leadership (노동당 당대표 특별당대회, 2026-07-17, completed).
gbr-2026-pm-succession(총리 교체)과 다른 이벤트. 당대표 경선만. 후보자·투표 방식·결과.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/gbr-2026-labour-leadership.json + 목차.
추측 금지. UI 금지.
```

### 29. usa-2026-midterms (USA · 2026-11-03 · 총선) — 뒤로

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: usa-2026-midterms (미국 중간선거 상·하원, 2026-11-03). system_id=usa-house.
새 파일 public/data/elections_contests/usa-2026-midterms.json 만 만든다.
기존 usa_elections_ui_ready_* 와 state_drilldown 은 읽기만 하고 수정하지 마라. 값은 원 출처에서 다시 만든다(레거시 JSON을 형식만 바꿔 복사 금지).
하원 435 + 상원 Class 1. 1MB면 열 분리. PR 본문에 레거시 대조(하원 자리 수·상원 자리 수·현재 의석).

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md 0절 미국 순서 + BRIEF_SCHEMA 1절.
UI 금지. 여론조사 필드 금지.
```

### 30. usa-2026-governors (USA · 2026-11-03 · 지방) — 뒤로

```
너는 작업 B(대진)만 한다. 일정·제도를 다시 만들지 마라. 한 턴에 이벤트 하나.

이번: usa-2026-governors (주지사 36개주+자치령, 2026-11-03). system_id=usa-governor.
중간선거 상·하원 파일과 합치지 말 것. 레거시 ui_ready/state_drilldown 수정 금지. 원 출처에서 다시.

규격: HANDOFF_CURSOR_ELECTION_CONTESTS.md + BRIEF_SCHEMA 1절.
산출: public/data/elections_contests/usa-2026-governors.json + 목차.
추측 금지. UI 금지.
```
