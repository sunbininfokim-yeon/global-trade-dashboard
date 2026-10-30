# 정책 데이터 국가 확장 가이드

미국 Phase 2-1에서 확정한 기관·입법 데이터 처리 원칙을 다른 국가에 적용하기 위한 가이드다. 이 문서는 화면 문구를 번역하는 방법이 아니라, **공식 데이터가 실제로 제공하는 사실만 저장하고 UI에 연결하는 방법**을 정리한다.

## 1. 역할 분리

```text
공식 정부 API / 공보
        ↓
수집 스크립트 (GitHub Actions)
        ↓
정규화·관계 연결·재시도
        ↓
Supabase (영구 저장)
        ↓
UI / API (조회)
```

- **GitHub Actions**: 일정에 따라 수집·분류·저장하는 작업자다. 데이터 저장소가 아니다.
- **Supabase**: 법안, 행정명령, 규제, 기관 관계와 동기화 이력을 저장하는 DB다.
- **UI**: Supabase에서 읽기만 한다. 기관 유형이나 법안 단계를 화면에서 이름 규칙으로 추측하지 않는다.

스키마를 바꿀 때는 먼저 Supabase 마이그레이션을 실행하고, 그 다음 새 컬럼을 쓰는 수집 코드를 배포한다. 반대 순서면 새 코드가 없는 컬럼에 쓰기를 시도해 동기화가 실패할 수 있다.

## 2. 미국에서 확정한 기관 분류 모델

미국 Federal Register의 `agencies[]` 객체는 기관명·ID·`parent_id`를 제공한다. 하지만 “내각 부처인지, 독립기관인지”는 제공하지 않는다. 따라서 다음 네 값을 **미국 전용 표시 분류**로 사용한다.

| 값 | 의미 | 판정 근거 |
|---|---|---|
| `eop` | 대통령실 구성기관 | 검증된 Executive Office of the President 구성기관 목록 |
| `department` | 15개 내각 부처 | 검증된 부처명 목록 |
| `independent` | 독립기관·외청 | 상위기관이 없고 위 두 목록에 해당하지 않는 기관 |
| `sub` | 하위 기관 | Federal Register의 `parent_id`가 존재 |

중요한 원칙은 우선순위다. `parent_id`가 있으면 이름이 어떻든 `sub`로 분류한다. 즉 IRS·FDA 같은 기관은 독립기관으로 잘못 보이지 않고 상위 부처 상세 안에 표시된다.

## 3. 저장 구조

미국 기관 기준정보는 `agencies`에 저장한다.

| 필드 | 역할 |
|---|---|
| `agency_id` | 서비스 내부의 안정적 ID. 미국 Federal Register는 `fr-<slug>` 형식 |
| `federal_register_id` | 원천 API의 숫자 ID |
| `name`, `short_name` | 공식·표시 명칭 |
| `agency_type` | 위의 네 가지 미국 표시 분류 |
| `parent_agency_id` | 같은 테이블의 상위 기관을 가리키는 FK |
| `raw_source` | 원천 API 기관 객체 보존 |

`parent_id`는 원천의 숫자 ID이므로 UI에 직접 쓰지 않는다. 수집 과정에서 `federal_register_id → agency_id`로 변환해 `parent_agency_id`에 저장한다. 상위기관이 아직 DB에 없으면 하위 기관은 `sub`로 저장하고, 이후 동기화/백필 때 관계를 다시 해소한다.

EO와 규제는 기관을 텍스트로 중복 저장하지 않는다.

```text
executive_orders ── executive_order_agencies ── agencies
regulations      ── regulation_agencies       ── agencies
```

한 문서가 여러 기관과 연결될 수 있으므로 중간 관계 테이블을 반드시 쓴다.

## 4. UI 계약

행정부 기관 목록 API는 최소한 아래 필드를 반환한다.

```json
{
  "agency_id": "fr-national-park-service",
  "name": "National Park Service",
  "short_name": null,
  "agency_type": "sub",
  "parent_agency_id": "fr-interior-department",
  "executive_order_count": 0,
  "eo_ids": []
}
```

UI 표시 규칙:

