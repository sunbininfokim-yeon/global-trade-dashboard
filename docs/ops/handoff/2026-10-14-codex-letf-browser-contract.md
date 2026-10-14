# 2026-10-14 — Codex: 해외 LETF 구조 검사·설정 보강

## 범위와 근거

- 사용자 지적: #480 validate가 해외 LETF 브라우저의 `/선물/` 기대값에서 실패. 후속으로 상품 구조 고정 검사의 위험, 삼성 ETP 설정 불일치, 13일 수집 공백 확인 요청. #546 병합 허용.
- 기준 main `9d7e79d194d0143ad54c9c0b8050c22393d01c85`, 최신 확인 `74be3734205aee112cfe3a5c4dd912cf3a198a15`. 브랜치 `codex/letf-browser-contract`, 독립 sparse worktree. 기존 WIP 보존.
- #480은 이미 병합된 작황상태 수집 PR. 실패 job https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/37706806373/job/113082993005 . 작황 코드가 아니라 공통 해외 LETF 검사 실패. #456은 병합 없이 닫혔고 main에 옛 기대값이 남아 있었다.

## 최종 변경

- 브라우저 검사는 삼성/TQQQ의 구조값을 고정하지 않는다. 읽어 온 상품 데이터의 구조를 독립 표시 계약으로 한국어 문구에 대응시키고, 선택된 ID·이름·바로 뒤 구조 설명과 대조한다. 다른 상품 행의 문구만으로 통과하지 않는다.
- 미래의 합법적인 구조 변경을 가정한 **합성 브라우저 fixture**도 데이터와 화면이 함께 바뀌면 통과하는지 검증한다. 실제 관측 자료나 상품 변경 주장이 아니다.
- 삼성 ETP `XS3388190301` 설정의 futures를 physical_margin으로 정리. [발행사 공식 상품 페이지](https://leverageshares.com/en/etps/leverage-shares-3x-long-samsung-electronics-etp/)를 2026-10-14 확인: Physical / KRX shares, 현물 보유·margin borrowing. 별도의 공식 API POST 1회는 HTTP 403으로 실패했으며 이를 숨기거나 재시도하지 않았다.
- 보존된 공개 보드의 공식 API 자본구성은 2026-09-29 `KRX shares`. `structure_as_of=2026-09-29`, 구조만의 검토일 `structure_verified_on=2026-10-14`로 구분. 상품 전체의 기존 verified_on과 목록 전체의 verified_on을 현재 날짜로 바꾸지 않는다. 실제 구조 전환일은 미확인이고 9/29 이전으로 소급하지 않는다.

## 공백·장애 확인

- 수집기는 Yahoo 종가/거래량·FX·기준자산에 대해 as_of 이전 **110일**을 다시 조회하고 날짜/상장 ID별 upsert한다. 13일 공백은 조회 범위 안이므로 원자료가 해당 세션을 반환하면 복구 가능하다. 발행사 AUM은 반환된 날짜 있는 이력만 반영하며, 현재 보유 구성 snapshot을 과거로 채우지 않는다. 실제 네트워크 복구·완전한 공백 해소를 오프라인 테스트로 주장하지 않는다.
- 추가 파이프라인 테스트: 9/30 기존 자료 → 10/1~13 사이 반환된 8개 세션 추가 및 9/30 수정값 반영 → 중복 없음·반환되지 않은 날짜 미생성 → 후속 전체 수집 실패에서 exit 2와 failed 상태, 정규화 archive와 공개 시계열의 기존 관측 bytes 보존.
- 장애 때 '상태 파일만 커밋'이라고 단정하면 안 된다. 빌더는 보드·공개 이력·manifest도 다시 쓰고 workflow의 always 단계가 대상 파일들을 stage한다. 실제 변경 파일은 산출 diff에 달려 있다. 전체 실패 상태와 기존 관측 보존을 구별한다.
- 운영 수집 기본시점: UTC 월~금 23:35 = 한국 화~토 08:35. 2026-10-14 시점 다음 명목 일정은 **10/15(목) 08:35 KST**이며 GitHub 스케줄 실행은 지연될 수 있다. push로 update는 실행되지 않는다. 이번 작업에서 실제 수집 dispatch는 실행하지 않는다.

## 검증·출시 상태

- 수정 전 실제 Chromium에서 `/선물/` 실패 재현. 최종 브라우저 검사 전체 통과: 15상품/1,106개 이력, 구조 변경 fixture, ADR 부족 안내, 3개 이상 차트, 736/360px 가로 넘침 없음, gzip/plain JSONL, JS 오류 없음.
- Python 해외 데이터/파이프라인 계약 **17개** 통과. 기존 16개에 공백 회복·장애 보존 경로 한 건 추가. Node 문법·diff whitespace 검사 통과.
- 코드 변경은 테스트와 삼성 상품 registry, 이 문서. 수집기·운영 UI·Worker·workflow·현재 공개 시세/이력 편집 없음.
- 보강 커밋의 GitHub validate/guard 통과 후 #546을 사용자가 허용한 범위에서 병합한다. PR validate 성공, 병합, 실제 자동 수집, 운영 데이터 갱신은 각각 별도 확인 단계다.
