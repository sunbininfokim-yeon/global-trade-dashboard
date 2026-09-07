# 해외 LETF 데이터·자동화 인수인계 — 2026-09-08

## 구현과 범위

실제 작업 저장소는 `/Users/yeoninair/Documents/New for anti`다. 해운 데이터 폴더의
`global-trade-dashboard-github` 복사본은 최신 LETF 이력 기능이 없으므로 수정하지 않았다.

국내 13101 시세와 13108 PDF의 역할 분리를 해외에도 적용했다. 거래소별 시세는
`listings`, 운용사 보유내역은 `holdings`, 순자산은 `aum`, 주식·지수 수익률은
`returns`, 환율은 `fx`, 차입·자산 구성은 `capital`로 저장한다.

신규 레지스트리 `config/overseas_letf_universe.json`은 **선별한 15개 경제적 상품**이다.
전 세계 상품 전체 또는 거래량 순위 상위 15개라는 의미가 아니다.

| 상품 | 대상·레버리지 | 구조 근거 및 취급 |
|---|---|---|
| CSOP 7709.HK | 하이닉스 보통주, 최대 +2 | 합성 스왑. 2026-08-03부터 가변 목표 |
| CSOP 7747.HK | 삼성전자 보통주, 최대 +2 | 합성 스왑. 9747 USD 거래통화는 같은 펀드 |
| CSOP 7347.HK | 삼성전자 보통주, 최대 -2 | 합성 스왑. 9347 USD 거래통화 상태 확인 필요 |
| Leverage Shares HNX3 / 3HNX | 하이닉스 보통주, +3 | 9/4 운용사 API `Underlying_holding=KRX shares`, 현물·차입 |
| Leverage Shares SMG3 / 3SMG | 삼성전자, +3 | 9/4 운용사 API `Underlying_holding=KRX futures`, 선물 기반으로 표시 |
| SKHX / SKHZ / SKHQ | 미국 SKHY ADR, +2 / -1 / -2 | 일별 holdings의 스왑. 한국 보통주 수익률로 대체 금지 |
| KORU | MSCI Korea 25/50, +3 | 한국 주식 바스켓. 개별주 LETF가 아님 |
| SOXL / SOXS | NYSE Semiconductor Index, +3 / -3 | 글로벌 업종 비교. SOX 지수와 혼동하지 않음 |
| TECL / TECS | Technology Select Sector Index, +3 / -3 | 글로벌 업종 비교 |
| TQQQ / SQQQ | Nasdaq-100, +3 / -3 | 현물·스왑·선물·담보 등 일별 공식 holdings와 NAV 자료 |

유럽 두 펀드는 ISIN으로 식별하고 LSE USD/GBP, 이탈리아 EUR, 독일 EUR 상장을 분리했다.
`GBp`는 파운드의 1/100인 펜스다. AUM을 상장 통화 수만큼 더하지 않는다.
삼성전자 ETP의 일반적인 “physically backed” 홍보와 상품별 `KRX futures` 값은
구분해야 한다. 일별 구조를 과거로 소급하지 않으며, 계약 만기·구체적 선물 비중은
공식 상세 holdings가 없으므로 아직 미확인이다.

다른 KOSPI 기업의 해외 단일종목 상품은 이번에 공식 상장·구조가 확인된 목록에
없어 임의로 추가하지 않았다. 이는 그런 상품이 전혀 없다는 전수조사 결론이 아니다.
펀드가 투자 가능한 옵션과 실제 옵션 보유량, ETF를 기초로 거래되는 옵션 거래량은 별개다.

## 출처와 날짜

