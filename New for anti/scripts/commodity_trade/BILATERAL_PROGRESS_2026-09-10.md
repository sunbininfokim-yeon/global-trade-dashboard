# 월별 상대국 데이터 확장 — 2026-09-10

작업 루트: `/Users/yeoninair/Documents/New for anti-dart`.
이 문서의 수치는 로컬 산출물 검증 결과이며, 사이트 배포 확인이 아니다.

## 실제 확보 범위

| 구분 | 직전 | 이번 완료 후 |
|---|---:|---:|
| 우선 국가 패널의 월별 총량 보유 신고국 | 14 | 14 |
| 새 상대국별 월별 데이터 보유 신고국 | 6 | 12 |
| 두 범위 합집합 | 15 | 15 |
| 상대국별 source/reporter/HS/period/flow 묶음 | 30 | 41 |
| 상대국 행 | 291 | 329 |

국가별로 하나 이상의 관측치가 있다는 뜻이다. 모든 상품·방향·기간의 완성을 의미하지 않는다.
JODI 에너지·산업 프록시 묶음은 이 우선국 집계와 별도이며 합산하지 않는다.
미국·브라질·호주·캐나다·칠레·인도네시아의 기존 30묶음은 보존했다.

### 이번에 추가한 신고국별 관측치

| 국가 | 상품 | 통계 월 | 방향 |
|---|---|---|---|
| 아르헨티나 | 철광석 HS2601 / 밀 HS1001 | 2026-03 / 2026-02 | 철광석 수입 / 밀 수출 |
| 일본 | 철광석 HS2601 | 2026-05 | 수출·수입 |
| 남아공 | LNG HS271111 | 2026-05 | 수출·수입 |
| 말레이시아 | LNG HS271111 | 2026-06 | 수출·수입 |
| 멕시코 | 구리광·정광 HS2603 | 2026-05 | 수출 |
| 사우디 | 철광석 HS2601 | 2025-09 | 수출·수입 |

**이번 사우디 추가분은 원유가 아니다.** 사우디 원유의 목적국별 월별 수출은 여전히 미확보다.
사우디의 과거 월을 최신 월에 대입하지 않는다. 총량 또는 USD로 배럴을 추정하지 않는다.
공식 Preview 성공 연결 후 17회 요청: 11개 정상 묶음, 5개 빈 응답, 1개 HTTP 요청 제한.
그 전에 격리 환경 DNS 실패 17개 작업이 `error`로 남았다. 이는 통계 공백 증거가 아니다.
요청 제한 이후 추가 네트워크 수집은 하지 않았다.

## 구현한 보완

- `monthly_coverage.py`: 기존 두 총량 패널과 새 bilateral 인덱스를 대조한다.
  - 생성물: `public/data/commodity_trade_coverage_v1.json` (`New for anti/` 기준).
  - source·HS·방향·원 단위·관측 월을 보존하고 국가 수는 합집합으로 센다.
  - `world_total_available`과 `bilateral_available`은 별개다. 0은 관측치, null·bool·잘못된 월은 제외한다.
  - `next_step`, 조회 오류·빈 응답·요청 제한 건수를 함께 제공한다.
- `build_bilateral.py --period-strategy observed`: 기존 패널의 국가×HS×방향별 관측 월을 **조회 후보**로 쓴다.
  - `--months 1`이면 각 계열의 가장 최근 관측 월 1개. 같은 달로 강제하지 않는다.
  - `--end-period`보다 미래인 월은 제외한다. 국가별 순환 순서로 호출 예산을 나눈다.
  - 원천국 자료가 있다는 사실은 Comtrade 자료 존재나 HS 개정판 일치를 증명하지 않는다.
  - 원천국 수치 자체를 양국 간 행·World 분모로 복사하지 않는다. 응답 분류·기간·흐름 검증은 그대로 적용한다.
- 네트워크 오류 시 한 번의 실패로 실행을 멈추고 상태를 저장한다. 예외 URL·키를 기록하지 않는다.
- 현재 실행의 `stop_reason`을 출력한다. 인증/네트워크 중단 exit 2, 요청 제한 exit 3.
  - 성공적으로 확보한 관측치는 중단 시에도 출판·체크포인트에 보존한다.
  - 과거 실패가 있어도 오프라인 출판은 exit 0. 과거 실패를 성공으로 바꾸지는 않는다.
