# Macro Monitor — 선빈이 확보할 API / 데이터 소스

엔진은 지금 `fixture_synth`다. 실데이터를 붙이려면 아래를 **우선순위대로** 뜯어오면 된다.  
✅ = 공개 API/다운로드로 비교적 수월 · ⚠️ = 스크래핑·수동·유료 · ❌ = 공개로 거의 불가(대체지표만)

---

## 0. 공통 인프라 (먼저)

| 소스 | 용도 | 난이도 | 메모 |
|------|------|--------|------|
| **FRED API** (`api.stlouisfed.org`) | 미·일부 국제 금리/FX/물가 | ✅ 키 발급 | 이미 레포 금융패널과 친함 |
| **BIS SDMX** / BIS statistics | REER | ✅ | 엔·파운드·달러 REER |
| **Yahoo / Stooq / Polygon** 등 | 주가지수 일봉 | ✅~⚠️ | 라이선스·약관 확인 |
| **IMF IFS** | M2/M4·예비 | ✅ | 갱신 느림 |
| **Ember Yearly Electricity** | 국가별 발전량 TWh · 연료 믹스 | ✅ CC-BY | `config/electricity_ember_v1.json` · `tools/extract_ember_electricity.py` |

키/시크릿은 커밋 금지. Worker 시크릿 또는 로컬 env.

갱신 주기 티어: [`REFRESH_TIERS.md`](./REFRESH_TIERS.md) (Alpha Vantage = last resort only).

### 0b. 매크로 뉴스 (UI 사이드 레일 — forthcoming)

| 항목 | 메모 |
|------|------|
| 트리거 | 지표 칩/차트 클릭 → `news_query` / `news_tags` |
| 구현 | **서버사이드** Worker + **캐시(KV)** — 브라우저에서 뉴스 API 직콜 금지 권장 |
| fixture | `news: null` only — **가짜 기사 넣지 말 것** |
| UI 계약 | [`CLAUDE_UI_HANDOFF_US_TUNING.md`](./CLAUDE_UI_HANDOFF_US_TUNING.md) §B |

---

## 1. 미국 (`us_macro_benchmark_v1`) — 대부분 FRED

| 지표 | 추천 소스 | ID/힌트 | 난이도 |
|------|-----------|---------|--------|
| Fed 총자산 | FRED | `WALCL` | ✅ |
| TGA | FRED | `WTREGEN` | ✅ |
| ON RRP | FRED | `RRPONTSYD` | ✅ |
| Discount window | FRED | `WLCFLPCL` 등 | ✅ |
| M2 | FRED | `M2SL` | ✅ → vs2019·YoY 엔진 계산 |
| EFFR / SOFR | FRED | `EFFR`, `SOFR` | ✅ |
| 2Y / 10Y / TIPS10 | FRED | `DGS2`, `DGS10`, `DFII10` | ✅ |
| 10Y−3M | FRED | `T10Y3M` 또는 계산 | ✅ |
| HY OAS | FRED | `BAMLH0A0HYM2` | ✅ |
| DXY | FRED / ICE | `DTWEXBGS`(근사) 또는 DXY 벤더 | ✅~⚠️ |
| EURUSD, USDJPY | FRED | `DEXUSEU`, `DEXJPUS` | ✅ |
| S&P / Nasdaq / RUT / VIX | FRED or 시세 API | `SP500`, `NASDAQ100`, `RU2000PR`, `VIXCLS` | ✅ |
| GDP QoQ/YoY | FRED / BEA | `A191RL1Q225SBEA` 등 | ✅ |
| GDPNow | Atlanta Fed | 웹/JSON | ⚠️ |
| ISM PMI | ISM | 유료·지연 | ⚠️ → S&P Global flash로 대체 검토 |
| NFP / U-rate / Claims / Sahm | FRED | `PAYEMS`, `UNRATE`, `ICSA`, `SAHMREALTIME` | ✅ |
| Core PCE / CPI / Core CPI | FRED | `PCEPILFE`, `CPIAUCSL`, `CPILFESL` | ✅ |
| 5Y/10Y BEI | FRED | `T5YIE`, `T10YIE` | ✅ |
| Fed UST 만기분포 | NY Fed / Fed H.4.1 | HTML/PDF | ⚠️ |
| MBS 보유 | FRED | `WSHOMCB` | ✅ |
| FIMA repo | NY Fed | 주간 통계 | ⚠️ |
| QRA coupon/bill | Treasury QRA HTML | 이미 `macro_intel` | ✅ 재사용 |
| FedWatch 확률 | CME | 스크래핑/유료 | ⚠️ |

