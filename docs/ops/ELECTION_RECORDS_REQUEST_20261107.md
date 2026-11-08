# 국가별 선거 기록 자료 요청 (2026-11-07, Claude)

국가 화면 오른쪽 대시보드의 **'선거' 블록**에 들어갈 자료이며, **지금 추적하는 54개국 전체에 공통으로 적용하는 요구사항**입니다. 쟁점만 10개국에 추가로 받습니다. 이 블록은 아래 순서로 읽힙니다.

1. 행정수반
2. 의회
3. 지방선거
4. 쟁점 (10개국만)

각 직위마다 보여 주는 항목은 다음과 같습니다.

- 직전 선거: 날짜, 투표율, 후보·정당별 득표.
- 결선이 있었으면 1차와 결선 표를 따로 둡니다.
- 임기: 시작일과 만료일.
- 다음 선거: 날짜.

화면과 변환 코드는 이미 있습니다. 이 요청은 **자료만** 받습니다.

- 자료를 아래 계약대로 `config/election_records/<iso3>.json`에 넣으면, 빌더가 공개 파일을 다시 만들고 화면이 그대로 읽습니다.
- 지금 공개 파일(`public/data/election_records/*.json`)은 기존 선거 일정판·대진 파일에서 자동으로 옮긴 것입니다.
  - 54개국 가운데 20개국만 기록이 있습니다.
  - 그 20개국도 대부분 득표 표가 없습니다.

## 1. 파일 위치와 범위

```
New for anti/scripts/election_watch/config/election_records/<iso3>.json   ← 조사 결과 (이 요청)
New for anti/scripts/election_watch/build_election_records.py              ← 빌더 (Claude 소유, 수정 금지)
New for anti/public/data/election_records/<ISO3>.json                      ← 생성물 (손으로 고치지 말 것)
```

- **PR 단위:** 한 나라 = 한 PR입니다. 여러 나라를 한 PR에 섞지 않습니다.
- **PR에 넣을 파일:** 입력 파일 하나와, 빌더를 돌려 바뀐 그 나라 공개 파일입니다.
  ```bash
  cd "New for anti/scripts/election_watch"
  python3 build_election_records.py && python3 build_election_records.py --check
  ```
- **손대지 않을 것:** 화면 코드(`js/**`), 다른 나라 파일, `elections_board_v1.json`.

## 2. 계약 (`election_records_input_v1`)

```jsonc
{
  "schema": "election_records_input_v1",
  "country": "KOR",                       // 파일 이름의 iso3 대문자와 같아야 함
  "as_of": "2026-11-07",                  // 조사 기준일
  "offices": [
    {
      "key": "executive",                 // executive | legislature | local
      "system_id": "kor-president",       // elections_system_v1.json 의 id. 없으면 새 id(iso3-소문자-직위)
      "title_ko": "대한민국 대통령 선거",
      "elected_how": "direct",            // direct | by_legislature | indirect
      "term_years": 5,
      "incumbent": {
        "name": "…", "party": "…",
        "since": "YYYY-MM-DD",            // 취임일
        "term_end": "YYYY-MM-DD",         // 법정 임기 만료일
        "sources": ["https://…"]
      },
      "records": [                         // 최근 것이 앞. 직전 선거 + 그 이전 1회(가능하면 2회)
        {
          "election_id": "kor-2025-president",   // iso3-연도-직위[-r1|-r2]
          "date": "YYYY-MM-DD",            // 결선이 있으면 결선일
          "first_round_date": null,        // 결선이 있을 때만 1차 날짜
          "label_ko": "제21대 대통령 선거",
          "status": "completed",           // completed | certified
          "term_start": "YYYY-MM-DD",
          "term_end": "YYYY-MM-DD",
          "electorate": 0,                 // 선거인 수 (정수)
          "turnout_pct": 0.0,              // 투표율 % (소수 둘째 자리까지, 공식 발표값 그대로)
          "winner_ko": "이름 · 정당",
          "candidates": [                  // 단일 직위(대통령·지사·시장) 선거. 결선 없으면 여기
            {"name": "…", "party": "…", "votes": 0, "vote_pct": 0.0, "elected": true, "incumbent": false}
          ],
          "rounds": [                      // 결선이 있으면 candidates 대신 이것
            {"round": 1, "date": "YYYY-MM-DD", "turnout_pct": 0.0, "candidates": [ … ]},
            {"round": 2, "date": "YYYY-MM-DD", "turnout_pct": 0.0, "candidates": [ … ]}
          ],
          "seats_total": 300,              // 의회 선거: 정수
          "seats": [                       // 의회 선거: 정당별 의석·득표
            {"party": "…", "party_ko": "…", "seats": 0, "vote_pct": 0.0, "seats_change": 0}
          ],
          "summary_ko": "한두 문장 요약 (선택)",
          "sources": ["https://공식 집계 페이지"],
          "verification": "official"       // official | official_partial | media_two
        }
      ],
      "next": {"date": "YYYY-MM-DD", "date_status": "scheduled", "label_ko": "…", "source": "https://…"}
    }
  ],
  "issues": [ … ]                          // 3-4절. 쟁점 ○ 10개국만
}
```