- `eop`: 대통령실 블록
- `department`: 내각 부처 블록
- `independent`: 독립기관·외청 블록
- `sub`: 최상위 블록에는 중복으로 보이지 않고 `parent_agency_id`의 상세 화면에서 표시

“15개 부처” 같은 숫자는 고정 문구가 아니다. 현재 DB에 실제로 수집된 최상위 기관 수를 표시한다. 아직 해당 부처의 공식 문서가 수집되지 않았다면 임의의 빈 기관을 만들지 않는다.

## 5. 다른 국가를 추가할 때의 절차

미국의 `eop`, `department`, `independent`, `sub` 값을 그대로 다른 나라에 재사용하지 않는다. 국가별 헌정·행정 체계가 다르므로 아래 순서로 국가 전용 분류표를 만든다.

1. **공식 원천 확정**
   - 의회 법안 API, 관보, 대통령령/시행령, 부처 조직도 등 공식 출처만 선택한다.
   - 원문 전체를 보관하지 않는 현재 정책을 유지하고, 공식 URL과 공식 요약만 저장한다.

2. **원천이 주는 사실 확인**
   - 기관의 안정 ID가 있는지
   - 상위기관 ID가 있는지
   - 법안 단계·공포일·담당 부처·법적 근거가 구조화되어 있는지
   - 변경분 커서 또는 수정일 필터가 있는지

3. **국가 전용 taxonomy 정의**
   - 예: 일본은 `cabinet_office`, `ministry`, `agency`, `independent_commission`, `sub`처럼 일본 조직법에 맞는 값이 필요할 수 있다.
   - 분류 목록은 출처 URL, 검토일, 담당자를 함께 문서화한다.
   - 이름 정규식은 보조 수단일 뿐이다. 공식 상하위 ID가 있으면 그것을 우선한다.

4. **비파괴 마이그레이션**
   - 새 국가 필드·참조 테이블을 `add column if not exists`, `create table if not exists`로 추가한다.
   - 기존 행 삭제·트런케이트·원문 아카이브를 동시에 하지 않는다.
   - 기존 데이터가 있으면 분류 백필 함수를 만들고, 실행 전·후 행 수를 기록한다.

5. **동기화 코드**
   - 새 문서는 항상 upsert한다.
   - 원천 ID를 내부 안정 ID로 변환한다.
   - API 제한에 맞춰 재시도·지수 백오프·커서 재개를 유지한다.
   - 수집 실패가 임베딩 실패와 섞이지 않도록, 임베딩은 선택적 단계로 둔다.

6. **UI 연결 전 검증**
   - 유형별 기관 수
   - 상위기관이 연결된 하위기관 수
   - 문서→기관 관계 행 수
   - 미분류 행 수
   - 동기화 실행의 성공·실패·재시도 상태

## 6. 미국 기관 분류 검증 SQL

```sql
select
  coalesce(agency_type, 'unclassified') as agency_type,
  count(*) as agency_count
from public.agencies
group by 1
order by 1;
```

```sql
select
  count(*) filter (where parent_agency_id is not null) as linked_child_agencies,
  count(*) filter (where agency_type = 'sub' and parent_agency_id is null) as unresolved_child_agencies
from public.agencies;
```

`unresolved_child_agencies`가 있다면 데이터 손실이 아니라 상위기관이 아직 수집되지 않은 상태일 수 있다. 다음 동기화에서 해결되는지 확인하고, 계속 남으면 원천 API의 상위기관 ID와 내부 ID 변환 규칙을 점검한다.

## 7. 운영 기준

- 백필 중에는 작은 배치로 먼저 검증하고, API·GitHub Actions·Supabase 사용량을 보면서 단계적으로 늘린다.
- 반복 실행은 `policy_ingestion_queue`, `data_sync_state`, `data_sync_runs`로 재개·감사 가능해야 한다.
- GitHub Actions는 수집 실행 환경이고 Supabase는 저장소다. Cloudflare는 현재 정책 동기화 경로에 필요하지 않다.
- 국가별 taxonomy·공식 원천·UI 계약이 확정되기 전에는 이름만 보고 기관 또는 법적 관계를 만들어내지 않는다.
