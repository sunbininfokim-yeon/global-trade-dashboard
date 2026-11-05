# 정치 › 국가별 화면: 추가 자료 요청서 (2026-11-04, Claude)

이 문서는 수집 담당(Cursor/Codex)에게 넘기는 요청서입니다. 같은 날짜의 `POLITICS_DATA_GAPS_20261104.md`가 지역 수장 공백을 다룬다면, 이 문서는 그다음 단계인 **정당·의회 지도부, 행정부 조직, 대통령실·총리실 구조, 계파·족의원, 분쟁 지역**을 다룹니다.

## 공통 규칙 (모든 요청)
- **파일 위치:** 국가별 `config/<iso3>_personnel_<날짜>.json`에 블록을 더합니다. 별도 파일이 필요하면 `config/<iso3>_<주제>_<날짜>.json`으로 만들고, 화면 연결은 Claude가 합니다.
- **출처:**
  - 정부·의회·정당·선관위 공식 페이지를 1순위로 씁니다.
  - 언론은 공식 페이지가 없는 항목(계파 등)에만 쓰고, **2곳 이상 교차**한 경우만 씁니다.
  - 위키백과·나무위키는 쓰지 않습니다.
- **값을 못 찾을 때:** null로 두고 `note_ko`에 이유를 적습니다. 추정해서 채우지 않습니다.
- **필수 필드:** 모든 사람 줄에 `name`, `title_local`, `title_ko`, `since`(모르면 null), `source_url`, `source_date`를 둡니다.
- **확인 수준:** `verification`은 `official` / `two_media` / `single_media` 중 하나로 적습니다. 화면은 `single_media`를 회색으로 표시합니다.
- **단위:** 한 PR = 한 나라 × 한 주제입니다. 여러 나라를 한 PR에 섞지 않습니다.

---

## 요청 1. 정당 지도부 (당대표·원내대표·최고위원 등)

**왜 필요한가:** 지금 '정당' 블록은 성향 설명뿐이고 사람이 없습니다. 의원내각제에서는 여당 대표가 곧 총리 후보이고, 대통령제에서도 원내대표가 입법을 좌우합니다.

```json
"party_leadership": [
  {"party": "더불어민주당", "party_ko": "더불어민주당", "party_id": "dpk", "seats": 161, "role_in_govt": "ruling",
   "posts": [
     {"post": "leader", "title_ko": "당대표", "name": "...", "since": "...", "source_url": "..."},
     {"post": "floor_leader_lower", "title_ko": "원내대표", "name": "...", "since": "...", "source_url": "..."},
     {"post": "floor_leader_upper", "title_ko": "상원 원내대표", "name": null},
     {"post": "secretary_general", "title_ko": "사무총장", "name": "..."},
     {"post": "policy_chief", "title_ko": "정책위의장", "name": "..."},
     {"post": "executive_member", "title_ko": "최고위원", "name": "...", "kind": "elected|appointed"}
   ]}
]
```
- **범위:**
  - 의석 순 상위 정당 4곳까지. 대통령제는 여당과 제1야당만 받아도 됩니다.
  - 일당·왕정 국가(사우디·카타르·쿠웨이트·UAE)는 생략합니다.
  - 중국은 이미 별도 화면이 있습니다.
- **`post` 표준값:** `leader`, `deputy_leader`, `floor_leader_lower`, `floor_leader_upper`, `whip`, `secretary_general`, `policy_chief`, `executive_member`, `spokesperson`. 나라별 고유 직함은 `title_local`에 그대로 적습니다. 예: 일본 幹事長·総務会長·政調会長(党三役), 독일 Fraktionsvorsitzender, 영국 Chief Whip.
- **우선순위:** KOR JPN GBR DEU FRA ITA CAN AUS BRA MEX IND TUR ISR TWN ESP POL ARG.

## 요청 2. 의회 구조 (의장단·교섭단체 대표·주요 상임위원장)

