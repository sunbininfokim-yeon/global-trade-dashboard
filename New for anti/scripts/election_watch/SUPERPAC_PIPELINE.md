# 미국 슈퍼팩 분석 파이프라인

## 기존 파이프라인 검토 (2026-09-06)

- `run_refresh_cycle.py`는 공개 원문을 수집하고 검토 완료된 profile/extracted 자료로 board/calendar/manifest를 재생성한다. 일반 원문을 자동으로 정치적 사실로 승격하지 않는다.
- `build_board.py:build_usa_state_drilldown`은 현직 연방 의원·주지사·주 의회 요약과 주별 2026 경선 진행을 결합한다. 현직 명부는 도전자·탈락 경선 후보를 포괄하지 않는다.
- `usa-district-map.js`는 기존 선거구 도형과 현직 정당을 표시한다. 선거자금, 광고 집행 위치, 다음 선거 경계의 정본이 아니다. 구획 개편 시 지도의 구획과 향후 공시 선거구가 다를 수 있다.
- 기존 election_watch 전용 자동 갱신 workflow는 발견되지 않았다. 새 수집기는 검토된 기존 보드를 덮어쓰지 않고 별도 데이터 계약을 사용한다.
- `country-explorer/index.js`에서 미국 국가 화면과 주별 화면에 분석 패널을 연결했다. 화면은 주·전국, 공시 사이클, 직위, 정당, 후보/단체, 선거유형, 하원 선거구로 필터링한다.

## 구현 범위

`FEC candidate master → 후보 ID 명부`와 `OpenFEC processed Schedule E → 정정 상태·중복·memo 검증 → 후보 × 정당 × 선거유형 × 단체 × 주/선거구 집계 → 주별 JSON → 미국 분석 화면`.

- 연방 하원·상원·대통령만 자동 수집한다. 주 의회·시장·법무장관 등은 제외한다.
- FEC 위원회 유형 O만 슈퍼팩이다. U(단일후보 독립지출), V/W(하이브리드), 기타 PAC·정당·개인 및 분류 불명은 별도 범주로 보존한다.
- 모든 정당 코드 및 경선 후보를 보존한다. REP를 화면에서 공화당으로 표기한다. 후보 등록은 실제 경선 참가, 투표용지 등재, 사퇴 여부 또는 현재 출마의 증거가 아니다.
- 후보 명부는 공시 사이클의 두 해를 선거연도로 신고한 등록 후보다. 지출에만 나타나는 후보도 지출 행에는 보존한다. 다음 대선 초기 자금은 현 사이클 지출에 `P2028`처럼 신고된 유형 그대로 남을 수 있지만 미래 후보 전체 명부를 의미하지 않는다.
- `P2026/G2026/S2026` 등 선거 코드 및 원문 명칭을 보존한다. 특별선거·결선 코드의 의미를 일반 경선 또는 본선으로 임의 변환하지 않는다.
- 대통령은 US 전국, 하원은 주+두 자리 지역구(전역 00), 상원은 주 단위. 상원 seat class 및 별개 동시 선거 식별은 미완이다.
- 금액은 정수 센트. 마이너스 정정액을 보존한다. 지지·반대 금액은 별도 집계하고 반대 지출을 경쟁 후보/정당의 지원금으로 재배분하지 않는다. 월별 흐름은 공개배포일 우선, 없으면 지출일을 사용한다.
- 후보/슈퍼팩별 지출과 원본 링크를 제공한다. 모금액·현금잔고·기부자 분석·최종 자금 제공자 추적 및 득표/당선확률 모델은 이번 구현에 포함하지 않는다.

## 중복·품질 정책

- `/schedules/schedule_e/?cycle=2026&most_recent=true&is_notice=false`의 정기보고를 사용한다. API가 most_recent=null도 반환할 수 있어 그 행은 합산에서 제외하고 품질 카운트를 남긴다.
- 긴급 24/48시간 보고는 제외한다. 따라서 최근 독립지출이 정기보고까지 누락될 수 있다. 모든 시점의 실시간 총지출을 의미하지 않는다.
- `sub_id`가 같은 행만 중복 제거한다. 이름·금액·날짜가 같아도 별개 거래이면 유지한다. 수정신고 계보는 FEC processed의 최신 여부에 의존한다.
- memo·삭제 행을 제외한다. 후보 식별·주·선거구·금액을 검증하지 못한 행은 합계에 넣지 않고 사유별 카운트를 남긴다. 이름 유사도로 후보를 결합하지 않는다.
- 분류는 반환된 FEC 위원회 정보 기준이며 유형 변경의 사건시점 이력까지 복원하지 않는다.
- API 전체 커서 순회를 완료해야 발행한다. 반복 커서·페이지 한도·429/네트워크 실패는 성공으로 처리하지 않는다. 기존 발행 index를 유지하고 작업이 실패한다. 원본 응답과 API 키를 로그/공개 파일에 저장하지 않는다.
- 주별 파일은 내용 해시를 포함한 이름을 사용하고 마지막에 index를 원자 교체한다. 화면은 선택한 주만 읽는다. 오래된 해시 파일은 독자가 사용할 수 있어 자동 삭제하지 않는다. 저장 용량 관리 시 현 index 참조와 보존 기간을 확인해 별도 정리해야 한다.
- 수집시각과 마지막 포함 신고일을 모두 표시한다. 72시간 넘게 갱신되지 않으면 화면에서 지연을 표시한다. `ready`는 연방 정기보고 처리 상태이며 전국 주지사 커버리지 인증이 아니다.

