# 호르무즈 원유·LNG 연간 조건부 전망

- 브랜치: `codex/hormuz-annual-outlook`, base `48901caf8`. #1113(누적/전년비), #1115(항로)와 병합 의존 없음.
- 기존 EIA 정규화 분기 표를 사용한다. 새 API 키·신규 수집 호출·UI·workflow·운영 산출물 변경 없음.

## 화면 계약

해운 → 호르무즈 → 공식 물량 세부에서 `hormuz_annual_outlook.cards[]`를 읽는다. 기존 JSON에는 필드가 없을 수 있다. `status = unavailable`이면 보류하거나 숨긴다.

- `conditional_outlook`: `published_period_end`까지 기관 발표 추정 누적(`reported_cumulative`)과 `unreported_period_start`부터 연말까지의 조건부 시나리오를 나란히 표시한다. `unreported_days`는 **미발표 구간 전체**이며 `unreported_elapsed_days`는 그중 계산 기준일까지 이미 지난 날짜 수다. ‘앞으로 남은 일수’로 표시하면 안 된다.
- `scenarios[]`의 `latest_quarter_pace`가 기준이다. `previous_quarter_pace`는 바로 앞 분기의 하루 통항량을 적용한 비교안이며, 두 분기 값이 같으면 두 번째 행은 없다. 두 값 사이를 신뢰구간·최저/최고·발생확률로 표현하지 않는다.
- 각 행은 `reference_period_start/end`, `assumed_daily_rate`, `unreported_period_estimate`, `annual_total`을 제공한다. 기간 합계는 `unit`, 가정 일평균은 `daily_rate_unit`을 따른다. LNG는 기체 환산 ft³로 액화 화물창 부피가 아니다. 브라우저는 환산 표시 외에 숫자를 다시 계산하지 않는다.
- `full_year_institution_estimate`이면 전망 대신 `full_year_institution_total`만 표시한다. 그 해 1~4분기 기관 발표치 합계이며 실측은 아니다.
- `insufficient_reported_quarters`: 중간·마지막 분기 결측이나 중복으로 산출 보류, `missing_quarter_starts` 참고. `awaiting_second_quarter`: 1분기 이후 전망 보류. `past_year_awaiting_final_quarter`: 지난 연도에 대한 가정 전망을 더 보여주지 않는다.
- `source_published_at`, `source_status`(캐시 여부), `source_url`, `attribution`, 패널 `warning_ko`를 표시한다. 합산은 단일 EIA 발표의 호르무즈 원유+콘덴세이트 또는 LNG 분기 일평균 × 실제 분기 일수다. IEA 월간·PortWatch 톤·대체 수출항을 합치지 않는다. EIA가 직접 전망한 숫자로 표기하지 않는다.

## 공개 원문 검증

[EIA 2026-11-16 발표, 표 4](https://www.eia.gov/outlooks/steo/report/energysecurity/article.php) 원문을 직접 파싱해 재현했다. 2026년 10~12월 92일을 모두 미발표 구간으로 계산한 결과:

| 품목 | 1~9월 기관 추정치 누적 | 2분기 하루 물량 적용 시 | 3분기 하루 물량 유지 시 |
|---|---:|---:|---:|
| 원유+콘덴세이트 | 19.984억 배럴 | 연간 23.480억 배럴 | 연간 26.700억 배럴 |
| LNG | 867.6 십억 ft³ | 연간 941.2 십억 ft³ | 연간 996.4 십억 ft³ |

신규 PortWatch 관측·일별 화물 시계열·자동 예측 학습은 추가하지 않았다. 연간 전망의 통계적 성능이나 통항 가능성을 주장하지 않는다.
