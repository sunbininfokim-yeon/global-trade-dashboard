# Codex: 고정 비교 모델·전향 평가 보강

- 사용자 요청: 내일부터 Cursor가 입력을 업데이트하므로 방향 엔진을 보강.
- 브랜치: `codex/us-kr-forward-evaluation-20261105`, base main `99c8960c7`.
- 범위: `New for anti/scripts/market_microstructure/**`, 자체 검증 manifest/인수 문서.
- `.github/workflows/**`, UI, worker, 공개 데이터, 기존 고정 모델과 해시 대상 helper 수정 없음.

## 구현

1. `us_kr_comparison.py`와 새 고정 비교 아티팩트. 기존 전체 모델과 동일한 학습 입력 해시,
   종료일 2026-10-22, 동일 train/calibration 표본. 국내 가격+옵션, 가격+미국, 보정 구간 빈도 기준선.
   신규 계수는 이 비교 아티팩트에만 추가했으며 기존 주 모델은 그대로다.
2. runner가 기본 비교 아티팩트를 함께 추론한다. 비교 실패는 별도 unavailable로 드러내고
   기존 primary 예측은 보존. 비교가 추가/변경돼도 옛 first를 바꾸지 않고 revision으로 기록.
3. 모든 비-replay 추론 결과의 성공/실패 시도를 archive의 `attempts/`에 보존.
4. `evaluate_us_kr_forward.py`: 최초 사전예측만, ID/날짜/실제 생성시각/원천 세션/cutoff 재검사.
   실행 기록 없는 날 포함 발행률, 실패 이유, 전체·최근 20마감 거래일 성적, 확률 구간별 실제 빈도,
   Brier와 공통 날짜 비교. reference_only/중립을 모델 방향 신호와 구분.
5. 사후 실제 가격의 새 스냅샷 수집 CLI. 미마감/결측/가격 기준 혼합을 피하고, 부분 실패 exit 2.
   시가·종가 평탄한 날은 원래 연구와 동일한 이진 공통 표본에서 제외하고 감사값을 남김.

주 모델 ID: `115ddb42c8c8449b63c57c35fe7642d22f9af3f2fe84def467bebd30ed976d07`.
비교 ID: `69b110020c932a1e21d82e0824415598a20917115c34994e9dff3589e07815ea`.

## 검증

- 고정 requirements 환경(`PYTHONPATH=/tmp/krx-short-horizon-deps`): 시장 미시구조 unittest 250개 통과.
- UI 계약 검증 통과. 상세 검증 manifest: `data/manifests/us_kr_forward_evaluation_smoke_20261105.json`.
- 실제 네이버 수집: 2026-10-29~10-30 대상 + 직전 종가, 3종목 각 3행, 결측/수집 오류 없음.
- 실제 과거 입력으로 11/2 replay: 기존 runner와 주 모델 결과 전체 동일, 비교 예측 추가 성공.
  replay는 평가용 first/실행 시도 archive를 만들지 않았다.
- 실패/누락/시각 초과/다른 모델/사후 비교 추가/변경된 가격/중립·reference_only/공통 날짜 집계 테스트.
- 현재 새 전향 성적은 없다. 11/6 이후 실제 최초 발행을 쌓아 검증해야 한다.

## 소유권별 다음 실행

Cursor: `CURSOR_US_KR_DAILY_INPUTS_20261105.md`대로 private 원본 4개·61세션 연속성,
21세션 한국 가격, 7개 미국 심볼의 2세션, 사후 정답 가격을 유지. 원격 commit/SHA manifest로 보고.

Claude Code: `US_KR_FORWARD_EVALUATION.md`의 실제 명령을 장 마감 평가 workflow에 연결.
현행 preopen job은 runner 기본 경로를 사용하므로 이 PR 병합 후 비교/attempt를 함께 기록한다.
아직 장 마감 평가 workflow는 이번 작업에서 활성화하지 않았다. 기존 공개 홈 점수는 primary를 사용.
실제 첫 실행의 생성/공개 시각과 원격 파일·화면은 별도로 확인해야 한다.

원본 수집 스냅샷은 30일짜리 Actions artifact만으로 장기 보관하지 않는다.
이 코드는 로컬 생성 시각을 검증하며 공개 이전 발행의 독립 원격 증명을 대신하지 않는다.
가격은 기존 네이버 기준이며 KRX 단독 범위/조정 정의의 독립 검증은 미완료다.
