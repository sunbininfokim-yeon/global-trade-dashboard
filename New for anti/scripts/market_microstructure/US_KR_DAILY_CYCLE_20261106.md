# 아침 새 입력 → 고정 모델 계산 → 공개 확인 → 마감 후 평가

대상은 KOSPI·삼성전자·SK하이닉스다. 매일 새 자료로 추론하며, 모델 계수·보정기·
기준 확률·판정 임계값은 고정한다. 일일 실행에 학습이나 모델 자동 선택은 없다.
미국 옵션 세부 체인이나 외국인 보유율을 이번에 운영 모델에 추가하지 않았다.

## 아침 실행

현재 main의 `.github/workflows/us_kr_direction_preopen.yml`이 기존 명령을 호출한다.
저장소 root에서 같은 명령을 실행할 수 있다.

```bash
MM='New for anti/scripts/market_microstructure'
python "$MM/run_us_kr_preopen.py" \
  --target 2026-11-09 \
  --model "$MM/models/shadow/us_kr_preopen_20261022_v1.json" \
  --krx-root krx-month-paste/data/raw/krx_15007 \
  --refresh-prices \
  --run-dir "runner-state/<unique-run-id>" \
  --archive-dir data/forecasts/us_kr_direction \
  --public-output 'New for anti/public/data/us_kr_direction_v1.json'
```

11/9 대상이면 한국 원천일과 미국 원천일은 모두 **11/6**이다. 원천 세션이 실제로
마감한 뒤 실행해야 한다. 입력 수집이 끝난 실제 시각에 08:30 KST cutoff를 검사한다.
실제 날짜가 달라지면 `--target`도 그날의 한국 거래일로 바꾼다.

- 한국: source일까지 정확한 61거래일 콜·풋 금액 이력과 21거래일 종목/지수 OHLC.
- 미국: QQQ, SPY, VIX, SMH, MU, NVDA, AMD의 정확한 두 마감 세션 가격.
- 새 raw 폴더의 네 파일은 `options_{call,put}_{buy,sell}.csv`다. 기존 15007 파서를 재사용한다.
- 가격은 새로 수집하며, 오래된 날짜나 다른 제공처로 결측을 메우지 않는다.
- 성공은 exit 0, 자료 부족/시간 초과는 exit 2와 `unavailable`이다. 계산 불가를 50%로 만들지 않는다.
- 같은 날 재실행해 값이 바뀌면 revision으로 보존한다. 최초 예측 `first.json`은 바꾸지 않는다.

이 구조는 아침 입력이 갱신될 때마다 기존 계수에 넣어 새 확률을 계산한다.
데이터 갱신만으로 학습이 다시 수행되지는 않는다.

## 확률 출력 계약

기존 `probability`, `score_0_100`, `direction`, `information_state`를 보존한다.
`cards[].scores.opening_up`과 `closing_up`에 다음 필드를 추가했다.

```json
{"probability": 0.54, "up_probability": 0.54, "down_probability": 0.46}
```

위 숫자는 형식 예시다. 실제 예측이 아니다.

- `opening_up`: 전일 종가 대비 대상일 시가의 상승/하락.
- `closing_up`: 전일 종가 대비 대상일 종가의 상승/하락.
- `direction_persists`: 시작 방향과 마감 방향이 같은 사건의 확률.
- `opening_extends`: 시가 이후 시작 방향으로 추가 진행하는 사건의 확률.

마지막 두 사건에는 UP/DOWN 필드를 붙이지 않는다. 시가→종가 자체의 상승 확률은
현행 모델에 별도 head가 없으며, 위 확률들을 곱하거나 빼서 만들어서는 안 된다.
동결 모델의 공통 학습 표본은 시가·종가가 전일 종가와 다른 날이다. 따라서 UP+DOWN=1은
그 조건에서의 이진 확률이며 보합 확률을 0으로 추정했다는 뜻이 아니다.
이 조건과 사건 정의는 최상위 `probability_contract`에도 들어 있다.
`REFERENCE_ONLY`/`recent_base_rate_only`는 계속 최근 빈도 참고값이다.
그 head는 입력이 달라져도 같은 확률을 낼 수 있다. 이를 새 방향 신호로 바꾸지 않는다.

## 실제 공개 확인

계산 완료나 GitHub 커밋만으로 화면 발행 성공을 판단하지 않는다. 배포 완료 뒤:

```bash
python "$MM/us_kr_publication.py" \
  --archive-dir data/forecasts/us_kr_direction \
  --model "$MM/models/shadow/us_kr_preopen_20261022_v1.json" \
  --target 2026-11-09
```

기본 endpoint는 현재 운영 Worker의 `/public/data/us_kr_direction_v1.json`이다.
HTTP 응답 수신 **후** 시각을 기록하며, 최초 예측의 날짜·모델·원천일·생성시각·12개 점수가
같고 cutoff보다 이른 경우에만 `verified_preopen_publication`이다.
오래된 payload, revision 점수, replay, 404/연결 오류, 늦은 배포는 검증 성공이 아니다.
동일한 최초 점수를 보존한 실패 refresh 메타데이터와 새 표시 필드의 생략은 허용한다.