```json
"legislature_offices": {
  "chamber": "lower",
  "presiding": [{"title_ko": "의장", "name": "...", "party": "..."}, {"title_ko": "부의장", "name": "..."}],
  "groups": [{"name": "교섭단체명", "seats": 0, "leader": "...", "source_url": "..."}],
  "committees": [{"name_local": "...", "name_ko": "예산결산특별위원회", "chair": "...", "chair_party": "...", "key": true}]
}
```
- **상임위원장 범위:** 전원이 아니라 **핵심 위원회만** 받습니다. 예산(재정), 외교, 국방, 법사(사법), 정보, 운영, 그리고 그 나라 고유의 핵심 위원회 1~2곳입니다.
- **양원제:** 상·하원을 각각 별도 블록으로 둡니다.

## 요청 3. 행정부: 부처·외청 조직과 장·청장

**왜 필요한가:** '행정부·정부' 블록을 미국 EOP·중국 국무원처럼 **부처 박스 격자**로 만들기 위해서입니다. 지금은 대부분 명단이 "장관 전원은 넣지 않는다"로 비어 있습니다.

```json
"ministries": [
  {"id": "mofa", "name_local": "...", "name_ko": "외교부", "kind": "ministry", "rank": 3,
   "head": {"title_ko": "장관", "name": "...", "party": "...", "since": "...", "source_url": "..."},
   "deputies": [{"title_ko": "제1차관", "name": "..."}],
   "agencies": [
     {"id": "...", "name_ko": "재외동포청", "kind": "agency", "head": {"title_ko": "청장", "name": "..."}}
   ]}
]
```
- **`kind` 표준값:**
  - `ministry`: 부·성. 한국의 처·위원회 중 장관급은 `rank`로 표시합니다.
  - `agency`: 외청·청.
  - `independent`: 독립기관. 중앙은행, 감사원, 선관위 등.
- **`rank`:** 정부 서열(의전 순서)입니다. 모르면 null로 둡니다.
- **범위:**
  - 장관·청장 이름까지만 받습니다. 차관은 1차 대상이 아닙니다.
  - **조직 골격(부처 목록)은 사람이 비어도 먼저** 제출합니다. 골격이 있으면 화면은 "명단 수집 예정" 박스로 그립니다.
- **우선순위:** KOR(18부 4처 18청 우선) JPN(1府12省庁+외국) GBR DEU FRA CAN AUS IND BRA MEX TUR ITA ESP.

## 요청 4. 대통령실·총리실 구조와 인사

**왜 필요한가:** 지금은 직함 낱말로 급(실장급·수석급·비서관급)을 추정합니다. 그러다 보니 한국 국가전략투자보좌관처럼 애매한 사례가 생깁니다. 급을 **자료에 직접** 적어 주면 추정을 끌 수 있습니다.

```json
"head_office": {
  "kind": "presidential_office|prime_ministers_office|royal_court",
  "org_chart_url": "...", "as_of": "...",
  "units": [
    {"name_ko": "비서실", "grade": 1, "head": {"title_ko": "비서실장", "name": "..."},
     "children": [
       {"name_ko": "정무수석실", "grade": 2, "head": {"title_ko": "정무수석비서관", "name": "..."},
        "children": [{"name_ko": "정무기획비서관실", "grade": 3, "head": {"title_ko": "정무기획비서관", "name": "..."}}]}
     ]}
  ]
}
```
- **`grade`:** 1 = 실장급(장관급), 2 = 수석·차관급, 3 = 비서관(1급)입니다. 나라별 대응은 `grade_note_ko`에 적습니다.
  - 일본: 官房長官 = 1, 副長官·補佐官 = 2, 秘書官 = 3.
  - 영국: Chief of Staff·Cabinet Secretary = 1.
  - 프랑스: Secrétaire général·Directeur de cabinet = 1.
- **범위:**
  - 3단계(비서관급)까지 받습니다.
  - 한국은 행정관은 받지 않습니다.
  - 일본은 内閣官房·内閣府의 국장급까지 받습니다.
- **우선순위:** KOR JPN USA(보유) FRA GBR DEU TWN RUS BRA TUR.

## 요청 5. 계파·족의원 분석 (일본 우선, 한국·미국·이스라엘 확장)

