# 수출통제 주간 점검

수출통제 모니터(원자재 › 모니터링)와 무역 지도는 `New for anti/public/data/export_controls/` 를 읽는다. 이 디렉터리는 그 카탈로그를 매주 검사하고, 검사했다는 기록을 GitHub PR로 남기는 쪽이다. 워크플로 파일 설치와 화면 별칭은 Claude가 한다.

## 카탈로그 구조 (2026-10-02부터)

하나의 JSON이 아니라 `manifest.json` + 분류별 모듈이다.

- `manifest.json` — `as_of`, `levels`, `measure_types`, `modules`(분류 → 파일), `survey`
- `agri.json`, `energy.json`, `minerals.json` — 각자 `category` 와 그 분류의 `controls` 만

행은 `category` 와 같은 모듈 파일에 둔다 (`validate` 가 잡는다). 새 분류(예: 귀금속)는 파일 하나와 `modules` 한 줄이면 되고, 검증기는 manifest 의 분류를 그대로 쓴다. 행에는 화면 표시용 `country_ko` 를 넣는다. 읽기는 `export_controls/catalogue.py` 의 `load()` 하나로 통일했다.

## 주기

매주 월요일 02:00 UTC. 격주가 아니다. 인도 설탕은 9월 30일에 기한이 끝나고, 러시아 석유제품 금지의 예외도 월 경계에서 움직이며, 팜유 기준가는 달 안에서 바뀐다. 조치가 그대로인 주도 그 주 기록은 남긴다. 카탈로그는 원문을 읽은 뒤에만 고친다.

## 30개국

카테고리마다 30개국. 2023–2024년 1차 수출이 큰 나라다. 농산물은 USDA PSD·FAO, 귀금속·광물은 USGS, 에너지는 IEA. 재수출 허브(네덜란드, 벨기에, 싱가포르, 스위스, 홍콩)는 빼다. 아랍에미리트는 원유 수출국이라 에너지 30에만 있다.

이집트(쌀·밀), 미얀마(쌀), 가나(코코아)는 그 품목의 상위 30 밖이거나 다른 그룹에만 있어서 `pinned_outside_role`로 같이 본다.

대시보드에 없는 품목도 슬러그는 둔다. 금, 은, 백금, 팔라듐, 다이아몬드, 석유제품, 우라늄, 면화, 쇠고기, 과일. 수출통제 모니터는 슬러그와 상관없이 모든 행을 보여 준다. 품목별 무역 지도에 색이 칠해지려면 Claude가 `export-controls.js`의 `ALIASES`에 슬러그를 넣어야 하고, 한글 이름은 같은 파일의 `COMMODITY_KO`에 있다.

목록 원본은 `universe.py`다. `universe.json`은 그 출력이다.

## 실행

저장소 루트에서:

```bash
cd "New for anti/scripts"
python3 -m export_controls.universe    # universe.json 재생성
python3 -m export_controls.validate
python3 -m export_controls.survey
python3 -m unittest export_controls.tests.test_controls
```

`survey.py`는 검증이 실패하면 주를 기록하지 않는다. 성공하면 `surveys/weeks.json`에 그 ISO 주 한 칸을 넣거나 같은 주를 덮어쓴다. `unchecked`는 원문을 아직 안 본 나라·품목이다. 통제가 없다는 뜻이 아니다.

## Claude가 설치할 것

`workflow.yml.example`을 `.github/workflows/export_controls_weekly.yml`로 복사한다. `cursor/` 브랜치는 그 경로를 수정할 수 없다. 잡은 main에 push하지 않고 `cursor/export-controls-weekly-survey` PR 하나를 갱신한다.

이번 카탈로그에서 화면 별칭이 필요한 슬러그: `petroleum_products`, `fruit`, 그리고 아직 행이 없는 귀금속 슬러그(`gold`, `silver`, `platinum`, `palladium`, `diamonds`).

## 주간 결과표 (2026-10-02부터)

`survey.py`가 `report.py`로 그 주의 결과표를 `surveys/reports/<주>.md`(와 `latest.md`)에 쓰고,
주간 PR 본문이 이 표가 된다. 네 칸이다.

1. **기한**: 살아 있는 행의 `until`·`review_valid_until`이 지났거나 21일 안에 오는 것.
   지난 `until`은 화면에서 「기한 경과」로 보인다.
2. **원문 링크**: 행마다 한 번 받아 본다. 404·410만 「깨짐」이고, 차단·시간 초과·5xx는
   「자동 확인 불가」다(정부·언론 사이트는 봇을 자주 막는다).
3. **공고 → 후보**: 보고서 파이프라인의 `boards.export_controls` 중 최근 8일의
   수출금지·수출통제·해제·목록조정 공고를 발표국·품목으로 카탈로그 행과 맞춘다.
   맞으면 「갱신 후보」, 아니면 「신규 후보」와 초안(신뢰도 low, 재확인 필요). 원자재를
   명시하지 않은 기술 통제(반도체·무기 등)는 건수만 적는다.
4. **열린 질문**과 감시 쌍 커버리지.

표는 카탈로그를 고치지 않는다. 초안은 원문을 읽고 분류 모듈 파일에 직접 넣는다.
로컬에서 네트워크 없이 보려면 `python3 -m export_controls.survey --no-links`.

## 사람이 하는 일

자동 수집 결과를 `high`로 올리지 않는다. 정부 고시나 공식 발표 원문일 때만 `high`다. 수출세를 금지로 올리지 않는다. 추정 HS를 넣지 않는다. 해제한 지 12개월이 지난 행은 지운다.
