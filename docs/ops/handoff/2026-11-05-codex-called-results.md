# 2026-11-05/06 — 미국 전국 당선 결과 우선 반영

## 11/06 후속 현재 상태 — PR #888

사용자 `진행`에 따라 보류 13곳을 모두 재검토했고, 새 하원 win 레이블 24곳도 대조했다. **현재 당선 선언 472건(상원 33·주지사 34·하원 405) + LA-05 결선 1건**이다. 아래 최초 435건 보고는 작업 이력이며 현재 수치는 이 절을 기준으로 한다. 원래 435건의 이름·출처·확인 시각은 한 필드도 변경하지 않았다.

- 최초 보류 CA-12·34·37, LA-01·03·04, FL-10, MA-01·02·05·07, PA-03, WI-02는 모두 해소했다.
- 새로 들어온 CA-29도 동일 정당 후보가 복수여서 일단 보류한 뒤, DDHQ의 실명 승자 체크로 별도 해소했다. 새 스냅샷 `media_call_map_held_20261106.json`의 `held=[]`다. 이는 **검토한 win 레이블의 신원 보류가 0이라는 뜻**이며 전국 모든 선거가 끝났다는 뜻이 아니다.
- CA-12 Lateefah Simon·CA-29 Luz Maria Rivas·CA-37 Sydney Kamlager-Dove: DDHQ 원문 Results 탭의 녹색 승자 체크를 시각 확인했다. Forecast·득표 선두를 선언으로 바꾸지 않았다. 실제 `#DecisionMade` 표시를 UTC로 변환한 시각은 각각 11/04 04:52·04:29·04:31Z이며, 발표 주체는 **DDHQ**로 구분했다. 해당 페이지의 성만 표시된 이름은 기존 공식 본선 명부의 유일한 해당 전체 이름에 연결했다.
  - <https://votes.decisiondeskhq.com/races/2026-11-03/california-us-house-12-general-election>
  - <https://votes.decisiondeskhq.com/races/2026-11-03/california-us-house-29-general-election>
  - <https://votes.decisiondeskhq.com/races/2026-11-03/california-us-house-37-general-election>
