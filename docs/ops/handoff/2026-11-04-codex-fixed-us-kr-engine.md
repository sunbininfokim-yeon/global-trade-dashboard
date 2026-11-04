# Codex 고정 개장전 US→KR 엔진

사용자 '이어서': 고정 모델로 새 옵션/가격 입력을 재계산하는 엔진까지 구현.
UI/workflow 소유권은 Claude. 원천 갱신은 Cursor와 조정. 현재 외부 메시지 전송 없음.

코드: `New for anti/scripts/market_microstructure/us_kr_direction_engine.py`.
고정모델: 같은폴더 `models/shadow/us_kr_preopen_20261022_v1.json`.
model_id115ddb42c8c8449b63c57c35fe7642d22f9af3f2fe84def467bebd30ed976d07.
학습 label cutoff10/22, 모델생성11/4. 종목별4머리, 변환/계수/보정/환경/코드해시 고정.
CLI train/predict분리, 예측불변기록, 부족자료unavailable, 명시 replay만과거재생.
학습에 쓴 체인파일은 일일predict에 불필요.61일콜풋+21일종목OHLC+직전US종가2일 필요.

정식 목표11/5는 한국11/4+미국11/4마감자료가 필요하다. 현재11/4마감전검사는unavailable.
별도11/2재생은 모델생성11/4이므로 전향성적 집계 금지.
일일새자료가 들어오면predict만 호출. 자동재학습/모델경로 덮어쓰기 금지.

단위8검사 통과. 9시점 학습/추론 입력완전일치, 미래OHLC불필요, 계수불변,
replay전향집계제외, 동일파일최초시각보존 확인.
상세 CLI/JSON/UI계약: `US_KR_DIRECTION_ENGINE_HANDOFF_20261104.md`(코드폴더).

로컬 backend/모델완료. 일일수집/워크플로·UI/공개예측 저장소 연결 및 신규전향검증은 미완료.
기존v1/shadow모델·예측/public자료/UI/workflow 변경 없음. commit/push/PR/배포 미실행.