### 2-1. 칸별 규칙

| 칸 | 규칙 |
|---|---|
| `vote_pct` | 공식 발표값을 그대로 씁니다. 직접 계산하지 않습니다. 발표값이 없으면 `null`이고, 그러면 빌더가 표의 득표 합으로 계산해 '계산값'이라고 표시합니다 |
| `turnout_pct` | 공식 발표값을 씁니다. 결선 투표율은 `rounds[].turnout_pct`에 따로 둡니다 |
| `candidates` | 득표 순서로 적습니다. 1% 미만 군소 후보는 생략할 수 있지만, 그때는 `summary_ko`에 '기타 N명 합 X표'를 적습니다 |
| `rounds` | 1차는 **전원**(1% 미만 생략 규칙 동일), 결선은 결선 후보 2명입니다. 1차에서 끝났으면 `rounds`를 쓰지 않고 `candidates`만 씁니다 |
| `seats` | 의석 1석 이상인 정당 전부와, 의석은 없지만 득표율 1% 이상인 정당(`seats: 0`)을 적습니다. 혼합형은 `seats_district`·`seats_list` 칸에 나눠 적습니다(2-3절) |
| 양원제 | 상원과 하원을 각각 별도의 `office`로 둡니다(`system_id`가 다름). 일부만 바꾸는 상원 선거는 `seats`에 改選분만 적고, `summary_ko`에 전체 의석 구성을 따로 적습니다 |
| 의원내각제 행정수반 | `key: executive`, `elected_how: by_legislature`로 두고 `records`는 비웁니다. 대신 `incumbent`(총리 이름, 취임일)과, 어느 의회 선거 결과로 정해졌는지(`selected_by_system_id`)를 적습니다 |
| 보궐선거 | `by_election: true`를 붙여 같은 직위의 `records`에 넣습니다. 화면은 이를 '이전·보궐'로 접습니다 |
| 다음 선거 | 법정 날짜나 공고 날짜가 있을 때만 `date`를 씁니다. 없으면 `date: null`, `label_ko: "법정 기한 YYYY-MM"`으로 둡니다. 추정 날짜를 만들지 않습니다 |
| 날짜 | `YYYY-MM-DD` 형식만 씁니다. 모르면 `null`로 두고 `note_ko`에 이유를 적습니다 |
| 출처 | 모든 `records[]`·`incumbent`·`next`에 `sources`를 붙입니다. http(s) URL만 씁니다 |

### 2-3. 보강 규칙 (2026-11-08, 일본 #922·한국 1차분 검토 반영)
1·2차 제출분을 보니 모든 나라에 공통으로 생길 문제가 아래 12가지였습니다. 이 규칙은 이후 모든 나라에 적용합니다. 빌더와 화면은 이미 이 칸들을 읽습니다.

