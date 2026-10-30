# 매크로 모니터 — 숨김 카드(데모) 정리와 연결 방안

기준 2026-09-30. 실측 출처가 없는 카드는 `apply_hidden_flags.py`가 `hidden: true`로 숨긴다(매 실행 재계산 —
실측이 붙으면 자동으로 다시 보임). 수동 예외는 `config/hidden_cards_v1.json`.

처음 188장 → 이번 연결 후 남은 수는 맨 아래 합계 참고.

## 표시

| 기호 | 뜻 |
|---|---|
| ✅ | 연결 완료 (2026-09-30, 이 문서와 같은 커밋) |
| 🟢 | 무료 공식 출처 확인됨 — 코드만 쓰면 됨 |
| 🔶 | 가능성 있음 — 추가 확인 필요(코드·파일 형식·이용조건) |
| ⛔ | 원천 접근 불가(이 맥·지역에서 차단) — Actions 러너에서 재시도 또는 다른 경로 |
| 🔒 | 유료·라이선스 데이터 (S&P Global PMI, CDS, ISM, CME, 지수사업자 등) |
| ✖ | 공개된 시계열 자체가 없음(추정치·이벤트·정책 문서) — 숨김 유지 또는 카드 재설계 |

## 공통

- **5년 CDS (19개국 전부)** 🔒 — 무료 출처 없음. 숨김 유지 권장(또는 카드 삭제).
- **PMI 계열** 🔒 — S&P Global/HCOB/Caixin/Absa/Ivey/procure.ch/SIPMM. 무료 재배포 불가.

## 국가별

### 미국 (4)
| 카드 | 판정 | 방안 |
|---|---|---|
| fedwatch | 🔒 | CME FedWatch 약관상 재배포 불가 |
| ism_mfg, ism_services | 🔒 | ISM 라이선스 (FRED에서도 삭제됨) |
| sovereign_cds_5y | 🔒 | |

### 한국 (5)
| 카드 | 판정 | 방안 |
|---|---|---|
| fx_intervention | 🔶 | 한은 분기 외환 순거래 공시(웹 표) — 분기 1회 수동/스크래핑 |
| pf_loan_balance, pf_delinquency | 🔶 | 금융위·금감원 보도자료(PDF, 분기) — 자동화 어려움 |
| vkospi | 🔶 | KRX Open API (등록된 `KRX_API_KEY`) — 제공 여부 확인 필요 |
| sovereign_cds_5y | 🔒 | |

### 일본 (13)
| 카드 | 판정 | 방안 |
|---|---|---|
| fx_intervention | ✅ | 재무성 외환평형조작 CSV(월 합계, 마지막 공개 분기까지) |
| topix | 🔶 | Yahoo에 지수 없음 — ETF(1306.T) 대용 가능, 또는 JPX |
| foreign_equity_flow | 🔶 | JPX 투자주체별 매매동향(주간 xls) |
| boj_jgb_share | 🔶 | BOJ 자금순환통계(분기) — 기존 BOJ API로 가능성 |
| boj_jgb_purchase_actual, boj_jgb_ops | 🔶 | BOJ 시장운영 결과 — 월 집계 계열 확인 필요 |
| boj_jgb_purchase_target | ✖ | 정책 결정문 값(수동) |
| boj_etf_share | ✖ | ETF 시장 전체 규모 분모 필요(JPX) |
| shunto_wage | ✖ | 렌고 연 1회 발표(수동) |
| nikkei_vi | 🔒 | Nikkei |
| ism_mfg, pmi_services_jp | 🔒 | S&P Global |
| sovereign_cds_5y | 🔒 | |