- CSOP [하이닉스](https://csop.onlineminisite.com/skhynixleveraged/en/),
  [삼성전자](https://csop.onlineminisite.com/samsunglandi/en/): 스왑·가변 레버리지.
- HKEX [9747 최종 거래일](https://www.hkex.com.hk/eng/market/sec_tradinfo/tradarng/tradarng_news/currentmonth/e9747b_260813.htm): 2026-08-17.
- HKEX [9347 거래정지 공지](https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0615/2026061500115.htm).
  재개/최종 종료일 확인 전에는 이 통화를 단순히 없는 것으로 간주하지 않는다.
- Leverage Shares [하이닉스](https://leverageshares.com/en/etps/leverage-shares-3x-long-sk-hynix-etp/),
  [삼성전자](https://leverageshares.com/en/etps/leverage-shares-3x-long-samsung-electronics-etp/),
  [공식 상품 목록](https://leverageshares.com/documents/pdfs/en/Leverage-Shares-Products.pdf).
  페이지 공개 API `POST /Lab_Forty_Scripts/php/etp_data.php`는 조회용이다.
  API의 `etp_securities_issued`는 발행 **주식 수**가 아니라, 운용사 화면의 **AUM**에
  연결되는 금액이다. 실제 발행수량 필드는 `Outstanding_Shares_Par`다.
  현재 자산−부채=AUM을 검산하고, 모의 데이터 `IsSimulated != 0`는 제외한다.
- 미국 [SKHX](https://leverageshares.com/us/etfs/leverage-shares-2x-long-sk-hynix-daily-etf/),
  [SKHZ](https://leverageshares.com/us/etfs/leverage-shares-1x-short-sk-hynix-daily-etf/),
  [SKHQ](https://leverageshares.com/us/etfs/leverage-shares-2x-short-sk-hynix-daily-etf/).
  Full Holdings CSV는 각각 `.../us/storage/holdings/{ticker}_Holdings.csv`.
  9/7 수집 당시 SKHX/SKHZ CSV 기준일은 8/24로 웹페이지보다 오래됐다.
  SKHQ CSV에는 9/8 미래 날짜가 있어 배제했다. 웹페이지 날짜로 덮어쓰지 않았다.
- [KORU](https://www.direxion.com/product/daily-msci-south-korea-bull-3x-etf),
  [SOXL/SOXS](https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs),
  [TECL/TECS](https://www.direxion.com/product/daily-technology-bull-bear-3x-etfs).
  공식 상품 목표는 확인했으나 이 환경에서 일부 상세 다운로드는 HTTP 403이었다.
  실제 구성 비율을 만들어 채우지 않는다.
- [TQQQ](https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq),
  [SQQQ](https://www.proshares.com/our-etfs/leveraged-and-inverse/sqqq): Holdings 표,
  [TQQQ NAV/AUM 이력](https://accounts.profunds.com/etfdata/ByFund/TQQQ-historical_nav.csv).
- 시장 시세/거래량/환율: Yahoo Finance의 일별 bar, 2차 공급자.
  종가×동일 거래일 거래량을 **거래대금 프록시**로 명시한다. 거래소 실측 거래대금과
  동일시하지 않는다. 휴장일·결측일 보간은 하지 않는다.

## 실행과 자동화

```bash
cd '/Users/yeoninair/Documents/New for anti/New for anti/scripts/market_microstructure'
python -m pip install -r requirements-overseas.txt
python build_overseas_letf.py --live --print-stats
```

`--as-of YYYY-MM-DD`로 종료 기준일을 고정할 수 있다. `--live` 없이 실행하면
`--cache-dir`의 확보된 자료와 정상 정규화 이력으로 재생성한다.
기본 live 수집은 최근 110일을 재조회하고 동일 키만 갱신한다.

신규 `.github/workflows/overseas_letf_daily.yml`:

- UTC 월~금 23:35 = 한국시간 화~토 **08:35** 예약 실행.
- `workflow_dispatch` 수동 실행, PR에서는 네트워크 없는 계약 테스트만 실행.
- 원본 다운로드는 러너 임시 폴더에만 두며 Git에는 정규화 JSONL.gz와 manifest만 저장.
- 국내 배치와 독립 실행. `run_daily.sh`에도 같은 명령을 연결했다.
- 재시도 가능한 HTTP 오류는 최대 2회 재시도. 상품별 실패는 나머지 수집을 계속한다.
- 정상 이력은 보존하고 누락·거절·지연 상태를 별도 status JSON에 남긴다.
- 전 소스 수집 실패 시 상태를 저장한 뒤 실패 종료한다. Actions 실패 알림과
  14일 보존 진단 artifact를 이용할 수 있다.
- 설정된 신규 workflow는 **main에 반영된 뒤** 예약 실행된다. 로컬 파일 작성/실행은
  운영 스케줄 활성화와 다르다. 신규 해외 LETF 화면과 기존 배포 workflow까지 연결했다. Worker 본체와 app.js는 변경하지 않았다.

소유권 경계: 사용자가 “데이터 파이프라인 연동해야해”라고 재요청하여 해외 수집부터
화면·배포까지 필요한 연결을 구현했다. 원래 작업 폴더의 다른 에이전트 WIP는 수정하지
않고 main 기반 별도 worktree에서 통합했다. 작성자는 Codex이며, 소유권 검사가 안내하는
UI/배포 통합 브랜치 접두(claude/)를 사용한다. 공통 소유권 검사 자체는 변경하지 않는다.

## 저장 계약

정규화 장기 이력: `scripts/market_microstructure/data/overseas_letf/`.

| 파일 | 중복 대체 키 |
|---|---|
| `listings.jsonl.gz` | date, listing_id |
| `holdings.jsonl.gz` | date, product_id, holding_id |
| `aum.jsonl.gz` | date, product_id |
| `capital.jsonl.gz` | date, product_id |
| `returns.jsonl.gz` | date, reference |
| `fx.jsonl.gz` | date |
| `products.jsonl.gz` | date, product_id |

`manifest.json`은 매 실행 후 실제 압축 파일에서 행수·날짜 범위·date_count·SHA256을
재계산한다. 압축은 mtime=0으로 결정적이며 교체는 임시 파일을 통한 atomic replace다.
정상 파싱한 전체 holdings 스냅샷은 해당 날짜·상품 구성만 교체하여 수정 공시에서
삭제된 구성종목이 남지 않게 한다. 실패/빈 응답은 정상 스냅샷을 지우지 않는다.
현재 파일 스토리지 어댑터를 쓰고 있으며 R2/GCS 설정이나 업로드 완료를 주장하지 않는다.

화면 산출물:

- `public/data/overseas_letf_board_v1.json`: 상품 메타데이터·최신 거래·AUM의 자체 기준일·구성.
- `public/data/overseas_letf_history_v1.jsonl.gz`: 최근 120일 상품 이력.
- `public/data/overseas_letf_listings_v1.jsonl.gz`: 최근 120일 거래통화별 가격·수량·거래대금.
- `public/data/overseas_letf_pipeline_status_v1.json`: 수집 실패·미래 날짜 거절·실행 상태.

`date/as_of`는 금융 관측 기준일, `generated_at/last_attempt_at`은 실행 시각이다.
이 날짜를 바꿔 과거 자료를 최신 관측으로 보이게 하지 않는다.

## 계산·표시 원칙

1. `trading_value_usd`는 동일 날짜의 필요한 거래통화를 모두 확보한 경우만 합산한다.
   미완전 수집은 `null`; 확보분 합계는 `covered_trading_value_usd`에 별도로 남긴다.
2. `covered_turnover_share_pct`의 분모는 해당 날짜·대상 그룹의 **확보한 선별 상품**이다.
   세계 전체 ETF 시장점유율, 외국인 포지션, 설정·환매 자금 유입 비율이 아니다.
3. `aum_usd`는 해당 날짜에 운용사 AUM이 있을 때만 생성한다.
   오래된 최근 AUM은 `latest_aum.date`와 함께 별도 표시하고 현재 날짜로 보간하지 않는다.
4. `etf_to_kr_cash_tv_ratio`는 동일 날짜 KRX 시장 전체 해당 종목 거래대금이 분모다.
   `stock_letf_history_v1.jsonl`의 `spot_trading_value_krw`만 읽는다.
   ADR 및 바스켓은 한국 개별주 분모로 계산하지 않는다.
5. 목표 레버리지·전일 AUM·동일 기준자산/통화 수익률이 모두 확인된 경우만 계산한다.
   기준 부호는 **양수=매수 방향, 음수=매도 방향**이다.

```text
implied_rebalance = A_prev × [L_end × (1 + L_start × r) − L_start × (1 + r)]
고정 L이면        = A_prev × L × (L − 1) × r
```

이는 자금 유출입·수수료·장중 리셋·실제 헤지 경로를 제외한 추정이다.
CSOP 가변 레버리지의 일별 실제 목표가 없으면 상한 2로 대체하지 않고 null.
한국 주식 수익률을 USD 펀드 수익률로 대체하지 않는다. 순합의 절댓값과
상품별 절댓값 합계는 각각 `abs_net_implied_rebalance_usd`,
`gross_implied_rebalance_usd`로 분리한다.

6. holdings의 스왑 노출은 100%를 넘을 수 있고 현금/차입 항목은 음수가 될 수 있다.
   **100% 파이 차트로 재정규화 금지**. signed 막대 그래프로 보여 준다.
   ProShares exposure weight와 market value, Themes의 원래 MarketValue 표기까지 보존한다.
7. 5개 미만 유효 관측은 축적 중, 5개 이상 단기 선, 20개 이상 추세/기간 비교 허용.
   실제 경보 임계값은 이번 범위에서 임의로 추가하지 않았다.

## 운영 UI 연결

금융 → 시장미시구조 → `해외 LETF` 탭을 추가했다. 기존 국내 종목 스트레스 영역에도
해외 탭 이동 버튼을 연결했다. `market-microstructure.js`가 board와 압축 이력을 직접 읽는다.

- 기본 하이닉스, 삼성전자·한국 바스켓·글로벌 비교를 선택 가능하게 한다.
- 상품 선택 표: 거래소/거래통화, 직접 한국주/ADR/바스켓, 목표 또는 상한,
  구조와 근거 날짜, 거래량, 거래대금 프록시, 같은 그룹 확보분 비중,
  AUM과 AUM 날짜, coverage 및 missing.
- 시계열: 거래량(단위=해당 상품 수), 거래대금, AUM, 해당 현물 대비 비율,
  추정 리밸런싱과 데이터 충분성. null은 gap으로 유지한다.
- 구조: 확인된 signed holdings 노출을 표시하고, 비중 미확보 상품은 구조 이름만 표시.
  유럽 두 ETP는 자산·차입·순자산을 별도 막대로 보여줄 수 있다.
- JSONL.gz는 static fetch 응답의 HTTP Content-Encoding과 파일 압축을 혼동하지 않는다.
  파일 바이트가 gzip일 때 `DecompressionStream('gzip')`으로 풀고 JSONL을 읽는다.
- 신규 board를 기존 `global_leverage_stack`으로 역주입하지 않는다. 그 경로에는
  가변 L을 상한으로 평가하거나 null을 0으로 바꾸는 오래된 가정이 남아 있다.
- UI는 Python 결과를 렌더링하고 추정치를 JS에서 재계산하지 않는다.

## 배포·검증 연결

`deploy.yml`은 `Overseas LETF daily`의 main 실행 완료를 `workflow_run`으로 받아
최신 main을 체크아웃한다. 수집 시작 SHA에는 새 데이터 커밋이 없으므로 그 SHA를
배포하지 않는다. 동일 저장소·main·PR 이외 실행만 허용하고 배포는 직렬화한다.
수집이 실패한 경우도 마지막 정상 관측 + 실패 status를 배포해 지연을 표시한다.
GITHUB_TOKEN의 push가 다른 push workflow를 재호출하지 않는 문제를 이 경로로 해결한다.

배포 후 `verify_overseas_letf_deploy.py`는 실제 사이트의 board/status/두 이력 파일을
받아 체크아웃된 파일과 압축 해제 후 SHA256이 일치하는지 검증한다. 기준일만 같은
오래된 파일을 통과시키지 않는다. 불일치는 재시도 후 배포 작업 실패로 남는다.

16개 데이터 계약 테스트와 실제 화면 코드를 사용하는 Playwright 테스트를 연결했다.
브라우저 테스트는 15개 상품의 동일 날짜 중복 처리, gzip/HTTP 자동 해제, 상품 전환,
신규 상품 축적 상태, 실제 차트 출력, 모바일 폭을 검증한다.

운영 활성화 결과와 PR·실행 링크는 아래 실행 기록에 추가한다.

CSOP의 기준일 있는 AUM·실제 가변 목표, Direxion 일별 holdings, 9347 거래통화 상태,
신상품 메타데이터 변경은 추가 수집이 필요하다. 해당 값은 가짜 수치 없이 null로 남는다.

## 실행 기록 — 2026-09-08

- 로컬 live 실행: 2026-09-07 19:49 UTC. 시세 최신 관측 9/4, 15개 상품 모두 확보.
- 정규화 listing 1,427건, 상품 일별 961건, holdings 162건. 일부 공식 상세 자료 미확보로 status=partial.
- 데이터 계약 테스트 16개 통과, 실제 UI+압축 이력 브라우저 테스트 통과.
- manifest의 모든 파일 행수·SHA256 검산 통과. 배포 검증 함수는 동일 날짜의 오래된 내용도 거절하는 것을 확인.
- 실제 저장소 확인: `sunbininfokim-yeon/global-trade-dashboard`, private, 현재 계정 ADMIN.
- 원격 업로드는 자동 승인 검토가 “명시적 외부 게시 승인 미확인”으로 거절하여 아직 미실행.
  사용자에게 해당 저장소 업로드·PR 병합·예약 수집·운영 배포의 일괄 승인을 요청한 상태.
  승인 전에는 운영 활성화·사이트 반영 완료로 표현하지 않는다.
- 통합 변경 정본 worktree: `/Users/yeoninair/Documents/해운 데이터/overseas-letf-review`.