**미국 우선순위:** FRED 묶음 → QRA(기존) → GDPNow → Fed 만기분포/FIMA.

---

## 2. 일본 (`jp_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| BOJ 총자산 | BOJ Time-Series / BOJ API | ✅~⚠️ | BOJ 통계 다운로드 |
| BOJ/GDP | 위 + Cabinet GDP | ✅ | 비율은 엔진 계산 |
| BOJ ETF / J-REIT | BOJ 매입잔고 공시 | ⚠️ | 월간 표 |
| JGB BOJ 보유비율 | BOJ + MOF 발행잔고 | ⚠️ | 분자·분모 각각 |
| BOJ 당좌예금 | BOJ | ✅~⚠️ | |
| M2 | BOJ / FRED `MYAGM2JPM189N` | ✅ | vs2019·YoY 계산 |
| Call rate | BOJ | ✅ | |
| JGB 2/10/30 | MOF / Investing / FRED 일부 | ✅~⚠️ | |
| JGB 매입 목표·실적 | BOJ 오퍼레이션 공지 | ⚠️ | 월간 테이퍼 표 |
| USDJPY, EURJPY | FRED / FX API | ✅ | |
| 엔 REER | BIS | ✅ | |
| 외환보유액 | MOF | ✅ | |
| 외환개입 | MOF 개입실적 | ⚠️ | 사후 공표, 비정기 |
| Nikkei / TOPIX / Nikkei VI | 시세 API / JPX | ✅~⚠️ | |
| 외국인 수급 | JPX / Quick | ⚠️ | 주간 |
| GDP | Cabinet Office | ✅ | |
| Jibun PMI | S&P Global | ⚠️ | |
| 춘투 | Rengo / Keidanren 연간 | ⚠️ | **연 1회** — 시계열 희소 |
| 실질임금 | MHLW | ✅~⚠️ | |
| 유효구인배율 | MHLW | ✅ | |
| 근원/근원근원/도쿄CPI / CGPI | MIC / BOJ | ✅ | |

**일본 우선순위:** BOJ 자산·당좌·M2 → JGB 금리·USDJPY → CPI 묶음 → ETF/JGB비중(수동표 OK) → 춘투(연간 슬롯).

---

## 3. 영국 (`uk_macro_v1`) — 이번에 추가

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **Gilt 2/10/30Y** | BoE yield curves / FRED 일부 | ✅ | LDI 핵심 = **30Y** |
| **Gilt−Bund 10Y** | UK 10Y − DE 10Y | ✅ | 엔진 파생 가능 (DEU `bond_10y` 동시 수집) |
| **UK 5Y CDS** | Markit/ICE / 터미널 | ❌~⚠️ | **가장 아픈 포인트** — 공개 API 거의 없음. Refinitiv/Bloomberg 또는 대체(스프레드만) |
| **RPI** | ONS | ✅ | ILG·연금 기준 |
| BOE 총자산 | BoE Database / FRED `UKASSETS`류 | ✅ | |
| **APF 잔고** | BoE APF 공시 | ✅~⚠️ | QT 추적 |
| 비상 국채매입·레포 | BoE 시장운영 (2022식) | ⚠️ | 평시 0, 위기 시 급증 |
| **M4** | BoE / ONS | ✅ | vs2019·YoY (영국은 M2 대신 M4) |
| Bank Rate | BoE | ✅ | |
| **SONIA** | BoE | ✅ | |
| GBPUSD, EURGBP | FRED / FX | ✅ | |
| GBP REER | BIS | ✅ | |
| FTSE 100 / 250 | 시세 API | ✅~⚠️ | |
| GDP QoQ/YoY | ONS | ✅ | |
| UK PMI | S&P Global | ⚠️ | |
| **AWE** (±bonus) | ONS | ✅ | BOE가 서비스물가와 함께 봄 |
| 실업 · 비경제활동 | ONS | ✅ | |
| CPI / Core / **Services CPI** | ONS | ✅ | Services = 고착화 핵심 |