### 중국 (27)
| 카드 | 판정 | 방안 |
|---|---|---|
| bond_10y, us_chn_10y_spread | ✅ | CFETS 국채 수익률곡선 10년(월말, 캐시) |
| pboc_fixing, cfets_rmb | ✅ | CFETS 기준환율·위안지수 |
| hscei | ✅ | Yahoo ^HSCE |
| current_account | ✅ | IMF BOP(분기) |
| m2_yoy, m2_vs_2019, m1_yoy, m1_m2_spread, tsf_yoy, rrr, omo_net | ⛔ | 인민은행·국가통계국 차단, IMF MFS에 중국 없음 — PBOC 영문 통계 페이지 재시도 |
| ppi_yoy, new_home_price, property_fai, youth_unemployment, nbs_pmi | ⛔ | 국가통계국 403 |
| northbound_flow, southbound_flow | 🔶 | HKEX 일별 통계(2024년부터 일별 순매수 공개 중단 — 확인 필요) |
| usdcnh, csi300 | ✖ | Yahoo 이력 1점, 무료 대체 없음 |
| li_keqiang | ✖ | 비공식 합성지수 |
| lgfv_spread, cn_hy_prop_spread | 🔒 | 채권지수 사업자 |
| caixin_pmi | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 유로존 (12)
| 카드 | 판정 | 방안 |
|---|---|---|
| app_balance, pepp_balance, ecb_bond_ops | 🟢 | ECB 웹 CSV(APP_breakdown_history.csv 응답 200) — 파서 작성 |
| tltro_repay | 🔶 | ECB ILM 장기대출 계열 키 확인 |
| bls_credit | 🔶 | ECB BLS 데이터셋(키 재탐색 필요) |
| negotiated_wages | ⚠️ | ECB 계열이 2025Q3 이후 미갱신 — 후속 계열 확인 |
| ifo_business | 🔶 | ifo xlsx 공개 — 이용조건 확인 |
| stoxx_banks | 🔶 | 지수 없음 — ETF(EXV1.DE, 유럽600 은행) 대용 가능 |
| tpi_active | ✖ | 이벤트 플래그(수동) |
| hcob_pmi_mfg, hcob_pmi_svc | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 영국 (10)
| 카드 | 판정 | 방안 |
|---|---|---|
| bond_2y, bond_30y, spread_10y2y | 🔶 | BoE 수익률곡선 아카이브(zip) 또는 IADB 다른 만기 코드 |
| boe_total_assets | 🔶 | IADB Bank Return 주간 계열 코드 확인 |
| apf_balance, boe_gilt_ops | 🔶 | BoE APF 분기 보고서 |
| boe_emergency_facility | ✖ | 이벤트성 |
| ism_mfg, ism_services | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 캐나다 (8)
| 카드 | 판정 | 방안 |
|---|---|---|
| gdp_per_capita_yoy | 🟢 | StatCan 실질GDP ÷ 분기 인구(파생) |
| hh_debt_income | 🟢 | StatCan 11-10-0065(가계부채/가처분소득) — 벡터 번호만 찾으면 됨 |
| foreign_securities_ca | 🔶 | StatCan 36-10-0025(월간) |
| wcs_oil, wcs_wti_spread | 🔶 | 앨버타 경제 대시보드 API(응답 확인, WCS 코드 탐색) |
| teranet_hpi, ivey_pmi | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 호주 (7)
| 카드 | 판정 | 방안 |
|---|---|---|
| m3_yoy, m3_vs_2019, rba_total_assets, hh_debt_income, acgb_3y | ⛔ | RBA 403 — Actions 러너에서 재시도 |
| corelogic_hpi | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 스위스 (4)
| 카드 | 판정 | 방안 |
|---|---|---|
| kof_barometer | ⛔ | KOF 데이터서비스 연결 거부 — 재시도 |
| swiss_banks | ✖ | 무료 지수 없음 |
| procure_pmi | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 남아공 (6)
| 카드 | 판정 | 방안 |
|---|---|---|
| core_cpi_yoy | ⛔ | Stats SA(Imperva) — SARB 코드 탐색 🔶 |
| sarb_total_assets | 🔶 | SARB 월간 대차대조표 코드 탐색 |
| foreign_bond_share | 🔶 | 재무부 월간 xls |
| m3_vs_2019 | ✖ | SARB·OECD 과거치 불일치로 보류(설계 결정 필요) |
| absa_pmi | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 싱가포르 (7)
| 카드 | 판정 | 방안 |
|---|---|---|
| sg_total_liquidity, fx_deposits | ⛔ | MAS만 공표 — MAS API 약관상 재배포 불가 |
| neer_slope, neer_band_width | ✖ | MAS 비공개(시장 추정치뿐) |
| m2_vs_2019 | ✖ | 2021-07 정의 변경으로 단절 |
| sreit_index | 🔒 | SGX |
| sovereign_cds_5y | 🔒 | |

### 홍콩 (6)
| 카드 | 판정 | 방안 |
|---|---|---|
| aggregate_balance, hk_fx_reserves, hk_base_rate | ⛔ | HKMA API 차단 — Actions에서 재시도 |
| hstech, usdcnh | ✖ | Yahoo 이력 없음(3032.HK ETF 대용 가능) |
| sovereign_cds_5y | 🔒 | |

### 러시아 (15)
| 카드 | 판정 | 방안 |
|---|---|---|
| current_account | ✅ | IMF BOP(분기) |
| unemployment, core_cpi_yoy, gdp_qoq, gdp | ⛔ | Rosstat 차단 — IMF 노동·국민계정 확인 🔶 |
| cbr_total_assets | 🔶 | CBR 월간 대차대조표 xlsx |
| nwf_liquid, ofz_auction_cover | 🔶 | 재무부(minfin.gov.ru) 공표 |
| urals_brent_spread | 🔶 | 재무부 월평균 Urals 공표(브렌트는 Pink Sheet) |
| fx_reserves_usable, fx_frozen_share, labor_shortage | ✖ | 추정치·비정기 |
| ism_mfg, ism_services | 🔒 | |
| sovereign_cds_5y | ✖ | 제재로 호가 없음 |