계파·족의원은 공식 명부가 없어서 다른 요청과 성격이 다릅니다. 그래서 **관측 가능한 증거**만 씁니다.

### 5-1. 일본 자민당 파벌(구 파벌)
- 현재 `jpn_ldp_factions.json`은 파벌 단위 인원 추정까지 있습니다.
- **추가로 받을 것:**
  - 의원별 소속(`member_faction`)
  - 2024 해산 이전 소속(`former_faction`)
  - 근거 2곳(언론 명단 기사, 파벌 회합 참석 보도)

### 5-2. 일본 족의원(族議員)
족의원은 자기 신고가 없습니다. 아래 **세 신호** 중 둘 이상인 의원만 `zoku`로 표시합니다.
1. 자민당 정무조사회(政調会) **부회장·부회 부회장·조사회장** 경력. 당 공식 페이지와 보도로 확인합니다.
2. 해당 분야 **중의원·참의원 상임위원장·이사** 경력. 중의원·참의원 공식 기록을 봅니다.
3. 해당 성청의 **대신·부대신·정무관** 경력. 内閣 공식 명부를 봅니다.

```json
"zoku": [
  {"field": "agriculture", "field_ko": "농림족", "members": [
    {"name": "...", "house": "lower", "signals": [
      {"kind": "seichokai_post", "title": "農林部会長", "period": "2021-2022", "source_url": "..."},
      {"kind": "committee", "title": "農林水産委員長", "period": "...", "source_url": "..."}]}
  ]}
]
```
- **분야 표준값:** 농림(agriculture), 국토·건설(construction), 상공(commerce), 후생·노동(welfare), 문교(education), 국방(defense), 체신·IT(telecom), 재정·세제(tax), 외교(foreign).
- **화면 원칙:** 화면에서는 "족의원 **후보**"라고 표시합니다. 증거 목록을 같이 보여 주고, 판정은 하지 않습니다.

### 5-3. 확장
- **한국 계파:** 친명·비명 등. 언론 2곳 이상, 그리고 의원 본인 발언이나 모임 참석을 근거로 씁니다. 신뢰도가 낮아 `single_media`는 받지 않습니다.
- **미국 코커스:** 공식 명단이 있습니다. `usa_house_factions.json`이 이미 있으니 상원 확장만 하면 됩니다.

## 요청 6. 분쟁 지역 조사·처리 방식 (리비아·예멘 → 확장)

### 6-1. 현재 상태와 문제
- 리비아·예멘의 **쪽 위상, 후원국, 통제 지역**은 Claude가 일반 지식으로 채운 '검증 전' 값입니다.
- 출처가 있는 자료로 바꿔야 합니다. 이름·직함은 이미 각 쪽 공식 매체를 출처로 합니다.

### 6-2. 데이터 층과 출처

| 층 | 내용 | 1순위 출처 | 처리 |
|---|---|---|---|
| ① 쪽(진영) 정의 | 정부 측 / 경쟁 정부 / 반군 / 분리 세력 | 유엔 안보리 결의, 유엔 의석(신임장), 각 쪽 헌장·선언 | `authorities[]`·`camps[]`. 이름은 각 쪽 자칭과 중립 명칭을 둘 다 적는다 |
| ② 승인 상태 | 유엔 의석, 승인국 | 유엔 신임장위원회 보고서, 외교부 발표 | `recognition: {un_seat, recognized_by[], as_of, source_url}` |
| ③ 지도부 | 각 쪽 수반·군 지휘·정부 | **각 쪽 공식 매체**(이미 적용: 리비아 LANA·대표원, 예멘 SABA 양쪽) | 지금처럼 쪽별로 따로. 상대 쪽 직함으로 부르지 않는다 |
| ④ 통제 지역 | admin1(또는 admin2) 단위 지배 세력 | ISW/CTP 지도(예멘), UN OCHA·UNSMIL 보고, ACLED(라이선스 확인 필요) | `control_map.regions[code] = {camp, contested, source_url, source_date}`. 출처 날짜가 다른 지역끼리 섞이지 않게 지역마다 날짜를 둔다 |
| ⑤ 외부 후원 | 군사·재정 지원국 | 유엔 전문가패널 보고서(리비아·예멘 제재위원회) | `backers[] = {country, kind: military/financial/diplomatic, source_url}`. 보도만 있으면 `single_media`로 회색 |
| ⑥ 사건 연표 | 휴전·주요 교전·협상 | 유엔 안보리 브리핑, OCHA | 월 단위 3~5건. `events[] = {date, kind, title_ko, source_url}` |
| ⑦ 인도 상황(선택) | 난민·피해 | OCHA, UNHCR | 수치는 출처 날짜와 함께. 추정은 범위로 |

