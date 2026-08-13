# Macro Kit Template — **미국(US) 기준 통일 양식**

모든 국가 키트는 이 양식을 따른다. 벤치마크 = `us_macro_benchmark_v1`.

구현: `config/series.spec.json` → `country_series.<ISO3>` · 엔진 `CATEGORIES_ORDER` 고정.

---

## 1. 6탭 (순서 고정 · 생략 금지)

| order | id | 한글 | 미국 기준 역할 | 타국 매핑 규칙 |
|------:|----|------|----------------|----------------|
| 1 | `liquidity` | 유동성 | 중앙은행 BS · TGA/RRP · **Net Liquidity** · M2 | CB 자산 + **공통 M2/M3 vs 2019** + 국가 고유 유동성(가계부채·NFRK·Sight Deposits·Credit Quota 등) |
| 2 | `rates` | 금리 | EFFR · 국채 · 스프레드 · 신용스프레드 | **정책금리** + 국채 2Y/10Y(+필요시 30Y) + 대미/대역내 스프레드 + CDS(가능 시) |
| 3 | `fx` | 환율 | DXY · EUR · JPY | **USD/\*** 또는 주요 교차 + 외환보유/경상 + us_fx_watch (+ FX 스프레드·Urals−Brent 등). **주력 수출 원자재는 넣지 않음** |
| 4 | `equity` | 주식 | SPX · NDX · RUT · VIX | 대표지수 + 외국인/FDI + (가능 시) 변동성 |
| 5 | `growth` | 성장 | GDP · GDPNow · PMI · 고용 | GDP QoQ/YoY + **수출 드라이버**(KR 반도체 · BR 철광석/대두/원유 · AU 철광석 등) + 선행지표 + (필요 시) 부동산/산업분리 |
| 6 | `inflation` | 물가 | Core PCE · CPI · BEI | Headline + Core/중앙은행 선호지표 |

탭을 합치거나(`FX & Commodities`) 이름을 바꿔서 넣지 않는다.  
주력 수출·교역 원자재는 **`growth`**(한국 반도체 수출과 동일 슬롯). 부동산·생보 헤지 등은 해당 탭에 슬롯으로 넣는다.

---

## 2. 문서 골격 (`XX_MACRO_KIT.md`)

```markdown
# <Country> Macro Kit (`xx_macro_v1`)

한 줄 purpose (미국 연동 / 자원 / 부채 제약 등).

## 구조 (6탭)
| 탭 | 핵심 |
|----|------|
| 유동성 | … |
| 금리 | … |
| 환율 | … |
| 주식 | … |
| 성장 | … |
| 물가 | … |

## 헤드라인 (정확히 6개 · 탭당 대표 1)
liquidity · rates · fx · equity · growth · inflation 순 권장

## 한계 (3~4항)
인과 단절 · 비선형 · 비정량 외생

## 데이터
fixture_synth → 실어댑터 링크 (DATA_SOURCES)
```

---

## 3. 공통 시리즈 (가능하면 모든 국가)

| id | 탭 | 의미 |
|----|-----|------|
| `m2_vs_2019` 또는 `m3_vs_2019` | liquidity | 코로나 이전 대비 통화량 (공통 규약) |
| `m2_yoy` / `m3_yoy` | liquidity | 전년비 |
| `bond_10y` | rates | 장기 국채 (라벨만 국가별 override) |
| `bond_2y` | rates | 단기 (있는 나라) |
| `gdp_yoy` · `gdp_qoq` | growth | |
| `cpi_yoy` · `core_cpi_yoy` | inflation | |
| `unemployment` | growth | 있는 나라 |
| `fx_reserves` / `current_account` | fx | 있는 나라 |

미국만의 고유 파생은 타국에 억지로 복제하지 않는다.  
대신 **기능 동등물**을 쓴다:

| 미국 | 기능 | 타국 예 |
|------|------|---------|
| Fed Total Assets | CB BS | BOJ/ECB/BOK/RBA/SNB assets |
| TGA + ON RRP | 유동성 흡수 | Sight Deposits(CH), Aggregate Balance(HK), Credit Quota(VN) |
| **Net Liquidity** | 시중 순유동성 | 국가별 파생식(정의 문서화) 또는 CB자산−흡수항 |
| EFFR | 정책금리 | Overnight / Cash / SELIC / Base Rate … |
| DXY | 통화가치 | USD/\* |
| HY OAS | 신용스트레스 | 회사채·CDS·CP 스프레드 |
| VIX | 공포 | VKOSPI / ASX VIX / Nikkei VI |
| Core PCE | CB 타겟 물가 | Trimmed Mean / CPI-trim / Core HICP |

---

## 4. 헤드라인 규칙

- **6개** (미국: Net Liq · 10Y · DXY · SPX · GDPNow · Core PCE)
- 순서 권장: liquidity → rates → fx → equity → growth → inflation
- display는 `series.format`으로 통일

---

## 5. 한계(limitations) 규칙

- 제목: `지표 분석·추론의 한계 (<국가>)`
- **3항 기본**, 지정학·특수구조면 4항(대만)
- 각 항: **인과 단절**을 명시 (지표 A↑ ≠ 결과 B)

---

## 6. 미국 벤치마크 체크리스트 (새 국가 추가 시)

- [ ] 6탭 모두 `active_categories`에 존재
- [ ] 공통 `m2/m3_vs_2019` 포함 (해당 통화통계 있을 때)
- [ ] 정책금리 + 국채 10Y
- [ ] USD 교차환율
- [ ] 대표 주가지수
- [ ] GDP + CPI
- [ ] 한계 ≥ 3
- [ ] `featured: true` · kit = `xx_macro_v1`
- [ ] DATA_SOURCES에 무료 소스 1절