| # | 문제 (실제 사례) | 규칙 |
|---|---|---|
| 1 | 현직 이름이 원문 표기만 있음 (高市 早苗) | 사람 이름은 `name_ko`와 `name`(현지 원문)을 **둘 다** 적습니다. 현직·후보·당선자 모두 해당합니다 |
| 2 | 혼합형의 지역구·비례 의석이 `summary_ko` 문장에만 있음 | `seats[]`에 `seats_district`와 `seats_list`를 나눠 적습니다. `vote_pct`는 정당(비례) 득표율이고, 지역구 득표율이 있으면 `vote_pct_district`에 따로 적습니다 |
| 3 | 소선거구·비례 투표율이 다른데 하나만 칸에 들어감 (56.26 / 56.25) | `turnout_pct`에는 대표값(지역구 또는 대통령 1차)을 적고, 나머지는 `tiers: [{"tier": "district", "label_ko": "소선거구", "turnout_pct": …}, {"tier": "list", "label_ko": "비례", …}]`에 둡니다 |
| 4 | 의석 0인 정당의 득표가 문장에 묻힘 | 득표율 1% 이상이면 `seats: 0` 행으로 표에 넣습니다 |
| 5 | 선거 뒤 회파 이동·결원이 `note_ko`에 섞임 | 선거 결과(`records`)와 **지금 구성**을 나눕니다. 지금 구성은 `office.current_composition = {"as_of", "by_party": [{"party", "party_ko", "seats"}], "vacancies", "sources"}`에 적습니다 |
| 6 | 의원내각제 총리의 '다음 선거'를 '다음 지명일 없음'으로 적음 | 총리 직위의 `next`는 비웁니다. 화면이 근거 의회의 다음 선거를 대신 보여 줍니다. 대신 연정 구성 `government = {"parties": [...], "seats", "majority_line", "formed", "sources"}`를 적습니다. 지명 투표 수는 선택 칸 `investiture`입니다 |
| 7 | 현직 정당이 '원문에 없어서' null | 같은 기관의 다른 공식 페이지(의원 명부, 정당 공식 당직 페이지)로 채우고 `party_source`에 출처를 적습니다 |
| 8 | 같은 선거가 일정판 id와 조사 id로 두 줄 생김 (한국 2024 총선) | 빌더가 같은 날짜의 정기 선거는 하나로 합칩니다. 그래도 가능하면 일정판의 `election_id`를 그대로 씁니다 (`elections_board_v1.json`의 events[].id) |
| 9 | 직전 2회 중 한 회만 표가 있음 (한국 2022 대선: 투표율만) | 직전 2회는 **같은 형식**으로 받습니다. 2회 모두 후보별 득표 또는 정당별 의석이 있어야 비교됩니다 |
| 10 | '열지 않았다'(시도하지 않음)와 '열리지 않았다'(차단)가 구분되지 않음 | 직위마다 `coverage`(`complete` / `partial` / `not_collected`)와 한 줄 사유 `coverage_note_ko`를 적습니다. 차단된 URL은 `unreachable_sources: [{"url", "reason": "blocked|timeout|not_found|format"}]`로 남깁니다. **Claude가 GitHub 수집 워크플로(source_fetch)로 대신 받아 줍니다**. 시도하지 않은 칸을 '못 열었다'로 적지 않습니다 |
| 11 | 조사 과정 설명이 화면 요약 자리를 차지함 | `summary_ko`는 화면에 그대로 나가므로 두 문장 이내로 씁니다. 조사 과정·원문 대조 메모는 `note_ko`에 적으며, 화면에서는 '조사 메모'로 접혀 보입니다 |
| 12 | 현 단위 보궐(후쿠시마현의회)이 별도 지방 직위로 뜸 | 지방 직위는 전국 단위로만 만듭니다(2-2절). 개별 지역의 보궐은 해당 지방 직위 아래 `by_election: true` 기록으로 넣습니다 |

추가로 의회 직위에는 법정 임기 만료일 `term_end`와 `dissolution_possible`(해산 가능 여부)을 적습니다. 해산이 가능한 의회의 '다음 선거'는 날짜가 아니라 법정 기한입니다.

### 2-2. 지방선거의 범위
지방선거는 **전국 단위 집계만** 받습니다. 지역별 수장은 지역 수장 명단(`region_leaders`, `POLITICS_DATA_GAPS_20261104.md`)으로 따로 받습니다.