**영국 우선순위:**  
1) BoE Bank Rate + SONIA + Gilt 2/10/**30**  
2) ONS CPI/Core/Services + RPI + AWE  
3) M4 + APF  
4) GBP FX + FTSE  
5) **CDS는 유료/터미널** — 없으면 Gilt−Bund + 30Y 변동성으로 LDI 프록시

---

## 4. 중국 (`cn_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **TSF YoY** | PBOC / Wind / CEIC | ⚠️ | **최중요** — 표·지연 공개 많음 |
| **RRR** | PBOC 공시 | ✅ | 변경 시에만 움직임 |
| M1 / M2 YoY | PBOC / FRED 일부 | ✅~⚠️ | 가위표 = 엔진 `m1−m2` |
| M2 vs 2019 | 위 | ✅ | 엔진 계산 |
| OMO/MLF 순공급 | PBOC 일일 오퍼 | ⚠️ | 스크래핑 또는 Wind |
| **LPR 1Y/5Y** | PBOC | ✅ | |
| 중국 10Y | ChinaBond / Investing | ✅~⚠️ | |
| 미−중 10Y | US DGS10 − CN 10Y | ✅ | 엔진 파생 가능 |
| **LGFV 스프레드** | Wind / 지방채 벤치 | ❌~⚠️ | **유료 벤더** 거의 필수 |
| **부동산 $ HY** | Markit/ICE / 터미널 | ❌ | Asia HY property |
| USD/CNY · CNH | FRED / FX API | ✅ | `DEXCHUS` 등 |
| PBOC Fixing | PBOC 일일 | ✅~⚠️ | |
| 외환보유 · CFETS | SAFE / CFETS | ✅~⚠️ | |
| SSE / CSI300 (A주) · HSCEI (H주) · 북향/남향 | 시세·HKEX Connect | ✅~⚠️ | B주는 미포함(사장) |
| Northbound | HKEX / Wind | ⚠️ | 일별 순유입 |
| 커창지수 | 전력·화물·대출 합성 | ⚠️ | 공식 단일 API 없음 |
| NBS PMI | NBS | ✅ | |
| Caixin PMI | Caixin/S&P | ⚠️ | 라이선스 |
| 신규주택가격 · 부동산 FAI | NBS | ✅~⚠️ | |
| 청년실업 | NBS | ⚠️ | **기준 변경** 메타데이터 필수 |
| **PPI** / CPI | NBS | ✅ | PPI = 글로벌 핵심 |

**중국 우선순위:** TSF+M1/M2+LPR+PPI → CNY/CNH → **A주(CSI300)+북향** → H주(HSCEI) → NBS PMI+부동산 → LGFV/HY

---

## 5. 유로존 (`ez_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| ECB 총자산 / **APP** / **PEPP** | ECB SDW / Statistical Data Warehouse | ✅ | QT·재투자 핵심 |
| **M3** | ECB SDW | ✅ | vs2019·YoY |
| TLTRO 상환 | ECB | ✅~⚠️ | |
| **DFR / MRO / MLF** | ECB | ✅ | DFR = 실질 기준 |
| **Bund 10Y / BTP 10Y** | ECB / Investing / FRED | ✅ | 스프레드 엔진 파생 |
| TPI 가동 | ECB 공시 | ⚠️ | 평시 0 · 이벤트 플래그 |
| EUR/USD·GBP·JPY | FRED / FX | ✅ | |
| 유로 EER | ECB | ✅ | |
| Euro Stoxx 50 / DAX / CAC / Banks | 시세 API | ✅~⚠️ | |
| GDP | Eurostat | ✅ | |
| **HCOB PMI** | S&P/HCOB | ⚠️ | 라이선스 |
| **IFO** | IFO Institute | ✅~⚠️ | |
| **BLS** | ECB | ✅ | 분기 |
| **HICP / Core HICP** | Eurostat / ECB | ✅ | |
| 협약임금 | ECB | ✅~⚠️ | |

**유로존 우선순위:** DFR + Bund/BTP 스프레드 + HICP → APP/PEPP/M3 → EUR/USD + Stoxx → PMI/IFO

---

## 6. 러시아 (`ru_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **NWF 유동자산** | MinFin 월보 / 매체 재인용 | ⚠️ | **최우선** · 영문 API 거의 없음 |
| CBR 총자산 | CBR | ✅~⚠️ | |
| 외환보유 총/접근가능/동결비중 | CBR + 추정치 | ⚠️ | 동결분은 추산·언론 |
| M2 | CBR | ✅~⚠️ | vs2019 엔진 계산 |
| **Key Rate** | CBR | ✅ | |
| OFZ 10Y | MOEX / CBR | ✅~⚠️ | |
| **OFZ 입찰 커버** | MinFin 입찰 결과 | ⚠️ | 표·PDF |
| **CNY/RUB** | MOEX | ✅~⚠️ | 주력 페어 |
| USD/RUB | 장외/매체 | ⚠️ | 공식 왜곡 큼 |
| **Urals−Brent** | Argus / 로이터 / EIA 근사 | ⚠️~❌ | 제재강도 핵심 · 유료 많음 |
| MOEX / RTSI | MOEX | ✅~⚠️ | |
| GDP / CPI / 실업 | Rosstat / CBR | ⚠️ | **신뢰도↓ · 발표 중단 이력** |
| PMI | S&P Global | ⚠️ | |
| 노동력 부족 | 설문/대리(임금·공석) | ⚠️ | 공식 단일지수 약함 |
| 가계 기대인플레 | CBR | ✅~⚠️ | |

**러시아 우선순위:** NWF + Key Rate + CNY/RUB → OFZ·입찰 → Urals할인 → CPI/기대인플레 → RTSI  
**기대치:** 미·EU 대비 공개 API가 가장 빈약. 공식 수치만으로 붕괴시점 추론 **금지**(한계문 필수).

---

## 7. 홍콩 (`hk_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **Aggregate Balance** | HKMA | ✅ | **최중요** · 일별 |
| 외환보유 | HKMA | ✅ | |
| M2 | HKMA / Census | ✅ | |
| Base Rate | HKMA | ✅ | FFR 연동 규칙 |
| **HIBOR 1M/3M** | HKAB / HKMA | ✅ | |
| HIBOR−SOFR | 위 + FRED SOFR | ✅ | 엔진 파생 가능 |
| **USD/HKD** | HKMA / FX | ✅ | 밴드 7.75–7.85 |
| USD/CNH | FX / 중국키트 공유 | ✅ | |
| HSI / HSCEI / HSTECH | HKEX | ✅~⚠️ | |
| **CCL** | Centaline | ⚠️ | 주간 · 스크래핑/유료 |
| GDP · 소매 · 무역 · CPI | C&SD | ✅ | |

**홍콩 우선순위:** Aggregate Balance + USD/HKD + HIBOR → HSI/CCL → 소매·무역

---

## 8. 싱가포르 (`sg_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **S$NEER** | MAS | ✅~⚠️ | 정책 핵심 · 공개 지수/추정치 |
| NEER 기울기/폭/중심 | MAS 성명 | ⚠️ | 반기 MPS · 이벤트 플래그 |
| USD/SGD | FX / MAS | ✅ | |
| OFR | MAS | ✅ | |
| 총유동성 · M2 · 외화예금 | MAS / DOS | ✅~⚠️ | |
| **SORA** | MAS | ✅ | ≠ 정책 스탠스 |
| SGS 2Y/10Y | MAS / SGS | ✅ | |
| SOFR−SORA | FRED + MAS | ✅ | 엔진 파생 |
| STI / S-REIT | SGX | ✅~⚠️ | |
| 민간주택 | URA | ✅ | |
| **NODX** | IE Singapore / DOS | ✅ | **실물 최중요** |
| SIPMM PMI | SIPMM | ✅~⚠️ | |
| **MAS Core** / CPI | DOS / MAS | ✅ | Core = 정책 타겟 |

**싱가포르 우선순위:** S$NEER/기울기 + NODX + MAS Core → SORA/SGS → STI/REIT

---

## 9. 남아공 (`za_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| 재정수지 · **부채/GDP** | National Treasury | ✅ | 최우선 재정 |
| SARB 자산 · Repo · M3 | SARB | ✅ | |
| SAGB 10Y | SARB / JSE | ✅ | |
| **5Y CDS** | Markit/터미널 | ❌~⚠️ | 유료 |
| **USD/ZAR** | FX | ✅ | |
| 금·백금·석탄 | LBMA / 상품 API | ✅~⚠️ | |
| 무역수지 | SARS / Stats SA | ✅ | |
| JSE Top40 | JSE | ✅~⚠️ | |
| 외국인 수급 | JSE / National Treasury | ⚠️ | |
| **Load Shedding hours** | Eskom / CSIR / 매체 | ⚠️ | **실물 최중요** · 일·월 집계 |
| Absa PMI | Absa/S&P | ⚠️ | |
| GDP · 실업 · CPI | Stats SA | ✅ | 실업 구조적 30%+ |

**남아공 우선순위:** Load Shedding + 부채/GDP + USD/ZAR → Repo/SAGB → 원자재/무역 → CPI

---

## 10. 인도 (`in_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| 외환보유 · **CRR** · M3 | RBI | ✅ | |
| **Repo** · LAF | RBI | ✅ | |
| G-Sec 10Y | RBI / CCIL | ✅ | |
| **USD/INR** | RBI / FX | ✅ | |
| **CAD/GDP** | RBI / MoSPI | ✅ | 분기 · 최중요 |
| Nifty / Sensex | NSE / BSE | ✅~⚠️ | |
| **FPI** | NSDL / CDSL | ✅ | |
| GDP · CPI · WPI | MoSPI | ✅ | CPI 식료 비중↑ |
| PMI | S&P | ⚠️ | 서비스 중점 |
| 이륜차·트랙터 | SIAM / 업계 | ⚠️ | 월간 |
| 은행신용 YoY | RBI | ✅ | |

**인도 우선순위:** CAD/GDP + Repo + USD/INR → FPI/Nifty → CPI/WPI → 농촌판매·신용

---

## 10b. 이스라엘 (`il_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| BOI 총자산 · 외환보유 · M2 | Bank of Israel | ✅ | |
| **BOI 정책금리** · 셰켈 국채 | BOI | ✅ | 물가목표 1–3% |
| **5Y CDS** | Markit/터미널 | ⚠️ | **위험프리미엄 핵심** — 유지 |
| **USD/ILS** | BOI / FX | ✅ | |
| 재정수지 · 부채/GDP | MOF / CBS | ✅ | 전시 재정 |
| **TA-125** | TASE | ✅~⚠️ | |
| **하이테크 수출** | CBS / BOI | ✅~⚠️ | KR 반도체 슬롯 |
| GDP · 실업 · CPI | CBS | ✅ | 전시 노동공급 주의 |

**이스라엘 우선순위:** CDS + USD/ILS + BOI Rate → 하이테크수출/TA-125 → 재정 → CPI

### 이란 (`IRN`) — 키트 없음

제재·이중환율·통계 불투명·접근 제한. **표준 6탭 비추천.**  
유가·호르무즈·해운은 글로벌 외생으로만 추적.

---

## 11. 한국 (`kr_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| 한은 총자산 · M2 · 기준금리 | BOK ECOS | ✅ | |
| **가계신용** | BOK | ✅ | 정책 제약 |
| **PF 잔액·연체** | FSS / 언론·공시 | ⚠️ | 비은행 중심 |
| 국고 3Y/10Y · 회사채·CP 스프레드 | BOK / 금융투자협회 | ✅ | |
| 한미 금리역전 | FFR + BOK | ✅ | 엔진 파생 가능 |
| **USD/KRW** · 외환보유 · 경상 | BOK | ✅ | |
| KOSPI/KOSDAQ/VKOSPI · 외국인 | KRX | ✅ | |
| **반도체 수출** · 수출 1–20일 | 관세청 / MOTIE | ✅ | **최중요** |
| GDP · CCSI/BSI · 산업활동 | BOK / 통계청 | ✅ | |
| CPI · Core · 기대인플레 | 통계청 / BOK | ✅ | |

**한국 우선순위:** 반도체수출 + USD/KRW + 기준금리 → 가계/PF → 스프레드 → CPI

---

## 12. 캐나다 (`ca_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **가계부채/가처분소득** | StatCan / BOC | ✅ | BOC 최대 제약 |
| M3 · BOC 총자산 | BOC | ✅ | |
| Overnight · GoC 2Y/10Y | BOC | ✅ | |
| 미−캐 2Y 스프레드 | UST + GoC | ✅ | 엔진 파생 가능 |
| **USD/CAD** · 무역수지 | BOC / StatCan | ✅ | |
| **WCS** · WCS−WTI | 시장/Alberta | ⚠️ | WTI 스프레드 |
| S&P/TSX · 외국인 증권 | TMX / StatCan | ✅ | |
| **Teranet-National Bank HPI** | Teranet | ⚠️ | 라이선스·지연 |
| GDP · 1인당 GDP · 고용 | StatCan | ✅ | **총량 vs 1인당** |
| Ivey PMI | Ivey | ⚠️ | |
| CPI · CPI-trim/median | StatCan / BOC | ✅ | BOC 핵심 |

**캐나다 우선순위:** 가계부채/소득 + Overnight + USD/CAD → WCS/Teranet → CPI-trim → 1인당GDP

---

## 13. 호주 (`au_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **가계부채/가처분소득** | ABS / RBA | ✅ | G10 최고 |
| M3 · RBA 총자산 | RBA | ✅ | TFF 만기 |
| Cash Rate · ACGB 3Y/10Y | RBA | ✅ | |
| 미−호 10Y 스프레드 | UST + ACGB | ✅ | |
| **AUD/USD** · 무역수지 | RBA / ABS | ✅ | |
| **철광석 · 원료탄** | 시장/중국철강 | ✅ | 중국 연동 |
| ASX 200 · VIX | ASX | ✅ | |
| **CoreLogic HPI** · 건축승인 | CoreLogic / ABS | ⚠️ | 라이선스 |
| GDP · 1인당 GDP · 고용 | ABS | ✅ | **총량 vs 1인당** |
| CPI · 월간 CPI · Trimmed Mean | ABS / RBA | ✅ | RBA 최우선 |

**호주 우선순위:** 철광석 + 가계부채/소득 + Cash Rate → AUD → CoreLogic/Trimmed Mean → 1인당GDP

---

## 14. 스위스 (`ch_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| SNB 총자산 · 외환보유 | SNB | ✅ | GDP 초과 기형 |
| **Sight Deposits** | SNB | ✅ | 개입 선행 |
| M3 | SNB | ✅ | |
| Policy Rate · 연맹 10Y | SNB | ✅ | |
| CH−Bund 10Y | SNB + Bund | ✅ | |
| **EUR/CHF** · USD/CHF · REER | SNB / BIS | ✅ | **최중요 FX** |
| 경상수지 | SNB | ✅ | 구조적 흑자 |
| SMI · 금융주 | SIX | ✅ | 방어주 편중 |
| GDP · **KOF** · PMI | SECO / KOF / procure.ch | ✅ | |
| CPI | SFSO | ✅ | 구조적 저인플레 |

**스위스 우선순위:** EUR/CHF + Sight Deposits + Policy Rate → SMI/KOF → CPI → CH−Bund

---

## 15. 브라질 (`br_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **기초재정수지** · 공공부채/GDP | Treasury / BCB | ✅ | 재정 최민감 |
| M3 | BCB | ✅ | |
| **SELIC** · 국채 10Y | BCB | ✅ | |
| **5Y CDS** | 터미널 | ⚠️ | 유료 |
| **USD/BRL** · 외환보유 · 경상 | BCB | ✅ | |
| 철광석 · 대두 · 원유 | 시장 | ✅ | 수출 3대 축 |
| Ibovespa · 외국인 유입 | B3 | ✅ | |
| GDP · **IBC-Br** · 실업 | IBGE / BCB | ✅ | 농업·기후 |
| PMI | S&P Global | ⚠️ | 라이선스 |
| **IPCA** · IPCA-15 | IBGE | ✅ | BCB 타겟 |

**브라질 우선순위:** 기초재정 + SELIC + USD/BRL → 원자재 → Ibovespa/CDS → IPCA

---

## 16. 베트남 (`vn_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **USD/VND** · 외환보유 | SBV | ✅ | 관리변동 ±5% |
| 무역수지 · 수출 YoY | GSO / Customs | ✅ | FDI기업 비중 |
| **FDI 등록·실행** | MPI | ✅ | China+1 |
| VN-Index | HOSE | ✅ | 부동산·금융 |
| 재융자·할인율 · 예금/대출 | SBV | ✅ | |
| **Credit Growth Quota** | SBV | ⚠️ | 연간 한도 · 핵심 |
| M2 | SBV | ✅ | |
| GDP · IIP · PMI | GSO / S&P | ⚠️ | PMI 라이선스 |
| CPI | GSO | ✅ | 목표 ~4–4.5% |

**베트남 우선순위:** FDI + USD/VND + Credit Quota → 수출 → VN-Index → CPI

---

## 17. 카자흐스탄 (`kz_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **NFRK** | MinFin / NBK | ✅ | 재정 완충 |
| M3 | NBK | ✅ | |
| **USD/KZT** · **RUB/KZT** | NBK | ✅ | 유가·러시아 연동 |
| Brent · CPC Blend | 시장 | ✅ | 수출 50%+ |
| **우라늄** | spot / Kazatomprom | ⚠️ | |
| 경상수지 | NBK | ✅ | 배당 송금 |
| Base Rate · 국채 | NBK | ✅ | 고금리 |
| KASE · FDI | KASE / NBK | ✅ | 채굴 편중 |
| GDP · 광업/제조 IP | Bureau of Stats | ✅ | 분리 필수 |
| CPI | Bureau of Stats | ✅ | 수입물가 |

**카자흐스탄 우선순위:** NFRK + USD/KZT + 유가/우라늄 → Base Rate → RUB/KZT → CPI

---

## 18. 대만 (`tw_macro_v1`)

| 지표 | 추천 소스 | 난이도 | 메모 |
|------|-----------|--------|------|
| **USD/TWD** · 외환보유 · 경상/GDP | CBC | ✅ | |
| **생보 해외투자·헤지비율** | FSC / 업계 | ⚠️ | 핵심 FX 변수 |
| 초과저축 · M2 | DGBAS / CBC | ✅ | |
| CBC 할인율 · 국채 10Y | CBC | ✅ | UST보다 낮음 |
| **가권(TAIEX)** · 외국인 | TWSE | ✅ | TSMC·SOX |
| **수출주문** · 수출 YoY | MOEA | ✅ | 테크 선행 |
| GDP · PMI | DGBAS / S&P | ⚠️ | PMI 라이선스 |
| CPI · Core | DGBAS | ✅ | |

**대만 우선순위:** USD/TWD + 헤지비율 + 수출주문 → 가권/외국인 → CBC → CPI

---

## 19. 공개로 거의 안 되는 것 (기대치 조절)

| 항목 | 이유 | 대시보드 대안 |
|------|------|----------------|
| 연금 LDI OTC 레버리지·마진 | 비공개 | Gilt 30Y + APF비상 + Gilt−Bund |
| CME FedWatch 공식 API | 스크래핑/벤더 | 생략 또는 수동 |
| ISM / S&P / Caixin PMI 실시간 | 라이선스 | 지연 공개치 |
| Sovereign CDS / LGFV·CN HY | 터미널 | 스프레드 프록시 또는 생략 |
| BOJ ETF Exit 스케줄 | 없음 | 잔고 + 한계 문구 |
| LGFV 음성부채 전수 | 비공개 | TSF + 한계 문구 |
| 커창 공식 API | 없음 | 구성요소로 자체 합성 |
| HCOB/S&P PMI 실시간 | 라이선스 | flash·지연치 |
| 러시아 무역·자본흐름 상세 | 발표 중단 | NWF·Urals·CNY/RUB 프록시 |
| Urals 할인 실시간 | 유료(Argus 등) | 주간 매체 인용 |
| CCL 실시간 API | 상업 | 주간 공개치·스크래핑 |
| NEER 밴드 실시간 파라미터 | MAS 비공개 상세 | 성명 기울기 + 공개 NEER 지수 |
| ZA Sovereign CDS | 터미널 | SAGB·USD/ZAR 프록시 |
| Load Shedding 공식 API | 파편화 | Eskom 앱/CSIR/매체 집계 |
| 인도 비공식 고용 실시간 | 없음 | 이륜차·트랙터·신용으로 보완 |
| 한국 PF 전수 연체 실시간 | 공시 지연 | FSS 분기·언론 |
| Teranet HPI 실시간 API | 상업 | 월간 공개치 |
| CoreLogic HPI 실시간 API | 상업 | 월간 공개·지연치 |
| 브라질 CDS 실시간 | 터미널 | 지연·매체 인용 |
| SBV Credit Quota 은행별 잔여 | 비공개 | 연간 한도·총량 공표 |
| CPC 가동/정치 리스크 실시간 | 지정학 | 뉴스·한계 문구 |
| 생보 헤지비율·스와프 포지션 전수 | 비공개 | FSC 집계·업계 추정 |

---

## 20. 선빈 액션 체크리스트 (짧게)

**당장 키만 있으면 되는 것**
- [ ] FRED API key
- [ ] (선택) 주가/FX용 Polygon 또는 기존 Worker 프록시

**다운로드·어댑터**
- [ ] BoE: Bank Rate, SONIA, APF, M4, Gilt curve
- [ ] ONS: CPI, Services, RPI, AWE, GDP, labour
- [ ] BOJ: assets, current account, M2, JGB/ETF
- [ ] **PBOC/NBS: TSF, M1/M2, LPR, RRR, PPI/CPI, PMI**
- [ ] **ECB SDW: APP/PEPP, M3, DFR, BLS · Eurostat HICP**
- [ ] **CBR/MinFin: Key Rate, NWF, M2, 기대인플레 · MOEX CNY/RUB**
- [ ] **HKMA: Aggregate Balance, Base Rate, HIBOR, USD/HKD · C&SD 소매/무역**
- [ ] **MAS: S$NEER/OFR/SORA · DOS NODX · MAS Core CPI**
- [ ] **SARB/Treasury: Repo, SAGB, M3, 부채/GDP · Load Shedding 집계**
- [ ] **RBI: Repo, CRR, LAF, FX reserves, M3, CAD · MoSPI CPI/WPI/GDP**
- [ ] **BOK ECOS: 기준금리, M2, 가계신용, 국고·스프레드, USD/KRW · 관세청 반도체수출**
- [ ] **BOC/StatCan: Overnight, M3, 가계부채/소득, GoC, USD/CAD, CPI-trim · Teranet/WCS**
- [ ] **RBA/ABS: Cash Rate, M3, 가계부채/소득, ACGB, AUD, Trimmed Mean · 철광석**
- [ ] **SNB: Policy Rate, Sight Deposits, FX reserves, EUR/CHF · KOF · SFSO CPI**
- [ ] **BCB/IBGE: SELIC, 기초재정, USD/BRL, IBC-Br, IPCA · 철광석/대두**
- [ ] **SBV/GSO/MPI: USD/VND, 외환보유, FDI, Credit Quota, CPI · 수출**
- [ ] **NBK/MinFin: Base Rate, NFRK, USD/KZT, RUB/KZT, CPI · 유가/우라늄**
- [ ] **CBC/MOEA/TWSE: USD/TWD, 할인율, 수출주문, TAIEX · 생보 헤지(FSC)**
- [ ] BIS REER · Atlanta GDPNow · Treasury QRA

**유료/포기 후보**
- [ ] Sovereign CDS · LGFV · Urals · FedWatch · 실시간 PMI

원하면 `fetch_cbc.py` 스켈레톤.
