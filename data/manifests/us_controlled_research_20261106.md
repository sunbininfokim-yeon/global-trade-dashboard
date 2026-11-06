# 미국 통제 후 수급·보유율·옵션 활동 연구

모든 숫자는 이미 탐색한 과거의 재학습·재현이다. 실제 사전 예측이나 오늘의 확률이 아니다.

## 다음 장 방향 (Brier: 낮을수록 좋음)

| 종목 | 목표 | test n | 미국 기준 | +수급 | +보유율 | +둘 다 | +잔차 수급 | +옵션 활동 | 최근 빈도 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 005930 | opening1 | 161 | 0.22377 | 0.21717 | 0.21445 | 0.22166 | 0.21808 | 0.22449 | 0.25177 |
| 005930 | closing1 | 163 | 0.23196 | 0.23086 | 0.23557 | 0.23655 | 0.23089 | 0.23153 | 0.24908 |
| 005930 | intraday1 | 159 | 0.26228 | 0.26210 | 0.26055 | 0.26285 | 0.26231 | 0.26286 | 0.25844 |
| 000660 | opening1 | 171 | 0.22671 | 0.21826 | 0.21974 | 0.21728 | 0.21814 | 0.22411 | 0.25547 |
| 000660 | closing1 | 171 | 0.22857 | 0.22881 | 0.22865 | 0.22962 | 0.22883 | 0.22909 | 0.25504 |
| 000660 | intraday1 | 171 | 0.24765 | 0.25697 | 0.25595 | 0.25726 | 0.25703 | 0.24975 | 0.25622 |

## 다음 장 움직임 크기 (MAE: 낮을수록 좋음, 단위는 로그변화×100)

| 종목 | 목표 | test n | 미국 기준 | +옵션 활동 | +수급·활동 | 최근 평균 |
|---|---|---:|---:|---:|---:|---:|
| 005930 | absolute_gap_pct | 166 | 2.07590 | 2.06475 | 2.12026 | 2.04255 |
| 005930 | absolute_intraday_pct | 166 | 1.87667 | 1.86593 | 1.88696 | 1.81761 |
| 005930 | range_pct | 166 | 2.11662 | 2.09851 | 2.20044 | 2.36942 |
| 000660 | absolute_gap_pct | 172 | 2.27435 | 2.26499 | 2.27457 | 2.44395 |
| 000660 | absolute_intraday_pct | 172 | 2.03518 | 2.06091 | 2.05658 | 2.12031 |
| 000660 | range_pct | 172 | 2.49551 | 2.50430 | 2.53740 | 2.77140 |

## 1차36검정

| 종목 | 비교 | n | 평균 loss 차이 | Holm p |
|---|---|---:|---:|---:|
| 005930 | direction:opening1:us_flow | 161 | -0.00660 | 1.00000 |
| 005930 | direction:opening1:us_ownership | 161 | -0.00933 | 1.00000 |
| 005930 | direction:opening1:us_flow_ownership | 161 | -0.00211 | 1.00000 |
| 005930 | direction:opening1:us_residual_flow | 161 | -0.00569 | 1.00000 |
| 005930 | direction:opening1:us_activity | 161 | 0.00072 | 1.00000 |
| 005930 | direction:opening1:us_flow_activity | 161 | -0.00509 | 1.00000 |
| 005930 | direction:closing1:us_flow | 163 | -0.00110 | 1.00000 |
| 005930 | direction:closing1:us_ownership | 163 | 0.00362 | 1.00000 |
| 005930 | direction:closing1:us_flow_ownership | 163 | 0.00459 | 1.00000 |
| 005930 | direction:closing1:us_residual_flow | 163 | -0.00107 | 1.00000 |
| 005930 | direction:closing1:us_activity | 163 | -0.00043 | 1.00000 |
| 005930 | direction:closing1:us_flow_activity | 163 | -0.00202 | 1.00000 |
| 005930 | magnitude:absolute_gap_pct:us_activity | 166 | -0.01115 | 1.00000 |
| 005930 | magnitude:absolute_gap_pct:us_flow_activity | 166 | 0.04436 | 1.00000 |
| 005930 | magnitude:absolute_intraday_pct:us_activity | 166 | -0.01075 | 1.00000 |
| 005930 | magnitude:absolute_intraday_pct:us_flow_activity | 166 | 0.01029 | 1.00000 |
| 005930 | magnitude:range_pct:us_activity | 166 | -0.01811 | 1.00000 |
| 005930 | magnitude:range_pct:us_flow_activity | 166 | 0.08381 | 1.00000 |
| 000660 | direction:opening1:us_flow | 171 | -0.00845 | 1.00000 |
| 000660 | direction:opening1:us_ownership | 171 | -0.00697 | 1.00000 |
| 000660 | direction:opening1:us_flow_ownership | 171 | -0.00943 | 1.00000 |
| 000660 | direction:opening1:us_residual_flow | 171 | -0.00857 | 1.00000 |
| 000660 | direction:opening1:us_activity | 171 | -0.00260 | 1.00000 |
| 000660 | direction:opening1:us_flow_activity | 171 | -0.00905 | 1.00000 |
| 000660 | direction:closing1:us_flow | 171 | 0.00024 | 1.00000 |
| 000660 | direction:closing1:us_ownership | 171 | 0.00008 | 1.00000 |
| 000660 | direction:closing1:us_flow_ownership | 171 | 0.00105 | 1.00000 |
| 000660 | direction:closing1:us_residual_flow | 171 | 0.00026 | 1.00000 |
| 000660 | direction:closing1:us_activity | 171 | 0.00052 | 1.00000 |
| 000660 | direction:closing1:us_flow_activity | 171 | 0.00117 | 1.00000 |
| 000660 | magnitude:absolute_gap_pct:us_activity | 172 | -0.00936 | 1.00000 |
| 000660 | magnitude:absolute_gap_pct:us_flow_activity | 172 | 0.00023 | 1.00000 |
| 000660 | magnitude:absolute_intraday_pct:us_activity | 172 | 0.02573 | 1.00000 |
| 000660 | magnitude:absolute_intraday_pct:us_flow_activity | 172 | 0.02140 | 1.00000 |
| 000660 | magnitude:range_pct:us_activity | 172 | 0.00878 | 1.00000 |
| 000660 | magnitude:range_pct:us_flow_activity | 172 | 0.04189 | 1.00000 |

음수 loss 차이는 추가 입력에 유리하다. p값은 작은 과거 표본의 HAC 근사이며 전향 검증이나 인과효과를 증명하지 않는다.
상승/하락 정밀도·재현율, 동가 제외 수, reference-only, 보정 구간별 빈도,2~5일 결과는 JSON에 보존했다.
옵션 활동은 국내 콜풋 시장 거래금액이다. 계약 거래량·미국 옵션·변동성 순매수·딜러 포지션이 아니다.
수급 잔차화는 정보를 새로 추가하지 않는다. 원래 수급과의 차이는 규제/정규화 효과일 수도 있다.
현재 운영 모델/계수/UI/워크플로/공개 데이터 변경 없음. 비용·손익 계산 없음.
