# GOAL — 글로벌 무역·작황 대시보드

최종 수정: 2026-08-04 · 관리: Cursor (ops)

## 제품 목표

연구·정책·물류 관점에서 **지역별 주요 작물 작황 신호 + 무역/물류 맥락**을 한 화면에서 추적한다.

핵심 사용자 가치:

1. 국가/산지별 **수확량 예측 범위(신뢰구간)** 와 신뢰도
2. 무역·물류 보조 지표 (Comtrade 프록시, shipping capacity 등)
3. 로컬 PC에 데이터를 쌓지 않고 **GitHub + Cloudflare에 산출물을 남겨** 파이프라인이 반복 실행 가능하게 함

## 데이터 철학

| 원칙 | 내용 |
|------|------|
| 원본은 재생성 | NASA POWER 등 원본 캐시는 git 제외. 스크립트로 복원 |
| 산출은 원격 | 학습 테이블·모델 JSON·forecast JSON은 저장소(및/또는 CF KV)에 커밋·업로드 |
| 정직성 > 정확도 과장 | skill 낮으면 `low_confidence`. 가짜 0 예측 금지 |
| 모델 기본형 | yield = technology trend + weather deviation (Ridge). 소표본에 LSTM/XGB 기본 금지 |

정본: `New for anti/scripts/yield_model/DATA_LAYOUT.md`,  
`New for anti/scripts/yield_model/HANDOFF_PROMPT.md`

## 아키텍처 (목표 상태)

```text
[논문/스펙 docs] → [수집 스크립트 GH Actions]
        ↓
[training.csv + model.json]  ──git──►  GitHub
        ↓
[public/data/*_yield_forecast.json]
        ↓  push main / deploy
[Cloudflare Worker + static assets + KV API_CACHE]
        ↓
[브라우저 대시보드]
```

로컬 맥은 **편집·실험 환경**이지 데이터 창고가 아니다.

## 성공 기준 (단기)

- [ ] 에이전트 4종이 `docs/ops` 규칙만으로 파일 충돌 없이 병렬 작업
- [ ] 신규 국가 추가 시 **forecast JSON 커밋만**으로 패널 표시 (렌더러 변경 최소)
- [ ] 일일/주기 Actions가 실패 시 알 수 있음 (CI 로그)
- [ ] UI 안정 후 Cursor가 ML 실험 브랜치에서 성능 개선 PR 가능

## 명시적 비목표 (당분간)

- 딥러닝 기본 채택
- 도구 간 API로 상호 호출하는 “슈퍼 오케스트레이터”
- Antigravity의 프로덕션 코드 직접 수정 (자료 요약만)
