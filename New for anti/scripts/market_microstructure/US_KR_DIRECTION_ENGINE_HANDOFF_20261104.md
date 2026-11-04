# 고정 US→KR 개장전 방향 엔진 인계

현재 상태: 로컬 백엔드/고정 연구모델/추론 CLI/검증 완료. UI/일일 workflow 연결은 미실행.
워크플로와 화면은 Claude 소유. 원천자료 갱신 경로는 Cursor와 조정한다.
기존 v1 옵션 모델/ETF shadow 모델/public JSON/기존 예측은 변경하지 않았다.

## 모델과 계산 계약

- 코드: `New for anti/scripts/market_microstructure/us_kr_direction_engine.py`.
- 고정 모델: `models/shadow/us_kr_preopen_20261022_v1.json` (위 코드와 같은 디렉터리 기준).
- model_id: `115ddb42c8c8449b63c57c35fe7642d22f9af3f2fe84def467bebd30ed976d07`.
- 생성시각: 2026-11-04T06:10:19.114144+00:00. 학습결과 cutoff: 2026-10-22.
- 대상: 005930/000660/KOSPI, 각각4개 확률머리. 새 입력으로 추론할 때 재학습하지 않는다.
- 입력18개: 종목가격6, KOSPI200 콜풋수급4, 미국시장4, 미국반도체4.
- 미국 입력: QQQ/SPY/VIX 변화+log(VIX), SMH/MU/NVDA/AMD 변화.
- 판단시각: 한국 목표일08:30 KST 이전. 직전 완료 미국 정규장→다음 한국장, 휴장/DST 반영.
- 학습250개 이상, 별도 직전6개월 보정. 삼성/하닉 n_base1372/1384, n_calibration99/99;
  KOSPI1561/101. 학습 label과 보정 source 경계를 분리했다.
- 모델이 고정한 파일해시/패키지 버전이 달라지면 중단한다. 버전변경은 검토 후 새 아티팩트로 한다.

목표:
1. opening_up: 다음시가>전일종가.
2. closing_up: 다음종가>전일종가.
3. direction_persists: 시가·종가가 전일종가의 같은쪽.
4. opening_extends: 시가→종가도 출발방향으로 더 진행.

확률점수는100*p, 50은 해당 사건의 균형점. 유지/추가진행 확률을 상승확률로 표시하지 않는다.
머리별 확률을 곱해 결합확률로 만들지 않는다. 학습은 비동가 표본이며 무조건 실전확률로 확정하지 않는다.
모든 출력은 연구 참고점수다. 과거 적중률은 현재 예측의 신뢰도로 고정해서 표시하지 않는다.

## 입력 형식과 최신성

- board: 기존 derivatives_board_v1.json의 detailed_15007 call/put series.
  한국 source일 포함 정확한61거래일의 observed 매수/매도/순매수·시장총액 필요.
  kr.as_of 같은 루트 메타데이터로 날짜를 대신 판정하지 않는다.
- stocks: candidates[] 안 ticker005930/000660와 rows[date,open,high,low,close,volume].
- kospi: 같은형식 ticker=KOSPI. 각 종목 source일 포함 정확한21거래일 OHLC 필요.
  provider/원시·수정주가/시장범위를 기존 학습 시계열과 맞춰 보존한다.
- us: symbols{} 안 QQQ/SPY/SMH/MU/NVDA/AMD/^VIX별 rows[date,close,...].
  해당 한국 목표일 직전 예정 미국거래일과 그 전 거래일 종가가 정확히 있어야 한다.
- chain: **학습 때만** 과거 공통표본 재현에 사용. 일일추론에는 옵션체인 파일이 필요하지 않다.
- 위 자료의 변환기에는 collected_at/원천시각·시간대/source/hash를 함께 보존한다.
  코드가 검사하는 것은 세션·자료행·로컬 생성시각이며 원천 공개시각을 소급 입증하지는 않는다.

매수-매도 항등식/관측품질/정확한 거래일창을 검사한다. 누락 시 최근날로 후퇴하지 않는다.
예: 11/5 목표는 한국11/4 OHLC·콜풋과 미국11/4 정규장/그 전장 종가가 필요하다.
11/4 한국·미국장이 아직 안 끝났다면 정식 점수는 unavailable이다.

