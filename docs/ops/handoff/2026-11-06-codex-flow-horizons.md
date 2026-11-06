# Codex: 1~5거래일·외국인 보유율·리밸런싱 연구

사용자 요청: 하루뿐 아니라 5영업일 시차와 포지션 비율로도 분석하고 통계 모델을 설명.
branch `codex/flow-horizons-position-ratios-20261105`, base `16ce12a49`.
이전 #884는 병합됐음을 GitHub에서 확인한 뒤 새 main 기반 별도 작업으로 진행했다.

## 실제 추가 수집과 분석

- 원본 trend 응답의 `foreignerHoldRatio`를 발견. 기존 공개 출력에는 이 필드가 빠져 있었다.
- 기존 Naver fetcher·trend_to_frame 재사용. 삼성전자/하이닉스 각각520행,
  2024-09-11~2026-11-05의 순매수 수량과 제공처 보유율을 실제 수집했다.
- 새 collector `collect_foreign_ownership_research.py`: 덮어쓰기 없는 snapshot,
  별도 raw와 연구 flow 출력, 실제0/null 구분, 원본 hash/실제 수집 시각 보존.
- 독립 가격 원값 구간을 보존. 현재 가격 패널은10/30까지여서 최종5일 비교 source는10/23까지다.
- 1~5일 공통 가격511일, 완전 특징507일, 보유율 포함506일.
  누적 종가/지연된 하루/첫 개장 이후/시가 갭/장중 방향을 분리했다.

## 통계 프로토콜

- h별 L2 logistic C=1 + 별도 sigmoid 보정. 기본 최소250 유효 base, 독립60 source일 보정 창,
  20 source일 test block, 두 경계 모두5일 label 종료일 기준 purge.
- 학습 구간에서만 정규화. 매 h의 동가만 해당 이진 head에서 제외한다.
  다른 미래 h의 동가 여부가 현재 h의 예측을 제거하지 않도록 테스트했다.
- 상승/하락 정밀도·재현율·혼동행렬·중립·reference-only·Brier·같은 날짜의 기준선 비교.
- 기간별 연관은 OLS+HAC(5), 외국인1일/5일 비율의 2종목×5h×2=20 p값을 함께 Holm 보정.
  인과적 충격을 식별한 모델이 아니다.
- 최초80/30 탐색을 해 본 뒤 이력을 늘려250/60으로 다시 실행했다.
  초기 탐색 기록도 보존. 새 자료 기간이 길어져도 이미 탐색한 과거이며 새 전향 검증은 아니다.

## 결과와 범위

보유율/누적 수급을 추가하거나5일로 늘려도 일관된 확률 오차 개선을 확인하지 못했다.
20개 조건부 회귀에서 Holm 보정 후5% 유의한 수급 계수 없음.
LETF 노출87 source일, `observed_krx` 게이트를 통과한 리밸런싱26일이어서
해당 모델은 표본 부족으로 학습하지 않았다. 수급 비율·제공처 보유율·LETF 바스켓 노출은 서로 다르다.

신규 코드/문서/정규화 입력/연구 산출물만 추가했다.
운영 모델·계수·기존 helper·public JSON·UI·워크플로는 수정하지 않았다.
사후 재생 예측을 운영 forecast archive나 실제 사전 발행 성적에 섞지 않는다.

검증: 시장 미시구조 unittest 281개 통과, UI 계약 통과.
24개 신규 테스트: 미래값 누수/양 경계 purge/단독 h 동가 처리/상하방 지표/보유율과 수급 구분/
LETF 품질 게이트/짧은 리밸런싱 데이터 학습 차단/LP 합성계수/전체 Holm/압축 기록 재현 등.

## 인수 파일

`New for anti/scripts/market_microstructure/FLOW_HORIZONS_POSITION_RESEARCH_20261106.md`에
실행 명령·모델·정확한 입력 기준·결과와 Cursor/Claude 지시를 정리했다.
산출은 `data/manifests/flow_horizons_research_20261105.{json,md}`와
`flow_horizons_predictions_20261105.jsonl.gz`. 날짜는11/5 수집 스냅샷 기준이며 분석 완료 정리는11/6이다.

Cursor는 보유율과 순매수 수량을 같이 유지하고 원천 분모/기업행동 기준을 확인한다.
원본 API 응답 `/tmp/foreign-ownership-long-raw-20261105.json`과
초기 `/tmp/foreign-ownership-raw-20261105.json`의 private 장기 백업은 아직 미확인이다.
원본SHA는 정규화 파일에 있으며, 이 PR은 정규화된 연구 입력과 결과를 GitHub에 보존한다.

Claude는 향후 UI에서 기간과 방향 질문을 분리하고 이번 결과를 연구로만 표시한다.
새 운영 horizon은 새 고정 모델/발행·결과 성숙일 계약 검토 후 연결해야 한다.
현재 자동 모델 교체나 시차 선택을 요청한 것이 아니다.
