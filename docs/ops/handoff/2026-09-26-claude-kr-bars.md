# 인수인계 2026-09-26 — claude

## 막대 차트 전 국가 확대 + 한국 KOSIS 파이프라인 (claude/kr-bars-kosis)

### 끝난 것
- **막대/선 판정을 화면에서 한다**(`macro.js` `mmUseBars`). 예전엔 데이터의 `chart_type: 'bar'`(미국 CPI/PCE 등 11개)에만 의존해서 다른 나라 물가·성장은 월 사이를 선으로 이었다.
  한 기간에 한 숫자씩 발표되는 값 — 물가, 성장률(`*_yoy/_qoq/_mom`, 어느 카테고리든), 흐름(무역수지·경상수지·고용변화·판매량·외환개입) — 은 막대, 가격·금리·지수와
  수준인 비율(실업률·수급갭·BEI·GDPNow·PMI/CCSI류 지수)은 선. 엔진이 따로 패널을 준 것(stack·status·fiscal 쌍)은 그대로.
  팩 전체에서 71개 지표(국가 중복 제외)가 막대. 규칙은 `mmUseBars` 상단 주석과 `MM_LEVEL_IDS`/`MM_FLOW_IDS` 두 집합에서 고친다.
  `nfp`·`gdp_yoy`·`gdp_qoq`·`trimmed_mean_cpi`처럼 `us_public_series.py` 가 `chart_type="line"`으로 박아 둔 것도 화면 규칙이 우선한다.

### (해결됨 — 2026-09-27) 한국은 KOSIS 가 아니라 ECOS 로 채웠다: `2026-09-27-claude.md` 참고
### 막혀 있던 것 — KOSIS 통계표 ID·이름이 확인되지 않았다
- `KOSIS_API_KEY` 는 Actions 시크릿에만 있고 로컬에 없다. 워크플로는 기본 브랜치에 있어야 `workflow_dispatch` 가 되므로(새 파일은 404),
  탐색 프로브(`kosis_probe.py`)를 돌릴 방법이 (a) 사용자가 본인 터미널에서 키를 입력해 로컬 실행 (b) 프로브 워크플로를 main 에 머지 (c) 기존 워크플로 슬롯을 임시로 빌려 쓰기 중 하나다.
  (c)는 권한 분류기가 막았다(공유 워크플로 수정) — 사용자 결정을 기다린다.
- 준비된 것: `macro_monitor/kosis.py`(클라이언트: 키는 환경변수로만, 에러·URL에 안 남김, 분류/항목을 **이름**으로 골라 코드 변경에 강함),
  `kosis_probe.py`(통계표 검색 → 분류·항목 이름·최신 값 출력), `kr_public_series.py`(원화 환산·지표 개명·통계표 자리), `tests/test_kr_public_series.py`.
- **한국 수출은 원화로**: 관세청은 달러로만 발표해서 `달러 수출액 × 그 달 평균 원/달러(FRED EXKOUS, 키 없음, 2026-08까지 확인)`로 환산해 `export_yoy_kr` → `export_krw`(조원)로 바꿀 계획.
  환율 평균이 아직 안 나온 달은 비워 둔다(추정 안 함). 화면에 환산값이라고 밝힌다.
- 프로브 결과가 나오면: `KOSIS_TABLES` 채우기 → `wire_kr_public_series.py` → 워크플로(다른 갱신기와 같은 패턴, deploy.yml 목록에 추가) → 프로브 워크플로 삭제.
- KOSIS 로 채울 후보: `cpi_yoy`, `core_cpi_yoy`, `ip_yoy`(전산업생산), 수출(달러) 및 반도체 수출, `gdp_yoy`/`gdp_qoq`.
  KOSIS 에 없어 ECOS(키 필요, 시크릿에 없음)가 필요한 것: CCSI·BSI·경상수지·M2·외환보유액·가계신용·국고채 금리.
