# NM C그룹 원문 조사 연결 — 2026-10-09

사용자 AL→NJ→**NM**→NH 순서. NJ #511의 f59138e0에서 `codex/nm-evidence-20261009` / `us-nm-state-evidence-20261009`로 분리했다. UI/workflow/LETF/병합/배포/배포 dispatch는 변경·실행하지 않았다.

## 후보와 금융

하원3·상원1·주지사1, 현행 검토 명부10명을 대조했다. [공식 후보 포털](https://candidateportal.servis.sos.state.nm.us/CandidateList.aspx?cty=99&eid=2917)은403으로 접근 실패했다. 따라서 [Green Papers 보조 명부](https://www.thegreenpapers.com/G26/NM)/기존 NGA와 후보 신원을 재검토했으나 공식 인증 완료로 승격하지 않았다. 기명후보 전수 완결·무투표 당선 검증도 아니다. 경선6/2 다음6/3부터 본선 비교를 적용한다.

주지사 Greggory Hull과 원문 Gregg Hull은 보조 명부의 `Greggory D. "Gregg" Hull`로 명시적 동일인 검토했다. 퍼지 이름 매칭은 추가하지 않았다. 기존 NM02의 Gabriel Vasquez/Gabe Vasquez, Greg Cunningham 약칭을 공식명처럼 보고된 장명과 함께 유지해 과거 조사 연결이 끊기지 않게 했다. 상원 Ben Ray Lujan/Luján·Larry E. Marker/Larry Marker도 명시적 검토를 유지했다.

하원 FEC ID6명·상원2명, 현재 후보의 연방 O범주 관측 하원3/3·상원1/1 연결. 기존10/8 금융 스냅샷이며 **FEC 새 금액을 수집하지 않았다**. O/U/V/W·경선/본선/기타·정정/중복 원래 계약은 보존한다.

[NM CFIS](https://www.cfis.state.nm.us/media/)와 [공개 CSV 내려받기](https://www.cfis.state.nm.us/media/CFIS_Data_Download.aspx)는 키 없이 접근 가능함을 확인해 재실행 가능한 접근 검사를 연결했다. 이것은 후보별 IE 금액 수집기가 아니다. 캠프 수입/일반 비용/모든 PAC 지출을 주지사 지지·반대로 변환하지 않았다. 수혜 후보·방향·기간·정정/중복 검증을 위한 공시 매핑은 미완료이며 주지사 금액은 null. 작업 상태는 `live_poll_sources_reviewed_finance_mapping_required`이다.

## 실제 여론조사

[SurveyUSA #28031 전체 원문](https://results.surveyusa.com/client/PollReport_main.aspx?g=6e6ded19-6ad8-4379-8fa9-6a15dfa99052)을 직접 읽었다. 기존 링크는630바이트 frameset이며 실제 증거는 main frame에 있다. 본문 전체 수치·표본·방법·문항을 검토했다.

- 9/25–30, 총800성인→673RV→**567LV**, KOB-TV 의뢰,10/5발표.
- Q9 주지사 Deb Haaland47 / Gregg Hull41 / 미정12: API에 없는1건을 원문 보완으로 추가.
- Q10 상원 Ben Ray Luján54 / Larry Marker36 / 미정10: API의576 표본을 **567로 검토 정정**. 원래 API576·레코드 지문·정정 근거를 공개 관측에 보존.
- 기존 NM02 8/28–9/2 SurveyUSA554LV Vasquez46/Cunningham43은 누적 관측으로 보존. 현재 기간 수치로 갱신하지 않음.

45% Cint 비확률 패널과55% Aristotle 전화 표본(30% IVR,25% SMS-to-web)을 혼합하고 성별·연령·인종·교육·주택 소유로 가중했다. Q9/10은 호감도와 투표 가능성 문항 뒤, 이슈/데이터센터 문항 전의 최초 후보 선택이다. 보고±5.1pp는 기관의 credibility interval이며 고전적 오차범위·정확도/유의성 인증이 아니다.

10/9 기준 최신 두 관측은 **7일0건 / 14일각1건**. 14일 DEM 수치상 우세는 단일 기관 참고이며 당선 예측/확률이 아니다. BSP Research 주지사·Research & Polling 상원은 원문/출처 검토 미완료로 신규 편입하지 않았다. NM01/03 기명조사 미확보는 조사 자체 전수 부재가 아니다.

원문 보완은 검토한 정확한 HTML URL1개만 허용한다. 스크립트·ASP.NET 숨은 속성을 제외한 가시 본문 지문을 재확인하고, 다른 보고서/빈 frameset/변경된 수치는 참고 이월 처리한다. 같은 조사 API가 뒤늦게 들어오면 수치·표본·의뢰자 일치 때만1건으로 병합하고 충돌은 실패시켜 마지막 유효 자료를 보존한다. 표본 정정은 정확한 원래 API 레코드 지문에만 적용하며 변경 레코드는 재검토한다. 새로운 비API 발표 전체를 자동 발견한다고 주장하지 않는다.

## 검증·재실행

```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state NM --as-of YYYY-MM-DD
python3 refresh_governor_source_access.py --state NM
python3 refresh_state_evidence.py --state NM --as-of YYYY-MM-DD
```

원문 표본 정정·약칭·7/14일·변경 레코드·성인 표본 오용 방지·공식출처 오인 방지·HTML 지문/frameset·후발 API중복/충돌·금액 null·기존 NM02 보존 회귀10개를 추가. election_watch 전체 **465검사 통과**. 타주501poll레이스·58누적이력·49주index·기존금융/공시/접근4,652파일과 금융index·타주지도·국가·원래 글로벌 날짜 보존 비교 통과. 새 키/유료권한 사용 없음.

다음 사용자 지정 주 **NH**. 주지사 공시 정규화와 공식 명부 재시도는 후속 미완료 항목으로 남긴다. GitHub 검증은 PR 게시 후 별도 확인한다. 병합·배포 보류 유지.
