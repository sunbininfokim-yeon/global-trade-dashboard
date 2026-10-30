# VA 공식 명부·여론조사·기존 FEC 연결 인수 — 2026-10-09

사용자의 다음 state 요청으로 B그룹 **버지니아(VA) 한 주**를 처리했다. 브랜치 `codex/va-state-evidence-20261009`, 기반은 미병합 Draft PR #505의 `5b4436b2894cac2bb93afd97314820dc2c0a14c2`다. #492의 Claude 배포 준비를 보존하고 CO 이후 별도 stacked Draft PR을 제출한다. UI·workflow·LETF 편집, 병합·배포·수동 Actions 실행은 없다. 다음 새 주는 **AK(알래스카)**이며 이번에 시작하지 않았다.

## 공식 후보와 선거 범위

[VA ELECT 11월3일 연방 후보 명부](https://www.elections.virginia.gov/casting-a-ballot/candidate-list/november-3-2026-gen-elect-federal-offices/)를 실제 HTTP200 수집했다. HTML SHA256 `0fd2ca4913f0eba111e695025e50ea20a41da2a3390d623450ef6b503877f967`, **하원11구·36명 + 상원1석·2명**이다. 상원은 Mark R. Warner(DEM)와 Bert Mizusawa(REP). **2026 주지사 선거는 없으므로 신규 조사·금액을 생성하지 않는다.**

하원 소수정당·무소속까지 포함하고, 공식 약칭과 기존 검토된 법적 이름을 같은 주·직위·선거구·정당의 명시적 별칭으로 연결했다. 기존 FEC ID는 증명된 것만 유지했다. 기명후보 전수 확인이나 별도 투표용지 인증·당선 인증을 주장하지 않는다. 각 선거에 DEM/REP를 포함한 복수 후보가 있어 명부상 무경쟁/무투표 당선으로 판정한 곳은 없다.

새 `va_ballot.py`는 공식 페이지 제목·열·연방 직위·11구 전체·정당·후보 중복을 검증한다. 주소·전화·이메일은 반환/공개하지 않으며 원본 HTML도 커밋하지 않는다. 이 파서는 검토에 재사용할 수 있지만 자동 후보명부 승인/배포 워크플로를 새로 설치한 것은 아니다.

[VA ELECT 5월8일 공지](https://www.elections.virginia.gov/news-releases/supreme-court-of-virginia-voids-april-21-redistricting-referendum-2.html)는 연방상·하원 모두 경선8월4일, 본선11월3일 및 기존 선거구 경계 유지를 명시한다. 2026년2월23일 후보 bulletin과 함께 대조해 일반 본선 조사 허용 시작을 경선 다음날 **8월5일**로 정정했다. 제안되었다가 무효화된 새 지도 번호를 현재 구역으로 사용하지 않는다. 지도 실물/UI 변경은 이번 범위가 아니다.

## 실제 조사 — API12건 중 원문 대조2건 편입

VoteHub 전체회기 API를 실제 재호출하여 **VA12건**을 검토했다. Post/Schar 두 파동만 정확한 레코드 지문으로 승인했다. 같은 기관의 미래 발표 전체를 승인한 것은 아니다.

| 지역구 | 원문 최초 후보 응답 | 조사·처리 |
|---|---|---|
| VA01 | Taylor50 · Wittman46 | 9/23–28,609LV. 원문 Q2·방법론·발행기관 기사 대조 |
| VA05 | Perriello45 · McGuire51 | 9/23–28,600LV. 원문 Q3·기사 대조. API의 Perriello46은 특정 원본 지문에서만45로 정정하고 원래46/근거 보존 |

[발행기관 원문](https://washingtonpost.com/documents/c5cba6fd-7edb-4550-93c3-0580e8084bfb.pdf)은 독립적인 주 전체 조사 두 건이 아니라 **서로 다른 지역구의 별도 표본**이다. 표본틀, 확률선정, 모드, 가중, LV확률 모형, 질문 순서, 기투표·leaner 포함 및 비후보 응답을 확인했다. 모드 비율은 두 구역 합산 보고이므로 구역별 비율로 주장하지 않는다. 전체 RV에 투표 확률을 부여하여 LV 결과를 만들었고 별도 LV부분표본 수를 임의 계산하지 않았다. 발표 오차4.5/4.6pp·design effect1.31/1.34를 기록하며 정확도 등급·유의성·당선 확률로 바꾸지 않는다.

원문 PDF는 웹 도구로 전체 수치·방법론을 읽었으나 직접 바이너리 다운로드는 timeout/HTTP2 장애, 페이지 이미지 렌더는 cache miss였다. **PDF SHA256·시각 검증 성공을 만들지 않았다.** 후보 명부와 API의 실제 바이트/정규화 지문, 원문 URL/문항과 접근 상태를 감사 JSON에 남겼다. 원문 수치 검토는 텍스트·발행기관 기사 대조 범위다.

10월9일 기준 두 조사는 **7일 창 밖 / 14일 창 안**이다. 기본7일에는 우세색이 없고, 선택14일에는 각 지역구에서 단일 기관의 수치상 우세만 보여준다. 한 파동을 링크 수만큼 중복 계산하지 않으며 선거 승자로 취급하지 않는다.

보류10건:

- VA01 PPP2025년 named/HMP 조사: 경선 전 역사 자료, 원문 방법론 미확보. 같은 파동의 정당47/47과 Ragnar2026년 정당42/44는 named후보 선거조사가 아니므로 구분한다.
- VA02 Tulchin7/9–13: [HMP 의뢰기관 공개 발표](https://www.thehousemajoritypac.com/news/hmp-poll-elaine-luria-has-a-clear-path-to-victory-in-va-02)의 초기47/47은 확인했다. 정보 제공 후48/46은 제외했다. Politico 메모403, 의뢰기관 본문에는 API의700LV와 전체 방법론을 검증할 자료가 없어 **원문 발견·방법론 미확보**로 보류한다. 경선 전 자료로 현재 승패에 사용하지 않는다.
- 상원 TPSI6건: 원문 기사 `996 weighted LV`, 공개 첫 시트 `996 weighted RV`, API의RV/LV표와 후보별 문항이 충돌한다. LV3건의 n은 null이며996을 복사하지 않는다. Farington/Williams/Moran은 현재 공식2명 명부와 달라 가상·경선 전 구도를 현 본선으로 바꾸지 않는다. 기관이 허위라고 단정하지 않으며 이번 문항·모집단 검증 실패로 보류한다.
- API 밖 VA05 Expedition 메모(7/29–8/1,602LV, 초기44/47/미정9)는 실제 PDF를 확보했다. 후보 홍보 후47/44와 부정정보 후 결과를 초기응답으로 사용하지 않는다. 모드·표본틀·가중·전체문항·LV화면이 없고 경선 전이라 이번 current관측에 편입하지 않았다. 문서와 발표문의 후반 정보제공 수치 충돌도 초기응답과 분리한다.

이번 점검에서 원문 적격 조사가 없는 상원·나머지 하원9곳을 조사 부재로 전수 단정하지 않는다. VA02와 상원은 **발견했으나 검증 보류**, 나머지는 **현재 수집/검색 범위에서 적격자료 미확보**다.

## 후보별 연결 결과

금액은 이미 수집한 FEC O범주 Super PAC 후보 대상 독립지출의 부분 관측이다. **이번에 FEC 신규 금액을 재수집하지 않았다.** U단일후보 IE·V/W hybrid·후보 캠프 수입과 합치지 않는다. 경선/본선/UNKNOWN을 보존하며 반대액을 상대 지지액으로 옮기지 않는다.

하원30/36명 ID연결, O범주 현재 후보 관측 **6/11구(VA01·02·05·07·10·11)**. 상원2명 ID연결, Warner에 O범주 관측이 있다. 나머지 금액이 없다는 것은0달러를 뜻하지 않는다. ID 미연결6명은 J. Matt Baker(VA02), Makiba A. Gaines(VA03), Joan E. Andrews Bell(VA04), Taner E. Demirci Lopez·Joshua E. Ertle(VA07), Shelly M. Arnoldi(VA08)다. 검토된 이름·정당·보고ID와 연결 보류를 감사 JSON에 기록했다.

| 대상 | 공식후보 수 | 조사 | O범주 현재 후보 관측 |
|---|---:|---|---|
| USA:VA:house:01 | 2 | 원문 적격1건 · 14일만 | Shannon L. Taylor / Robert J. "Rob" Wittman |
| USA:VA:house:02 | 4 | 현재 편입 없음 | Elaine G. Luria / Jen A. Kiggans |
| USA:VA:house:03 | 4 | 현재 편입 없음 | O범주 관측 없음 |
| USA:VA:house:04 | 3 | 현재 편입 없음 | O범주 관측 없음 |
| USA:VA:house:05 | 3 | 원문 적격1건 · 14일만 | Tom S. P. Perriello |
| USA:VA:house:06 | 2 | 현재 편입 없음 | O범주 관측 없음 |
| USA:VA:house:07 | 6 | 현재 편입 없음 | Eugene S. Vindman |
| USA:VA:house:08 | 4 | 현재 편입 없음 | O범주 관측 없음 |
| USA:VA:house:09 | 2 | 현재 편입 없음 | O범주 관측 없음 |
| USA:VA:house:10 | 3 | 현재 편입 없음 | Suhas Subramanyam |
| USA:VA:house:11 | 3 | 현재 편입 없음 | James R. Walkinshaw |
| USA:VA:senate | 2 | 현재 편입 없음 | Mark R. Warner |

FEC 마지막 성공일 `2026-10-08T08:23:14.889991+00:00`, 금융index 생성일 `2026-10-08T10:27:35.080057+00:00`를 보존했다. 원래 전역poll기준일10/8과 조회시각도 유지하며 VA 개별race의as_of만10/9다. 전수/새 수집으로 오해하지 않도록 source_dates와 state capture를 같이 읽어야 한다.

## 자동 실행과 검증

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state VA --as-of YYYY-MM-DD
python3 refresh_state_evidence.py --state VA --as-of YYYY-MM-DD
```

전국/주별 수집기는 새 API기록을 가져와 후보·원문·출처·기간 계약으로 검사한다. 이 두 원문 검토는 **기존 특정 API 레코드**에 연결한 것이며 미래 뉴스 전체를 자동 발견하거나 새 기관을 자동 승인하지 않는다. 원문별 수치 정정은 실제 원본 지문이 그대로일 때만 적용한다. 새 API키·유료권한은 필요하지 않았다.

현재 이 브랜치의 `us_election_polls_refresh.yml`은 **매주 월요일06:10KST**다. 이번 state 작업에서 일일 일정·본선 자동배포를 설치하지 않았으며 해당 변경은 workflow담당과 별도로 조율해야 한다. PR자동 검증과main수집/배포를 구분한다. 사용자 배포 보류를 유지한다.

로컬 **polling315 + finance68 + federal6 + JS51 = 440개 통과**, 금융 원본/지도 합계(2026:576race·4,842candidate-race·16,265source기록) 및 diff공백 검사 통과. 실제 API갱신2건·보류10건이고 변경된원본/미래파동·표본·후보·정당·경계·원문정정·7/14일·무투표판정·연락처제외를 검사했다.

타주 **494poll레이스·53누적이력·49주index**, **금융·주공시·감사4,649파일**, 타주/타국지도·전역날짜·금융index의 보존을 SHA/구조 비교했다. 별도state심화검토는 부분관측이며 전국완결을 뜻하지 않는다. 자동 `next_state_to_review`는 선행 미완료심화 상태인IA를 가리킬 수 있으나 신규주처리 순서의 다음은 **AK**다. 선행 장애는 숨기거나 완료로 바꾸지 않았다.