| 지방 유형 | 받는 것 |
|---|---|
| 동시 지방선거(한국·일본 통일지방선거·브라질 주지사·멕시코 주지사) | 날짜, 투표율, 정당별 당선 수(광역단체장 기준) |
| 주별 개별 선거(독일 주의회·미국 주지사·인도 주의회) | 최근 2년 안에 치러진 선거만, 주마다 `office` 하나(`system_id`: `deu-landtag-by` 등). 정당별 의석을 적습니다 |
| 수도·대도시 단체장(서울·도쿄·런던·파리·마드리드) | 단일 직위 선거처럼 `candidates`를 적습니다 |

## 3. 모든 조사 대상 국가에 공통으로 받는 자료

이 절이 요청의 본체입니다. **지금 추적하는 54개국 전부**가 대상입니다.
나라마다 아래 '공통 필수'를 채우고, 정치 체제(3-2)에 따라 받을 직위를 고릅니다. 3-3 표가 나라별 체제 분류와 현재 보유량입니다.

### 3-1. 공통 필수 (직위마다)
| 항목 | 받는 것 | 몇 회분 |
|---|---|---|
| 직위 정의 | 직위 이름, 선출 방식(직선·의회 선출·간선), 임기, 결선 규칙, 정수(의회) | — |
| 현직 | 이름, 정당, 취임일, 법정 임기 만료일 | 현재 |
| 직전 정기 선거 | 날짜(결선이면 1차·결선 둘 다), 선거인 수, 투표율, 당선자 | 최근 **2회** |
| 결과 표 | 단일 직위는 후보별 득표·득표율(결선이면 회차별 표 따로), 의회는 정당별 의석·득표율·의석 증감 | 최근 2회 |
| 보궐·조기 선거 | 날짜, 결과 한 줄 (`by_election: true`) | 직전 정기 선거 이후 전부 |
| 다음 선거 | 법정 또는 공고된 날짜. 없으면 `null`과 법정 기한 | 1회 |
| 출처 | 각 기록마다 공식 집계 URL | 기록마다 |

### 3-2. 정치 체제별로 받을 직위
| 분류 | 행정수반 | 의회 | 지방 | 비고 |
|---|---|---|---|---|
| A 대통령제 | 대통령 선거 (결선국은 1차·결선) | 하원(+상원) | 2-2절 기준 | 부통령 동반 선거면 `summary_ko`에 러닝메이트 |
| B 의원내각제 | 총리: `by_legislature`, 현직과 근거 선거만 | 하원 정당별 의석 (+상원 선출 방식) | 2-2절 기준 | 군주·의례적 대통령은 받지 않음. 의회가 뽑는 대통령(DEU·ITA·ISR 등)은 `indirect`로 한 줄 |
| B′ 합의제(CHE) | 연방평의회: 의회 선출 7인 명단 | 국민의회·전주의회 | 칸톤 선거는 생략 | 국민투표는 범위 밖 |
| C 이원집정부제 | 대통령 선거 + 총리 현직(`by_legislature`) | 하원(+상원) | 2-2절 기준 | 대통령과 총리를 각각 office로 |
| D 비경쟁 선거(RUS·VNM·IRN·AZE·EGY) | 선거가 있으면 A와 같이 받음 | 같음 | 같음 | `note_ko`에 경쟁 제한 사실(후보 자격 심사·등록 거부 등)만 적고, 평가하지 않음 |
| E 군주정+의회(MAR·KWT) | 군주는 받지 않음, 총리 현직만 | 의회 선거 | 생략 | |
| F 경쟁 선거 없음(CHN·SAU·QAT·ARE) | `elected_how: "none"` | 간선·지명 기구가 있으면 구성 방식만 | 생략 | 기록 없이 `note_ko`만 |
| G 분쟁국(LBY·YEM) | 마지막 전국 선거(있었다면) 1회 | 같음 | 생략 | 선거 연기 사유와 날짜를 `note_ko`에 (권력 구조는 분쟁국 화면이 따로 다룸) |

### 3-3. 전체 54개국 (분류 · 현재 보유 · 쟁점 · 1순위 공식 출처)
현재 보유량은 기존 일정판에서 자동으로 옮긴 기록 수입니다. '득표·의석 표'가 0이면 날짜와 한 줄 결과만 있다는 뜻입니다.

