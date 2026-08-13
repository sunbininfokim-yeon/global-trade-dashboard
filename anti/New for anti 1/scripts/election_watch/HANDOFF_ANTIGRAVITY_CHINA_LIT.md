# Antigravity 핸드오프 — 중국 정치 싱크탱크 문헌 (lit only)

## 왜 Anti인가

`docs/ops/OWNERS.md`: **Literature only = Antigravity** → `docs/literature/**` (+ Obsidian 요약).  
Cursor는 CMPR/NPC 문서 추출 파이프라인만 유지. 싱크탱크 서베이는 문헌 담당이 맞음.

## 요청

중국 **엘리트정치·PLA·양회** 관련 **권위 싱크탱크·연구소** 자료를 검색·목록화하고, 최신(2024–2026) 인물·기구 해석을 Cursor 추출 슬롯과 맞출 수 있게 요약.

### 우선 검색 대상 (초안 — Anti가 검증·확장)

| 기관 | 왜 |
|------|-----|
| CSIS China Power / Freeman Chair | 엘리트·PLA 공개 분석 |
| Brookings John L. Thornton China Center | 당·국가 기구 |
| Carnegie Endowment (China) | 지도부·외교 |
| MERICS (Mercator Institute for China Studies) | 유럽 측 권위 |
| ASPI (Australia) | PLA·국방 기술 |
| RAND | PLA 조직·전구 |
| Jamestown China Brief | 인사·파벌 속보성 |
| USCC hearings / staff research | 미 의회 연계 (CMPR 보조) |
| Stanford SCCEI / UCSD 21st Century China | 학술 |

### 산출물 형식 (코드 금지)

`docs/literature/china_elite_pla_YYYY-MM.md` 또는 Obsidian 노트:

1. 출처 URL·발행일·기관  
2. 다루는 슬롯: PSC / Politburo / CMC / 전구 / 국무원  
3. CMPR 2025 추출물(`election_watch/config/china_leadership_extracted.json`)과 **일치·불일치**  
4. 최신화가 필요한 이름 3–10개  

Cursor가 이어서 `china_leadership_extracted.json` 을 패치한다.

## 이미 Cursor가 가진 것 (Anti 작업 불필요)

- DoD CMPR 2025 PDF/TXT + 5전구 사령·정치위원·참모장  
- `config/china_leadership_extracted.json` (구조화 슬롯)  
- **`config/china_pla_bios.json`** — DIA식 한국어 스키마 바이오 21명 (CMC+전구). Cursor 규칙추출.  
  재생성: `python3 -m election_watch.build_china_pla_bios`  
- USNI 인덱스, USCC/ODNI URL 카탈로그  
- `LEARNING.md` 문서추출 규약  

## 역할 경계 (맥스)

| Anti (문헌만) | Cursor (구현) |
|---------------|---------------|
| 싱크탱크 URL·발행일·일치/불일치 노트 | JSON 채움·파서·보드 병합 |
| CMPR vs 최신 인사 불일치 3–10명 | `china_pla_bios` / `china_leadership_extracted` 패치 |
| **코드·LLM API·implementation plan 파이프 금지** | 필요 시 Cursor가 파이프 가동 |

Anti 산출물이 오면 Cursor가 바이오/슬롯에 병합한다. LLM 자동추출 plan은 Anti에 맡기지 말 것.
