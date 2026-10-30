# 공식 호르무즈·수에즈 화물 자동 수집 — UI 연결 계약

브랜치: `codex/chokepoint-cargo-official-pipeline`

작업 폴더: `/Users/yeoninair/Documents/해운 데이터/chokepoint-cargo-pipeline`
2026-10-01 실제 EIA/IEA/IMO 수집 성공을 확인했으며 공개 bundle 4종을 생성했다. 이 문서는 데이터 PR의 UI 연결 계약이다. 병합·배포 완료를 뜻하지 않는다.

검증: 전체 테스트 98개 통과, JSON Schema 4종 및 화면/진단 golden contract 통과. 실제 EIA 호르무즈 24개·수에즈 24개 기간/품목 기록, IEA 8월 석유 전체 월평균 1개, IMO 공식 경보 링크 5개 수집. 생성 시 bundle_id는 4종 동일하게 바뀌므로 하드코딩하지 않는다. 새 모듈의 API 키 요구는 없다.

## 원격 자동화의 현재 차단 요인

2026-10-01 GitHub API 읽기 확인: shipping workflow는 `active`지만 최근 예약 실행 3회가 실패했다. [최근 실행 36786108541](https://github.com/sunbininfokim-yeon/global-trade-dashboard/actions/runs/36786108541)의 오류 안내는 계정 결제 실패 또는 spending limit 문제로 job 자체가 시작되지 않았다는 내용이다. 실패한 모델 단계가 있는 상황이 아니다. 사용자의 GitHub Billing & plans 확인이 필요하다. 계정 한도/결제 변경, 재실행, 배포는 Codex가 수행하지 않았다.

따라서 병합만으로 즉시 자동 갱신이 정상화된다고 보고하지 않는다. GitHub 실행 차단 해소 → main 반영 → 예약/수동 실행 성공 → 산출물 변경 → 배포/화면 확인을 각각 검증해야 한다.

## 구현 범위

Codex 데이터 변경이며 UI·배포·기상/ACP 모델 변경은 포함하지 않는다.
기존 초안 `eia_hormuz.py`의 시드·유가 영향·파이프라인 총용량 차감은 사용하지 않는다.

- EIA 공개 HTML 표를 API 키 없이 수집한다. 호르무즈와 수에즈+SUMED의 석유 전체·원유+콘덴세이트·제품, 수에즈 운하 단독 및 호르무즈 LNG를 구분한다.
- IEA 공식 주제 페이지에서 최대 4개의 공개 commentary를 발견한다. 개별 문서의 CC BY 4.0·출처 URL·발표일을 검증한 뒤 명시된 완료 월 호르무즈 석유 전체 일평균만 수집한다. 지원되지 않는 표현/권리는 `candidate_errors[].status=review_required_not_published`; 임의 숫자 추출이나 유료 chart 데이터 접근은 없다.
- IMO 공개 페이지에서 사건 목록·UKMTO·JMIC·NAVAREA 공식 링크를 갱신한다. 사건 본문/발생 건수나 성공확률을 수집·산출한 기능은 아니다.
- 실제 일별 차트는 기존 PortWatch `metric_histories`를 재사용한다. 선종 분류를 화물 품목으로 이름만 바꾸지 않는다.
- 파서 실패 시 마지막 정상값의 `retrieved_at`, 기간, 원출처를 유지하고 `cached_fallback`을 붙인다. 정상값이 없으면 비어 있는 공식 카드와 unavailable 상태다. 시드/가짜 0/분기평균의 일별 복제는 없다.

## 자동 실행 연결

기존 `.github/workflows/shipping_capacity_update.yml`이 사용하는 `build_snapshot.py --fetch-portwatch`가 공식 참고 수집도 실행한다. workflow/Secrets 변경 불필요. `--fetch-official-cargo`로 공식 참고만 별도 갱신할 수도 있다.
생성 결과는 기존 shipping bundle 4종에 포함되므로 파일 업로드 경로를 추가할 필요가 없다. 관련 변경을 main에 병합해야 원격 예약 실행이 이 코드를 사용한다. 로컬 구현/테스트는 원격 실행·배포 완료의 증거가 아니다.

공식 참고만 갱신하는 경우에도 같은 bundle_id를 가진 diagnostics의 730일 이력을 보존한다. `--previous-snapshot`은 별도 출력 경로로 검증할 때 사용할 수 있다. 이번 로컬 생성에서 기존 일별 PortWatch 값은 보존했고, 현재값으로 재수집했다고 표시하지 않았다. 일별 자료의 노후화 상태는 JSON에 남아 있다.

```sh
cd "New for anti/scripts/shipping_capacity"
python build_snapshot.py --fetch-official-cargo --output ../../public/data/shipping_capacity_v1.json
python -m unittest discover -s tests -v
python validate_schema.py
```

## UI — 기존 칩·지도·상세 구조 유지

선택한 `point.id`로 아래를 읽는다:

```js
const monitor = payload.official_cargo_monitor;
const point = monitor?.chokepoints?.[selectedPointId];
```

1. 일별 그래프: 기존 `payload.chokepoints_live[id].metric_histories[type].history` 및 해당 평균을 읽는다.
2. 공식 참고 카드: `point.reference_cards[]`를 그대로 렌더링한다. `display_label_ko`, `value`, `unit`, `period_start`, `period_end`, `publisher`, `source_url`, `source_published_at`, `source_status`, `warning_ko`를 보인다.
3. 월간 보조 참고: `point.supplementary_reference_cards[]`는 IEA의 별도 월간 **석유 전체 일평균**이다. EIA 분기 구성비 카드에 섞지 않는다. `license`, `attribution`, `source_published_at`, `period`, `warning_ko`를 같이 표시한다. 현재 2026-08 760만 배럴/일이며 오늘의 원유 통과량이 아니다.
   기간별 공식 추세: `point.reported_series[]`에는 EIA 분기와 IEA 월간 기록이 함께 있다. 반드시 publisher·frequency·geography_scope·cargo_category별로 나눠 그린다. 날짜별 실측 선그래프와 혼합하지 말고 기간 막대 또는 별도 참고 그래프를 쓴다.
4. `geography_scope === 'suez_canal_and_sumed_pipeline'`이면 제목에 `수에즈+SUMED`를 반드시 표시한다. LNG의 `suez_canal` 범위는 운하 단독이다.
5. `barrels_per_day`는 숫자 배럴/일, `billion_cubic_feet_per_day`는 십억 입방피트/일로 표시한다. 원유+콘덴세이트를 원유 단독으로 축약하지 않는다.
6. `point.transit_assessment.advisory_references[]`는 공식 경보 원문 링크다. “통항 여건 확인” 패널로 표시한다. `success_probability`는 null이며 백분율·안전판정·보험 가능 여부로 만들지 않는다. `advisory_source_status`도 함께 표시한다.
7. `point.daily_crude_barrels.value`는 현재 null이다. 일별 원유 숫자를 기관 분기평균이나 탱커 톤에서 만들어 채우지 않는다.
8. 수에즈의 최신 SCA 품목별 톤 통계는 `latest_sca_commodity_tonnes_not_connected`다. 현재 선종별 일별 추정량과 별개로 최신 화물별 실제 통계가 연결됐다고 표시하지 않는다.
9. `reference_cards`가 비었으면 “공식 화물 참고 자료 미수집”으로 표시하거나 참고 카드만 숨긴다. 기존 일별 AIS 차트/시뮬레이터는 그대로 동작해야 한다.
10. EIA도 `attribution`과 원출처 링크를 표시한다. EIA 공개 재사용 정책의 제3자 예외를 기록했고, EIA가 발표한 표의 사실값만 추출한다. Vortexa/Kpler 원자료·사진·차트 원본을 재배포한 것이 아니다.

계산 금지: 배럴 변환, 원유 구성비 추정, AIS 비가시율, 통항 성공확률, 파이프라인 대체 손실을 브라우저에서 산출하지 않는다.

## 미포착 보조 추정 — 별도 연구, 아직 수치 미산출

`HORMUZ_UNOBSERVED_FLOW_RESEARCH.md`에 Antigravity 핸드오프 감사, 오만만 질량수지와 수입측 지연 확인 방법, 무료 자료 커버리지를 정리했다. 무료 JODI 국가 자료는 일부 누락, Sentinel-1 metadata는 조회되지만 영상 탐지/개별 AIS 대조/화물 추정은 미실행이다. 따라서 일별 미포착 원유량·통항 가능성 %는 이번 JSON에 만들지 않았다.

‘62% 미송신’으로 관측량을 38%로 나누거나, EIA 2분기와 IEA 8월 값의 차이를 미포착 물량으로 표시하지 않는다. 다음 단계의 입력이 검증될 때만 월간 미설명 물량 범위를 별도 보조지표로 추가한다. 연구를 운영 모델 구현으로 소개하지 않는다.

## 배포 전 스모크

- 호르무즈 카드의 기간·원유+콘덴세이트 명칭·단위 확인.
- IEA 월간 참고를 EIA 분기 원유/제품 카드와 분리하고 출처·라이선스·잠정/수정 가능 경고를 확인.
- 수에즈 석유 카드 SUMED 경고, LNG 별도 단위 확인.
- 컨테이너/벌크/탱커 일별 토글은 기존 일별 자료만 사용.
- fallback/unavailable/null 처리 시 실제 통항 0으로 표시하지 않음.
- 기존 희망봉 시나리오 행과 렌더링 회귀 없음; shipping bundle_id 4종 일치.
- UI·원격 workflow 실행·배포 확인은 Claude 담당이며 별도 완료 확인 필요.