| ISO3 | 나라 | 분류 | 현재 기록 | 쟁점 | 1순위 공식 출처 |
|---|---|---|---|---|---|
| CHN | 중국 | F 경쟁 선거 없음 | 없음 |  | — |
| JPN | 일본 | B 의원내각제 | 13건 (득표·의석 표 3) | ○ | 총무성 選挙関連資料, 都道府県 選管 |
| RUS | 러시아 | D 비경쟁 선거 | 3건 (득표·의석 표 1) |  | 중앙선관위 cikrf.ru |
| USA | 미국 | A 대통령제 | 8건 (득표·의석 표 3) | ○ | FEC, 하원 Clerk, 각 주 국무장관 |
| ARG | 아르헨티나 | A 대통령제 | 없음 |  | DINE·선거관리 resultados.gob.ar |
| AUS | 호주 | B 의원내각제 | 1건 (득표·의석 표 0) |  | AEC |
| BRA | 브라질 | A 대통령제 | 5건 (득표·의석 표 3) | ○ | TSE resultados.tse.jus.br |
| CAN | 캐나다 | B 의원내각제 | 없음 |  | Elections Canada |
| CHL | 칠레 | A 대통령제 | 없음 |  | SERVEL |
| COL | 콜롬비아 | A 대통령제 | 2건 (득표·의석 표 1) |  | Registraduría Nacional |
| DEU | 독일 | B 의원내각제 | 10건 (득표·의석 표 5) | ○ | Bundeswahlleiterin, 주 Landeswahlleiter |
| FRA | 프랑스 | C 이원집정부제 | 2건 (득표·의석 표 1) | ○ | 내무부 archives-resultats-elections, 헌법위원회 |
| GBR | 영국 | B 의원내각제 | 6건 (득표·의석 표 2) | ○ | House of Commons Library, Electoral Commission |
| IDN | 인도네시아 | A 대통령제 | 없음 |  | KPU |
| IND | 인도 | B 의원내각제 | 2건 (득표·의석 표 0) | ○ | 인도 선관위 results.eci.gov.in |
| IRN | 이란 | D 비경쟁 선거 | 없음 |  | 내무부 선거본부 |
| ISR | 이스라엘 | B 의원내각제 | 없음 |  | 중앙선관위 votes*.bechirot.gov.il |
| ITA | 이탈리아 | B 의원내각제 | 없음 |  | 내무부 Eligendo |
| KOR | 한국 | A 대통령제 | 4건 (득표·의석 표 2) | ○ | 중앙선관위 info.nec.go.kr |
| MEX | 멕시코 | A 대통령제 | 없음 |  | INE |
| MYS | 말레이시아 | B 의원내각제 | 1건 (득표·의석 표 0) |  | 선관위 SPR |
| NGA | 나이지리아 | A 대통령제 | 없음 |  | INEC |
| PHL | 필리핀 | A 대통령제 | 1건 (득표·의석 표 0) |  | COMELEC |
| POL | 폴란드 | C 이원집정부제 | 없음 |  | PKW |
| SAU | 사우디아라비아 | F 경쟁 선거 없음 | 없음 |  | — |
| THA | 태국 | B 의원내각제 | 1건 (득표·의석 표 0) |  | 선관위 ect.go.th |
| TUR | 튀르키예 | A 대통령제 | 없음 |  | YSK |
| TWN | 대만 | A 대통령제 | 없음 | ○ | 중앙선거위원회 db.cec.gov.tw |
| VNM | 베트남 | D 비경쟁 선거 | 1건 (득표·의석 표 0) |  | 국회 선거위원회 공고 |
| ZAF | 남아프리카공화국 | B 의원내각제 | 없음 |  | IEC |
| ARE | 아랍에미리트 | F 경쟁 선거 없음 | 없음 |  | 국가선거위원회(FNC) |
| ARM | 아르메니아 | B 의원내각제 | 없음 |  | CEC Armenia |
| AZE | 아제르바이잔 | D 비경쟁 선거 | 없음 |  | CEC Azerbaijan |
| BIH | 보스니아 헤르체고비나 | A 대통령제 | 없음 |  | CIK BiH |
| CHE | 스위스 | B′ 합의제 | 없음 |  | 연방통계청 BFS |
| CPV | 카보베르데 | A 대통령제 | 1건 (득표·의석 표 1) |  | CNE |
| DZA | 알제리 | A 대통령제 | 1건 (득표·의석 표 0) |  | ANIE |
| EGY | 이집트 | D 비경쟁 선거 | 없음 |  | 국가선거청 NEA |
| ESP | 스페인 | B 의원내각제 | 없음 | ○ | 내무부 infoelectoral.interior.gob.es |
| GEO | 조지아 | B 의원내각제 | 없음 |  | CEC Georgia |
| GRC | 그리스 | B 의원내각제 | 없음 |  | 내무부 ekloges.ypes.gr |
| HTI | 아이티 | A 대통령제 | 없음 |  | CEP |
| HUN | 헝가리 | B 의원내각제 | 1건 (득표·의석 표 0) |  | NVI valasztas.hu |
| IRQ | 이라크 | B 의원내각제 | 없음 |  | IHEC |
| KWT | 쿠웨이트 | E 군주정+의회 | 없음 |  | 법무부·정보부 공고 |
| LBN | 레바논 | B 의원내각제 | 없음 |  | 내무부 |
| LBY | 리비아 | G 분쟁국 | 없음 |  | HNEC |
| MAR | 모로코 | E 군주정+의회 | 없음 |  | 내무부 |
| NZL | 뉴질랜드 | B 의원내각제 | 1건 (득표·의석 표 1) |  | Electoral Commission |
| PAN | 파나마 | A 대통령제 | 없음 |  | Tribunal Electoral |
| PRT | 포르투갈 | C 이원집정부제 | 1건 (득표·의석 표 1) |  | SGMAI·CNE |
| PSE | 팔레스타인 | A 대통령제 | 없음 |  | CEC Palestine |
| QAT | 카타르 | F 경쟁 선거 없음 | 없음 |  | 내무부(슈라위원회 선거) |
| YEM | 예멘 | G 분쟁국 | 없음 |  | — |

