# 2026 관심 주 주지사 독립지출 연결 상태

2026-10-02 기준. `FEC_API_KEY`는 연방 선거용이며 주지사 공시의 공통 키가 아니다. 주 공시 독립지출을 연방 `Super PAC`과 같은 유형으로 표기하지 않는다. 금액 미수집은 0달러가 아니다.

| 주 | 공식 출처 | 후보별 지지·반대 자동 집계 |
|---|---|---|
| AZ | [Spotlight 공개 API](https://spotlightv2.arizona.vote/Reporting/Api) | 미연결. 공식 문서는 후보·직위별 독립지출 조회를 설명하지만 직접 API 요청은 Cloudflare 403. |
| FL | [선거자금 DB](https://dos.fl.gov/elections/candidates-committees/campaign-finance/campaign-finance-database/) | 미연결. 일반 지출 검색을 후보 대상 독립지출로 전환하지 않음. |
| GA | [공시 검색](https://media.ethics.ga.gov/search/Campaign/Campaign_ByExpenditures.aspx) | 미연결. 검색/내보내기는 가능하나 지출자 유형·대상 후보·정정 매핑 미검증. |
| MI | [MiTN 공시](https://www.michigan.gov/sos/elections/disclosure/cfr) | 미연결. 연간 거래 다운로드가 있으나 직접 요청은 타임아웃. |
| NV | [선거자금 검색](https://www.nvsos.gov/SOSCandidateServices/AnonymousAccess/CEFDSearchUU/Search.aspx) | 미연결. 후보 대상 독립지출 추출 경로 미검증. |
| NY | [공시 포털](https://publicreporting.elections.ny.gov/Home/Home) | 미연결. IE 검색·CSV 기능은 있으나 자동 수집 요청 403. |
| PA | [연도별 전체 내보내기](https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/campaign-finance-data) | 미연결. 공개 expense 파일에는 지지·반대 대상 후보 필드가 없어 이 파일만으로 계산 불가. |
| TN | [선거자금 검색](https://apps.tn.gov/tncamp/) | 미연결. CSV 내보내기는 있으나 후보 대상 독립지출 필드 미검증. |
| TX | [TEC 야간 CSV](https://www.ethics.texas.gov/data-reports/campaign-finance/downloadable-database/) | **어댑터 작성, 실자료 미발행**. CAND의 단일 주지사 수혜 DCE만 부분 집계. 1GB ZIP의 범위 조회 중 CloudFront 403으로 실자료 재검증 실패. |
| WI | [CFIS](https://cfis.wi.gov/) | 미연결. IE 신고 검색/거래 추출 경로 미검증. |

노스캐롤라이나는 [2026 선거 목록](https://www.ncsbe.gov/voting/upcoming-election)에 주지사가 없으므로 2026 수집 대상 10곳에 포함하지 않는다. 주지사 선거가 있는 해에는 별도로 연결해야 한다.

텍사스 어댑터는 `build_governor_finance.py --cycle 2026 --state TX`로 실행한다. 원본 ZIP을 검증된 경로로 확보한 경우 `--tx-local-archive`를 쓸 수 있다. 수집이 끝나면 기존 `build_superpac_map.py`가 `TX_governor` 부분 자료를 지도 JSON에 연결한다. 정기 `refresh_superpac.py`에는 아직 TX를 넣지 않았다. 공식 원본의 실제 행과 정정 반영을 성공적으로 재검증한 뒤 활성화해야 한다. 실패 시 기존 공개 파일은 보존한다.

다음 구현 기준은 주별로 동일하다: 대상 후보·지지/반대·지출액·고유 신고 ID·최신 정정본·원문 링크를 모두 확인해야 금액을 발행한다. 지출자 유형이 불명확하면 `state_independent_spender_unclassified`로 유지한다. 선거구나 정당은 지명 추측으로 보완하지 않는다.
