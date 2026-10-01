# Claude 배포 인수인계 — 원유 리그 수 (2026-06 이후)

데이터 추출 완료. UI 연결·커밋·push·PR·운영 배포는 하지 않았다.
`app.js`, `data.js`, `index.html`, `style.css`, `shipping.js`, `_worker.js`, `wrangler.jsonc`, `.github/workflows/**` 는 수정하지 않았다.

## 배포 파일

`New for anti/public/data/oil_rig_count_v1.json`

- schema: `oil-rig-count-v1`
- 품목: 원유 시추 리그 (`DrillFor=Oil`)만. 단위는 `rigs`. 생산량(bpd)이 아니다.
- 시작: 2026-06. 그 이전 행은 두 엑셀에 있어도 넣지 않았다.
- 가스(`Gas`)·기타(`Miscellaneous`)는 제외했다.

기존 원유 화면은 이 파일을 자동으로 읽지 않는다. 정적 파일 배포와 화면 표시는 별개다.
화면은 이 JSON의 `label_ko` / `map_key` / `caveats_ko` 를 그대로 쓰고, 없는 달을 0으로 채우지 않는다.

## 원본

| 파일 | 쓰는 범위 | SHA256 |
|---|---|---|
| `09-25-2026 North_America Rig_Count Report.xlsx` | 미국·캐나다. 시트 `NAM Weekly`, `NAM Monthly` | `aff8a451905e0c02f306f9f9de1226f461f73e2840428a73baaf8f4d34204b92` |
| `August-2026  WorldWide Rig Count Report .xlsx` | 북미를 뺀 국제. 시트 `WW Monthly` | `e8d2f215bc4f8e63738b7f18872a25c5f99932f43e24385a0dad9682ca03cd06` |

세계 파일의 `North America` 행은 넣지 않았다. 9월 25일 북미 파일이 6–8월 평균을 개정한 상태라, 두 값을 더하면 이중 계산이다.

## 화면이 써도 되는 숫자

최신 주간 (2026-09-25 발표): 미국 원유 455, 캐나다 원유 145, 북미 합 600.

국제 원유 (북미 제외, 월 스냅샷): 2026-06 726, 2026-07 744, 2026-08 749.
2026-08 지역: 중동 311, 중남미 123, 아프리카 104, 아시아태평양 144, 유럽 67.

월드와이드 원유 = 위 국제 + 북미 월평균 (9월 25일 파일의 `NAM Monthly`):

| 월 | 국제 | 미국 | 캐나다 | 북미 | 합계 |
|---|---:|---:|---:|---:|---:|
| 2026-06 | 726 | 434.25 | 125.5 | 559.75 | 1285.75 |
| 2026-07 | 744 | 448.6 | 134.4 | 583 | 1327 |
| 2026-08 | 749 | 452 | 147.25 | 599.25 | 1348.25 |

2026-09 월드와이드 합계는 없다. 북미 9월 평균만 있다 (미국 451.5, 캐나다 140). 국제 9월은 이 원본에 없다.

북미 월간 값은 그 달 주간 발표의 평균이다. 9월은 09-04, 09-11, 09-18, 09-25 네 번의 평균이고, 주간 합의 평균과 `NAM Monthly` 시트가 일치한다.
북미 외는 월 스냅샷이라 북미 월평균과 같은 종류의 숫자가 아니다. 합계를 보여줄 때는 그 차이를 같이 적는다.

## 합치면 안 되는 것

- `CHINA OFFSHORE`, `UNITED KINGDOM OFFSHORE` 는 해상만이다. 중국 전체·영국 전체 리그 수가 아니다.
- UAE는 `UAE - ABU DHABI` / `DUBAI` / `SHARJAH` 로 나뉘어 있다. 화면용 합은 각 월의 `uae.total` 만 쓴다. 토후국 행과 그 합을 둘 다 지도에 올리지 않는다.
- `CONGO` 는 콩고공화국(COG)이다. 콩고민주공화국이 아니다.
- `SERBIA AND MONTENEGRO` 는 원본 표기 그대로다. ISO 코드를 임의로 붙이지 않았다 (`iso3: null`).
- 파키스탄·이집트는 원본 지역이 Middle East다. 아프리카/남아시아로 옮기지 않는다.
- 행이 없는 나라·월은 미발표다. 0으로 넣지 않는다. JSON 안의 0은 원본이 0으로 적은 값이다.

## 검증

주간 위치(육상/해상/내수) 합 = 국가 합, 주(state) 합 = 국가 합.
북미 월평균 = 해당 월 주간 원유 리그의 산술평균 (`NAM Monthly` 와 차이 0.02 미만).
수록 시작은 2026-06-05 주간, 2026-06 월간. 가스·기타 리그 행은 없다.

```bash
python3 -c "
import json
p='New for anti/public/data/oil_rig_count_v1.json'
d=json.load(open(p))
assert d['schema_version']=='oil-rig-count-v1'
assert d['drill_for']=='Oil'
assert d['coverage_from']=='2026-06'
assert min(x['date'] for x in d['north_america_weekly'])>='2026-06-01'
assert min(x['month'] for x in d['international_monthly'])>='2026-06'
assert '2026-09' not in {x['month'] for x in d['worldwide_oil_monthly']}
w=d['latest']['north_america_weekly']
assert (w['date'], w['usa_oil'], w['canada_oil'])==('2026-09-25', 455, 145)
print('ok', d['latest'])
"
```

레포 루트 `/Users/yeoninair/Documents/New for anti-dart` 에서 실행한다.

## Claude 배포 순서

1. `oil_rig_count_v1.json` 과 이 문서만 배포 브랜치에 선별한다. 원본 xlsx, 다른 업무 변경, `.verify_live/` 는 넣지 않는다.
2. 위 검증이 통과한 뒤에만 PR을 만든다. 머지는 운영 배포를 유발할 수 있으니 검토 전 자동 머지하지 않는다.
3. 운영에서 `/public/data/oil_rig_count_v1.json` 을 받아 로컬 파일과 해시를 비교한다.
4. 화면 연결은 사용자 승인 후에, 원유 패널의 참고 수치로만 붙인다. 생산량·수출량·재고와 같은 단위로 섞지 않는다.

## Claude 시작 문장

“`/Users/yeoninair/Documents/New for anti-dart`에서 `New for anti/scripts/commodity_trade/CLAUDE_DEPLOY_OIL_RIG_2026-09-26.md`를 먼저 읽고, `New for anti/public/data/oil_rig_count_v1.json`만 선별 배포 준비해줘. UI는 승인 전에는 수정하지 마. 가스 리그를 더하지 말고, 9월 국제 리그 수를 만들지 마.”