- CA-34 Angela Gonzales-Torres: [LAist의 명시적 AP 판정 인용](https://laist.com/brief/news/politics/voter-guides/2026-election-california-general-congress-34-district-gomes-gonzales-torres-la-live-results). 현직 Jimmy Gomez를 자동 선택하지 않았다.
- LA-01 Steve Scalise·LA-03 Clay Higgins·LA-04 Mike Johnson: [Axios New Orleans의 명시적 AP 판정 인용](https://www.axios.com/local/new-orleans/2026/11/04/julia-letlow-senate-louisiana-election-results). 기존 명부의 전체 이름을 보존하며 별칭을 증거에 기록했다. AP 원문을 직접 읽었다고 표시하지 않았다.
- MA-01 Richard E. Neal·MA-02 James P. McGovern·MA-05 Katherine M. Clark·MA-07 Ayanna S. Pressley: AP 정당 승리 레이블 + [공식 2026 본선 명부](https://www.sec.state.ma.us/divisions/elections/research-and-statistics/2026-state-election-candidates.htm). MA-01 공식 행의 누락 정당은 [Green Papers](https://www.thegreenpapers.com/G26/MA)로 교차 확인했다.
- FL-10 Maxwell Alejandro Frost·PA-03 Christopher M. "Chris" Rabb·WI-02 Mark Pocan: AP 정당 승리 + 해당 주 [FL](https://www.thegreenpapers.com/G26/FL)·[PA](https://www.thegreenpapers.com/G26/PA)·[WI](https://www.thegreenpapers.com/G26/WI) 검토 본선 명부를 결합했다. 이 3곳의 **후보 신원 근거는 검토된 2차 명부**이며 공식 인증으로 표시하지 않는다. 모두 각 호출의 `winner_resolution_ref`에서 방법·출처를 추적할 수 있다. 공개 후보 주소 등 불필요한 개인정보는 복사하지 않았다.

새 검토 스냅샷 `media_call_map_review_20261106.json`은 이전 파일을 덮어쓰지 않는다. 실제 검토 시각은 `2026-11-06T02:03:47Z`, CA-29의 후속 실명 확인은 `02:04:30Z`다. AP 화면의 갱신 표시는 `Nov 6, 2026 at 10:58 AM`이지만 시간대가 명시되지 않아 AP 선언 시각이나 UTC 게시 시각으로 사용하지 않았다. 하원 헤더는 253D/157R(410), 실제 지도 win 레이블은 405개(249D/156R)였다. **차이 5건을 만들어 채우지 않았다.** 지도는 나머지 29곳을 leading, LA-05를 runoff로 표시했다. LA-06은 기사와 지도 단계가 달라 이번에는 기존 미정 상태를 유지한다.

현재 실제 파일을 기존 UI의 `resultsOnly=true` → `electionOutlook`에 넣은 집계:

| 직위 | 당선 선언 | 비선거 포함 결과 | 미정(결선 포함) |
|---|---:|---|---:|
| 상원 | 33 | DEM 52 · GOP 44 · IND 2 | 2 |
| 주지사 | 34 | DEM 28 · GOP 20 | 2 |
| 하원 | 405 | DEM 249 · GOP 156 | 30 (결선 1) |

선언 전용 Python 9개·기존 overview JS 11개 통과, 실제 UI 함수의 합계·결선 분리·선언 수 일치 확인. 최초 435건 보존 및 새 스냅샷 재적용 멱등성도 확인했다. 추가 코드는 없고 이번 후속은 수동 검토 데이터와 인수 문서만 바꾼다. 재현은 아래 기존 `apply_reviewed_media_map.py` 명령에서 review/held 파일의 날짜를 `20261106`으로 지정한다. 공개 calls 파일의 실명 직접 검토 입력이 이전 파일로 유지되며 그 위에 지도 입력을 적용한다.

11/06 현재 원격 PR #888은 Draft/Open, 병합 가능이었다. 최초 커밋의 소유권 CI는 성공했고 선거 CI는 아직 진행 중이었다. 새 커밋의 CI는 별도로 확인해야 한다. **병합·배포·운영 workflow dispatch는 하지 않았다.** #885→#886과 독립적으로 #888을 먼저 검토할 수 있다.

## 사용자 정정과 현재 결과

사용자는 선거가 거의 끝났으므로 주별 실시간 수집기 확대보다 **이미 발표된 전국 당선 결과를 먼저 반영**하라고 정정했다. 이 PR은 기존 언론 선언 파일의 빈 `calls`를 채운다. #885·#886의 수집기/AZ 등록과 독립적으로 먼저 검토·병합할 수 있다.

- worktree: `/Users/yeoninair/Documents/해운 데이터/us-called-results-20261105`
- branch: `codex/us-called-results-20261105`
- 시작 main/base: `16ce12a492742814698ff3957c269cab2ea83607`.
- 11/06 확인한 `origin/main=897f6d3c2`와 이 PR의 기존 변경 파일 3개는 충돌하지 않았다.
- 결과 입력: **435개 선거, 49개 주**. 상원 33·주지사 34·하원 368.
- AK는 검토한 시점의 상원·주지사·하원 모두 단순 선두여서 당선 입력에 넣지 않았다.
- 공식 인증이 아니라 **AP 등 언론의 비공식 당선 선언**이다. 인증 파일은 비워 둔 기존 상태를 유지했다.
- UI·workflow·다른 국가·운영 DB 변경 없음. main 병합·배포·운영 workflow 실행·reset 클릭 없음.

## 자료 확인 방법

브라우저에서 AP 원문 보도를 확인했고, AP 원문 안에 공개된 결과 지도의 실제 iframe을 열어 화면의 `Democratic win` / `Republican win` 레이블을 대조했다. `leading`, 비선거 의석, 출구조사·예측은 당선 입력에서 제외했다.

- 공개 지도: <https://interactives.apelections.org/election-results/assets/apnews/embeds/ge-bop-map/index.html>
- 이를 포함한 AP 원문: <https://apnews.com/article/f126e12e05b579a327b98481c0ae2226>
- 직접 원문 보도로 이름까지 확인한 결과 32건은 해당 기사 URL과 최초 확인 시각을 보존했다.
- 나머지 403건은 **AP의 명시적 정당 승리 + 기존 검토된 본선 후보 명부**를 결합했다. 이름을 AP 지도에서 직접 읽은 것으로 표시하지 않는다. 해당 정당의 canonical 후보가 단 한 명이며 검토된 명부 출처가 있을 때만 연결한다. 중복 별칭은 canonical 이름으로 묶되, 같은 정당의 서로 다른 후보가 둘 이상이면 보류한다.
- 후보 증거는 공용 `candidate_identity_sources`에서 참조한다. 공식/검토 명부와 NGA의 기존 fullname/party/office/cycle 신원 계약을 구분하며, 원문 URL은 보존한다.
- 유료 API·비공개 응답·인증 키를 사용하지 않았다. 이 PR은 **특정 공개 화면의 검토 스냅샷**이며 AP 자동 수집 계약을 확보한 것이 아니다.

주요 직접 확인 원문:

- TX 상원·주지사: <https://apnews.com/article/6e285484736b5116629a3b6e37e1dda5>
- SC 상원: <https://apnews.com/article/74fc0bf08f5822378fcfa2fe09377d69>
- ME 상원: <https://apnews.com/article/ac895e873f373e5560c4a6c137b2ac19>
- OH 상원: <https://apnews.com/article/9e7ae9e1715c0e8203614aea6f71666d>
- NC 상원·하원: <https://apnews.com/article/6cc139bf37efe41050796457d3d57b74>
- GA 상원: <https://apnews.com/article/32dad2d529f42d055326b9ea7df9ce05>
- NH 상원: <https://apnews.com/article/2b2235cf4d8ca6e0eebd2817bf8767f6>
- WI·MN 주지사: <https://apnews.com/article/e3abf3135f626e37d8d2f57e5591ea6a>
- IA 주지사: <https://apnews.com/article/b1d26390b7ed7968435089be6d3bf612>
- 하원: <https://apnews.com/article/8317355ef149f8f8d5f518211038edd2>
- RI 주지사: <https://apnews.com/article/411bd62929ca4f079a77485e8f5afd4d>
- SC 주지사: <https://apnews.com/article/3bff42947d7e4e8fad49e5d77ea60111>
- OK 주지사(AP 원문 전재): <https://www.kxii.com/2026/11/04/republican-mike-mazzei-wins-election-oklahoma-governor/>

AP 최초 기사 발행일·마지막 갱신 시각을 정확한 당선 선언 시각으로 바꾸지 않았다. 선언 시각이 없으면 `called_at=null`, `call_time_status=not_reported`, `verified_at`에 실제 원문 확인 시각을 둔다. 기존 정확한 `called_at` 입력 계약도 유지한다.

## 공개 지도와 합계 차이

검토 입력 `config/usa_polls/media_call_map_review_20261105.json`은 상원 33·주지사 34·하원 381개 `win` 레이블(총 448개)을 담는다. AK/MS 상원, AK/KS 주지사 등 `leading` 레이블은 없다.

하원 상단 합계는 387개 선언으로 보였지만, 같은 공개 지도에서 검토한 개별 `win` 레이블은 381개였다. 이를 억지로 일치시키거나 없는 6개 선거를 만들어 넣지 않았다. AP 화면의 서로 다른 갱신 시점일 가능성은 있지만 원인은 확정하지 않았다. 해당 차이는 검토 입력에 보존했다.

전역구 주의 AP `District 1` 표기는 보드의 `00`으로 정규화했다(AK·DE·ND·SD·VT·WY). 기존 보드의 후보·선거 ID와 대조한 것이며 지도 도형은 변경하지 않았다.

## 보류 13건

`config/usa_polls/media_call_map_held_20261105.json`에 보존했다. AP의 정당 승리 판정이 없어서가 아니라 **후보를 안전하게 특정할 명부가 부족해서** 이번 후보별 입력에서 보류한 것이다.

- 같은 정당 후보 복수: CA-12·34·37, LA-01·03·04.
- 해당 정당 후보 명부 누락: FL-10, MA-01·02·05·07, PA-03, WI-02.

이들은 패배·동률·0석이 아니다. CA/LA는 원문 당선자 이름을 직접 확인하고, 나머지는 본선 후보 명부를 보완해 후속 검토한다. 보류를 풀기 위해 다수 후보 중 현직이나 득표 선두를 임의 선택하지 않는다.

## 재현·검증

`apply_reviewed_media_map.py`는 네트워크 없이 검토 스냅샷과 기존 명부를 읽는다. 직접 기사 증거·원래 확인 시각을 우선 보존하며, 중복·기존 선언과 정당 충돌·미래 검토일·선거 혼입을 거부한다. 정확한 후보 이름이 없는 경우 보류한다. 재실행은 멱등적이며 새로운 수집 시각을 생성하지 않는다.

```sh
cd 'New for anti/scripts/election_watch'
python3 apply_reviewed_media_map.py \
  --review config/usa_polls/media_call_map_review_20261105.json \
  --held config/usa_polls/media_call_map_held_20261105.json
python3 -m unittest tests.test_poll_media_calls tests.test_poll_reviewed_media_map -v
```

- Python 전용 검사 9개 통과: 누락 선언 시각, 별칭/복수후보/누락 명부, NGA 신원 계약, 단순 선두 거부, 잘못된 출처/시각/중복/충돌 거부, 직접 원문 보존, 재생성 멱등성.
- 기존 선거 overview JS 검사 11개 통과.
- **실제 입력으로 기존 UI 집계 함수를 실행**했다. `resultsOnly=true` 경로에서 아래처럼 나온다. 이 옵션은 기존 UI가 선거 후 이미 사용하는 경로다.

| 직위 | 이번 입력에 연결된 선언 | 기존 UI 결과 집계(비선거 포함) | 미반영/미결정 |
|---|---:|---|---:|
| 상원 | 33 | DEM 52 · GOP 44 · IND 2 | 2 |
| 주지사 | 34 | DEM 28 · GOP 20 | 2 |
| 하원 | 368 | DEM 225 · GOP 143 | 67 |

상원의 AP 표기 DEM 54는 민주당과 함께하는 무소속 2명을 포함한다. 우리 기존 UI는 무소속을 별도로 남긴다. 하원 67은 AP가 전부 미결정이라고 선언한 숫자가 아니다. 이번 검토 입력에 포함하지 못한 곳과 실제 미결정이 함께 포함된다.

- 소유권 규칙 15개 통과, deploy-chain 57개 연결 검사 통과.
- 공개 JSON은 후보 명부 증거 URL을 중복 제거해 약 180 KB로 유지했다. 원문 확인 메타데이터는 생략하지 않았다.
- GitHub CI·실제 공개 사이트 갱신은 PR 이후 확인 대상이다. 로컬 집계 검증을 배포 완료로 보고하지 않는다.

## 배포 담당에게

이 PR을 #885·#886보다 **먼저** 검토할 수 있다. `US_ELECTION_NIGHT_RUNBOOK.md`가 정한 기존 수동 검토 선언 입력 경로이며 별도 수집 workflow가 필요 없다. 병합 후 배포가 끝나면 전국 상·하원·주지사 카드와 지도에서 선언을 반영하는지 확인한다. 공식 인증 결과가 들어오면 기존 우선순위대로 인증 결과가 먼저 적용된다.