- **작업 순서:** 표 순서(우선순위 등급 순)대로 진행합니다. 한 나라에서 막혀도 다음 나라로 넘어갑니다.
- **기존 자료 먼저:** 다른 형식으로 이미 수집한 자료(`config/extracted/*`, 국가별 personnel 등)가 있으면 새로 조사하기 전에 이 계약으로 옮깁니다. 이때 원래 출처와 수집일은 유지합니다.

### 3-4. 쟁점 (`issues`, 쟁점 ○ 표시 10개국)
대통령선거급 선거(내각제는 총선)의 **직전 선거와 다음 선거**에 대해 각 3~5개를 받습니다.

```jsonc
"issues": [
  {
    "election_id": "kor-2025-president",     // 또는 다음 선거 id
    "title_ko": "부동산·주거",
    "summary_ko": "두세 문장. 무엇이 왜 쟁점이었는가.",
    "positions": [
      {"actor_ko": "후보·정당", "stance_ko": "공약 한 줄", "source": "https://공약집·정당 공식"}
    ],
    "salience": {"kind": "poll", "value_ko": "갤럽 '가장 중요한 문제' 1위 31%", "source": "https://…"},
    "sources": ["https://…"],
    "verification": "official"                // official(선관위 공약집) | party_official(정당·후보 공식) | media_two
  }
]
```

- **쟁점은 선거 기록과 따로 냅니다.** 쟁점 때문에 선거 기록 PR을 미루지 않습니다.
- **공약(positions) 출처 순서:** 아래 순서로 내려가며, 위의 출처를 열 수 없으면 다음 것을 씁니다. 어느 단계를 썼는지는 `verification`으로 표시합니다.
  1. 선관위 공약집 (PDF)
  2. 정당·후보 공식 웹페이지 (공약 페이지, 보도자료)
  3. 공영방송이나 통신사의 '후보별 공약 비교' 기사 2곳 → `verification: "media_two"`
- **PDF나 원문을 열 수 없을 때:** 그 이유 때문에 쟁점을 통째로 비우지 않습니다. 2·3단계로 채우고, 열지 못한 원문 URL과 이유는 `note_ko`에 남깁니다.
- **쟁점 순위(salience)는 선택 칸입니다.** 여론조사 원문을 열 수 없으면 `salience`만 빼고 나머지 쟁점 칸은 냅니다.
- **표현:** 평가 문구('유리했다', '실패했다')를 쓰지 않고, 무엇이 쟁점이었고 누가 무엇을 약속했는지만 적습니다.

