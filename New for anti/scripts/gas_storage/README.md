# 천연가스 재고 조사 및 수집 파이프라인 — 2026-09-09

사용자 요청에 따라 원유 페이지를 먼저 확인했다. 운영 https://chokemonitor.com/oil 화면은
2026-08-28 기준 SPR 286.6백만 배럴(-3.1), 쿠싱 22.5백만 배럴(+0.1), 26주 추이를 표시한다.
글로벌 Rig 카드는 2026-07 1,878.8기로 표시됐다. 이는 가스 전용 리그 수가 아니다.
원격 main의 기존 `scripts/rig_count/build_rig_count_v1.py`는 수동 Excel export를 입력으로 쓰며,
실시간 자동 다운로드 파이프라인이 아니다.

## 사용자에게 필요한 키

1. **GIE_API_KEY: 등록·실호출 확인.** https://agsi.gie.eu/account 에서 등록하고 AGSI와 ALSI **둘 다** 접근하도록 선택.
   같은 키로 유럽 지하 저장과 LNG 탱크 재고를 수집한다. 국가마다 별도 키는 필요 없다.
   공식 안내: https://www.gie.eu/transparency-platform/GIE_API_documentation_v007.pdf
2. **EIA_API_KEY: 선택/기존 키 재사용.** https://www.eia.gov/opendata/register.php
   현재 원유 Worker 코드가 EIA_API_KEY를 사용하는 것을 확인했다. 실제 secret 값은 읽지 않았다.
   재고는 키 없는 WNGSR JSON, Henry Hub 현물은 인증 API `/v2/natural-gas/pri/fut/data/`의 RNGWHHD 시계열을 이용한다.
3. JODI, AEMO 공개 CSV, 일본 METI 공개 자료는 별도 API 키 불필요.
   Baker Hughes 공개 리포트도 별도 공개 API 키 발급 대상이 아니다.
4. 중국/베트남의 최근 전국 재고는 키 발급만으로 해결되지 않는다. 공식 공개 연속 관측치를 확인하지 못했다.
   상용 데이터 계약은 이번 범위에서 요청하지 않았다.

키는 GitHub Actions repository secrets에 등록한다. 코드/공개 JSON/채팅에 키를 넣지 않는다.
Cloudflare 배포용 인증은 기존 배포 경로를 재사용하며, 이번 조사 때문에 신규 키를 발급할 필요는 없다.

## 실제 다운로드 결과

| 지역 | 기준 지표/출처 | 관측값 | 기준일 및 제약 |
|---|---|---:|---|
| 미국 | EIA Lower 48 working gas | 3,214 Bcf, 전주 +30 | 2026-08-28; 5년 평균보다 +5.2%; 공식 표본 추정 |
| 한국 | JODI national closing stocks | 2,737 million m3 = 27.37억 m3 | 2026-06 말; 전월 차이 -88 million m3 |
| 일본 | JODI national closing stocks | 7,163 million m3 | 2026-06 말; 일본 발전용 LNG 주간 통계와 범위 다름 |
| 대만 | JODI closing stocks | 913 million m3 | 2026-06 말; assessment code 3 보존, partial |
| 태국 | JODI closing stocks | 378 million m3 | 2026-05 말; assessment code 3 보존, partial |
| 중국 | JODI closing stocks | null | 최신 파일에 CLOSTLV 행 없음; STOCKCH로 역산하지 않음 |
| 베트남 | JODI closing stocks | 현재값 null | 마지막 행 2013-03, 0/code 3. Thi Vai 180,000 m3는 탱크 용량 |
| 인도 | JODI closing stocks | 최신 현재값으로 사용 불가 | 마지막 관측 2024-09, 278.54 million m3, stale |
| 인도네시아 | JODI closing stocks | 표시값 null | 최근 0/code 3 값을 실제 재고 0으로 확정하지 않음 |
| 말레이시아/싱가포르 | JODI closing stocks | 현재값 null | 오래된 행 또는 재고 행 없음 |
| 호주 Iona UGS | AEMO HeldInStorage | 12,919.409 TJ = 12.919409 PJ | 2026-09-08; 개별 시설이며 호주 전체 아님 |
| 유럽 EU | GIE AGSI | 759.5226 TWh / 67.12% | 2026-09-07; 국가 합계와 중복 |
| 독일 Rehden | GIE AGSI 개별 시설 | 3.2801 TWh / 9.18% | 2026-09-07; 독일 총계에 포함 |

출처와 정의:
- EIA 주간: https://ir.eia.gov/ngs/ngs.html ; JSON https://ir.eia.gov/ngs/wngsr.json
- JODI 다운로드: https://www.jodidata.org/gas/database/data-downloads.aspx
- 이번 자료 publicationId=26: https://www.jodidata.org/jodi-publisher/gas/26/GAS_world_NewFormat.zip
- JODI 단위/정의: https://www.jodidata.org/gas/support/user-guide/data-available-in-the-jodi-gas-world-database.aspx
- AEMO: https://www.aemo.com.au/energy-systems/gas/gas-bulletin-board-gbb/data-gbb/gas-flows
- 베트남 시설: https://www.pvgas.com.vn/news/pv-gas-breakthrough-efforts-to-bring-lng-into-vietnam
- 일본 발전용 LNG 주간: https://www.enecho.meti.go.jp/category/electricity_and_gas/electricity_measures/pdf/denryoku_LNG_stock.pdf