## 주지사: 현재 자동 수집 미지원

50개 주 모두 `unsupported`와 금액 null로 시작한다. FEC는 연방 선거 자료이고 주별 공시 시스템·보고 기준·식별자가 다르므로 전국 주지사 슈퍼팩 총액을 FEC에서 만들 수 없다. 예컨대 Washington PDC는 독립지출과 electioneering communication을 함께 다루므로 통째로 슈퍼팩으로 부르면 안 된다.

공식 자료를 검토·정정 처리한 행은 아래 형태의 JSON으로 입력할 수 있다. 이는 수동 정규화 입력 계약이며 주별 원본을 자동 변환하는 어댑터는 아니다. import 후에도 `partial`이다. `reviewed`와 `is_current`는 입력 작성자의 검토 확인이며 프로그램이 원본 진위를 판정하는 기능이 아니다. 아래 TEST 자료는 예시로만 사용한다.

```json
{
  "schema": "usa_governor_ie_import_v1", "cycle": 2026,
  "state": "WA", "coverage": "partial",
  "records": [{
    "source_id": "WA:TEST", "candidate_id": "WA:CANDIDATE-TEST",
    "candidate_name": "TEST", "party": "DEM", "office": "governor", "state": "WA",
    "committee_id": "WA:COMMITTEE-TEST", "committee_name": "TEST",
    "category": "state_independent_expenditure_committee", "election_type": "P2026",
    "direction": "support", "amount_usd": "10.25", "as_of": "2026-09-06",
    "source_url": "https://www.pdc.wa.gov/replace-with-official-filing",
    "classification_source_url": "https://www.pdc.wa.gov/replace-with-classification-evidence",
    "reviewed": true, "is_current": true
  }]
}
```

주지사 후보 전체 명부 수집, 자동 정정/삭제 처리, 단체 유형 판별은 아직 미구현이다. 주 공시를 단체 모금액이나 후보 캠프 직접 후원액과 혼합하지 않는다.

## 실행 및 운영

```bash
cd 'New for anti/scripts/election_watch'
python3 -m unittest discover -s tests -p 'test_superpac*.py' -v
# FEC_API_KEY 또는 DATA_GOV_API_KEY 환경변수를 안전하게 설정한 환경에서 실행
python3 build_superpac.py --cycle 2026
python3 build_superpac.py --cycle 2024
python3 build_superpac.py --cycle 2026 --governor-import /path/to/reviewed-state.json
```

`--cycle`은 짝수 공시 사이클이다. 2026은 2025–2026 공시를 읽는다. 2028 대선은 2028 공시 사이클을 별도로 실행한다. 한 사이클을 다시 수집해도 다른 사이클 index는 보존한다. 주별 검토 입력을 `config/governor_ie/2026/*.json`에 저장하면 정기 실행에서도 자동으로 읽는다. 각 파일은 해당 사이클 하위 폴더에서 읽고 실행 사이클과 일치해야 하며 불일치는 실패로 처리한다. 별도 경로의 `--governor-import` 파일은 재실행 때 다시 전달해야 한다. 같은 주는 하나의 통합 파일만 허용한다.

`.github/workflows/us_superpac_refresh.yml`은 일일 08:25 UTC(17:25 KST) 및 수동 실행을 정의한다. `FEC_API_KEY`가 없으면 기존 GitHub Secret `DATA_GOV_API_KEY`를 사용한다. api.data.gov는 참여 API 간 키 재사용을 지원한다. 사용자가 GitHub에 FEC_API_KEY 등록을 완료했고, 제공된 키의 HTTP 200 인증과 2026 사이클 전체 수집을 로컬에서 확인했다. 키 값은 파일이나 산출물에 저장하지 않았다. DEMO_KEY는 전체 수집에서 거부한다.

전체 수집 성공 → 결과만 main에 커밋 → 기존 deploy.yml을 명시적으로 호출한다. GITHUB_TOKEN으로 발생한 push는 일반 push workflow를 자동 실행하지 않으므로 dispatch가 필요하다. 키 오류·브랜치 보호·Actions 권한 문제는 실패로 보이게 한다. 이 브랜치는 배포하거나 main에 병합하지 않았다. 2026 공시 사이클의 실제 공개 index와 주별 파일을 포함한다. 데이터가 없는 새 설치에서는 `--initialize`로 unconfigured index만 만들 수 있다.

## 검증 기록

