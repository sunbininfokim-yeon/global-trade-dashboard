# NJ C그룹 선거 증거 연결 — 2026-10-09

사용자 순서 AL→**NJ**→NM→NH. `us-nj-state-evidence-20261009` / `codex/nj-evidence-20261009`는 AL #510의6d82e9d6 다음에 분리했다. CT #507·AL #510 기반 변경을 보존한다. UI/workflow/LETF/병합/배포/배포 dispatch는 수행하지 않았다.

## 공식 후보와 실제 선거 범위

[NJ DOS 공식2026 페이지](https://www.nj.gov/state/elections/election-information-2026.shtml)의 전체 PDF를 내려받아 하원9/4명부 **12구35명**, 상원7/27명부 **4명**을 대조했다. 하원 기존35명은 유지하고 상원의 Cory Booker·Justin Murphy에 Veronica Fernandez(END THE CORRUPTION!)·Joanne Kuniansky(Socialist Workers Party)를 추가했다. 기타후보의 공식 문구를 그대로 보존하며 DEM/REP로 바꾸지 않았다. 명부·최초/수정 인증·기명후보·당선 인증을 구분하고 현재 명부 상태는 `complete_active_agency_listing`이다.

공식6/2정기 경선 이후 본선 비교 시작6/3. **NJ11의4/16보궐선거와11/3정기선거는 별개**다. 과거 보궐 조사/결과를11월 승패로 가져오지 않는다. 7구9/4수정 인증서 표지와p2명부를 렌더해 Lana Leguia의 출마 불가를 확인해 제외기록에 보존했다. 공식 페이지 HTML의 주석 안에 있는 오래된 수정 링크를 활성 최신 발표로 취급하지 않았다.

NJ08은 REP후보가 없지만 DEM1·기타3명이 있으므로 무투표 당선이 아니다. 13선거 모두 복수 후보이고 검증된 무투표 당선0건. 별도 기명 후보 Eduardo Jose Castillo Nicasio는 보조 명부 보고만 있어 공식 후보에 편입하지 않았다. **2026 NJ주지사는 비선거**, 2025주지사 선거/2026직무지지율을2026선거 조사로 만들지 않는다.

## API 누락 조사 보완

공개 VoteHub 실제 NJ관측은 **1건**(Z to A Research,5월 경선 전·당파 의뢰·기사 원문)이다. 원문 방법 재검증 미완료로 보류했다. 후보 이름 검색의 Bennett를 Peggy/Rick Bennett와 섞지 않고 subject/seat를 확인했다.

[Insider NJ/StimSight 원문5페이지](https://www.insidernj.com/wp-content/uploads/2026/09/StimSight_NJ07_toplines.pdf)를 검토해 **NJ07 498LV,9/8–12, Bennett47/Kean42/O’Toole1/미정10**을1관측으로 연결했다. Q8최초 후보 문항·leaners 포함·표본 프레임·영어 전화/text-to-web·가중 변수·원문 날짜/지문을 보존했다. Q9/10후보별 투표 가능성을 최초 득표율로 바꾸지 않는다.

기관은 확률 표본이라고 보고하나 방법론은 가중대상을 primary electorate라고 쓰고 제목/문항은 general election이다. 문항은 names rotated, 방법란은 county ballot order라고 달리 쓴다. 이를 임의로 오타로 고치지 않고 문서상 충돌/의뢰자 맥락 검토 미완료로 **참고 전용** 처리했다. 보고±4.7pp는 독립 검증된 정확도/유의성/승리확률이 아니다. AAPOR·기관 수 등급 없음. 조사 종료9/12를10월 조회일로 바꾸지 않아 현재7/14일 적격0건이다.

같은 PDF의 Booker49/Murphy43은 **7구 안 표본**이므로 주 전체 상원 관측을 만들지 않았다. 2025주지사 투표회상/직무지지율도 배제했다. 상원·나머지11하원은 현재 검색/수집 범위에서 검증된11월 기명조사 미확보이며 조사 자체의 전수 부재를 단정하지 않는다.

특정 원문 URL만 보완 허용했다. 미래 StimSight의 모든 발표를 자동 승인하지 않는다. 원문 지문 변경/장애 시 원래 날짜 자료를 참고 이월, 후발 API동일 파동은 표본·수치·의뢰자 일치 시1건/충돌 시 실패 및 마지막 유효 자료 보존.

## FEC 신원 연결

후보선정은 공식 명부, ID보조는 검토한 [Green Papers 신원 표](https://www.thegreenpapers.com/G26/NJ), 금액은 기존 동일 레이스 FEC스냅샷으로 구분했다. 기존 PDF는 FEC ID를 싣지 않으므로 잘못된 `secondary_identifier_source_url=official PDF` 표기를 실제 보조 출처/지문으로 바로잡았다.

명시적 이름 변형 검토로 Norcross·McGuire·Kirrane·Menendez·Pino의5하원 ID, 상원4명 ID를 연결했다. 하원ID링크21→26, 상원1→4. Menendez의H2NJ13075는H2NJ08232에 합치지 않았고 Herzig의 두 신고ID도 기존 검토 ID만 유지한다. 지역구05에 신고된 Pino금액을09로 이동하지 않았다. Fernandez/Kuniansky의 FEC IND/SWP와 공식 투표용지 브랜드 OTH의 코드 차이는 검토 기록으로 보존했다.

현재 후보 FEC O범주 관측 하원 **7/12→10/12**, 상원1/1. 이는 기존 자료의 후보 연결 개선이며 새 금액 수집이 아니다. 하원02/04는 현행 스냅샷에서현재후보 O관측 미확보/null이다. 연방 O·U·V/W, P/G/S/R/X/기타 단계는 원래대로 유지하며 보궐/경선 지출을 본선 새 금액으로 재분류하지 않았다. 캠프 수입이나 다른 후보 반대액을 지지액으로 넣지 않았다.

## 반복 실행·검증

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state NJ --as-of YYYY-MM-DD
python3 refresh_state_evidence.py --state NJ --as-of YYYY-MM-DD
```

등록 API 신규자료는 기존 정책으로 자동 검사한다. 미등록기관 새 발표/새 비API 원문은 추가 검토가 필요하다. 별도 정기 workflow를 설치하지 않았고 일일 운영 변경은 #489통합 범위다. 새 키·유료권한 사용 없음.

NJ회귀8개: 초기/다후보·leaners·문서 충돌 참고·지역구상원 배제·공식39명·무투표 오인 방지·보궐/정기·자격제외·유한 발표승인·지문/후발 API중복·금융ID원출처. polling348개 통과(기존340+NJ8). 기존 finance68/federal6/JS51 및 금융지도 합계 검사는 AL부모에서 통과했고 관련 집계 코드·금액 파일 변경 없음.

타주493poll레이스·59누적이력·49주index와 기존금융/주공시/감사4,644파일을 SHA/구조 비교로 보존했다. 다른주/국가 지도·글로벌 기준일·금융index·공개순서파일도 유지했다. NJ조회receipt만10/9갱신. 공개 evidence 파일명은 index NJ항목을 참조하며 상태 `live_sources_reviewed_partial`이다. GitHub PR검사는 게시 후 별도로 확인한다.

다음 신규 주 **NM → NH**. NJ07방법론 문구/의뢰자 맥락과 나머지 여론조사 발견은 후속 보강 항목이다. 병합·배포 보류 유지.
