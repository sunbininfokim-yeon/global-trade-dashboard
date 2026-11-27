# PE/CR 공개 공시 주석 후보 파일럿

Gemini는 이미 사람이 추려 놓은 공개 DART/SEC 표에서 **행 ID와 계정 역할 후보**만 고른다. 공시 검색·HTML/PDF 파싱·주석 자동승격·가치평가·해석 생성은 하지 않는다. PE/CR 카드, 기존 금융 게이팅, Worker/UI, GitHub Actions, 배포 경로는 바꾸지 않는다.

`공개 표 행 묶음 → 모델에 표/행/열 이름만 전달 → 행 ID/역할 후보 → 원본 셀 첨부 → 원문 대조 및 검토 → 별도의 승인된 PE/CR 입력`

| 프로필 | 추출 후보 |
|---|---|
| `shipbuilding` | 기말 확정 수주잔고, 기간 신규 확정수주 |
| `machinery` | 순재공품, 순원재료, 주석 총재고 |
| `retail_wholesale` | 순매출채권, 공급업체 매입채무, 동일 범위 순상품매입액 |
| `it_services` | 비용 처리 R&D, 내부 개발비 자산화 증가액 |
| `industrial_earnings` | 손익 이자비용, 별도 유형자산 감가상각·무형자산 상각 |

포괄 합계나 범위가 불분명하면 후보를 생략하도록 요청한다. 모형이 숫자, URL, `verified` 등을 반환하면 응답을 거부한다. 등록된 행 ID라도 같은 행 중복, 기간·범위·통화 불일치, 잔액/기간금액 혼동은 거부한다. 이 검사는 문서 내용의 회계 의미까지 보증하지 않는다. 예를 들어 `Financing costs`를 이자비용이라고 잘못 선택한 경우는 검토 단계에서 탈락해야 한다.

## 파일과 실행

`tests/fixtures/pe_cr_gemini_itt_2025_rows.json`에 SEC ITT FY2025 10-K 주석 9에서 옮긴 공개 금액과 원문 위치가 있다. `*_replay.json`은 직접 작성한 모형 응답 예시이며 실제 Gemini 출력이 아니다. 아래 명령은 `scripts/dart` 디렉터리에서 실행한다.

```sh
python3 scan_pe_cr_notes.py tests/fixtures/pe_cr_gemini_itt_2025_rows.json \
  --replay tests/fixtures/pe_cr_gemini_itt_2025_replay.json
```

생성 모델 권한이 있는 `GEMINI_API_KEY` 또는 `AI_STUDIO_API_KEY`를 실행 환경의 시크릿으로 주입한 경우에만 공개 표 한 건을 호출할 수 있다. `GEMINI_NOTES_MODEL`에는 해당 프로젝트에서 사용 가능한 모델 ID를 지정한다(또는 `--model`). GitHub 저장소 시크릿은 로컬 셸에서 바로 읽을 수 없다. 기존 정책/의회 워크플로가 같은 시크릿을 임베딩에 쓰더라도 생성 권한·쿼터가 정상임을 뜻하지 않는다.

```sh
python3 scan_pe_cr_notes.py tests/fixtures/pe_cr_gemini_itt_2025_rows.json --send-public-rows
```

API 키는 헤더로만 전달한다. 해당 플래그는 표 제목·행·열 레이블이 공개 자료라는 확인이다. 원문 PDF, 셀 금액, 회사 식별자, 문서 URL, 임의 메타데이터는 요청 본문에 넣지 않는다. 표 레이블에 내부 메모나 미공개 정보가 없는지 실행 전에 확인한다. 최대 60행, 1회 호출, 자동 재시도·리디렉션·파일 업로드·검색 도구 사용 없음. 출력은 stdout에만 쓰고 스케줄이나 캐시는 추가하지 않는다.

결과 `kfa-note-candidates/1`은 검토용이며 계산 엔진의 `kfa-pe-cr-reviewed/1` 스키마와 호환되지 않는다. 사용하려면 리뷰어가 원문 접수번호·표·행·열·기간·단위·연결 범위, 계정 정의·중복 여부를 대조하고 별도의 승인 묶음을 작성한다. 이 파일럿의 결과를 스키마 이름만 바꿔 엔진에 넣지 않는다.

## 실호출 확인 기준

첫 실행은 공개 ITT 표 한 건으로 제한한다. 예상 후보는 재공품 125.2, 원재료 411.8, 총재고 671.9(백만 달러)이며, 2024 비교열과 제품 재고는 제외한다. 인증/쿼터/응답 오류는 별도 확인하고 자동 재시도하지 않는다. 후보가 일치하더라도 회계 승격·화면 노출은 별도 작업이다. 실호출 뒤 국내 조선·유통의 공개 표로 오탐과 누락을 별도 평가한다.

근거: [Google 구조화된 출력 API](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=ko), [ITT 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/216228/000021622826000012/itt-20251231.htm).
