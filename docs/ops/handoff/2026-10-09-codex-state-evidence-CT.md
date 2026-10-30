# CT D그룹 선거 증거 연결 — 2026-10-09

사용자 지정으로 D그룹 **CT부터** 처리했다. 다음 신규 주는 **MD**이며 이번 작업에서는 시작하지 않았다. 기존 AK 편집과 #489 통합 작업이 다른 대화에서 진행 중이므로 `us-ct-state-evidence-20261009` / `codex/ct-evidence-20261009`에서 #506 원본 tip을 기준으로 분리했다. AK 변경·기존 작업 폴더를 가져오거나 덮어쓰지 않았다. #506이 main에 병합되어 최신 main을 확인했고 선거 코드/공개 파일은 기준 tip과 동일했다. 후속 PR은 main 대상으로 작성한다. 이 작업은 UI·workflow·LETF·main 병합·배포를 수행하지 않는다.

## 공식 후보·선거 범위

[CT SOTS 2026 General Election Guide](https://portal.ct.gov/-/media/sots/electionservices/voter_guide/2026/2026_voter_guide_final.pdf?rev=4eaa300798fe46f9a5722765c5e7226d&hash=59A37CA0EF6C8402D58E1E37B12DE510) 전체114페이지 PDF를 내려받아 확인했다. 완전한 바이너리 SHA256은 `75ff93df140996da3f6de8d63b620d3a516d112f162831a2e6bc4ad1d1cd6bf8`이며 최초5MiB 부분 다운로드 지문을 완전한 원본 지문으로 사용하지 않았다. p56–57 하원5구 **13명**, p59 주지사2명을 공식 명부로 승격했다. 연락처·주소는 공개 계약/fixture에 포함하지 않는다. 안내서의 현재 명부이며 별도 인증 투표용지·기명 후보 전수·당선 결과를 뜻하지 않는다.

| 대상 | DEM | REP | 기타 공식 후보 |
|---|---|---|---|
| CT01 | Luke Bronin | Amy Chai | Mary Sanders (Green) |
| CT02 | Joe Courtney | George Austin | — |
| CT03 | Rosa DeLauro | Christopher Lancia | Thomas Egan (Independent Party) |
| CT04 | Jim Himes | Michael Goldstein | Benjamin Wesley (Independent Party) |
| CT05 | Jahana Hayes | Chris Shea | — |
| 주지사 | Ned Lamont | Ryan Fazio | — |

`R/I`, `D/WFP` 교차추천은 **동일 후보**다. Independent Party는 무소속 신분과 다르며 Egan/Wesley를 OTH로 유지한다. 기존 이름 변형은 동일 주·선거구·정당의 명시 검토 별칭으로 연결했다. Amy Chai의 다른 구역 신고ID를 CT01 현재 금융ID로 강제 연결하지 않았고, CT04 미확인 기명 후보 Damon Cerreta는 공식 활동 후보에 편입하지 않은 채 별도 보존했다.

[공식 선거 달력](https://portal.ct.gov/-/media/sots/electionservices/calendars/2026-elections/2026-election-calendar-122325.pdf?rev=340f2bcacc9748c1a2ed8f49d1774f52&hash=471ECCC3D26999C2D53BB5636927C0EB)의8/11경선에 근거해 본선 비교 시작을8/12로 설정했다. 달력 일반 안내의 US Senator 문구를 CT2026상원 선거 증거로 사용하지 않았다. 현행 전국35석 일정 및 실제 CT안내서 선거대상에 따라 CT연방상원은 **비선거**다. 주의회 상원36구는 연방선거로 가져오지 않는다. 여섯 선거 모두 복수 후보가 있으므로 무투표 당선으로 표시하지 않는다.

## 여론조사

API 실제 CT4건은 모두 주지사이고 하원5구는0건이다. API가 누락한 아래 **특정 원문2개**를 보완했다. 원문 PDF 전체 바이트 지문과 방법론·문항·발표일을 검토하고 관련 페이지를 렌더해 확인했다.

| 발표 | 원문 후보응답 | 모집단·조사기간 | 처리 |
|---|---|---|---|
| [Quinnipiac9/16](https://poll.qu.edu/poll-release?releaseid=3966) | Lamont55 / Fazio38 | 1,288LV,9/8–14 | 원문 수치·방법 대조, 비교 적격이나 현재7/14일 밖 |
| [GreatBlue/SHU9월](https://www.sacredheart.edu/news-room/news-listing/shu-poll-lamont-holds-lead-as-connecticut-voters-signal-growing-desire-for-change/) | Lamont48.2 / Fazio33.9 | 1,000RV,9/1–8 | 모집틀/확률선정 공개 불충분, 참고 전용 |

Quinnipiac의 확률 RDD 전화모드·영/스페인어·유선263/휴대1025·최소3회 접촉·표본층화·가중·대학 전액 부담을 확인했다. 최초 후보 질문Q1은 leaners를 포함하며 미정5/응답거절2를 기타후보2로 바꾸지 않았다. 발표±3.8pp는 design effect 포함이라고 기록하되 정확도등급·유의성·당선확률로 해석하지 않는다. 세부 LV screen과 신뢰수준은 없는 정보를 계산해 채우지 않는다.

GreatBlue는 공식 대학 발행 PDF p6/10의 디지털 조사·카운티별 초대·가중·RV를 확인했다. 최초48.2/33.9와 미정17.9를 보존하며 강제양자/기울임 후52.2/36.5 및7월49.7/29.5를 추가 파동으로 세지 않는다. 모집 프레임/확률 여부·전체35문항 순서가 공개되지 않아 우세 집계에서 제외한다. 대학9/15기사·9/14방송·PDF9/9보고 날짜는 다른 발표일 근거이며 조사 종료일9/8을 최신 날짜로 바꾸지 않는다.

API4건은 원문 검증 보류로 감사 목록에 남겼다: UNH6월·GreatBlue7월은 경선 전/방법 미확보, UNH8월·9월은 원문 PDF403으로 수치/방법 재검증 미완료다. UNH9월 자료의 API등록일10/8을 실제 조사일9/17–21로 바꾸거나 최근 조사로 사용하지 않았다. 기관이 허위라는 판정은 아니다.

현재7일·14일 적격 조사는 **0건**, 하원5곳은 **현재 수집/검색 범위에서 검증된 기명 본선 조사 미확보**다. 조사 자체의 부재를 전수 단정하지 않는다. CT05 등의 모델 전망·정당 일반선호·경선 결과를 여론조사로 전환하지 않았다. AAPOR 참여나 기관 수로 상중하 정확도 등급을 만들지 않는다.

## 금융·공식 공개 검색 파이프라인

하원13명 중10명 금융ID연결, 현재 후보의 FEC **O범주** 관측5/5구. 이번에 FEC 금액을 재수집하지 않았고 기존 금액과 원래 기준일을 보존했다. U단일후보IE·V/W hybrid·후보캠프 수입·주별 공시는 합산하지 않는다. 경선/본선/미확인 코드별 금액 유지, 반대액을 상대 지지액으로 옮기지 않는다.

[SEEC 공식 독립지출 검색](https://seec.ct.gov/eCrisReporting/SearchingIndependentExpenditure.aspx)을 무키·무로그인 공개 **읽기 검색 POST**로 연결했다. ViewState/cookie는 해당 세션 메모리에서만 사용하고 공개 파일에 저장하지 않는다. 신고·재설정 기능을 사용하지 않는다. 2026신고연도·Governor·최대100행·정정이력표시 안함의 검색에서 실제10행/1페이지를 수집했다. `usa_governor_finance_audits/2026/CT.json`에 원문 보고서링크·수신일·보고금액·지지/반대 대상 필드를 **감사 전용**으로 남겼다.

이 검색은 부지사 Bysiewicz와 경선 전 Erin Stewart, 일반 paid/unpaid 비용까지 반환한다. 현재 Fazio 이름과 일치하는1행도2025년 수신/2026신고연도·rootID0·정정 자료로 독립성/단계/정정 연결이 미확인이다. 검색 결과가 있다는 이유로 본선 슈퍼팩 금액으로 발행하지 않았다. 주지사 후보별 지지/반대 합계는 **null**, 상태 `collected_normalization_held`다. 마지막 검색 수신일7/7은 주지사 IE최신 공시일을 뜻하지 않는다. 추가로 보고서별 독립지출 항목·원본/정정 계보·후보의 공시상 신원·선거 단계를 확인해야 금액 공개가 가능하다.

## 갱신·자동화 경계

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state CT --as-of YYYY-MM-DD
python3 refresh_governor_finance_audit.py --state CT
python3 refresh_governor_source_access.py --state CT
python3 refresh_state_evidence.py --state CT --as-of YYYY-MM-DD
```

기존 전국/주별 polling수집기가 신규 API기록을 후보·출처·기간·모집단 검사 후 자동 평가한다. 등록 기관의 신규 API관측은 `partial`이며 이번 원문 수치 대조 완료 상태를 자동 상속하지 않는다. 미등록 기관/새 원문 발표는 별도 검토가 필요하다. 두 보완 원문은 매번 PDF 지문을 재확인하며 장애/변경 시 원래 날짜의 참고 자료로 이월한다. 후발 API동일 파동은 수치·표본·의뢰자 일치 시1건, 충돌 시 갱신 실패/이전 자료 보존이다.

SEEC수집기는 자동 실행 가능한 감사 CLI이며 **주지사 금액 자동 집계 완성/정기 Actions 설치가 아니다**. 기존 polling workflow는 이 기준 브랜치에서 월요일06:10KST 주간이고 일일 변경은 별도 #489 통합 범위다. 이번 작업은 workflow를 수정하거나 수집·배포workflow를 dispatch하지 않았다. 전국 polling workflow가 주별state_evidence 파일까지 자동 재빌드하는지는 별도 운영 연결이 필요하다. 새API키·유료 권한은 필요하지 않았다.

## 검증·보존

로컬 polling329 + finance68 + federal6 + JS51 = **454개 통과**. 금융 지도 합계(2026:576race/4,842candidate-race/16,265source기록), `check_deploy_chain.py`(39workflow), `git diff --check` 통과. GitHub PR 검증 결과는 게시 후 기록한다. 의미 있는 CT 회귀검사14개: fusion/부지사 제외/잘못된 선거구·정당/명부ID/원문지문/방법·모집단·최초/후속질문/동일파동충돌/7·14일/SEEC검색만 수행/페이지 예산/잘못된금액·날짜/후보금액null.

타주 500poll레이스·55누적이력·49주index와 기존 금융/주공시/감사 4649파일을 SHA/구조 비교해 보존했다. 다른 주·국가 지도와 글로벌 기준일·금융index·주별처리순서 파일도 유지했다. 글로벌poll기준일10/8, FEC마지막성공 `2026-10-08T08:23:14.889991+00:00`, 금융index `2026-10-08T10:27:35.080057+00:00` 그대로다. CT조사별 기준일/조회receipt만10/9갱신했다.

공개 CT evidence: `usa_election_state_evidence/2026/CT-0517ddc13d6b9e86.json`. `live_sources_reviewed_partial`은 검토된 부분 자료라는 뜻이며 하원여론조사·주지사금액·전국수집완결을 뜻하지 않는다. D그룹 다음 **MD**.
