# Distortion & Squeeze (수급 불균형 모니터링)

탭1. JSON 계약: `market_microstructure_v1.json` → **`distortion_squeeze`**

투자 권유 아님. 공개 LETF·수급만.

---

## 데이터 한계 (솔직히)

| 원하는 것 | 현실 |
|-----------|------|
| 증권사 고객 레버리지 비율 | **비공시** → LETF AUM/turnover proxy |
| KR 개별주 옵션 장부 | KRX_API 시도 가능하나 엔드포인트 불안정 → 없으면 **missing** |
| 공매도 잔고 | data.krx 로그아웃 이슈 등 → 자주 **missing** |
| 미국 개별주 옵션 풀체인 | **유료**. 공개: Cboe delayed (SOXL/SMH/EWY 등 ETF·지수) + FINRA short |
| X(트위터)로 OI 대체 | **불가**. 감성·일화만. 숫자 대체 금지 |
| 틱 호가 매집 | 공개 데이터 없음 |

→ 가짜로 채우지 않음. `data_limits.*.quality` 배지.

---

## UI가 읽을 블록

```text
distortion_squeeze
├── concentration          # Conc_top2(삼전+하닉) / Top5 / Top10 — 하닉만이 아님
├── market
│   ├── levered_etf_aum_usd
│   ├── letf_category_share / by_direction   # gobus_inverse_2x 분리
│   ├── foreign_vs_retail
│   ├── flows_kospi_market
│   └── deposit_credit
├── stocks[]               # 스트레스 순 정렬 (ir_if_minus_10pct ↓)
│   ├── letf_turnover_ratio / wag_the_dog_band
│   ├── long_aum_share / inverse_aum_share / inverse_tv_share
│   ├── realized_ir_pct / ir_if_minus_5pct / ir_if_minus_10pct
│   ├── products[] (AUM·TV·L)
│   └── external_vs_spot (HK/crypto 규모 비교만)
├── ir_bands
├── data_limits            # short / options / customer leverage
└── read_ko[]              # 해석 힌트
```

---

## 해석 규칙 (엔진 `read_ko`와 동일)

1. **wag_the_dog_band = high**  
   LETF 거래대금 ≈ 현물 ADV → 리밸런싱이 가격을 흔들 여지.

2. **inverse_tv_share ≫ inverse_aum_share**  
   인버스/곱버스가 체결에서 과대 → 하락일 비대칭.

3. **ir_if_minus_10pct ≥ 10**  
   하루 −10% 시 리밸런싱 노셔널이 현물 ADV의 10%+ (high band).  
   Paper: Hynix 큰 날 rebalancing ~25% of cash 언급.

4. **Conc_top2 높음**  
   삼전+하닉 쏠림 → 한 종목 충격이 지수로 전이.

5. **곱버스**  
   `by_direction.gobus_inverse_2x` — `(L²−L)=6`, 롱2x 대비 충격 3배.

---

## 하지 않는 것

- 옵션 OI/감마를 추정 숫자로 채우기
- 공매도 missing을 0으로 표시
- HK/crypto를 KR wag-the-dog IR에 합산
- X 게시물 숫자를 OI로 사용

---

## 재빌드 후 확인

```bash
python build_market_microstructure.py --live --source auto --fx 1400
# → public/data/market_microstructure_v1.json
#    .distortion_squeeze.stocks[0].ir_if_minus_10pct
#    .distortion_squeeze.data_limits
#    .letf_category_share.by_direction   (라이브 후)
```