## 4. 검수 체크리스트 (PR 본문에 그대로 붙이기)
- [ ] `country`가 파일 이름과 같고, `schema`는 `election_records_input_v1`입니다
- [ ] 모든 record에 `sources`가 있고, 모두 공식 집계 페이지입니다(언론은 `verification`으로 구분)
- [ ] 결선 선거는 `rounds`가 두 개이고, 각 회차 투표율이 따로 있습니다
- [ ] `vote_pct`와 `turnout_pct`는 발표값 그대로입니다(반올림하지 않음)
- [ ] 후보 득표 합이 유효표와 맞는지 확인했고, 다르면 `summary_ko`에 차이를 적었습니다
- [ ] `next.date`는 법정·공고 날짜이고, 없으면 `null`입니다
- [ ] 사람 이름이 `name_ko`와 원문 `name` 둘 다 있습니다
- [ ] 혼합형은 지역·비례 의석과 투표율이 칸으로 나뉘어 있습니다(문장에만 있지 않음)
- [ ] 직위마다 `coverage`가 있고, 막힌 URL은 `unreachable_sources`에 있습니다
- [ ] 직전 2회가 같은 형식(후보 득표 또는 정당 의석)입니다
- [ ] `python3 build_election_records.py --check`를 통과합니다
- [ ] 다른 나라 파일·화면 코드는 바꾸지 않았습니다

## 5. Cursor에 붙여 넣을 지시문

> ⚠️ 2026-11-07 수정. 처음 지시문은 한국 한 곳만 적어서 Cursor가 한국만 하고 멈췄습니다.
> 이 요청은 **54개국 전체에 대한 공통 요구사항**입니다. 아래 지시문으로 전 국가를 이어서 진행합니다.

### 5-1. 선거 기록 (54개국 전체, 멈추지 말고 끝까지)
> `docs/ops/ELECTION_RECORDS_REQUEST_20261107.md` 3절의 공통 요구사항대로 3-3 표의 54개국 선거 기록을 **표 순서대로 모두** 만들어줘. KOR은 이미 했으니 보강만 하면 된다.
>
> 나라마다 할 일:
> 1. 기존 자료가 있는지 확인하고, 있으면 먼저 이 계약으로 옮긴다.
> 2. 3-2 분류에 맞는 직위를 3-1 공통 필수 항목대로 채운다.
> 3. `config/election_records/<iso3>.json`을 쓰고 빌더(`--check` 포함)를 돌린다.
> 4. 브랜치 `cursor/<iso3>-election-records-<날짜>`로 PR을 낸다.
> 5. **곧바로 다음 나라로 넘어간다.**
>
> 막혔을 때:
> - 못 찾은 칸은 `null`로 두고 `note_ko`에 이유를 적는다. 그 때문에 멈추지 않는다.
> - F(경쟁 선거 없음)·G(분쟁국)는 `note_ko`만 채운 짧은 파일로 끝낸다.
>
> 지킬 것:
> - 득표와 투표율은 공식 집계만 쓴다.
> - 화면 코드는 건드리지 않는다.
>
> 10개국을 끝낼 때마다 '나라 / 채운 직위 / 못 채운 칸과 이유' 표로 중간 보고한다.

### 5-2. 쟁점 (쟁점 ○ 10개국, 선거 기록과 별도 PR)
> 3-4절대로 쟁점 ○ 표시된 10개국의 쟁점을 나라당 3~5개 만들어 `issues`에 넣어줘.
> - 공약 출처는 '선관위 공약집 → 정당·후보 공식 페이지 → 공영방송·통신사 공약 비교 기사 2곳' 순으로 쓴다.
> - PDF를 못 열면 다음 단계로 내려가고, 열지 못한 URL은 `note_ko`에 남긴다.
> - 여론조사 순위(salience)는 원문이 있을 때만 넣는다.
> - 나라당 PR 하나로, 10개국을 끝까지 진행한다.