## 실행

저장소 root 기준. 현재 검증 환경은 PYTHONPATH=/tmp/krx-short-horizon-deps이며
모델 runtime_versions와 동일한 연구 의존성을 배포환경에 설치해야 한다.

```
python 'New for anti/scripts/market_microstructure/us_kr_direction_engine.py' predict \
  --stocks <stocks.json> --kospi <kospi.json> --us <us-daily.json> \
  --board <derivatives_board_v1.json> \
  --model 'New for anti/scripts/market_microstructure/models/shadow/us_kr_preopen_20261022_v1.json' \
  --target YYYY-MM-DD --output <new-forecast-path.json>
```

--target은 실제 한국 거래일이어야 한다. source는 자동으로 직전 한국거래일을 선택한다.
실제 실행시각을 사용하며 과거시각을 CLI로 지정할 수 없다. 장마감 전 자료로 미래점수를 만들지 않는다.
모든 대상의 필수자료가 갖춰져야 결과가 생성된다. 일부대상만 조용히 성공 처리하지 않는다.
예측을 현재 public 자산으로 연결할 때는 unavailable/research 상태도 함께 렌더링한다.

학습은 별도 train 명령이며 --cutoff/--chain/새 --output이 필요하다.
일일 job에서는 train을 호출하지 않는다. 기존 모델 경로 덮어쓰기는 CLI가 거부한다.

## 출력과 기록 보존

- research_preopen_forecast: 정한 cutoff 전에 로컬에서 생성한 연구예측.
- retrospective_replay: 명시적 --replay를 사용한 과거 재생. 전향검증 집계에서 제외.
- unavailable: 자료부족/시각조건 불충족. results={}와 reasons/input_errors를 보존.
- eligible_for_prospective_evaluation: replay는false. 연구예측은 현지 생성시각 근거만 있으며
  실제 공개시각 검증은 배포층이 별도 수행한다.
- ticker별 scores에 probability/score_0_100/raw_probability/direction/information_state/calibration_slope.
- 보정기울기0은 recent_base_rate_only 및 REFERENCE_ONLY. 빈도만 높은 값을 모델 방향신호로 부르지 않는다.
- 모델ID/입력hash/한국source·target/미국source·마감UTC/cutoff/생성시각을 기록한다.
- 같은파일·동일입력 재실행은 최초 generated_at을 보존. 입력/점수가 달라지면 새 revision 경로 필요.
- 늦은 재실행으로 기존 개장전 예측을 덮어쓰지 않는다. 기존 기록과 수정 기록을 함께 남긴다.
- 최신자료가 없다고 예측을0이나50으로 만들지 않는다. 이전 예측도 새 목표일의 점수로 재사용하지 않는다.

## 검증과 남은 작업

엔진 단위검사8개 통과: 모델/코드/환경변경 거부, cutoff·US미마감·새입력결측·과거시각
차단, 목표별 방향해석, 멱등/불변 예측파일.
학습과 추론 입력9개시점(3대상×처음/중간/끝) 완전일치. 미래 한국OHLC를 제거해도 입력 동일.
실제 모델계수 불변, 과거 replay의 전향검증 제외, 모델해시 검증 완료.

시연 파일:
- data/manifests/us_kr_preopen_replay_20261102_created_20261104.json:
  11/4에 만든11/2 과거재생. 실제11/2사전예측으로 집계 금지.
- data/manifests/us_kr_preopen_availability_20261105_checked_20261104.json:
  11/4 한국/미국 장마감 전 검사에서 unavailable. 11/5 예측으로 표시 금지.

다음 작업은 현재자료 수집→본 CLI predict→불변기록 저장→화면표시를 연결하는 것이다.
미국 정보가 아직 확정되지 않은 한국 전일종가 직후의 임시 점수는 별도 국내모델이 필요하며,
이 개장전모델에 오래된 미국 입력을 넣어 대신하지 않는다.
새 날짜의 결과가 나중에 확정되면 사전생성 기록과 대조한다. 과거 replay/수정기록을 섞지 않는다.
신규 입력·시간 조건·변수 구성이 바뀌면 기존 아티팩트가 아닌 새 모델버전을 만든다.
