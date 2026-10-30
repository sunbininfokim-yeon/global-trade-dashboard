# 미국 여론조사 보완 출처 탐색

사용자 제공 목록을10/15 실제 접근 결과와 대조했다. 사용자는 여론조사 수집 확대를 먼저 하고 Kalshi·Polymarket은 이후로 지정했다. 베팅 API·UI·통계 가중 평균·당선확률은 이번에 추가하지 않는다.

## 출처별 결과

| 출처 | 확인 결과 | 이번 연결 |
|---|---|---|
| [270toWin](https://www.270towin.com/polls/latest-2026-house-election-polls/) | 주지사·상원·하원 페이지의 공개 jQuery GET 조회 조건을 각각 확인하고 동일 endpoint를 실제 조회했다 | **자동 탐색 구현**. 최신 각40개 목록 항목, 원문 링크·표시 정당/후보/수치·선거 단계 추출. 원문 수치 편입과 구분 |
| [RealClearPolling](https://www.realclearpolling.com/latest-polls) | 웹 도구에서 개별 조사와 원문 링크를 확인했다. 직접 수집 요청은403 | 조사 발견 참고. Actions용 자동 수집 성공으로 표기하지 않으며 우회·자동 평균 수입 없음 |
| [Race to the WH](https://www.racetothewh.com/allpolls) | 본문이 개별 조사와 평균/예측을 구분하고 Infogram embed를 연결한다. 공개 embed HTTP200이지만 조회한 table chart data는빈 배열이며 live provider 설정만 있다 | 공개한 실제 데이터 전송 계약 미확보. 내부 provider key/비공개 경로를 추측해 호출하지 않는다. 사이트의 적중률 자기보고는 품질 등급으로 채택하지 않음 |
| [NYT latest polls](https://www.nytimes.com/interactive/polls/latest-polls.html) | 직접 요청403. 공개 API 미확인 | 접근 장애. 원문 유료/회원 권한을 우회하지 않음 |
| [Ballotpedia polling indexes](https://ballotpedia.org/Ballotpedia%27s_Polling_Indexes) | JS 로봇 검증 페이지만 반환 | 자동 경로 미확보. 빈 응답을 조사 없음으로 해석하지 않음 |
| [Silver Bulletin](https://www.natesilver.net/p/pollster-ratings-silver-bulletin) | 2026-01-14 기관 등급/역사적 조사 XLSX를 공개하고 활용 시 출처 표기를 명시한다 | 정확도 평가 참고 후보. 현재 경마 조사 feed로 오인하지 않고 기관 등급·현재 발표 적격을 분리함 |
| [FiveThirtyEight 과거 데이터](https://github.com/fivethirtyeight/data) | 과거 데이터 저장소는 확인했으나 이번2026 선거의 새 원자료 feed는 확인하지 못함 | 과거 자료 참고 후보. 최신 자동 원천으로 등록하지 않음 |

추가로 RCP에10/15 MN상원/주지사 KSTP/SurveyUSA 링크가 보이지만 연결된 KSTP 원문을 웹 도구로 열면402다. 해당 숫자를 취합 사이트에서만 보고 원문 검토 완료로 추가하지 않았다. 이는 사용자 API 키가 없어 생긴 문제로 확인된 것이 아니다.

## 자동 탐색 계약

`discover_poll_sources.py --output <temporary-json> [--provider-capture <checkpoint>]`가3개 공개 목록을 독립 수집한다. `election_watch/poll_source_discovery.py`는 중첩 후보 table과 광고를 분리하고 rowspan의 다른 질문을 별도 항목으로 보존한다. 선거구 AL은00, 숫자는2자리로 표시하되 불일치 label은 보류한다. URL query를 보존해 서로 다른 SurveyUSA 발표 링크가 합쳐지지 않는다. 향후 단계는 현행 후보 명부와 다시 대조해야 한다.

각 source는1MiB·30초 한도, 예상 URL/HTML table을 검사한다. 한 직위의403·형식 변경은 다른 직위 결과를 버리지 않는다. 실패한 직위에0개 조사라는 수치를 넣지 않으며, 성공 수집과 부분 보류를 source_health에 기록한다. 세 요청이 모두 실패하면 명시 실패한다. public/data는 쓰지 않는다. 원문을 따라 임의 URL을 자동 요청하거나 로그인·비공개 API를 사용하지 않는다.

목록 날짜는 **aggregator_date**로만 저장한다. fieldwork·표본·모집단·방법론·의뢰자는 null/검토 필요다. 후보 표시를 검증된 명부 신원으로 승격하지 않는다. 전 항목 `signal_eligible=false`이며 라이브 우세·평균·조사 승패 수에는 더하지 않는다. 같은 파동이 여러 사이트에 보여도 새 독립 조사로 추가하지 않는다. 기존 VoteHub source/quality/ballot 검증은 완화하지 않았다.

main의 기존 일일 workflow capture job은 이 탐색 step을 `always()`로 실행하고 `.discovery.json`도14일 artifact로 보관한다. 탐색 실패 때문에 기존 유효 조사 게시를 막지 않는다. 개별 원문·문항을 확인한 후 해당 주의 독립 입력 PR로 기존 보완 원문 계약에 편입한다. 따라서 **새 링크 자동 발견**과 **모든 새 링크의 자동 UI 편입**은 다른 기능이다.

## 10/15 실제 검증

- 실제 공개 목록에서119개 항목·67개 선거: 하원40·상원40·주지사39. 최신 각40개 목록이지 조사 파동119개나 전체 선거 완전 수집이라는 뜻이 아니다.
- 주지사VT 한 행은 후보 하나만 제공돼 보류(`missing discovery candidates`). 상대 후보/지지율을 채워 넣지 않았다.
- VoteHub1,484행 capture와 **정확한 원문 URL**만 비교했을 때82개 항목에 같은 URL이 없다. URL이 다르면 같은 파동일 수도 있으므로82개 신규 조사/누락 확정이라는 뜻은 아니다. query·다른 의뢰 문항·지역을 원문으로 재검토해야 한다.
- 원본 응답 SHA256와 actual captured_at은 `/private/tmp/us-poll-expansion-20261015/us-polls-capture.discovery.json`의 source_health에 보관했다. 이는 로컬 검증이고 아직 GitHub 정기 수집 artifact나 배포 데이터가 아니다.
- 원문 접근·새 스키마·기관별 자동 적격 확대는 후속 검토다. 주지사·상원·하원만 범위이며 전국 generic ballot·대통령 지지율·사이트 평균/예측값은 지역구 조사로 섞지 않는다.

통합/운영 확인은 #557 인수 문서 순서에 따른다. 병합·production dispatch·배포 없음. 신규 API 키는 이번 공개 수집 경로에 필요하지 않았다.
