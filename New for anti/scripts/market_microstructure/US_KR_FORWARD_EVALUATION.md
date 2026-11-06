# 개장 전 방향 예측: 고정 비교와 전향 평가

2026-11-05. 모델 계수·시차·판정 기준을 일일 데이터에 맞춰 다시 고르지 않는다.
기존 주 모델 `us_kr_preopen_20261022_v1.json`과 해시로 고정된 helper는 수정하지 않았다.
비용·수익률 전략·매수 수량은 계산하지 않는다.

2026-11-06 보강: [아침→공개 확인→마감 평가](US_KR_DAILY_CYCLE_20261106.md).
`us_kr_publication.py` 관측 파일이 있으면 평가기는 이를 최초 예측과 다시 대조한다.
기존 생성 기준 성적을 보존하고 `publication_verified`에 정시 공개 확인 표본 성적을 별도로 출력한다.
관측 파일이 없는 과거 예측의 공개 여부는 미확인으로 유지한다.

## 이번 보강

- 기존 `run_us_kr_preopen.py` CLI를 그대로 실행하면 비교 모델도 함께 추론한다.
  `--comparison-model` 기본값은 `models/shadow/us_kr_comparison_20261022_v1.json`.
  기존 3종목·4사건의 주 모델 점수와 public 표시 계약은 그대로다.
- `comparisons`는 연구 기록에만 추가한다. UI 점수 대체나 가장 잘 맞는 모델의 자동 선택은 없다.
- 동일 입력·동일 결과라도 비교 버전/결과가 달라지면 revision으로 저장한다.
  예전 first.json에 새 비교 예측을 사후에 끼워 넣지 않는다.
- 성공·자료 부족·cutoff 초과 실행은 `TARGET/MODEL_PREFIX/attempts/*.json`에 기록한다.
  replay는 실제 실행 시도로 기록하지 않는다. 워크플로가 아예 실행되지 않았거나 gate에서
  생략하면 기록이 없으므로 평가기는 `no_recorded_attempt`로 구분한다.
- `evaluate_us_kr_forward.py`가 최초 유효 사전 예측만 채점한다. revision/replay는 제외한다.
  생성 시각·학습 종료일·모델 ID·KR/US 원천 세션·08:30 cutoff·eligible 플래그를 다시 검사한다.

## 비교 모델의 의미와 고정 범위

| 이름 | 입력 | 목적 |
|---|---|---|
| primary | 한국 가격 6 + 옵션 4 + 미국 8 | 기존 주 모델 |
| domestic_price_options | 한국 가격 6 + 옵션 4 | 미국 정보의 추가 효과 비교 |
| price_us | 한국 가격 6 + 미국 8 | 한국 옵션 정보의 추가 효과 비교 |
| frozen_recent | 독립 보정 구간의 사건 빈도 | 모델 점수가 과거 단순 빈도보다 나은지 비교 |

옵션 4개는 콜/풋 각각 `외국인 순매수금액 / 시장 전체 매수금액`의 직전 60세션 대비 순위와
최근 5세션 평균이다. 전체 거래량이나 개별 주식 자체 옵션을 새로 투입한 것이 아니다.
주 모델에 넣지 않은 거래량·금액 특징의 확장은 별도 버전 실험으로 검토한다.

비교 모델도 주 모델의 정확히 같은 4개 입력 해시와 2026-10-22까지의 결과,
동일 train/calibration 분리·동일 nonflat 표본을 사용했다. 원본 board는
commit `4187fd41d2c1724f6d3a174a081115ffe53e38ed`의
`New for anti/public/data/derivatives_board_v1.json`에서 모델 입력 해시와 일치함을 확인했다.
비교 모델의 `created_at` 이전 예측에는 비교 성적을 붙일 수 없다.
주 모델/비교 모델 모두 명시적 별도 학습 이외에는 계수가 바뀌지 않는다.

모든 비교는 주 모델이 발행 가능한 날에 같은 입력 벡터를 잘라 사용한다.
따라서 미국 자료가 없는 날의 국내 모델 단독 발행률을 비교하는 실험은 아니다.
추가 예측력 비교이며 인과효과를 증명하지 않는다.

## 실제 결과 평가

장 마감 이후 저장소 root에서 실행:

```bash
MM='New for anti/scripts/market_microstructure'
python "$MM/evaluate_us_kr_forward.py" \
  --archive-dir data/forecasts/us_kr_direction \
  --model "$MM/models/shadow/us_kr_preopen_20261022_v1.json" \
  --start 2026-11-06 --end YYYY-MM-DD \
  --refresh-prices \
  --run-dir "data/observations/us_kr_direction/<new-unique-run-id>" \
  --output data/manifests/us_kr_forward_evaluation_v1.json
```

