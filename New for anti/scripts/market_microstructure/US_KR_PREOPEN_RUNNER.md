# 일일 개장전 방향 실행기

한국 다음 거래일의 시작·종가·방향 유지·추가 진행을 고정 연구모델로 계산한다.
비용/손익은 계산하지 않는다. 일일 실행에서 train을 호출하지 않는다.

## 한 번에 수집·추론·기록·표시용 JSON 생성

저장소 root에서:

```
pip install -r 'New for anti/scripts/market_microstructure/requirements-us-kr-preopen.txt'
python 'New for anti/scripts/market_microstructure/run_us_kr_preopen.py' \
  --target YYYY-MM-DD \
  --model 'New for anti/scripts/market_microstructure/models/shadow/us_kr_preopen_20261022_v1.json' \
  --krx-root '<krx-month-paste>/data/raw/krx_15007' \
  --refresh-prices \
  --run-dir '<new-run-directory>' \
  --archive-dir data/forecasts/us_kr_direction \
  --public-output 'New for anti/public/data/us_kr_direction_v1.json'
```

`--board`는 기본적으로 기존 derivatives_board_v1.json을 읽는다. 원본 보드는 수정하지 않는다.
raw_root에서 source일 포함61거래일 안의 부족한 콜풋 날짜를 기존 merge_date_folder로 보충하고,
실제 source일 자료가 없으면 예전날로 대체하지 않는다. 다른 보드 필드는 복사 상태 그대로다.
해당 한국source 장마감/미국source 장마감 전이거나08:30KST cutoff가 지났으면 수집을 건너뛴다.
수집이08:29에 시작해08:31에 끝나면08:31 기준으로 판정하며 사전예측으로 만들지 않는다.

가격 수집은 네이버의 정확한21한국거래일 창 전체와 Yahoo 수정주가의 직전2미국세션을
각각 새로 가져온다. 제공처를 섞거나 결측일을 채우지 않는다. seed를 주면 중첩구간 수정 필드를 기록한다.
이력 원천가격의 조정 정의/거래소 범위가 독립 검증됐다는 뜻은 아니다.

오프라인 재계산은 --refresh-prices를 빼고 --stocks/--kospi/--us를 준다.
--replay는 과거재생 전용이며 --public-output과 같이 사용할 수 없다.

## 기록 구조

- run-dir/inputs/{board,stocks,kospi,us}.json: 이번 실행이 실제 사용한 입력.
- run-dir/forecast.json: 실제 생성시각/모델ID/입력해시/대상일/점수/자료부족사유.
- run-dir/display_payload.json: 소비 UI에 필요한 작은 표시 계약.
- run-dir/run_report.json: 수집 상태·source/cutoff·raw 영수증·수정 필드·오류·아카이브 위치.
- archive-dir/TARGET/MODEL/first.json: 최초 유효 개장전 예측, 불변.
- 같은날 수정본은 revisions/에 분리, primary 성적 집계에서는 제외.
- unavailable/replay는 first.json이 되지 않는다.

종료코드0은 연구 사전예측 또는 명시적 replay, 2는 unavailable이다. 실행오류는 별도 비정상 종료다.
자료부족을 조용한 success로 바꾸지 않는다. workflow는 진단/입력 저장 후 실패 상태를 복구해야 한다.

## 표시 계약

JSON 필드: schema_version, status, target_date, generated_at, KR_source_date, US_source_date,
forecast_cutoff_KST, model_id, trained_through, research_only, cards[], refresh.
cards는 ticker/label_ko/scores를 갖는다. scores의4키는 opening_up/closing_up/
direction_persists/opening_extends. probability/score_0_100/direction/information_state를 보존한다.

- 50은 각 사건의 균형. 유지확률은 상승확률이 아니다.
- REFERENCE_ONLY는 보정기울기0, 최근빈도만 반영. 모델신호로 강조하지 않는다.
- unavailable은0점/50점으로 표시하지 않는다.
- 같은대상일의 기존유효예측이 있으면 최초 생성시각을 유지하며 refresh.status=unavailable을 표시한다.
- 대상일이 바뀌면 어제 점수를 오늘 카드로 재사용하지 않는다. last_available은 이전날의 메타데이터만 남긴다.
- retrospective_replay는 과거재생임을 크게 표시하며 실제 사전예측처럼 노출하지 않는다.

실제 생성한 예시: tests/fixtures/us_kr_direction_display_replay.json.
검토용 HTML을 만들 수 있다:

```
python 'New for anti/scripts/market_microstructure/render_us_kr_direction_preview.py' \
  --input 'New for anti/scripts/market_microstructure/tests/fixtures/us_kr_direction_display_replay.json' \
  --output /tmp/us-kr-direction-preview.html
```

브라우저에서 실제3종목 카드/과거재생 표시/대상·입력·생성날짜/참고빈도 구분을 확인했다.
이 HTML은 운영 UI가 아니라 연결 검토용이다.

## Claude Code 적용 항목

워크플로·UI 소유권에 따라 운영 파일은 변경하지 않았다.
integration/us_kr_direction_preopen.proposed.yml은 새일일job의 구체적인 패치안이다.
06:20/06:50 KST 평일의2회 시도를 제안하며, GitHub 지연이 있어도08:30 이후 예측은 차단된다.
패치안은 현재 .github 밖에 있으므로 어떤 정기작업도 새로 활성화하지 않는다.

적용 시 모델·helper·새코드·고정 의존성 파일을 함께 포함하고,
실행 결과/불변 예측 기록 저장소·새 public JSON 소비 UI를 연결한다.
입력 미달/토큰 오류/늦은스케줄에서 실패가 드러나는지 확인한 뒤 신규 전향 성적을 적재한다.
UI는 기존날짜 점수를 새예측으로 바꾸지 않으며, 미래 target에 대한 사전 생성기록만 신규평가에 사용한다.

기존 PR #797은 병합된 상태다. 이 작업은 그 main 기반의 별도 실행기 PR이다.
