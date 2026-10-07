# 인수인계 → commodity_reports 파이프라인 담당 세션: 메일링 소스 검토 결과

작성: Claude, 2026-09-27. 대상: `New for anti/scripts/commodity_reports/**` 담당 세션 (TASKS T16).
관련: 마이페이지 메일링 서비스 탭(TASKS T33/T44, 이 파일 작성자 소유).

## 배경

사용자가 "메일링 서비스 기관이 늘어난 것 같다"고 지적해서 검토했다. **수정은 하지 않았고**, 분석만 정리해 전달한다 — `scripts/commodity_reports/**`는 이 세션 소유가 아니라서(`OWNERS.md`, T16 담당) 직접 손대지 않았다.

## 1. 확인된 사실: 소스는 실제로 늘었다

`New for anti/scripts/commodity_reports/config/sources.json`의 `sources` 배열 길이가 최근 커밋에서 계속 늘었다.

| 커밋 | 날짜 | 소스 수 | 메시지 |
|---|---|---|---|
| c94860b0 | — | 25 | chore: refresh KR/JP policy boards |
| 33fbf628 | — | 38 | feat(reports): official reports for every dashboard commodity, GAIN back, rubber |
| 9d0c5ff6 | — | 38 | fix(reports): tagging fixes from the first live build |
| 2ef15026 | 2026-09-26 | 40 | fix(digest): mail list-page reports too; dry-run mode; tin and WGC sources |
| 466038c9 (HEAD) | 2026-09-26 | 44 | feat(reports): PDF press releases, lead/zinc, cobalt, Indonesia ESDM, Rosario |

현재 44건 중 `enabled:false`가 11건(주로 2026-09-02 첫 라이브 실행에서 404 난 것들 — `us_usda_ers_newsroom`, `us_usda_ers_charts`, `us_fas_newsroom`, `ca_statcan_daily`, `int_fao_giews`, `au_abares`, `int_igc`, `int_opec_press`, `int_lme_notices`, `ua_minagro`, `int_wgc`), 실제 도는 건 33건 — 최신 `public/data/commodity_reports_v1.json`의 `feed_status` 길이(33)와 정확히 일치해 이 쪽은 설정과 빌드가 어긋나 있지 않다.

**결론: 늘어난 게 맞고, UI가 잘못 반영한 게 아니라 실제로 소스를 계속 추가해온 것.** 사용자에게는 UI 쪽엔 문제 없다고 안내했다.

## 2. `enabled:true`인데 이번 빌드에서 실패한 3건

`commodity_reports_v1.json`의 `feed_status`(2026-09-26T13:50 생성분) 기준:

| source_id | 에러 | sources.json 메모 |
|---|---|---|
| `jp_meti_en` | `HTTP Error 403: Forbidden` | "Not yet confirmed live -- next Actions run's feed_status decides." (2026-09-02 작성, 아직 한 번도 성공 확인이 안 된 듯) |
| `int_spglobal_energy` | `HTTP Error 403: Forbidden` | 마찬가지로 "Not yet confirmed live." (유일하게 유료 매체 예외 허용한 소스) |
| `cn_mofcom_en` | `URLError: <urlopen error [Errno 104] Connection reset by peer>` | 2026-09-26 신규 추가. 메모에 "MOFCOM resets connections from a non-browser User-Agent... hence headers: browser"라고 이미 대응해뒀는데도 이번 빌드에서 다시 connection reset이 난 것으로 보임 |

세 건 다 원자재 태깅에 기여하는 소스라(`jp_meti_en`→에너지/광물 정책, `int_spglobal_energy`→에너지, `cn_mofcom_en`→갈륨·게르마늄·흑연·희토류 수출통제) 계속 죽어있으면 해당 원자재 커버리지가 조용히 비게 된다. `enabled:false`로 내리거나 URL/헤더를 다시 확인하는 다음 조사에서 우선순위로 볼 만하다.

## 3. 태깅 오탐 1건 (`ar_bcr` → `oil`)

`ar_bcr`(Bolsa de Comercio de Rosario, 로사리오 곡물거래소 — 원래 대두/옥수수/밀 주간 리포트용으로 추가된 소스)의 다음 기사가 `commodities: ["oil"]`로 분류돼 있다:

> "Reservas internacionales y petróleo marcan la agenda económica y financiera"
> (국제 준비금과 석유가 경제·금융 의제를 좌우한다)
> `reasons: ["no_date"]`

곡물거래소의 거시경제 논평 기사가 본문에 "petróleo"(석유) 한 단어를 언급했다는 이유로 원유 리포트로 잡힌 것으로 보인다. `ar_bcr`는 `commodity_hint` 없이 등록돼 있어서(노트: "Argentina's agriculture secretariat has no feed, and BCR's crop estimates are the ones the market quotes" — 곡물 전용 소스로 추가한 것) 순수 텍스트 태거가 상품명 하나만 보고 잡은 케이스 같다. 1건뿐이라 급한 건 아니지만, 태거가 "이 소스는 애초에 이 카테고리 상품만 낸다"는 소스 단위 힌트 없이 전수 텍스트 매칭만 하고 있다면, 비슷한 오탐이 다른 거래소/협회 소스(BCR처럼 원래 좁은 주제인데 매크로 논평도 섞어 내는 곳)에서 더 나올 수 있다.

## 4. 이 쪽(메일링 UI)에서 확인한 것 — 참고용, 조치 불필요

실제 리포트 133건을 원자재별로 묶어보면 최대 5개(대두·옥수수), 대부분 1~3개라 마이페이지 메일링 탭 체크박스 목록이 넘치지 않는다. 같은 기관이 한 원자재 안에 여러 소스로 겹치는 경우(원유: EIA 3개, 천연가스: EIA 2개+캐나다 천연자원부+인니 ESDM)도 `commoditySourceFilterHtml`의 `agency (source_id)` 구분 로직이 정상적으로 라벨을 분리한다. 즉 소스를 몇 개를 더 늘려도 UI 쪽은 지금 구조로 버틸 수 있다.

## 제안 (판단은 그쪽에 맡김)

1. `jp_meti_en` / `int_spglobal_energy` / `cn_mofcom_en` 세 건 다음 조사에서 재확인 — 계속 죽어있으면 `enabled:false` 전환.
2. `ar_bcr` 같은 오탐이 태깅 로직(`tag.py`) 상 얼마나 흔한지 한 번 스캔해볼 가치 있음. 소스별로 "이 소스는 이 상품군 밖 기사는 애초에 안 낸다"는 화이트리스트가 있으면(`commodity_hint`와 반대 방향) 이런 케이스를 걸러낼 수 있을 것.
