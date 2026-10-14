# 한국 관련 미국 발표·고위급 동향 (2026-10-10 검토)

## 범위와 현재 상태

사용자 요청: 미국 발표 중심, 한국 발언은 대통령·총리·장관급 이상만. 한국을 국가 단위로 살펴 통상·투자·에너지·산업 공급망을 다루되, 최근 3개월·50건 미만·페이지당 5건·최신순 숫자 페이지로 표시한다.

`country_announcements_v1.json`은 2026-07-10~2026-10-10의 **선별 검토본 18건**이다. 미국 정부 16건(무역구제 12, USTR·DOE·CBP 발표 4), 한국 김정관 장관 발언 2건. 모든 공식 발표를 망라하지 않는다. 한국의 실무자·차관급 발표와 일반 부처 홍보자료는 넣지 않았다. 영어 직함에 Minister가 있다는 이유만으로 장관급으로 인정하지 않는다.

- 미국: USTR 제조업 과잉생산 공동성명(한국 서명국), DOE 방한 후 에너지·공급망 협력 발표, USTR 강제노동 301조 발표와 CBP 신고 지침. 서로 다른 성격의 발표를 구분한다.
- 한국: 김정관 장관의 프랑스 산업대화 및 베트남 산업·핵심광물·에너지 협력 회담 발언. 장관 발언이 본문에 확인된 공식 자료만 선택했다. 행사일과 발행일을 별도로 저장했다.
- 무역구제: 품목별 최신 주요 공고를 선택했다. 같은 제품의 모든 예비·최종·정정 이력을 넣은 사건 DB가 아니다. 공표 세율이나 현행 적용률을 추출하지 않았다.

## 출처와 검증 수준

- USTR: https://www.ustr.gov/about/policy-offices/press-office/press-releases/2026/october/fourteen-economies-join-united-states-signing-joint-ministerial-statement-address-global-excess
- DOE: https://www.energy.gov/hgeo/articles/resources-relationships-america-ready-power-indo-pacific
- CBP: https://content.govdelivery.com/accounts/USDHSCBP/bulletins/421d887
- USTR 301조: https://www.ustr.gov/about/policy-offices/press-office/press-releases/2026/july/ustr-takes-action-forced-labor-section-301-investigations
- 한국 장관 발언: https://english.motir.go.kr/eng/article/EATCLdfa319ada/2728/view 및 https://english.motir.go.kr/eng/article/EATCLdfa319ada/2714/view
- Federal Register API: `conditions[term]="Republic of Korea"`, 발행일 위 범위, `order=newest&per_page=100`. 1회 응답 99건(전체1페이지) 중 제목의 한국 관련성과 품목·절차를 확인해 12건을 선택했다. 검색 결과의 북한·본문 인용만 해당하는 자료는 편입하지 않았다. 개별 원문 URL·FR 문서번호·공식 PDF URL은 JSON에 보존했다.

6건은 공식 본문 확인, FR 12건은 공식 제목·발행일 메타데이터 확인으로 표시한다. FR 본문 전체와 기업별 세율·적용 대상은 이 작업에서 검증하지 않았다. 한국산 관련 공고가 국가 전체·모든 기업의 관세라는 뜻은 아니다. 공동성명·협력 발표 역시 새 규제 시행으로 취급하지 않는다. 기존 정책 카드의 검증 범위를 이번 확인일로 덮어쓰지 않는다.

## 연결과 페이지 동작

기존 수출통제 RSS 보드와 새 선별 동향 JSON은 분리한다. 한국 상세의 기존 조치·공고 아래 `한국 관련 미국 발표·고위급 동향`을 추가했다. 새 자료 로드 실패는 경고로 표시하며 기존 화면은 유지한다.

클라이언트도 기간·발행일·공식 출처 및 한국 발언자 직급/발언 확인 필드를 검사한다. 한국 `cabinet_minister`, `deputy_prime_minister`, `prime_minister`, `president`만 허용한다. 검토자가 공식 직급을 확인해야 하며 필드 자체가 자동 사실 검증은 아니다. 최신순 고유 ID 정렬 후 최대40건을 표시한다.

국가별 발신·대상 공고와 새 동향, 전체 최근 공고 목록은 각각 5건씩 독립된 페이지 상태를 가진다. 목록이 줄면 페이지를 보정하고, 번호를 누르면 목록을 교체한다. 날짜 미상인 기존 RSS는 마지막으로 정렬하며 날짜를 지어내지 않는다. 최근3개월 검토 목록에는 날짜 미상을 넣지 않는다.

**자동 수집·자동 갱신은 이번 범위가 아니다.** 공개 JSON에 고정된 검토 기간·확인일이 표시된다. 신규 발표는 출처·발행일·한국 관련성·직급·발언 근거를 다시 확인해 후속 검토본에 추가해야 한다. AI 호출·DB 변경·임베딩·메일 발송·워크플로 변경 없음.

## 검증 및 분리

- `node --check "New for anti/export-controls.js"`
- `node --test scripts/lib/country-announcements.test.cjs scripts/lib/us-trade-policy-cards.test.cjs`: 18개 통과.
- 실제 로컬 8771 화면에서 한국 목록 18건, 1~5→6~10 교체, 최신순 및 숫자1~4 버튼 확인.
- preview 서버는 명시한 공개 파일만 loopback에서 제공한다. 운영 배포가 아니다.

시뮬레이터는 `/Users/yeoninair/Documents/trade-policy-simulator-local`의 별도 로컬 작업이며 이 PR에 포함하지 않는다. 기존 #515/#516은 정책 자료·협상 동향 PR이다. 이번 작업은 별도 후속 PR로 검토하고 병합·배포는 수행하지 않는다.
