# 국가별 선거 기록 자료 요청 (2026-11-07, Claude)

국가 화면 오른쪽 대시보드의 **'선거' 블록**에 들어갈 자료입니다. 이 블록은 아래 순서로 읽힙니다.

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
  "issues": [ … ]                          // 3-5절. 10개국만
}
```

### 2-1. 칸별 규칙

| 칸 | 규칙 |
|---|---|
| `vote_pct` | 공식 발표값을 그대로 씁니다. 직접 계산하지 않습니다. 발표값이 없으면 `null`이고, 그러면 빌더가 표의 득표 합으로 계산해 '계산값'이라고 표시합니다 |
| `turnout_pct` | 공식 발표값을 씁니다. 결선 투표율은 `rounds[].turnout_pct`에 따로 둡니다 |
| `candidates` | 득표 순서로 적습니다. 1% 미만 군소 후보는 생략할 수 있지만, 그때는 `summary_ko`에 '기타 N명 합 X표'를 적습니다 |
| `rounds` | 1차는 **전원**(1% 미만 생략 규칙 동일), 결선은 결선 후보 2명입니다. 1차에서 끝났으면 `rounds`를 쓰지 않고 `candidates`만 씁니다 |
| `seats` | 의석 1석 이상인 정당 전부를 적습니다. 비례 득표율은 공식 값이 있을 때만 적습니다. 혼합형은 `summary_ko`에 '지역구 X · 비례 Y'로 적습니다 |
| 양원제 | 상원과 하원을 각각 별도의 `office`로 둡니다(`system_id`가 다름). 일부만 바꾸는 상원 선거는 `seats`에 改選분만 적고, `summary_ko`에 전체 의석 구성을 따로 적습니다 |
| 의원내각제 행정수반 | `key: executive`, `elected_how: by_legislature`로 두고 `records`는 비웁니다. 대신 `incumbent`(총리 이름, 취임일)과, 어느 의회 선거 결과로 정해졌는지(`selected_by_system_id`)를 적습니다 |
| 보궐선거 | `by_election: true`를 붙여 같은 직위의 `records`에 넣습니다. 화면은 이를 '이전·보궐'로 접습니다 |
| 다음 선거 | 법정 날짜나 공고 날짜가 있을 때만 `date`를 씁니다. 없으면 `date: null`, `label_ko: "법정 기한 YYYY-MM"`으로 둡니다. 추정 날짜를 만들지 않습니다 |
| 날짜 | `YYYY-MM-DD` 형식만 씁니다. 모르면 `null`로 두고 `note_ko`에 이유를 적습니다 |
| 출처 | 모든 `records[]`·`incumbent`·`next`에 `sources`를 붙입니다. http(s) URL만 씁니다 |

### 2-2. 지방선거의 범위
지방선거는 **전국 단위 집계만** 받습니다. 지역별 수장은 지역 수장 명단(`region_leaders`, `POLITICS_DATA_GAPS_20261104.md`)으로 따로 받습니다.

| 지방 유형 | 받는 것 |
|---|---|
| 동시 지방선거(한국·일본 통일지방선거·브라질 주지사·멕시코 주지사) | 날짜, 투표율, 정당별 당선 수(광역단체장 기준) |
| 주별 개별 선거(독일 주의회·미국 주지사·인도 주의회) | 최근 2년 안에 치러진 선거만, 주마다 `office` 하나(`system_id`: `deu-landtag-by` 등). 정당별 의석을 적습니다 |
| 수도·대도시 단체장(서울·도쿄·런던·파리·마드리드) | 단일 직위 선거처럼 `candidates`를 적습니다 |

## 3. 우선순위와 출처

### 3-1. 1차: 10개국 (쟁점 포함)
| 국가 | 행정수반 | 의회 | 지방 | 1순위 공식 출처 |
|---|---|---|---|---|
| 한국 KOR | 2025 대선(+2022) | 2024 총선 | 2026 지방 | 중앙선관위 선거통계시스템 info.nec.go.kr |
| 미국 USA | 2024 대선 | 2024 하원·상원 (2026 중간선거는 `usa_election_*` 파일이 있으므로 링크만) | 2026 주지사 | FEC "Federal Elections 2024", 하원 Clerk 선거 통계, 각 주 국무장관 |
| 일본 JPN | 총리(내각제, 자민당 총재 선거는 당권으로 별도) | 2026 중의원(이미 있음, 보강) + 2025 참의원 | 2023 통일지방선거, 도쿄도지사 | 총무성 選挙関連資料, 각 都道府県 選管 |
| 대만 TWN | 2024 총통 | 2024 입법원 | 2022 지방(2026-11-28 예정) | 중앙선거위원회 db.cec.gov.tw |
| 독일 DEU | 총리(내각제) | 2025 연방하원 | 2026 주의회 5곳(있음, 득표 보강) | Bundeswahlleiterin, 각 주 Landeswahlleiter |
| 영국 GBR | 총리(내각제) | 2024 하원 | 2026 스코틀랜드·웨일스·잉글랜드 지방 | House of Commons Library 선거 보고서, Electoral Commission |
| 프랑스 FRA | 2022 대선 (1차·결선) | 2024 하원 (1차·결선 투표율 각각) | 2026 코뮌 | 내무부 archives-resultats-elections, 헌법위원회 |
| 스페인 ESP | 총리(내각제) | 2023 하원·상원 | 2023 지방·자치지방 | 내무부 infoelectoral.interior.gob.es, JEC |
| 인도 IND | 총리(내각제) | 2024 하원(Lok Sabha) | 최근 2년 주의회 | 인도 선거관리위원회 results.eci.gov.in, eci.gov.in 통계 보고서 |
| 브라질 BRA | 2026 대선(있음, 투표율·선거인 수 보강) + 2022 | 2026 하원·상원 정당별 | 2026 주지사 | 선거고등법원 TSE resultados.tse.jus.br, dadosabertos.tse.jus.br |

### 3-2. 2차: 나머지 대통령제·결선 국가
ARG, CHL, COL, MEX, PER(없으면 생략), PRT, POL, ROU(없으면 생략), TUR, IDN, PHL, NGA, ZAF, KOR 외 결선국.
- 결선 국가는 1차와 결선 표를 반드시 따로 적습니다.

### 3-3. 3차: 의원내각제·기타
CAN, AUS, NZL, ITA, GRC, HUN, ISR, THA, MYS 등입니다.
- 의회 선거와 총리(incumbent)만 받습니다.

### 3-4. 받지 않는 나라
- 경쟁 선거가 없는 나라: CHN, SAU, ARE, QAT, KWT(의회만 있으면 의회만).
- 분쟁국: LBY, YEM.
- 이 나라들은 `elected_how: "none"`과 `note_ko`로 이유만 적습니다.

### 3-5. 쟁점 (`issues`, 1차 10개국)
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
- [ ] `python3 build_election_records.py --check`를 통과합니다
- [ ] 다른 나라 파일·화면 코드는 바꾸지 않았습니다

## 5. Cursor에 붙여 넣을 지시문

> ⚠️ 2026-11-07 수정. 처음 지시문은 '한국만' 적고 '한 나라당 PR'이라고 해서 한국 한 곳만 하고 멈췄습니다.
> 이제 **한 번의 작업으로 여러 나라를 순서대로 끝까지** 진행합니다. 나라마다 브랜치와 PR은 따로 둡니다.

### 5-1. 선거 기록 (1차 10개국, 멈추지 말고 끝까지)
> `docs/ops/ELECTION_RECORDS_REQUEST_20261107.md`대로 1차 10개국 선거 기록을 **순서대로 모두** 만들어줘. 순서: KOR(완료) → USA → JPN → TWN → DEU → GBR → FRA → ESP → IND → BRA.
>
> 나라마다 할 일:
> 1. 최신 main에서 브랜치 `cursor/<iso3>-election-records-<날짜>`를 만든다.
> 2. `config/election_records/<iso3>.json`을 작성한다.
> 3. `python3 build_election_records.py && python3 build_election_records.py --check`를 실행한다.
> 4. PR을 연다.
> 5. **곧바로 다음 나라로 넘어간다.** 한 나라에서 자료를 못 찾은 칸이 있어도 멈추지 말고, `null`과 `note_ko`로 남긴 채 다음 나라를 진행한다.
>
> 범위와 규칙:
> - 범위는 3-1절 표의 행정수반·의회·지방 칸이다.
> - 쟁점은 이번에 넣지 않는다(5-2에서 따로 한다).
> - 득표·투표율은 공식 집계만 쓴다.
> - 화면 코드는 건드리지 않는다.
>
> 끝나면 나라별로 '채운 칸 / 못 채운 칸과 이유'를 표 하나로 정리해서 보고한다.

### 5-2. 쟁점 (10개국, 선거 기록과 별도 PR)
> 3-5절대로 10개국 쟁점을 나라당 3~5개씩 만들어 `config/election_records/<iso3>.json`의 `issues`에 넣어줘.
> - 공약은 출처 사다리(선관위 공약집 → 정당·후보 공식 페이지 → 공영방송·통신사 공약 비교 기사 2곳) 순으로 쓴다.
> - PDF를 못 열면 다음 단계로 내려가고, 열지 못한 URL과 이유는 `note_ko`에 남긴다.
> - 여론조사 순위(salience)는 원문이 있을 때만 넣는다.
> - 나라 하나에 PR 하나씩, 10개국을 멈추지 말고 끝까지 진행한다.

### 5-3. 기존 자료 변환 (JPN·TWN·IND·THA·VNM 등)
> 이미 다른 형식으로 저장해 둔 선거 자료(`config/extracted/*`, 국가별 personnel 등)가 있는 나라는 새로 조사하기 전에 먼저 이 계약으로 옮겨줘.
> - 대상: JPN, TWN, IND, THA, VNM. 그 밖에 찾은 나라가 있으면 함께 옮긴다.
> - 옮길 때 원래 출처 URL과 수집일을 그대로 유지하고, 숫자는 고치지 않는다.
> - 나라당 PR 하나로 한다.

### 5-4. 2·3차 국가
> 5-1이 끝나면 3-2절 → 3-3절 국가를 같은 방식으로 이어서, 멈추지 말고 진행해줘.
