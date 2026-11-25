# 초크포인트 품목별 누적·전년 동기 비교

- 브랜치: `codex/chokepoint-cargo-cumulative`, base `cff79b211`.
- 대상: 호르무즈, 바브엘만데브, 수에즈. 신규 API 키·수집 호출·workflow 변경 없음.
- 기존 자동 갱신의 EIA 분기 자료에서 누적을 계산한다. 현재 공개 JSON, 렌더러, 배포는 변경하지 않았다.

## Claude 화면 연결

`official_cargo_monitor.chokepoints[id].cumulative_cards[]`는 EIA 품목별 카드다. 기존 JSON에는 필드가 없을 수 있다. 비어 있으면 누적 섹션을 숨긴다.

- `windows[].kind = year_to_date`: 마지막 발표 대상 분기까지의 연초 누적. UI에서 현재 날짜까지의 누적으로 바꾸지 않는다.
- `trailing_matched_quarters`: 동일 발표본의 전년 자료가 1분기 이후부터 시작할 때 보여주는 별도 비교 구간. `label_ko`, `period_start/end`, `prior_period_start/end`로 기간을 표기한다. 이 구간의 전년비를 연초 누적 옆에 붙이지 않는다.
- `value`와 `prior_value`는 기간 합계, `change_pct`는 같은 달 범위의 전년 비교다. `comparison_status == comparable`일 때만 변화율을 보이고, 누락 값은 0으로 쓰지 않는다. `missing_quarter_starts`와 `prior_missing_quarter_starts`에 누락 분기 시작일이 있다. 전년 값이 0이면 양쪽 값만 표시한다.
- 석유는 `barrels`, LNG는 `billion_cubic_feet`(기체 환산)이다. `/일`을 붙이지 않는다. 수에즈 석유는 `suez_canal_and_sumed_pipeline`, LNG는 `suez_canal`이다. `total_oil`은 원유+제품에 다시 더하지 않으며 EIA 표의 반올림으로 합계가 조금 다를 수 있다.
- 카드의 `source_published_at`, `source_status`, `source_url`, `attribution`, `warning_ko`를 함께 표시한다. AIS 일별 데이터·IEA 월간 값·다른 EIA 발행본을 합치지 않는다. 브라우저에서 숫자를 재계산하지 않는다.

## 실제 입력 확인

EIA 2026-11-16 발표 원문을 수집기로 읽어 세 통로 각각 24행을 확인했다. 기존 운영 입력을 로컬 임시 경로에 재생성해 산출을 검증했다. 이 검증은 새 PortWatch 관측을 수집하거나 공개 JSON을 갱신한 것이 아니다.

| 예시 | 2026년 1~9월 누적 | 2026년 4~9월 전년 동기 대비 |
|---|---:|---:|
| 호르무즈 원유+콘덴세이트 | 1,998,400,000 배럴 | −62.9% |
| 호르무즈 LNG | 867.6 십억 ft³ | −89.9% |
| 바브엘만데브 원유+콘덴세이트 | 1,284,300,000 배럴 | +101.7% |
| 수에즈+SUMED 원유+콘덴세이트 | 1,057,200,000 배럴 | +40.1% |

이 발표본에는 2025년 1분기가 없어 1~9월 누적 전년비는 미제공이다. 바브엘만데브 LNG도 미보고 분기가 포함돼 미제공이다. 연간 전망, 일별 실제 원유·LNG 역산, 북극·우회 시뮬레이터 변경은 후속 범위다.
