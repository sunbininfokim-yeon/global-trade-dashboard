# 월별 파이프라인 운영 보강 — 2026-10-12

사용자 요청: 이전 점검의 2번(한국 인증/게이트웨이 연결)은 제외하고 수정.
UI·Worker·wrangler·공용 deploy·Secrets는 변경하지 않았다. 실수집·배포를 실행한 결과가 아니다.

## 수정한 동작

- `runner.temp`를 job-level `env`에서 참조하던 파싱 오류 수정. #496과 같은 최소 수정이 포함되므로 #496 병합 시 중복 부분을 확인한다. actionlint 1.7.7과 공식 릴리스 체크섬으로 GitHub expression context를 검사한다.
- 매일 03:37 UTC(12:37 KST). 16일 batch0, 24일 batch1, 28일 batch2는 기존 전체 원천 갱신. 나머지는 날짜 기반 3배치 순환으로 **양자 무역만 최대 60건**, 요청 간격 3초. 무료 GitHub 러너와 원천 API 쿼터는 별개다.
- `checkpoint.json`에 전체 계획을 요청 전 저장. 미완료 계획은 월이 바뀌어도 교체하지 않는다. 완료된 쿼리는 반복하지 않으며, 동일 cycle의 새 관측 후보는 완료 후 추가할 수 있다.
- 빈 응답은 해당 cycle 조회가 끝난 것으로만 취급하고 다음 월 cycle에 재확인한다. 기존 데이터 유지, 0 생성 금지. 계약/형식/부분 응답 오류는 cycle당 3회 후 보류하고 다음 cycle에 재검토한다. 인증/429/네트워크 오류는 즉시 중지하고 대기열을 유지한다.
- 실제 `pending_jobs`, `empty_jobs`, `deferred_error_jobs`를 공개 상태에 분리한다. 실행 완료는 전 국가·상품 확보 완료가 아니다. 한국 키 미설정은 선택 원천의 `auth_required`이며 타 원천의 실행 완료를 가로막지 않지만 전체 커버리지는 여전히 partial이다. 한국 인증 코드는 변경하지 않았다.
- 실행 상태·정규화 체크포인트·공식 정책 페이지 점검 결과를 같은 90일 artifact에 보관한다. 마지막 전체 원천 실행일을 이어받아 일일 재개가 월간 수집 미실행을 숨기지 못한다.
- 국가×HS×X/M 최신 관측 월, 원천/단위별 공개 적격 월·보류 월·중간 관측 공백, 총량/양자 최신 월 불일치를 기록한다. 날짜 일치만으로 비교 가능 또는 분모 적격을 주장하지 않는다. HS revision/FOB/CIF/단위 검증과 점유율은 기존 partition 계약을 따른다. 총계와 양자 자료를 서로 보간하지 않는다.
- 매 갱신/재개 시 저장소 최신 분류별 수출통제 catalogue로 기존 파티션까지 재대조한다. 통계의 `retrieved_at`/관측 월은 변경하지 않는다. 전체 원천 실행 때 allowlist 공식 발표 2곳을 최대 4요청으로 점검한다. 페이지 해시 변화는 법률 개정 증거가 아니다.
- 과거 발표 문서가 최신 catalogue의 원문 URL·HS 범위·시행일을 덮어쓰지 못하게 했다. 누락된 catalogue module은 게시를 중단한다. 미매칭은 `not_assessed`, 법적 clearance는 null을 유지한다.
- 일일 watchdog은 **배포된** 상태 JSON을 검증하고 상품별 경고를 artifact로 남긴다. HTML SPA fallback은 정상 JSON으로 받아들이지 않는다. 명시적 User-Agent 사용. 관측 경고는 수집 장애와 구분되며, 실패한 실행/오래된 전체 갱신은 watchdog 실패다.

## 게시·배포 경계

현재 방식은 검증 → 데이터 PR → 사람의 merge → 기존 production deploy다. 자동 merge나 main 직접 push는 추가하지 않았다.

열린 `Monthly commodity trade update` 데이터 PR이 있으면 추가 PR을 매일 만들지 않는다. 수집은 계속 진행하고 최신 후보 전체를 `commodity-trade-candidate-<run_id>` artifact에 30일 보존한다. 기존 열린 PR을 자동 덮어쓰지 않는다. 오래된 PR을 병합한 뒤 다음 정상 실행이 누적 체크포인트로 최신 데이터 PR을 제안한다. 즉, artifact 최신 ≠ main 최신 ≠ 배포 최신.

원천 장애가 있어도 기존 유효 데이터가 release contract를 통과하면 partial 상태로 후보/PR을 남길 수 있다. 로컬 health 진단은 경고로 명시하고, 구조적 release validation은 반드시 성공해야 한다. 배포 watchdog은 실제 장애/미배포 상태를 별도로 알린다.

## 검증과 운영 인수

오프라인 Python 전체 회귀검사, 6개월 rollover/60건 분할의 미니 모형, 빈 응답·429·오류 보류·역사 데이터 보존, 품목별 오래된 원유 감지, 공개 보류/0 분리, 수출통제 재대조의 통계 vintage 보존을 검사한다. Node 기존 연간/월간·게이트웨이 계약과 소유권 범위도 검사한다. API quota를 소비하는 운영 수집은 이번 변경 검증에 포함하지 않는다.

실제 검증: Python 142, Node 36, 소유권 8 통과. actionlint 전용 workflow 3개 통과, 기존 deploy chain 39개 연결 유지. `monthly_coverage.py`로 기존 입력에서 공개 coverage를 오프라인 재생성한 뒤 실제 release gate 통과. 국가 수(대상27/관측15/양자12)와 통계 관측값·시점은 바뀌지 않았다. coverage의 generated_at만 새 감사 시각이다. SAU 원유 World 2025-09/양자 미확보는 그대로이며 석유금액 bulletin 2026-06과 섞지 않았다.

병합 후 첫 수집에서 확인:

1. refresh에 실제 job이 생성되는지(이전 jobs=0 문제 해소).
2. checkpoint artifact에 `active_plans`와 상태/정책 점검 파일이 있는지.
3. 3일 뒤 같은 배치의 pending이 감소하는지. empty/deferred는 데이터 확보로 세지 않는다.
4. 데이터 PR 검토·병합 및 production deploy 후 공개 `commodity_trade_refresh_status_v1.json`이 JSON으로 응답하는지.
5. 최신성 날짜를 generated_at이 아닌 실제 관측 월로 대조. SAU 석유 수출금액 bulletin을 HS2709 원유 수량/상대국 데이터로 대체하지 않는다.

한국 인증 연결은 사용자 제외 요청 때문에 보류. 이번 변경은 한국 운영 연결이 완료됐다는 근거가 아니다.

검증 근거 문서: [GitHub context availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability), [actionlint checks](https://github.com/rhysd/actionlint/blob/main/docs/checks.md).