### 브라질 (7)
| 카드 | 판정 | 방안 |
|---|---|---|
| current_account | ✅ | IMF BOP(분기) |
| bond_10y | 🟢 | Tesouro Direto 공개 CSV(CKAN) |
| primary_fiscal_balance, foreign_portfolio_br | 🔶 | BCB SGS 코드 확인(메타데이터 조회 필요) |
| pmi_mfg_br, pmi_svc_br | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 베트남 (14)
| 카드 | 판정 | 방안 |
|---|---|---|
| current_account | ✅ | IMF BOP(분기) |
| m2_yoy, m2_vs_2019, sbv_refinancing, sbv_discount, credit_growth_quota, vn_deposit_rate, vn_lending_rate | ⛔ | SBV 차단, IMF MFS에 없음 |
| ip_yoy | ⚠️ | IMF 계열 2025-03 정지 |
| fdi_registered, fdi_disbursed | 🔶 | 기획투자부 외국인투자청 월간 보도 |
| vnindex | ✖ | Yahoo 이력 없음 |
| pmi_mfg_vn | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 카자흐스탄 (13)
| 카드 | 판정 | 방안 |
|---|---|---|
| current_account | ✅ | IMF BOP(분기) |
| rubkzt | 🟢 | Yahoo KZT=X ÷ RUB=X 교차환율(파생) |
| nbk_base_rate, nfrk_assets, fdi_net_kz | 🔶 | 카자흐 국립은행 웹 공표 |
| ip_yoy, mining_ip_yoy, mfg_ip_yoy | 🔶 | 통계청(stat.gov.kz) — API 확인 |
| kase_index, bond_10y | 🔶 | KASE 웹 |
| uranium, cpc_blend | 🔒 | UxC / Argus·Platts |
| sovereign_cds_5y | 🔒 | |

### 대만 (11)
| 카드 | 판정 | 방안 |
|---|---|---|
| gdp_yoy, core_cpi_yoy | ⛔ | 주계총처(DGBAS) Cloudflare |
| fii_flow_tw | ⛔ | TWSE 응답이 HTML(점검/차단) — 재시도 |
| export_orders_yoy | ⛔ | 경제부 통계처 |
| fx_intervention | 🔶 | 중앙은행 반기 공시(수동) |
| life_fx_assets, hedge_ratio | 🔶 | 금관회·보험협회 월간 |
| ca_gdp_tw | 🔶 | CBC 국제수지 ÷ GDP(GDP가 막혀 보류) |
| excess_savings | ✖ | 파생·추정 |
| pmi_mfg_tw | 🔒 | CIER |
| sovereign_cds_5y | 🔒 | |

### 인도 (12)
| 카드 | 판정 | 방안 |
|---|---|---|
| current_account | ✅ | IMF BOP(분기) |
| cad_gdp | 🔶 | IMF 경상수지 ÷ 명목GDP(파생, GDP 출처 필요) |
| bank_credit_yoy, laf_balance | 🔶 | RBI DBIE(API 여부 확인) |
| fpi_flow | 🔶 | NSDL 일별 FPI 통계(웹) |
| wpi_yoy | ⚠️ | IMF 계열 2025-10 정지 — 경제자문실(eaindustry.nic.in) 🔶 |
| crr | ✖ | 정책값(수동) |
| two_wheeler_sales, tractor_sales | 🔒 | SIAM/TMA |
| ism_mfg, pmi_services_in | 🔒 | |
| sovereign_cds_5y | 🔒 | |

### 이스라엘 (7)
| 카드 | 판정 | 방안 |
|---|---|---|
| current_account | ✅ | IMF BOP(분기) |
| fx_reserves | ✅ | IMF 국제유동성(월) |
| boi_total_assets | 🔶 | BOI SDMX 대차대조표 계열 탐색 |
| fiscal_deficit_gdp, debt_to_gdp | 🔶 | IMF GFS / 재무부(연간) |
| ism_mfg | 🔒 | |
| sovereign_cds_5y | 🔒 | |

## 다음 순서 제안

1. 🟢 먼저: ECB APP/PEPP·순매입(3), 캐나다 1인당 GDP·가계부채(2), 브라질 10년물(1), 카자흐 RUB/KZT(1).
2. 🔶 중 공식 파일이 있는 것: BoE 수익률곡선·총자산, StatCan 외국인 증권, CBR 대차대조표, 앨버타 WCS, BOI 총자산.
3. ⛔은 내일 Actions 첫 실행에서 미국 IP로 접속되는지 보고 결정 (RBA·HKMA·KOF·TWSE).
4. 🔒·✖ (CDS 19장, PMI 등)는 숨김 유지 — 카드를 아예 지울지는 사용자 결정.