### 6-3. 처리 원칙
- **정통성 판정 금지:** 화면은 "어느 쪽이 정통인지 판정하지 않는다"를 유지합니다. 쪽의 순서는 유엔 의석 보유 쪽을 먼저 둡니다. 이건 사실 기준이지 가치 판단이 아닙니다.
- **통제 지역:**
  - "대략적 구분"을 기본값으로 둡니다.
  - 출처가 붙은 지역만 진한 색으로 칠하고, 출처 없는 지역은 빗금(혼재)으로 둡니다.
- **갱신 주기:** 통제 지도와 사건은 월 1회, 지도부는 변동이 생길 때 갱신합니다. `as_of`가 90일을 넘으면 화면에 "갱신 지연"을 띄웁니다.
- **명칭:**
  - 분리 세력의 자칭 국가명은 따옴표로 표기합니다.
  - 지역명은 국제표준(ISO 3166-2)을 씁니다.

### 6-4. 확장 후보 (우선순위 순)
1. **수단:** SAF(군정) 대 RSF. 다르푸르 통제 변화가 큽니다.
2. **미얀마:** 군정 SAC 대 NUG·소수민족 무장조직. 주·관구 단위입니다.
3. **시리아:** 과도정부 대 SDF(북동부)·남부 세력.
4. **팔레스타인:** 서안(PA) 대 가자. 경계 자료도 새로 필요합니다.
5. **우크라이나 점령지:** 러시아 통제 지역 표시. 국가 화면이 아니라 우크라이나 화면 안의 층입니다.
6. **소말리아:** 연방정부 대 알샤바브·소말릴란드(분리).
7. **아이티:** 정부 대 갱단 연합. 포르토프랭스 구역 단위라 admin2가 필요합니다.

각 나라에 대해 ①~④를 먼저 요청하고, ⑤~⑦은 두 번째 차수로 요청합니다.

---

## 요청 순서 제안

| 차수 | 요청 | 대상 |
|---|---|---|
| 1 | 요청 6 ①~④ | 리비아·예멘 출처 교체 (지금 '검증 전' 해소) |
| 2 | 요청 1 + 2 | KOR·JPN·GBR·DEU·FRA (정당·의회 지도부) |
| 3 | 요청 4 | KOR·JPN (대통령실·총리실 급 명시) → 급 추정 제거 |
| 4 | 요청 3 | KOR·JPN 부처·외청 골격과 장·청장 |
| 5 | 요청 5-1·5-2 | 일본 파벌·족의원 |
| 6 | 요청 1~4 | 나머지 우선순위 국가로 확장 |
| 7 | 요청 6 확장 | 수단·미얀마·시리아 |

## 수집 담당에게 붙여 넣을 지시문 (예: 1차)
> `docs/ops/POLITICS_DATA_REQUESTS_20261104.md`의 요청 6 ①~④를 리비아(LBY)부터 진행해줘.
> - `config/profiles/lby.json`의 `camps`, `control_map`, `authorities`를 출처가 있는 값으로 바꾸고, 지역마다 `source_url`과 `source_date`를 붙여줘.
> - 출처: 유엔 안보리 결의·UNSMIL 보고·유엔 전문가패널 보고서. 언론만 있으면 `verification: "single_media"`.
> - 화면 코드는 건드리지 말고, 한 나라당 PR 하나로.