`--start 2026-11-06`은 사용자 요청일 다음 날부터 시작하는 명시적 평가 구간이다.
그 전에 시작된 기존 주 모델의 운영 성적은 별도 start로 조회할 수 있다.
평가를 시작한 날을 성적에 맞춰 뒤로 옮기지 않는다.

`--refresh-prices`는 기존 네이버 차트 수집기를 사용한다. 첫 평가일 직전 종가와
마감한 평가 대상 거래일들의 OHLC를 같은 제공처에서 받는다. 실행일의 미마감 가격은 제외한다.
과거 스냅샷을 덮어쓰지 않도록 새 run-dir만 허용한다. 제공처 오류/빈 세션은 그대로 남기고
부분 결과와 진단을 저장한 뒤 exit 2로 알린다. 기존 정상 스냅샷을 빈 결과로 대체하지 않는다.

오프라인은 `--refresh-prices --run-dir` 대신 `--stocks <json> --kospi <json>`를 준다.
두 파일은 기존 `candidates: [{ticker, rows: [{date, open, high, low, close, quality}]}]` 계약이다.
평가 구간의 **모든** 원천일·대상일 가격이 필요하다. 단일 실행의 21세션 추론 창만 계속
사용하면 오래된 예측의 결과가 빠지므로 전체 결과 패널 또는 저장한 결과 스냅샷을 제공한다.

평가 출력:

- 거래일별 발행 여부, 마지막 실패 사유, 시도 기록 없음, 잘못된 first 기록 구분.
- cutoff가 지난 거래일 전체를 분모로 한 발행률. 미마감일은 아직 성적에 넣지 않는다.
- 3종목 × 4사건의 Brier, 명시적 중립을 뺀 적중률, 기준 사건 발생률,
  0.5 확률 Brier 및 고정 최근 빈도 기준선.
- 모델 신호와 `recent_base_rate_only` 적중률을 분리한다. 정확히 0.5는 방향 결정에서 제외한다.
  45~55 같은 중립 폭을 새로 선택하지 않았다.
- 고정 확률 구간별 평균 예측·실제 빈도·표본 수. 전체와 최근 **20개 마감 거래일**을 나란히 집계.
- 공통 날짜에만 주 모델과 비교 모델의 Brier 차이를 계산. 음수면 주 모델에 유리하다.
- 평탄한 시가/종가는 원래 연구와 같은 공통 nonflat 표본에서 제외하고 원래 방향을 audit에 남긴다.
  따라서 조건부 이진 성적이며 모든 발행일을 포괄한 무조건적 적중률은 아니다.
- 소표본 표기와 Wilson 구간은 설명용이다. 거래일 독립성이 보장되지 않으며 통계적 우위로 단정하지 않는다.

각 사건의 정의는 주 모델과 같다. 방향 유지 확률을 상승 확률로 표시하거나 4개 확률을
곱해 경로 확률로 만들지 않는다. 네이버 가격의 KRX 단독 시장 범위와 조정주가 정의는
독립 검증이 끝난 것이 아니다. KRX 결과 가격으로 임의 대체하지 않는다.

`generated_at`은 로컬 생성 시각이다. 실제 공개 시각이 08:30 이전이었음을 독립적으로
증명하는 원격 발행 영수증은 아직 없다. GitHub 실행 ID·커밋·배포 시각은 별도로 보존한다.

## Claude Code 통합 요청 (workflow/UI 소유)

현행 `.github/workflows/us_kr_direction_preopen.yml`과 UI는 이번 작업에서 수정하지 않는다.
현재 workflow가 archive 디렉터리를 커밋하므로 병합 후 기본 실행에서 비교와 attempt도 함께 보존된다.

1. 기존 inference 테스트에 `test_us_kr_forward.py`를 추가한다. 의존성은 기존 고정 requirements 그대로.
2. 장 마감 이후 위 평가 CLI를 실행하는 단계/별도 workflow를 연결한다. 19:00 KST 이후를 권장하며,
   제공처가 늦으면 오류/결측 상태를 보존하고 재시도한다. 이 작업에서 정기 실행을 활성화하지는 않았다.
3. 결과 스냅샷과 평가 보고서를 장기 저장한다. 업로드 artifact 보존 기간 30일에만 의존하지 않는다.
4. 홈 카드 점수는 기존 primary 그대로 사용한다. 비교 결과를 홈 점수로 대체하지 않는다.
   평가 화면을 만들 경우 관측 수·발행률·입력일·모델 버전을 같이 보여준다.
5. 내일 첫 실행의 실제 raw source 날짜·모델 ID·comparison ID·first/attempt 파일·공개 시각을 확인한다.
   실패나 replay를 성공한 전향 예측으로 보고하지 않는다.