- 이전 체크포인트의 누락 query metadata는 job identity 검증 후 복원하고 저장한다.
- 비활성 `deployment/monthly.yml.example`: 관측 월 60회 + 최근 달 60회로 분리하고 커버리지 생성물을 PR에 포함한다.
  - 중단 코드가 발생하면 후속 수집·PR 단계는 실행되지 않으며 checkpoint artifact는 always 저장한다.
  - 다음 실행은 저장 상태에서 재개한다. 예산 내에서 전체 27국×모든 상품을 완료한다는 보장은 없다.
  - 실제 `.github/workflows/`에는 설치하지 않았다.

## 남은 공백과 실행 조건

1. 기존 15개국 중 **인도·노르웨이·태국**: 아직 새 상대국별 자료 없음.
   이번 제한된 HS/월 조회의 빈 응답·요청 제한만 확인했다. 국가 전체가 불가능하다는 뜻이 아니다.
2. 확보한 12개국도 상품·방향·과거 월 백필이 더 필요하다. 국가 수를 완료율로 쓰지 말 것.
3. 한국: 직접 경로 또는 배포된 전용 gateway 인증 필요. 기존 Cloudflare Secret 존재 여부는 이번에 검증하지 않았다.
4. 사우디 원유: GASTAT의 총량을 목적국별로 쪼개지 말 것. 원유 직접 신고 또는 별도로 표시한 상대국 신고가 필요하다.
5. Cloudflare Worker·실제 Actions·UI는 Claude 담당 그대로. 관련 파일, Secrets, 원격 저장소, 운영 배포는 변경하지 않았다.

### 제한 해제 후 재개 명령 (지금 추가 실행하지 않음)

원격 환경에서는 artifact를 `$RUNNER_TEMP/trade-state/checkpoint.json`로 복원한다.
처음에는 `deployment/seed_checkpoint.json`으로 초기화하고 이후에는 최신 artifact를 사용한다.

```bash
python3 'New for anti/scripts/commodity_trade/build_bilateral.py' \
  --fetch --mode preview --period-strategy observed \
  --reporters ARG,JPN,ZAF,MYS,IND,NOR,THA,MEX,SAU \
  --hs 2709,271111,2601,2603,1001,1005,1201,1511,1701 \
  --months 1 --max-requests 60 --interval 3 \
  --checkpoint "$RUNNER_TEMP/trade-state/checkpoint.json"
```

매 실행월의 마지막 완료월이 기본 상한이다. `calendar` 전략을 별도로 실행해야 새로운 발표 월을 탐색한다.
`observed`만 실행하면 오래된 입력 패널의 월에 머물 수 있다. 기존 총량 패널 갱신과 함께 운영해야 한다.
인증 gateway가 준비되면 `--mode gateway`로 변경한다. `TRADE_GATEWAY_URL` 및 `TRADE_PIPELINE_TOKEN` 필요.
키를 채팅·JSON·코드에 넣지 않는다. 무료 Preview는 호출·행 제한이 있다: [공식 Comtrade API 설명](https://uncomtrade.org/docs/un-comtrade-api/).

## 수출통제와 검증

- 아르헨티나 밀 수출 9개 상대국 행에 기존 `arg-grains` **검토 후보**가 연결됐다.
- 인도네시아 니켈광·구리 정광의 조회 품목 후보도 보존했다.
- `legal_clearance=null`. 이번 실행은 새 법령의 현행 효력을 검증한 작업이 아니다.
- Python 89개 + Node 10개 테스트 통과. 공개 41묶음의 해시·스코프·비중·순위 재계산 검증 통과.
- Python 테스트 수에는 국가 합집합, 명시적 0, 잘못된 월, 연간/World-only 제외,
  국가별 월 선택, 국가 순환, DNS 중단, 요청 제한 중단과 오프라인 재개를 포함한다.

기존 배포 연결 세부사항은 `CLAUDE_MONTHLY_BILATERAL_HANDOFF_2026-09-09.md`를 참고하되,
확보 국가·묶음 수는 이 문서와 생성된 `commodity_trade_coverage_v1.json`을 우선한다.
