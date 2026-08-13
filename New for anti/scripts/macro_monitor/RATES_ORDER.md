# Rates chip order & spreads

금리 탭 배치는 **중요도 + 만기 짧은→긴 + 유사끼리 붙이기**.

```
정책금리 → (FedWatch/TPI) → 단기금리(SOFR/SONIA…)
→ 커브 3M → 2Y → 3Y → 10Y → 30Y → (TIPS)
→ 커브 스프레드 (10Y−3M → 10Y−2Y → 30Y−10Y)
→ 대미/대역내 금리차 (한미역전, 미−캐 2Y, Gilt−Bund…)
→ 신용 스프레드 (HY OAS / 회사채·CP / BTP−Bund / LGFV…)
→ (해당 시) 5Y CDS → 국가신용등급
```

## 스프레드 — 남기는 것만

| 유지 | 이유 |
|------|------|
| US `10Y−3M`, `10Y−2Y`, `HY OAS` | 커브·신용의 핵심 3개. **미국 CDS는 demote** |
| JP `10Y−2Y`, `30Y−10Y` | 일본은 초장기 스토리. CDS demote |
| KR `한미역전` + `회사채 AA` + `CP` | CDS 대신 이게 한국 신용 |
| EZ `BTP−Bund` (+ CDS) | 분절화 |
| CN `미−중 10Y` + `LGFV` + `부동산 $HY` | CDS demote |
| CA/AU/CH/HK/SG 대미·대역내 1개 | 각각 그 나라의 핵심 금리차만 |
| EM CDS (BR/ZA/RU/KZ/VN) + UK CDS | 스트레스/키트 문서화 |

브라질·남아공 **중복 CDS 별칭**(`br_cds_5y` / `za_cds_5y`)은 skip → `sovereign_cds_5y`만.

구현: `engine.CHIP_ORDER["rates"]` · country `chip: false` / `skip`.
