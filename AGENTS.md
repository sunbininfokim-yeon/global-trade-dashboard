# AGENTS.md — 모든 코딩 에이전트용

이 저장소는 여러 CLI 에이전트가 협업한다.

**운영 규칙 정본:** [`docs/ops/README.md`](docs/ops/README.md)  
**소유권 정본:** [`docs/ops/OWNERS.md`](docs/ops/OWNERS.md)

필수 읽기:

1. `docs/ops/GOAL.md`
2. `docs/ops/OWNERS.md`
3. `docs/ops/TASKS.md`
4. `docs/ops/PIPELINE.md`
5. 모델/데이터: `New for anti/scripts/yield_model/DATA_LAYOUT.md`

시작:

```bash
./tools/ops/status.sh
```

역할 요약 (2026-08-04 이후):

- **Cursor** = ops · 제품 통합 · ML · (기본) 프론트/워커 소유  
- **Claude** = 코드 리뷰 · `TASKS` claim 시 대형 UI/아키텍처  
- **Codex** = 좁은 모델/데이터 작업  
- **Antigravity** = 문헌만  

---

## 국가를 대시보드에 올리는 법 (2026-08-07)

**`New for anti/app.js` 는 수정하지 않는다.** 국가 추가에 UI 코드 변경은 필요 없다.

예전에는 `app.js` 의 `CLIMATE_COUNTRIES` 객체를 고쳐야 했고, 두 터미널이 각각
국가를 추가하면 같은 줄에서 충돌했다. 지금은 매니페스트 한 장이 그 자리를 대신한다.

```bash
cd "New for anti/scripts/yield_model"
python3 scaffold_manifest.py <country>     # model.yaml 초안
# TODO 채운 뒤
python3 build_registry.py --check          # 검증
```

스캐폴드가 자동으로 채우는 것: 산지 키·라벨·단위(forecast JSON), 좌표(regions.py
관측점 평균), `model_status`(실측 skill).
사람이 채울 것: `iso`, `label_ko`, `label_en`(월드 GeoJSON 이름과 일치), `view`,
`sources.labels`(기관·URL·데이터 최신 시점), `trade_policy.note_ko`.

**추측으로 채우지 말 것.** 틀린 좌표는 빈칸보다 나쁘다.

### 수정 금지

`New for anti/app.js` · `public/data/climate_registry_v1.json`(CI 생성물) ·
`public/data/admin1/*.json`(생성물) · `.gitignore`

### 자유

`New for anti/scripts/yield_model/{country}/**` ·
`New for anti/public/data/{country}_yield_forecast.json`
국가마다 경로가 달라 동시 작업해도 충돌하지 않는다.

### 학습이 덜 끝났으면

`model_status: training` + `status_note_ko` 로 밝히면 된다. 완성할 필요 없다.
`validated` 는 실측 skill 이 뒷받침해야 CI 를 통과한다.

전체 규격: `New for anti/scripts/yield_model/MODEL_MANIFEST.md`

## 미국 선거 주별 데이터 작업 (2026-10-10)

주별 PR을 시작하기 전에 `docs/ops/US_ELECTION_STATE_INPUTS.md`를 읽는다.
주별 검토 입력은 `scripts/election_watch/config/state_evidence/2026/<STATE>.json`에 둔다.
전국 생성 JSON·공용 검토 목록·공용 수집기·`TASKS.md`를 주별 PR에 함께 넣지 않는다.
공용 코드 보강은 별도 기반 PR로 먼저 처리하고, 주별 진행 기록은 주별 인수 문서에 남긴다.
생성 파일 충돌은 Git 텍스트 병합으로 해결하지 않는다. 최신 main과 원래 수집 입력으로 재생성한다.
입력의 다른 주 혼입·기준 자료 충돌은 보류하고, 종전 기준일·영수증과 `house_poll_focus`를 유지한다.
병합·배포는 사용자가 확정한다.