관측 기록은 `archive/TARGET/MODEL_PREFIX/publications/*.json`에 불변으로 저장한다.
실제 payload, payload/first 해시, URL, 관측 시각, 가능한 GitHub run/checkout 정보를 남긴다.
이는 해당 시각에 해당 endpoint에서 값을 읽었다는 증거다. 최초 공개 시각이나 독립 시계의
증거로 표현하지 않는다. 검증 실패도 저장한 뒤 exit 2로 알린다.

## 장 마감 후 평가

기존 `evaluate_us_kr_forward.py`와 2026-11-06부터의 고정 평가 구간을 그대로 사용한다.
실제 마감 가격과 새 수집 스냅샷을 저장하는 명령은 [US_KR_FORWARD_EVALUATION.md](US_KR_FORWARD_EVALUATION.md)에 있다.

기존 `issuance`/`all` 성적은 생성 기준이며 그대로 유지한다. 추가 `publication_verified`에는
원격 공개가 확인된 날짜만 넣은 발행률·Brier·적중률·확률 구간·기준선 비교를 별도로 집계한다.
관측 기록이 없으면 `no_publication_observation`이고 공개 성공으로 간주하지 않는다.
0건이면 점수는 null이다. 기록이 없는 과거 날짜의 공개 증거를 사후에 만들지 않는다.

## 통합 상태와 담당

이 변경은 UI·Worker·실제 `.github/workflows`를 수정하지 않는다. `docs/ops/OWNERS.md`에
따라 Claude Code가 아래 제안안을 검토·적용한다.

1. 현행 아침 workflow 테스트에 `test_us_kr_forward.py`, `test_us_kr_publication.py` 추가.
2. `integration/us_kr_direction_forward.proposed.yml`: 19:00 KST 마감 평가, 실제 outcome snapshot과
   평가 JSON을 GitHub에 보존. exit 2도 부분 기록을 보존하고 오류로 알림.
3. `integration/us_kr_direction_publication.proposed.yml`: 배포 성공 후 공개 관측. 기존 deploy-chain
   guard에 맞춰 두 제안안의 `name`을 `deploy.yml.workflow_run.workflows`에 추가.
   관측 workflow는 같은 대상일/모델에 관측 파일이 이미 있으면 자동 재실행을 생략하므로
   관측 커밋의 후속 배포가 반복 커밋을 만들지 않는다. 실패 후 재시도는 명시적 dispatch로 한다.
4. 현행 Worker의 아침 dispatch와 `GH_DISPATCH_TOKEN` 접근을 확인한다. GitHub 지연 cron만으로
   정시성을 보장하지 않는다. 비공개 raw checkout 실패 시 public board만으로 요건을 충족하는지도 확인.
5. UI는 이미 `probability`로 상승/하락을 나란히 표시한다. 새 필드는 호환 추가다.
   다만 시가·종가 행/홈 카드에도 `recent_base_rate_only`이면 ‘최근 빈도’를 표시해야 한다.
   현재 이 표시는 방향 유지/추가 진행의 보조 행에만 있다.

이전 `integration/us_kr_direction_preopen.proposed.yml`은 #868 당시 자료다.
토큰·gate가 다른 그 파일로 현재 아침 workflow를 덮어쓰지 않는다.

## 실제 확인 (2026-11-06)

- base main `166b8a04fe4156b0e0f56a5b1de9bec13226cde0`.
- 최신 공개 보드의 콜·풋은 각각 1,922행, 마지막 날짜는 11/2.
  11/9 실행에서 원천일을 맞추려면 11/3~11/6의 부족한 콜·풋을 raw에서 보충해야 한다.
  비공개 raw 11/5 경로는 connector와 CLI 모두 404여서 존재 여부와 접근 실패를 구분하지 못했다.
- 실제 네이버 마감 가격은 11/5·11/6에 대해 3종목 모두 수집됐고 오류가 없었다.
- 실제 새 수집 가격/최신 보드로 11/3 대상 과거 재생 성공. 이전 11/2 대상 재생과 같은 모델로
  12확률 중 7개가 바뀌었다. 이는 입력 반영 확인이며 정확도 검증이나 실전 예측이 아니다.
- 실제 늦은 11/6 실행은 `unavailable`; 첫 예측 기록과 점수를 만들지 않았다.
- 운영 endpoint 직접 조회는 HTTP 200 + `text/html`이었다. 실제 예측 JSON 확인이 아니며,
  새 관측기는 이런 앱 fallback을 공개 성공으로 세지 않는다.
- 테스트 309개 및 UI 계약 통과. 원격 배포 관측은 테스트 대역으로 검증했으며 운영 성공을 주장하지 않는다.

검증 영수증: `data/manifests/us_kr_daily_cycle_validation_20261106.json`.
새 실제 마감 가격: `data/manifests/us_kr_daily_cycle_outcomes_20261106.json`.
