# MS 동일 파동 문항·의뢰자·발표일 재검토

- 담당 Codex, worktree `/Users/yeoninair/Documents/해운 데이터/us-MS-primary-health-20261021`, branch `codex/ms-primary-question-20261021`.
- 기반: packet 없는 공용 #659 `codex/poll-question-scope-20261021`, 최신 main6a5bdd3a. 다른 주의 PR을 기반으로 쓰지 않는다. #659를 main에 반영한 뒤 state PR base를 main으로 전환한다.
- 10/21 실제 공개 API와 원문 재수집 성공. MS API3행은 기존3행과 값/날짜/표본/의뢰자가 전부 동일하며 추가 API 조사는0이다. 연방 IE·주지사 공시·UI·workflow·전국 JSON은 갱신하지 않는다.
- [의뢰자 발표](https://chartingthewayforward.substack.com/p/research-release-fresh-polling-from):8/28 발표·8/24 메모, Way to Lead PAC·Democracy Alliance·Democracy Strategy Partners. 원문 PDF는 기존SHA7c7e34816f6dd351f014cdcfcc1e6170caec5187e1e7ac670fcf431097eab649와 같다.
- 조사8/5–15,1,018LV, p4Q3초기3자 Hyde-Smith44/Colom38/Pinkins7, p5Q4초기양자47/41. Q3의10/18은 최초 검토일이었으며 실제 발표일8/28로 바로잡고 검토일10/21과 분리했다. 의뢰자와 DEM 의뢰 표기도 명시했다.
- Q3/Q4는 같은 wave_id와 exact API/원문 지문으로 구분한다. Q4에 실제 제3후보가 빠지므로 MS의 명시적 excluded_records에 근거를 남긴다. API8/29·Way to Lead PAC 표기는 원래대로 보존한다. Q3는 역사적 참고이며 최신7/14일 우세나2개 독립 조사가 아니다. 정보제공 후 문항은 편입하지 않는다.
- 새 capture에 원래 capture receipt를 그대로 보존했다. 이전 packet은 main6a5bdd3a의 MS 입력으로 복원 가능하며 새 감사 자료에 원문 영수증·기존 primary rows·원래 기준일을 남겼다. 금융 재수집 없음. 과거10/18 검사는 고정 audit의 당시 수치/검토를 사용하도록 바꾸어 이후 검토일 때문에 깨지지 않게 했다.
- 집중 MS10개 통과. source 장애·정정은 참고 보존/충돌 격리를 유지한다. 타주505선거·타주history와 focus104의 타주 레코드·root날짜를 보존한다. MS의 실제 새 수집시각은 갱신한다.
- 병합·배포·운영 workflow dispatch를 하지 않았다. 추가 API 키는 필요 없었다.
