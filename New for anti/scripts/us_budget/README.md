# 미국 예산 수집

`refresh_budget.py`는 Treasury MTS 표 1·3·6과 OMB 공식 링크의 엑셀 6종을 읽어
연간·월별 실적 및 정부안을 하나의 검증된 JSON으로 생성한다. API 키·Supabase·AI 호출은 없다.

저장소 루트에서:

```sh
python3 -m pip install -r 'New for anti/scripts/us_budget/requirements.txt'
python3 'New for anti/scripts/us_budget/refresh_budget.py' --output-dir /tmp/us-budget-staged
US_BUDGET_STAGED_DIR=/tmp/us-budget-staged node --test 'New for anti/scripts/us_budget/budget_live.test.mjs'
```

위 명령은 임시 폴더만 쓴다. 로컬 공개 JSON에 반영하려면 검증 후 실행한다.

```sh
python3 'New for anti/scripts/us_budget/publish_budget.py' --staged-dir /tmp/us-budget-staged --outcome success
```

기존 `refresh_mts.py --dry-run`은 같은 수집·검증을 임시 폴더에서 실행한다.
`--verify-snapshot`은 기존 검토본의 MTS 월별 값을 읽기 전용으로 재확인한다.

## 출력과 실패 처리

- `budget_live_v1.json`: 새 연간 표·국방 계정·최근 36개월·최신 FY 누계·출처·최근 수정 이력.
- `collection_status_v1.json`: 마지막 시도·마지막 성공·성공 데이터 ID·성공/실패 상태.
- 기존 `annual_v1.json`, `mts_live_v1.json`, `sources.json`은 변경하지 않고 대체 자료로 보존한다.

모든 수집·기간·금액 검증이 끝나야 새 금액 묶음을 atomic replace한다. 실패하면 오류 기록만 생성하고
기존 금액 파일은 보존한다. 게시 단계는 데이터 ID/해시와 발표본의 역행 여부를 다시 검사한다.
워크플로의 실패 실행도 실패 기록만 main에 반영할 수 있으므로 화면에서 실패를 숨기지 않는다.
검증 단계에서 실패한 금액 파일은 게시하지 않는다.

확인 지연 96시간·MTS 기준일 경과 65일은 화면의 점검 기준이며 공식 발행 기한 판정이 아니다.
MTS `record_date`는 회계 자료 기준일이다. 보고서를 실제로 공개한 날짜로 표시하지 않는다.

## 연간 자료 계약

OMB의 공식 Historical Tables/Supplemental Materials 페이지에서 가장 최근 FY의 링크를 찾는다.
URL의 업로드 월을 추측하지 않으며, 같은 발표본의 1.1·2.1·8.1·8.5·8.7·PBD outlays가 모두 필요하다.
새 FY의 일부 파일만 공개되었거나 표 구조·단위가 달라지면 이전 정상 자료를 유지하며 실패를 표시한다.

- 최근 5개 **완료** 회계연도를 표시한다. 진행 중 FY 누계는 연간 결산으로 승격하지 않는다.
- OMB의 실적/estimate 표기를 구분한다. 최신 완료 연도가 아직 OMB 추정치이면 해당 연도의 9월 MTS 실적을 쓴다.
- FY2027 정부안 비교는 같은 2026/04 발표본의 FY2026 정부 추정이다. 뒤의 MTS 실적과 섞지 않는다.
- 표 8.1의 십억 달러·일반 Historical Tables의 백만 달러·PBD의 천 달러를 각각 USD로 변환한다.
- 국방은 재량 051/053/054만 포함한다. 계정의 분할 행은 합치고 상위·하위 합계를 중복 합산하지 않는다.
- 정부안의 음수 Allowances와 순액을 보존한다. 미확인 금액·점선 표기를 0으로 바꾸지 않는다.
- 같은 MTS 기준일의 수정도 재검증하며, 관측 월별 금액 수정은 최근 100회 이력에 남긴다.
- 원본 XLSX/API 캐시를 커밋하지 않는다. 공개 URL·응답 해시·단위·발표본을 JSON에 함께 기록한다.

## 예산의 상태와 금액

`proposal.year.status = proposal_estimate`는 정부안의 **지출 추정(outlays)**이다.
`enacted_budget`의 확정 예산권한은 별도 근거가 아직 수집되지 않아 `status: not_collected`, `amount: null`이다.
정부안 지출 추정으로 확정 예산권한을 채우지 않는다. 집행 실적은 Treasury의 현금 수지다.
세 개의 금액은 서로 다른 개념이므로 집행률을 임의로 계산하지 않는다.

## 자동 실행과 검증

기존 `Refresh US budget monthly actuals` 예약(UTC 월~금 21:23)을 그대로 사용한다.
한국시간은 화~토 오전 06:23이며 GitHub 예약은 지연될 수 있다. 별도 예약을 추가하지 않는다.
수집 job은 contents 읽기 권한만 가지며, main 전용 게시 job만 쓰기 권한을 가진다.
PR·작업 브랜치·dry_run·verify_snapshot 실행은 main의 금액/상태를 게시하지 않는다.
동시 실행은 직렬화하며, main 충돌 시 JSON을 텍스트 병합하지 않고 검증 파일을 재적용한다.
기존 deploy.yml의 같은 workflow 이름 연결을 유지한다. 실제 병합·배포 성공은 별도로 확인해야 한다.

```sh
python3 -m unittest discover -v -s 'New for anti/scripts/us_budget' -p 'test_*.py'
node --test 'New for anti/scripts/us_budget/us_budget_data.test.mjs' 'New for anti/scripts/us_budget/budget_live.test.mjs'
```