- Python 집계/수집 테스트: 15개 (정정, 긴급보고, memo, 중복, 음수·센트, 정당·경선 분리, 전역 선거구, 대선 전국화, 등록 후보, 주지사 검토 입력, 페이지 실패, 키 비노출, 원자 발행).
- 2026 FEC 후보 master 실다운로드: 필터 후 4,485명. 현직 의원 명부보다 넓은 등록 후보 집합임을 확인했다.
- OpenFEC 실제 지출 응답 2건: O/W 분류 및 P2026/S2026 코드, 정기보고/정정 필드 파싱 확인. 표본은 전국 총계가 아니며 공개 산출물로 배포하지 않았다.
- 브라우저 합성 데이터 검증: 화면 로드, 주 선택, 경선 필터 적용 시 본선 반대 지출 제외 및 등록 후보 표기 확인.
- 실제 CA 자료 브라우저 검증: 전체 213개 조합에서 P2026 경선 135개로 필터링되고 정당별 금액이 갱신됨을 확인했다. 주지사 선택 시 자동 미지원과 집계 없음이 표시되고 금액 0으로 대체되지 않는다. REP/GOP 원문 코드는 구별해 표시한다.
- 2026 전국 공시 수집 완료: API 156회, 입력 15,405행 → 집계 13,860행. 제외: memo 1,114, 후보 ID/직위 충돌 167, 범위 밖·미기재 직위 191, ID 미해결 72, 주 미해결 1. 전체 처리행 수와 입력행 수가 일치한다.
- 포함 유형: 슈퍼팩(O) 7,875행, 하이브리드(V/W) 4,919행, 기타 999행, 단일후보 독립지출(U) 67행. 후보·단체·정당·선거유형 조합 2,379개.
- 주/DC/준주/전국 57개 파일(합계 약 2.28MB)의 월별 합계→각 행 합계→전체 집계가 일치함을 확인했다. 최대 파일은 CA 약 270KB, TX 약 250KB로 선택한 지역만 다운로드한다. 원본 개별 거래 대신 조합별 집계/월별 수치만 포함한다.
- 수집시각 2026-09-06 09:28 UTC; 최신 포함 신고일 2026-08-20. 처리된 정기보고만 포함하므로 이를 최신 실시간 지출 총액으로 해석하지 않는다.
- 운영 배포 검증은 아직 수행하지 않았다.

## 공식 근거

- [OpenFEC API 및 schema](https://api.open.fec.gov/developers/)
- [FEC Schedule E API 구현](https://github.com/fecgov/openFEC/blob/develop/webservices/resources/sched_e.py)
- [FEC 위원회 유형](https://www.fec.gov/campaign-finance-data/committee-type-code-descriptions/)
- [후보 master 정의](https://www.fec.gov/campaign-finance-data/candidate-master-file-description/)
- [긴급 독립지출 파일의 중복 경고](https://www.fec.gov/campaign-finance-data/independent-expenditures-file-description/)
- [대선 다중 주 지출 보고](https://www.fec.gov/help-candidates-and-committees/filing-pac-reports/multistate-independent-expenditures/)
- [Washington PDC 공개 공시](https://www.pdc.wa.gov/political-disclosure-reporting-data)
- [api.data.gov 키/한도](https://api.data.gov/docs/developer-manual/)

## 주별 공식 접속 주소

검증된 접속 방식은 `config/usa_state_campaign_finance_sources_v1.json`에 보관한다. 50개 주 전체 연락처는 [FEC 공식 디렉터리](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/combined-federalstate-disclosure-and-election-directory/)를 사용한다.

| 주 | 공식 접속처 | 방식 |
|---|---|---|
| MA | [Massachusetts OCPF](https://api.ocpf.us/developers) | public_json_api |
| WA | [Washington PDC](https://www.pdc.wa.gov/faq/do-you-have-data-api-programmers) | soda_odata_api |
| CA | [California Secretary of State](https://www.sos.ca.gov/campaign-lobbying/helpful-resources/raw-data-campaign-finance-and-lobbying-activity) | daily_bulk_zip_tsv |
| TX | [Texas Ethics Commission](https://webservices.ethics.state.tx.us/search/cf/) | bulk_csv_and_search |
| FL | [Florida Division of Elections](https://dos.fl.gov/elections/candidates-committees/campaign-finance/campaign-finance-database/) | search_tsv_export |
| NY | [New York State Board of Elections](https://elections.ny.gov/campaign-finance) | public_reporting_search |
| CO | [Colorado Secretary of State TRACER](https://tracer.sos.colorado.gov/PublicSite/SearchPages/PublicNonScheduledFilingsSearch.aspx) | public_reporting_search |
| OR | [Oregon Secretary of State ORESTAR](https://sos.oregon.gov/elections/campaign-finance/Pages/search-campaign-finance.aspx) | public_reporting_search |

MA는 공식 API 문서에서 인증/키 불필요를 명시한다. WA는 SODA/OData 지원을 명시한다. 나머지 다운로드·검색형 자료에 API 키가 있다고 가정하지 않는다. FEC_API_KEY는 주 공시 공통 키가 아니다.

MA의 공식 OpenAPI에서 `/miscreports/iepacs/reports/{year}`(독립지출 PAC 보고서, 연도/후보/입장 필터)를 확인했다. API 접근 가능 여부와 별개로 지출 대상 주지사 후보 ID, 정정 처리, 주 단체 유형 매핑을 구현·검증해야 한다.
