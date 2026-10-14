# 아이오와 IA — 2026-10-09 한국시간 후속

사용자 지시로 #492 이후 별도 브랜치 `codex/ia-state-evidence-20261009`에서 처리한다. 기준 커밋061c8f72, #492가 아직 OPEN이므로 해당 PR에 의존하며 #492에는 추가하지 않는다. UI·workflow·LETF·병합·배포 변경 없음. 실제 수집일은 UTC10/8이며 기존 전국 `as_of`/기준일10/8과 맞춰 IA만 갱신했다. KST 날짜만 앞서게 하여 UI의 공통 기간 계약을 어기지 않는다.

## 확보와 보류

- API39개 IA 대상 레코드 검토. 상원3관측(CNN/SSRS·Fox·Marist), 주지사4관측(동일3기관+기존Siena), 하원4구는 통과관측없음. 이번 원문 재검토6관측. 기존Siena 검토시점은 보존한다.
- 최근7일 상원 CNN1기관 Hinson45/Turek43, 주지사 CNN1기관 Sand51/Lahn42. 단일기관 참고 우세이며 승자/당선확률이 아니다.
- 14일 상원 LV2기관(CNN REP우세/Fox DEM우세)의 승패 건수가 같아 tie. Marist RV는 합산하지 않는다. 주지사 LV3기관(CNN/Fox/Siena)이 DEM우세이며 Marist RV별도.
- CNN Iowa801 RV 전체의 투표확률 가중 LV, L2등록표본624+SSRS확률패널177, 온라인/전화, 표본오차4.2pp/95%/설계효과포함. Ohio760 표본·4.5오차를 복사하지 않는다. 초기와leaner 합산문항이며 기타/미정 보존.
- Fox Iowa전체1204 RV(유선183/휴대전화733/text-to-web288), LV하위표본1008/오차3pp. 발표10/1과 APIcreated10/2를 분리한다. Q3/Q12 및 LV/RV열을 대조했다. 기존기관그룹 beacon_shaw를 유지해 새조사의중복기관 집계를 막는다.
- Marist9/17–20 RV1050, 원문표/발표방법을 확인. 상원50/42, 주지사54/42. 전체문항 표본·모집틀/가중 세부 미공개는빈칸으로 표시한다. 예상승자(Hinson59 등)를투표의향으로쓰지 않는다.
- 하원01 PPP2025자료는본선 최신자료 아님; Bullfinch7월자료는의뢰기관원문방법 미확보. 하원02 HMP/GSG 원문에초기James46/Mitchell45는있으나표본·모집·가중 미공개로보류. 하원03의2025년 정보제공후/경선비교 자료를현본선최신으로승격하지 않는다. API감시는4구 유지하며미확보를0%나승패로 채우지 않는다.
- Quantus9/30·Turek내부9/9원문발견 경로도 감사에 남기되 수치/방법 전체검토 없이 자동편입하지 않는다. API밖 모든 신규발표의전수발견·자동검토완료는 보장하지 않는다.

## 공식 후보와 외부지출

공식사이트가현재연결한8/19 Iowa SOS 본선명부 첫페이지를 재수집·SHA대조했다. 하원01 3명/02 4명/03 2명/04 2명, 상원3명(Hinson/Turek/ThomasLaehn LIB), 주지사2명(Sand/Lahn)·부지사대진을연결했다. 개인주소·연락처 미복사. 공식인증 명부와 FEC등록을분리하며기입/후속철회/당선결과는별도 검증이다. 이번6선거는모두정당간경쟁이며무투표당선·확정승자로판정하지 않는다.

기존연방공시 O누적은하원4/4·상원1/1 연결. 새FEC 금액재수집은하지않았고 기존공시의수집일·원래기준일·정정/중복·O/U/V/W 구분을유지한다.

Iowa Ethics공식사이트가연결한공개IE보고서 화면의 JavaScript에서 실조회API `POST https://webapp.iecdb.iowa.gov/api/publicreports/ie`와요청형식을 확인했다. 로그인/키 없이실제응답을검증했고 `refresh_iowa_ie_reports.py`로반복실행할수있다. API의 all-year1510건 중최신100건을단일응답으로보존했다. 날짜동률의페이지간ID겹침을실제로확인했으므로여러페이지를중복제거해전수인척하지않는다. 최대100건/부분확보표시·사이클경계/보고서ID/호스트/응답크기/미래날짜/실패시마지막파일보존을검사한다.

목록에는후보·금액·지지/반대가없고PDF에거래가있다. 최신10 PDF를읽고정확한두후보이름문자열은미발견이었다. 위원회별명 매핑·전체/과거신고·정정거래 미검토이므로주지사지출0을뜻하지않으며후보별금액은null이다. 주정부IE보고서발견과연방SuperPAC O/후보캠프일반비용을구분한다. 이번 주지사는 `public_endpoint_reachable_mapping_required`, 주전체 `live_poll_sources_reviewed_finance_mapping_required`로미완료를명시한다.

## 공개산출·검증

- 최신IA파일 `usa_election_state_evidence/2026/IA-2aa900d62525ef29.json`.
- 원문감사 `usa_election_poll_release_reviews/2026/IA-primary-20261009.json`.
- 공개신고목록 `usa_governor_ie_report_indexes/2026/IA.json`, 건강상태 `usa_governor_ie_report_index_status/2026/IA.json`, PDF검토범위 `usa_governor_ie_report_reviews/2026/IA-20261009.json`, 접근/연결 `usa_governor_source_access/2026/IA.json`.
- polling245·금융63·연방6·JS51=365검사통과. 새12검사는Iowa/Ohio표본구분·FoxRV/LV·14일양기관반대우세동률·공식소수후보/무경쟁·미확인하원보류·신원/기관 변경·공시100건부분상한·중복/불완전응답·PDF호스트·미래/타사이클·오류시원래자료보존을검증한다.
- 타주 500 poll레이스·42 누적이력·49주index·기존금융/감사/접근파일 4640개와 전역원래날짜 보존. 타주후보명부를 변경하지 않음.

실행:
```bash
cd "New for anti/scripts/election_watch"
python3 refresh_state_polls.py --state IA --as-of 2026-10-08
python3 refresh_iowa_ie_reports.py
python3 refresh_governor_source_access.py --state IA
python3 refresh_state_evidence.py --state IA --as-of 2026-10-08
```

새보고서목록은수집기에연결했지만Actions설치와PDF후보별거래금액자동매핑은미구현이다. 운영수집에설치할경우실행기와건강상태검사를별도연결해야한다. #489 일일여론조사workflow는이번범위밖이다. 이후사용자추가지시에따라별도PR로이어가며 TX/WI/AZ/NV 예약을대신실행하거나시간변경하지않는다.
