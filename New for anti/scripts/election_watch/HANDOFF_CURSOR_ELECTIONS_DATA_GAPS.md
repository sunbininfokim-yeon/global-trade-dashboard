# 핸드오프: 선거 UI 행정부·의회 데이터 보강 요청 (Claude → Cursor)

작성: Claude Code · 2026-09-10
대상 파일: `public/data/elections_board_v1.json`, `public/data/elections_ui_manifest_v1.json`
(둘 다 파이프라인 산출물 — Claude는 이 파일을 직접 손으로 고치지 않음. 아래 항목은
`run_refresh_cycle.py --build-derived` 체인을 통해서만 반영해줄 것)

## 배경

선거 UI(정치 대분류)를 열어 국가별 화면을 확인하면, 다음 화면들이 "데이터 수집 예정"
또는 비활성 카드로 뜬다. UI 쪽 렌더링 문제가 아니라 `elections_board_v1.json`에
해당 필드가 아예 `null`이거나 존재하지 않아서다 (직접 확인함). 클라이언트에서
합산·추정으로 채우는 건 계약 위반이라 하지 않았고, 원본 데이터를 보강해달라는
요청이다.

## A. 최우선 — 의회 실시간 구성이 통째로 없는 8개국

`elections_ui_manifest_v1.json`에서 아래 8개국은 `screens.legislature.status = "disabled"`,
`missing = ["live_composition"]`이고, `elections_board_v1.json`에서 해당 국가의
`legislature`/`legislature_live` 키 자체가 `null`이다 (확인 완료):

- IND (인도), TWN (대만), ZAF (남아공), NGA (나이지리아), IDN (인도네시아),
  TUR (튀르키예), SAU (사우디), ARE (UAE)

필요한 최소 필드는 이미 `ready` 상태인 JPN/DEU/GBR/FRA/BRA/ISR 국가들의
`legislature_live` 구조를 그대로 따르면 된다 — 양원/단원 여부에 맞춰
정당별 의석수 + 의장단(가능한 범위까지). 개별 의원 명부까지는 필요 없음
(핸드오프 §6 "국가 등급별 최대 깊이" — tier-2/3는 정당 구성 요약이 상한).

우선순위 체감: IND(세계 최대 의회 민주주의) · IDN · TUR이 사용자 노출 빈도상 먼저면 좋겠음.

## B. IRN(이란) 의회 — 부분 채움

매니페스트가 `partial`로 선언하고 `missing`에 `majlis_party_bloc_seats`,
`member_roster`, `committees`를 나열해뒀는데, 실제 board에는 `legislature: null`이라
아무것도 없다. 최소한 `majlis_party_bloc_seats`(계파 블록별 의석)만이라도 채워지면
`disabled → partial`로 승격 가능.

## C. USA 연방의회 상임위 — `congress.missing_fields`

`ui_ready.congress.missing_fields = ["standing_committees", "committee_chairs",
"committee_member_rosters"]`. 상원·하원 의석수/원내지도부는 이미 정상 표시되고,
상임위만 "데이터 수집 예정" 카드로 남아 있음. 하원·상원 상임위원장 명단 + 소속
위원 명부가 필요.

## D. KOR(한국) 행정부 내각 — 소스 충돌 2건 미해결

`executive_live.source_conflicts_excluded = ["해양수산부 장관", "중소벤처기업부 장관"]`.
공개 소스 간 불일치로 표시를 보류 중인 상태(핸드오프 §3 규칙대로 강제로 채우지
않고 각주만 노출 중). 정본 확정되면 `executive_live.cabinet`에 채워 넣고
`source_conflicts_excluded`에서 제거.

## E. (우선순위 낮음, UI에는 안 뜨지만 데이터 오염) 50개 주 `state_legislature.raw` 필드

`ui_ready.state_drilldown.states[].state_legislature.{state_senate,state_house}.raw`
필드 98/100(주×양원)에 위키텍스트/HTML 잔재가 그대로 남아 있음. 예 (Alabama):

```
"raw": "style=\"color:black; background-color:</span><span typeof=\"mw:Nowiki\" about=\"..."
```

UI는 이 필드를 읽지 않아(코드 전수 확인함) 화면엔 영향 없지만, 스크레이퍼가
위키 테이블 마크업을 못 걷어낸 흔적이라 다른 필드도 같은 파서를 거쳤다면
잠재 위험. 시간 날 때 파서 점검 + `raw` 필드 자체를 최종 산출물에서 빼는 것 권장
(디버그용이면 별도 내부 캐시로만 남기고 배포 JSON에는 미포함).

## 확인 기준

각 항목 반영 후:

```bash
cd "New for anti/scripts/election_watch"
python3 run_refresh_cycle.py --build-derived
```

`elections_ui_manifest_v1.json`의 `claude_handoff_gate.can_start_ui = true`,
`errors = []` 유지 확인. A/B 항목은 해당 국가 `screens.legislature.status`가
`disabled → partial` 또는 `ready`로, C는 `congress.missing_fields`에서 항목이
빠지는 것으로, D는 `source_conflicts_excluded`가 비는 것으로 완료를 확인할 수 있음.

## 지켜줄 것

- UI 쪽 파일(`New for anti/{app.js,index.html,style.css}`, `js/elections/**`)은
  건드리지 말 것 — Claude 단독 소유 (`docs/ops/OWNERS.md`).
- 클라이언트 조인이 필요 없도록, 정당명/의석수는 board JSON에 미리 계산해서 넣을 것
  (UI는 절대 합산·추정하지 않는다는 게 계약의 핵심 규칙).
- 확보 못 한 필드는 `null` 그대로 두고 매니페스트에 `missing`으로 정직하게 선언할 것
  — 임의 추정치로 채우지 말 것.
