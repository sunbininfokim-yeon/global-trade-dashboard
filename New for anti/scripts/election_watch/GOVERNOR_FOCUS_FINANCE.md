# 2026 관심 주 주지사 독립지출 연결 상태

2026-10-04 기준. `FEC_API_KEY`는 연방 선거용이며 주지사 공시의 공통 키가 아니다. 주 공시 독립지출을 연방 `Super PAC`과 같은 유형으로 표기하지 않는다. 금액 미수집은 0달러가 아니다.

| 주 | 공식 출처 | 후보별 지지·반대 자동 집계 |
|---|---|---|
| AZ | [Spotlight 공개 API](https://spotlightv2.arizona.vote/Reporting/Api) | 미연결. 공식 문서는 후보·직위별 독립지출 조회를 설명하지만 직접 API 요청은 Cloudflare 403. |
| FL | [선거자금 DB](https://dos.fl.gov/elections/candidates-committees/campaign-finance/campaign-finance-database/) | 미연결. 일반 지출 검색을 후보 대상 독립지출로 전환하지 않음. |
| GA | [공시 검색](https://media.ethics.ga.gov/search/Campaign/Campaign_ByExpenditures.aspx) | 미연결. 검색/내보내기는 가능하나 지출자 유형·대상 후보·정정 매핑 미검증. |
| MI | [MiTN 공시](https://www.michigan.gov/sos/elections/disclosure/cfr) | 미연결. 연간 거래 다운로드가 있으나 직접 요청은 타임아웃. |
| NV | [선거자금 검색](https://www.nvsos.gov/SOSCandidateServices/AnonymousAccess/CEFDSearchUU/Search.aspx) | 미연결. 후보 대상 독립지출 추출 경로 미검증. |
| NY | [공식 일일 공개 API](https://data.ny.gov/resource/e9ss-239a.json) · [IE 통지 검색](https://publicreporting.elections.ny.gov/IndependentExpenditure/IndependentExpenditure) | **실자료 부분 연결(브랜치)**. 검토된 IE 지출자 8곳 중 후보별 실제 지급액 75건. 직접 통지 API는 403이나 일일 공개 API는 키 없이 성공. |
| PA | [연도별 전체 내보내기](https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/campaign-finance-data) | 미연결. 공개 expense 파일에는 지지·반대 대상 후보 필드가 없어 이 파일만으로 계산 불가. |
| TN | [선거자금 검색](https://apps.tn.gov/tncamp/) | 미연결. CSV 내보내기는 있으나 후보 대상 독립지출 필드 미검증. |
| TX | [TEC 야간 CSV](https://www.ethics.texas.gov/data-reports/campaign-finance/downloadable-database/) | **감사 전용, 금액 미발행**. CAND에 거래별 지지/반대 필드가 없음. 수혜자 표기를 지지액으로 추정하던 초안 보정. ZIP 조회도 CloudFront 403. |
| WI | [Sunshine](https://campaignfinance.wi.gov/) | 미연결. 공식 기관이 안내한 현재 공시 시스템으로 출처 갱신. 직접 요청은 DNS 실패. |

노스캐롤라이나는 [2026 선거 목록](https://www.ncsbe.gov/voting/upcoming-election)에 주지사가 없으므로 2026 수집 대상 10곳에 포함하지 않는다. 주지사 선거가 있는 해에는 별도로 연결해야 한다.

뉴욕 수집: `python3 build_governor_finance.py --cycle 2026 --state NY`. 연방 키는 필요 없다. 공식 IE 통지 포털의 2026년 전체 CSV 490건에서 실제 주지사 이름이 있는 지출자 ID 8개를 검토하여 `config/governor_ie_filers/2026/NY.json`에 기록했다. 원본 CSV SHA256·조회 조건·행 수를 남겼으며 개인 주소가 있는 원본 파일은 커밋하지 않는다. 후보와 정당은 9월 17일 수정된 공식 본선 인증 명부 3쪽을 기준으로 하며 약식 이름은 명시적으로 검토한 별칭만 허용한다. 교차 정당 투표용 ballot line도 명부에 보존한다.

공개 API의 2026년 주지사 배분 100건 중 75건을 발행했다. 나머지는 미검토 지출자 13건(일반 정당위원회도 포함), 모호한 버전/복수 대상 11건, 방향/후보 미확정 1건이다. 연결 없는 누적 Schedule R은 합산하지 않는다. Schedule R의 S/O, 부모 Schedule F, 신고 문맥과 정정 플래그, 단일 대상, 같은 지급액을 모두 확인한다. `r_amend=Y`는 정정된 신고 표기이며 폐기된 원본이라는 뜻으로 해석하지 않는다. 복수 버전 연결은 ID의 크기로 최신을 추정하지 않고 제외한다. 지급액은 F에서 한 번만 가져오며 하도급 상세·미지급 잔액은 더하지 않는다([공식 핸드북](https://elections.ny.gov/system/files/documents/2023/08/campaignfinancehandbook.pdf) 93쪽). 환불 미차감 총지출이며 **주지사 선거 전체 총액이 아니다**.

2026-10-03 12:10:56 UTC 원본 갱신 기준, 포함 범위의 Kathy C. Hochul 지지 $13,014,850.23, Bruce A. Blakeman 지지 $3,016,811.10·반대 $2,380,037.00이다. 다른 방향의 포함 행이 없는 경우 전체 공시에서 0달러라는 결론을 내리지 않는다. 75건 중 47건은 내려받은 IE 통지의 후보·지출자·일자·금액·방향과도 일치했다. 일일 API와 24시간 통지의 범위·지연은 서로 다르므로 두 파일을 더하지 않는다.

`refresh_superpac.py`는 해당 사이클의 NY IE registry가 있을 때 NY를 수집한다. 신규 지출자와 향후 사이클은 별도 검토가 필요하다. API 실패·스키마 변경·페이지 중 원본 갱신은 기존 파일을 보존한다. 후보별 지도 금액 및 출처 제한사항 전달까지 임시 출력 폴더에서 검증했으며, 저장한 실자료는 `public/data/usa_governor_finance/2026/NY.json`이다. 브랜치가 병합된 다음 정기 워크플로가 실행되어야 운영 지도에 연결된다. **병합·배포는 하지 않았다.**

텍사스 `build_governor_finance.py --state TX`는 감사 스키마를 지도용 JSON으로 발행하지 않고 오류로 종료한다. 로컬 원본 ZIP 옵션도 이 제약을 우회하지 않는다. 원문 거래별 방향을 확보한 뒤 발행 어댑터로 바꿔야 한다.

GitHub 정기 작업은 활성 상태이며 평시 월요일·10월 월/금(17:25 KST)이다. 최근 10월 2일 실행은 2026 연방 15,813건·CA 222건 수집과 발행이 성공했으나, 2024 FEC 재수집의 반복 continuation cursor로 최종 실패했다. Actions 실행 자체가 막힌 상태는 아니다. 과거 사이클 수집 오류를 숨기거나 불완전 자료로 덮지 않는다. 이번 PR에서는 워크플로 파일과 FEC cursor 로직을 바꾸지 않았다.

다음 구현 기준은 주별로 동일하다: 대상 후보·지지/반대·지출액·고유 신고 ID·최신 정정본·원문 링크를 모두 확인해야 금액을 발행한다. 지출자 유형이 불명확하면 `state_independent_spender_unclassified`로 유지한다. 선거구나 정당은 지명 추측으로 보완하지 않는다.
