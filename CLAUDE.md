# CLAUDE.md — Claude Code

당신은 이 레포의 **UI 및 배포 파이프라인 소유자**다.
정본은 `docs/ops/OWNERS.md`.

> **2026-08-05 소유권 이전 (현행):** 사용자 지시로
> **UI(`New for anti/*`) + 배포(`_worker.js`, `wrangler.jsonc`, `.github/workflows/**`)
> 전체를 Claude Code가 소유**한다.
> “App/UI 기본 소유는 Cursor” / “Claude = 기본 코드 리뷰어” 문구는 폐기.

## 시작

```bash
cd "/Users/yeoninair/Documents/New for anti"   # 또는 clone 경로
./tools/ops/status.sh
```

읽고 따를 것: `docs/ops/README.md`, `OWNERS.md`, `TASKS.md`, `docs/ops/handoff/`.

## 소유

- **단독 소유:** `New for anti/{app.js,style.css,index.html,data.js,shipping.js}`,
  `_worker.js`, `wrangler.jsonc`, `.github/workflows/**`, `docs/ops/**`, `tools/ops/**`
- **협의:** `scripts/yield_model/**`(모델 담당), `public/data/*_forecast.json`(DATA_LAYOUT 준수)
- **금지:** `cache/`·시크릿 커밋, `main` 직접 push, force-push

## 편집 충돌 — 작업 전 확인

**전용 워크트리에서 작업한다.** 다른 세션과 같은 체크아웃을 쓰면, 그쪽 커밋에
내 미커밋 수정이 딸려 들어간다 (2026-08-07 에 세 번 발생). 그리고 **인수인계는
`docs/ops/handoff/<날짜>-<에이전트>.md` 자기 파일에만** 쓴다.

Cursor가 UI 파일을 열어 둔 채로 저장하면 오래된 버퍼가 진행 중인 수정을 덮어쓴다
(2026-08-05 실제 발생: `app.js` 전체 롤백). UI 작업 시작 전에:

1. Cursor에서 `New for anti/` 하위 UI 파일 탭을 닫는다 (확실하게는 File › Close Folder)
2. Cursor Agent/Composer가 이 레포에 붙어 있으면 중지
3. 큰 편집은 재실행 가능한 패치 스크립트로 적용하고, 적용 후 `grep` 으로 반영 확인

## 프론트엔드 구조 메모

- 지도는 deck.gl `_GlobeView` 하나로 통일 (홈·무역·기후). MapLibre 래스터 베이스맵은
  제거됨 — 평면 타일은 구부러지지 않아 곡률이 불가능했다. 베이스맵은
  `worldBaseLayers()`(구체 메시 + 국가 폴리곤)가 직접 그린다.
- **deck.gl 9.3.7의 `_GlobeView`에서 `ArcLayer` / `LineLayer` / `TextLayer`는 그려지지 않는다**
  (에러 없이 조용히 사라짐, MapView에서는 정상). 무역 흐름은 `greatCirclePath()` +
  `PathLayer`, 산지 라벨은 투영식 HTML 오버레이로 대체.
- 국가 식별은 `resolveCountry()` 하나로 통일. `window.CountriesData`(65개 수기 표)는
  게이트가 아니라 **좌표 오버라이드**다. 새로 들어오는 국가는 월드 GeoJSON에서
  중심점을 계산해 자동으로 클릭 가능해진다 — 국가명을 하드코딩하지 말 것.
- 남극은 마스크로 가리지 않고 소스 features 에서 제거한다 (`loadWorldGeo`).
- 매크로 모니터(`/macro_monitor`)만 베이스맵이 다르다: NASA VIIRS Black Marble
  야간광 타일(`mmNightBaseLayers`). 타일은 z0-5 를 `New for anti/public/night/`
  에 커밋해 두고(`tools/ops/fetch_night_tiles.py`), 그보다 확대하면
  `/api/night-tile` 워커 프록시를 탄다. 타일이 없으면 벡터 실루엣으로 내려앉는다.
  남극은 타일 `extent` 하단(-58°)으로 잘라 낸다.

## 데이터 계약

대시보드가 읽는 예측 JSON 규격은
`New for anti/scripts/yield_model/DATA_LAYOUT.md`
를 깨지 말 것. UI 리뷰 시 필드 정규화·`forecast_available: false` 처리를 확인.

## 배포

- Cloudflare Worker `global-trade-dashboard` (`wrangler.jsonc`), assets = `New for anti`
- `/api/*` 는 `_worker.js` 프록시 + KV `API_CACHE`. 로컬 정적 서버에서는 404가 정상.
- **작업 브랜치 커밋 후 main만 push 하면 배포되지 않는다 — PR merge 필수.**
- 배포 후 스모크: `curl -s https://global-trade-dashboard.sunbin-info-kim.workers.dev/api/ticker?limit=3`

## 브랜치

`claude/<주제>` · main 직접 push 금지 · 끝나면:

```bash
./tools/ops/handoff.sh claude "한 줄 요약과 남은 TODO"
```
