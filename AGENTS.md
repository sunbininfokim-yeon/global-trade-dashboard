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