JODI의 M3는 **million m3 기체 환산**이다. 액체 LNG 탱크 m3 또는 LNG 톤으로 읽으면 안 된다.
JODI 0/code!=1 보류는 이 제품의 보수적 규칙이며, code 3이 곧 결측이라는 공식 해석은 아니다.
원본 0은 reported_value에 남긴다. 수입량-소비량으로 재고를 만들지 않는다.

## Rig 및 추가 지표

- Baker Hughes gas-directed rigs: 미국·캐나다 주간, 국제 국가별 월간.
  oil/gas 구분을 사용해야 하며 현재 원유 카드의 전체 rig 합계를 가스 리그라고 부르면 안 된다.
  중국 육상·러시아 등 제외 국가가 있고 사우디는 2024-01부터 집계 정의가 달라졌다.
  https://rigcount.bakerhughes.com/rig-count-faqs/
- 미국 EIA 재공표 가스 리그: https://www.eia.gov/dnav/ng/hist/e_ertrrg_xr0_nus_cm.htm
  월간은 주간 보고치 평균이므로 주간 값과 섞지 않는다. 이 adapter는 이번 초안에 미구현.
- 저장 완충력: 재고, 전기 대비 증감, AGSI 충전율, EIA 전년/5년 평균 비교.
- 공급 활동: 가스 리그 수, 생산량, LNG 액화시설 feedgas. 리그 수는 즉시 생산량이 아니다.
- 수입국: LNG 터미널 재고, send-out, 수입량, 발전용 가스 수요, 터미널 정비.
  한국·일본 같은 수입국에는 국내 시추 리그보다 이 지표가 직접적이다.

## 자동화와 검증

수집기는 EIA 8개, JODI 11개, AEMO 6개, GIE 21개(AGSI·ALSI 국가/EU 및 Rehden)의
46개 시계열을 제공한다. 공개 관측이 없는 국가도 null/unsupported로 명시한다.
Rehden 시설 EIC `21Z000000000271O`를 AGSI 공식 목록에서 찾아 현 운영자 ID로 요청한다.
가상 저장풀 VSP NORD(Rehden+Jemgum)와 혼동하지 않는다.

- `.github/workflows/gas_storage_daily.yml`: 매일 UTC 00:35(한국 09:35), 수동 실행 지원.
- 공식 자료 수집 → 계약 검사 → 원자적 JSON 저장 → main에 데이터만 커밋 → 기존 Cloudflare 배포.
- `deploy.yml`의 신뢰된 main workflow_run이 봇 커밋도 배포한다.
- 부분 실패 시 이전 관측을 보존하고 실패 상태를 게시한 뒤 CI를 실패로 표시한다.
- gas-storage.js는 가스 세계/국가 화면에서 단위·관측일·품질·시설 범위를 표시한다.
- 세계/EU/국가/개별 시설과 기체·LNG 액체 단위를 합산하지 않는다.
- Secret은 Actions 실행환경에서만 읽으며 원본 인증 응답과 키를 공개 파일에 저장하지 않는다.

```sh
python3 -m unittest discover -s 'New for anti/scripts/gas_storage/tests' -v
python3 'New for anti/scripts/gas_storage/collect.py' --require-gie
```

2026-09-09 실제 자료로 EIA/JODI/AEMO 및 GIE 전체 인증 수집을 확인했다.
Henry Hub는 2026-09-01 $2.90/MMBtu를 확인했다. 일별 관측이 주간 단위로 공표되는
주기를 고려해 10일 이상 지난 가격에 stale을 표시한다. 최신 수집 시각과 관측일은 별개다.
최초 미국 재고 이력은 2주이며 이후 누적한다. GIE는 190일, AEMO는 최근 31일,
JODI는 공식 전체 스냅샷의 최신 400개 관측을 보존한다. 정정 이력은 당시 알려졌던 정보의
백테스트 자료로 간주할 수 없다.

## TTF 가격 연결 대기

TTF는 거래 허브·가격 기준이며 Rehden 같은 저장시설이 아니다. 현물/선물·거래소·만기·통화를
확인하기 전에는 값과 계약 유형을 null로 유지한다. `TTF_API_KEY`나 `OIL_PRICE_API_KEY`라는
secret 이름만으로 제공업체를 결정하지 않는다. 사용자가 말한 oilprice.com과 oilpriceapi.com은
별도 업체이므로 발급 도메인 확인이 필요하다.

OilPriceAPI인 경우 공식 API 문서의 `DUTCH_TTF_EUR` 및 `/v1/futures/ttf-gas`를 검토했으나,
공급자의 데이터 이용 안내는 거래소 데이터의 공개 표시 권한을 제공하지 않는다고 명시한다.
공개 Chokemonitor 게시에는 원천 제공자의 표시 권한도 확인되어야 한다.
- https://docs.oilpriceapi.com/api-reference/prices/latest
- https://docs.oilpriceapi.com/api-reference/futures/ttf-gas
- https://www.oilpriceapi.com/legal/data-usage

Rig 자동 수집, 미국 초기 26주 backfill, 일본 발전용 주간 LNG PDF는 이번 배포 범위 밖이다.
가스 리그의 의미와 공식 출처는 위의 Rig 절을 참고한다.

## 배포 확인

배포 작업은 `verify_deploy.py`로 공개 JSON과 체크아웃 파일의 SHA256 일치를 검사한다.
수집기 변경을 main에 합치면 최초 수집이 실행되고, 이후 매일 또는 수동으로 실행한다.
데이터만 갱신하는 봇 커밋은 수집을 재실행하지 않는다.
