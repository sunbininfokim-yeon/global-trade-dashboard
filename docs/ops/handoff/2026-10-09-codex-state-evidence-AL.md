# AL C그룹 선거 증거 연결 — 2026-10-09

사용자가 순서를 **AL → NJ → NM → NH**로 변경했다. CT의 예전 D그룹 MD 다음 순서는 현재 신규 작업 순서가 아니다. `us-al-state-evidence-20261009` / `codex/al-evidence-20261009`는 CT #507 tip `f3703e80`에서 분리했다. AK 및 #489 통합 작업 폴더는 수정하지 않았다. 이번 변경은 AL 데이터·수집기·검사만이며 UI/workflow/LETF/병합/배포/배포 dispatch를 수행하지 않는다.

## 공식 후보와 특별 경선

[AL SOS 2026 공식 선거 페이지](https://www.sos.alabama.gov/alabama-votes/voter/election-information/2026)의 민주당8/26·공화당8/26·9/2수정 인증 PDF 전체를 내려받아 관련 후보 표를 렌더해 대조했다. 8/28수정은 주의회51구, 9/2수정은 주상원25구이며 별도 연방 후보 변경으로 추정하지 않았다. 9/2통합 PDF p3의 연방 명부를 확인했다. 무소속 인증은 주의회 후보만 포함해 연방/주지사에 섞지 않았다. 전체 PDF 지문·페이지는 후보 계약에 기록했다.

| 선거 | DEM | REP |
|---|---|---|
| 하원01 | Clyde Jones | Jerry Carl |
| 하원02 | Shomari C. Figures | Rhett Marques |
| 하원03 | Lee McInnis | Mike Rogers |
| 하원04 | Amanda N. Pusczek | Robert B. Aderholt |
| 하원05 | Andrew Sneed | Dale W. Strong |
| 하원06 | Maurice Mercer | Gary Palmer |
| 하원07 | Terri Sewell | Ammie Akin |
| 상원 | Everett Wess | Barry Moore |
| 주지사 | Doug Jones | Tommy Tuberville |

하원7·상원1·주지사1, 공식18명. `complete_active_agency_listing`은 현재 기관 명부 범위이며 미확인 기명 후보 전수/무투표 당선/당선결과를 뜻하지 않는다. AL04 미확인 기명 후보는 별도로 보존했다. 공식 복수 후보이므로 무투표 당선 표시를 생성하지 않았다.

**하원01·02·06·07은 재획정 후8/11특별 경선**이므로 본선 비교 시작8/12, 나머지 하원·상원·주지사는6/16결선 다음6/17로 보수적으로 설정했다. 7월 AL02 본선 가정 조사를8/11이후 확정 후보 조사로 바꾸지 않는다. Aderholt/Sewell 이름 변형의 금융ID를 동일 주·구·정당·검토된 별칭으로 연결해 하원14명 ID가 연결된다. Rhett Marques의 옛 AL01 신고 금액을 AL02로 옮기지 않았다. 상원 기존2명 ID의 출처를 유지했다.

## 여론조사 원문 보완

VoteHub AL API5건을 실제 조회하고 특정 원문 PDF3개에 해당하는5관측을 검토 편입했다. 원문 전체 지문·표본·방법·의뢰자·발표일·최초 문항 및 동일파동 충돌 검사를 적용했다. 5건은 모두 **참고 전용**, 현재7일/14일 우세 집계0건이다.

| 발표 | 선거·응답 | 모집단·기간 | 제한 |
|---|---|---|---|
| [yes.everykid 원문](https://yeseverykidfoundation.org/wp-content/uploads/YESF_Alabama-Statewide-Survey_Topline.pdf) | 주지사 Tuberville49/Jones41; 상원 Moore47/Wess32 | 601LV,7/8–11 | text-to-web57%/online43%; 모집 프레임·확률·가중 공개 부족 |
| [APA/Napolitan 원문](https://alabamapolicy.org/wp-content/uploads/2026/10/0926-SURVEY-DATA.pdf) | 주지사 Tuberville50/Jones37; 상원 Moore54/Wess33 | 800RV,9/21–25 | RMG 제공, Alabama Policy Action 의뢰; mode/frame/weight 공개 부족·당파 의뢰 |
| [DCCC AL02 원문](https://dccc.org/wp-content/uploads/2026/08/DCCC-Polling-Memo-Rep.-Shomari-Figures-in-Toss-Up-Race-in-AL-02.pdf) | Figures46/Marques46 | 421LV,7/29–30 | 전화+text-to-web; 민주당 내부·8/11특별 경선 전 역사 참고 |

yes.everykid의 정수 합계/반올림은 원문49를35+13=48로 교체하지 않았다. 최초 Q15/Q16과 정책 질문 이후 응답을 분리했다. DCCC의 **AL02 안 주지사 응답 Jones48/Tuberville45는 주 전체 조사가 아니므로 주지사에 편입하지 않았다**. RMG의9/25조사 종료일을10월 게시/등록일로 바꿔 최신으로 만들지 않았다. AAPOR 참여·기관 수·의뢰자만으로 정확도 등급을 산출하지 않는다.

후발 API 같은 파동은 값·표본·의뢰자 일치 시1관측, 충돌 시 실패/기존 자료 보존이다. 2025 Cygnal 가정 조사는 원문 재검증 미완료·경선 전으로 보류했다. [HMP/Tulchin AL02 9/9](https://www.thehousemajoritypac.com/news/hmp-poll-shomari-figures-tied-with-rhett-marques-in-al-02)은 원문 HTML의 최초47/47·정보제공 후50/47을 확인했으나 표본/모집단/방법 미공개로 `discovered_held_releases`에만 남겼다. Impact Research6월 조사도 원문 미검증으로 보류했다. 하원 나머지6구는 현재 수집/검색 범위에서 검증된 기명 본선 조사 미확보다. 실제 조사의 부재를 전수 단정하지 않는다.

## 금융·AL FCPA 파이프라인

기존 FEC O범주 현재 후보 관측은 하원2/7·상원1/1이다. FEC를 새로 수집하지 않았고 기존 금액과10/8원래 기준일을 보존했다. O/U/V/W 및 선거 단계별 계약 유지. 캠프 수입/반대액을 지지액으로 변환하지 않는다.

[공식 FCPA 다운로드](https://fcpa.alabamavotes.gov/page.request.do?page=page.acfPublicDownloadData)의 공개 manifest → 2026 Expenditure ZIP → 공식 layout key를 연결했다. 무키·무로그인 GET만 사용한다. 서버 체인과 로컬 Python CA 호환 문제는 검증을 끄지 않고 시스템 인증서 신뢰를 사용하는 curl로 처리한다. 엄격한 HTTPS host·시간/크기/단일파일/헤더·연도·날짜·필수값 제한을 적용했다. 원시 지급처·주소 CSV는 공개/커밋하지 않았다.

실제 감사: **42,186행, 구조·날짜 검사 통과41,191행, 제외995행**(파손948/날짜·금액44/식별·상태3). 유효 행 중 후보캠프32,858/PAC8,333, 정정 표기1,325, 유효 ID중복0이다. 이는 완전한 고유 공시 수나 주지사 IE 건수가 아니다. 공식 key에서 `CandidateName`은 **지출한 캠프 소유자**이며 독립지출 수혜후보/지지반대 필드가 없다. 정정 계보·대상·방향·단계 미확보로 주지사 금액은 **null**이다. manifest기준10/9·일반 지출 신고 최신10/8을 주지사 IE 최신일로 표시하지 않는다. 상태는 `collected_normalization_held`, 금액 집계 완료가 아니다.

## 반복 실행·운영 경계

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state AL --as-of YYYY-MM-DD
python3 refresh_governor_finance_audit.py --state AL
python3 refresh_state_evidence.py --state AL --as-of YYYY-MM-DD
```

신규 API 기록은 기존 정책으로 후보·선거·품질 검사를 받아 자동 평가된다. 새 발표가 이번 특정 원문 확인 상태를 상속하지 않는다. 미등록 신규 발표는 추가 검토가 필요하다. 특정 원문 보완은 지문 불일치/접근 실패 시 원래 날짜 자료를 유지한다. FCPA는 자동 실행 가능한 **감사** 수집기이며 후보별 금액 자동 집계·정기 workflow 설치 완료가 아니다. 일일 workflow 변경은 별도 #489 통합 범위다. 새 API 키/유료 접근은 필요하지 않았다.

## 검증·보존·인수

polling340 + finance68 + federal6 + JS51 = **465개 통과**. 금융 지도 원장 일치(2026:576race/4,842candidate-race/16,265source기록), 배포 연결39workflow 읽기검사·`git diff --check` 통과. AL 회귀11개는 실제 원문 지문/동일파동/참고판정/하원과 주전체 분리/manifest·ZIP·CSV·null·실패 보존을 다룬다.

타주497poll레이스·56누적이력·49주index 및 기존 금융/주공시/감사 **4,651파일**을 SHA/구조 비교해 보존했다. 다른 주/국가 지도·글로벌 기준일·금융index·공개 순서 파일도 그대로다. AL 조회 receipt만10/9, 기존FEC최종성공 `2026-10-08T08:23:14.889991+00:00` 유지. 공개 evidence `usa_election_state_evidence/2026/AL-e77db4bf486be640.json`, 상태 `live_sources_reviewed_partial`.

기반 #507 미병합일 때 AL PR은 CT브랜치 대상으로 쌓는다. 병합/배포는 보류하며 검토 가능한 PR만 게시한다. 다음 신규 주 **NJ → NM → NH**. AL 주지사 대상 IE의 공시별 정규화와 보류 조사 방법론은 후속 보강 항목이다.
