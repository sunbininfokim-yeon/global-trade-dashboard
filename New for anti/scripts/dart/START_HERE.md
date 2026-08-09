# KFA / DART 문서 — 여기서 시작

옵시디언·학습용 **입구 문서**.  
폴더: `New for anti/scripts/dart/`  
(워크트리면 `/Users/yeoninair/Documents/New for anti-dart/New for anti/scripts/dart/`)

에이전트 협업 규칙(`AI_WORKFLOW`, `docs/ops/*`)이랑 **다른 줄거리**다.  
여기는 **재무엔진·펀더멘탈 모델**만 본다.

---

## 읽는 순서 (이 순서대로)

```
1. README.md              ← 엔진이 뭔지, 어떻게 돌리는지
       ↓
2. USER_INPUTS.md         ← 네가 준비할 것 (DART 키 등)
       ↓
3. LEVELS_OUTPUT.md       ← ① 재무분석 레벨 (beginner→investor→ma)
       ↓
4. OUTPUT_SCHEMA.md       ← 엔진 JSON 전체 계약 (desk, valuation…)
       ↓
5. INDUSTRY_RATIONALE.md  ← 업종 키트·한은 peer가 왜 그런지 (깊게)
       ↓
6. EXPORT_BOK_COVERAGE.md ← 수출·KSIC 매핑 (필요할 때)
       ↓
7. CREDIT_SOURCES.md      ← 무료 credit 패널 (이자보상·채공시 인덱스 / 등급·CDS 제외)
```

### 한 줄로

| 순서 | 파일 | 한 줄 |
|------|------|--------|
| **1** | [[README]] | 엔진 개요 + 실행 명령 |
| **2** | [[USER_INPUTS]] | API 키·입력물 체크리스트 |
| **3** | [[LEVELS_OUTPUT]] | 레벨별 재무분석 **출력 설계** |
| **4** | [[OUTPUT_SCHEMA]] | desk·valuation 포함 **전체 스키마** |
| **5** | [[INDUSTRY_RATIONALE]] | 산업·peer 논리 |
| **6** | [[EXPORT_BOK_COVERAGE]] | BOK/수출 커버리지 |

---

## 두 축이 뭐였는지 (복습)

1. **재무분석 (levels)** — 공시로 과거·현재 읽기 (`LEVELS_OUTPUT`)  
2. **펀더멘탈 모델** — 가정(성장·마진·WACC) 넣고 DCF/시나리오 (`OUTPUT_SCHEMA`의 `valuation` + desk)

UI는 Claude. 엔진·이 문서들은 Cursor (`cursor/ml-dart-kfa`).

---

## 옵시디언에서 가는 길

1. Vault / 폴더가 이 레포를 가리키는지 확인  
2. 왼쪽 파일 트리: `scripts` → `dart`  
3. **이 파일(`START_HERE.md`) 열기**  
4. 위 표 순서대로 링크 클릭  

`AI_WORKFLOW`는 ops 협업용 → 재무 학습 입구 아님.

---

## 코드로 넘어갈 때 (문서 다음)

```
dart_kfa/analyze.py          # 엔드투엔드
dart_kfa/fundamental_pack.py # desk(현업 원페이저)
dart_kfa/valuation.py        # 가정 DCF
dart_kfa/metrics.py          # 비율
fetch_live.py                # SEC/DART 실호출 CLI
config/                      # accounts.map, metrics.spec, valuation.spec
```

문서 1→4 읽은 뒤에 코드 보는 걸 추천.
