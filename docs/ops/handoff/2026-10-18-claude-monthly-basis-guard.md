# 인수인계 2026-10-18 — claude (월별 화면: 측정 기준 가드)

## 왜

#614 이후 월간 데이터 점(point)에 `measurement_basis`가 붙는다(`goods_net_mass`, `unknown`, `contained_copper_mass`).
월별 화면(`trade-monthly.js`)은 이 필드를 읽지 않았다. 지금 데이터에서는 안전했다 -- 함유 구리(Cochilco)의 단위 문자열이
`kMT_cu_content`로 달라서 시리즈가 따로 서고 숫자 비교도 막혔다. 하지만 `kg`·`KTONS`·`metric_tons`는 `kt`로 정규화되므로,
함유량 기준 관측이 평범한 단위로 들어오면 같은 상품 범위의 상품 중량 시리즈와 한 시리즈로 합쳐지거나(같은 달은 덮어씀)
"출처 비교"에서 숫자로 비교될 수 있었다.

## 바뀐 것 (`New for anti/trade-monthly.js`, `index.html` 캐시 v=11)

- `basisOf(point)`: `normalized.measurement_basis` 또는 `measurement_basis`. `goods_net_mass`·`unknown`·없음은 모두 `''`(기본 상품 중량)이라
  기존 시리즈는 그대로다.
- 시리즈 키가 `source|unit|basis`. 기준이 다르면 카드가 따로 선다. 단위 라벨에 이미 "함량"이 있으면 라벨은 그대로, 없으면 ` · 구리 함량 기준`(모르는 기준은 "상품 중량이 아닌 기준")을 붙인다.
- `compareSources`: 단위·범위가 같고 기준만 다르면 `kind: 'basis'` 노트("측정 기준이 다릅니다 … 직접 비교하지 않습니다")만 내고 평균 차이를 계산하지 않는다.
  단위가 다르면 기존 `units` 노트가 먼저라 칠레 구리 화면 문구는 바뀌지 않는다.
- 새 기준이 데이터에 처음 나오면 `tests/comtrade/measurement-basis.test.mjs`가 실패해 `BASIS_LABEL`에 라벨을 넣게 한다.

## 검증

`node --test tests/comtrade/*.test.mjs` 70개(신규 7), gateway 포함 80개, 소유권 13개, `git diff --check`.
새 테스트 중 4개는 수정 전 파일에서 실패하는 것을 확인했다.
점검 시점 데이터(10/18)에서 시리즈 병합 충돌·기준 혼합은 0건이었다 -- 이 PR은 앞으로를 막는 가드다.

## 손대지 않은 것

- 화면 밖(Worker `/api/*`, 비중·순위)은 서버 값을 그대로 쓴다. 변경 없음.
- 배포 후 실제 칠레 구리 월별 카드를 눈으로 확인한 것은 아니다(로컬 vm 테스트까지).
