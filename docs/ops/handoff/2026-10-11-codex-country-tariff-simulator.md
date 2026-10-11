# 인수인계 2026-10-11 — codex-country-tariff-simulator

## 2026-10-11 — codex-country-tariff-simulator

### Goal / summary
국가 CES + 기업 제품 손익 시뮬레이터: 사용자 요청 경로·두 탭 구현. 모델/탐색/기존 검색·즐겨찾기 44개 및 국가·기업 브라우저 저장·왕복·360px·국가 결과 연결 검증. PR #528 후속 보강, 병합·운영배포 없음. 상세: docs/country-tariff-simulator.md / docs/company-tariff-simulator.md

### Meta
- branch: `codex/country-tariff-simulator-20261011`
- head: `962901fa` 이후 기업 버전 후속 커밋 (PR #528)

### Files (working tree at handoff time)
```
"New for anti/policy.js"
docs/ops/TASKS.md
"New for anti/policy-simulator/"
docs/country-tariff-simulator.md
docs/ops/handoff/2026-10-11-codex-country-tariff-simulator.md
scripts/lib/country-tariff-model.test.mjs
scripts/lib/country-tariff-catalog.test.mjs
scripts/lib/country-tariff-navigation.test.cjs
scripts/trade_policy/preview_country_simulator.py
scripts/trade_policy/test_country_simulator_browser.cjs
```

### Not done / risks
- 실제 산업 구매액·공급탄력성 보정·전체 현행 관세·실제 기업 자료 보정 미구현. 기업 제품 손익·가격 전가/흡수·국가 대용 연결은 구현. DataWeb 공개 공급국 집계, 조건부 현행 관세·문헌 탄력성 구현. 중국·CAN/MEX·TRQ 미검증 조합은 직접 현행 세율/출처 필요.
- 가상 시장의 조건부 결과이며 GDP·기업 이익·AD/CVD 예치/확정액을 산출하지 않음.
- 병합·운영 배포 미실행. 기존 수집기·메일링 변경 없음.

### Next
- 별도 PR 검토 후 사용자 배포 지시에 따라 병합·정상 배포 절차로 반영.
- 운영 `/policy/us/simulator`에서 직접 진입·의회/행정부 왕복을 확인.
- 한 품목의 국내 출하·수입·가격 기준·탄력성을 보정한 검증 입력을 별도 준비.

### Commands
```bash
./tools/ops/status.sh
git push -u origin codex/country-tariff-simulator-20261011
```

---

### 10/11 후속 요청 반영
- 구매액 기준 연도·기간과 관세 검토일을 구분. 국가 탭 상단에 USITC 모형·원문 짧은 링크, 하단 상세 설명 유지.
- 관세 정책 카탈로그는 2026-10-11 부분 검토. HTS·원산지·금속 함량 등 조건별 조합 및 수동 총 세율. 합산 하한/추가율을 구분하며 232와 강제노동 301 중복 제외.
- 7개 HS6의 2025 공급국별 수입액 상위8 공개 집계 추가. 새 국가 구매액 자동 입력 없음. 로컬 DataWeb 키 커밋·원격 저장 없음.
- 메모리 σ=3.32(2023 연구 표4), 타이어 σ=3~6의 중간4.5(2021 보고서), η 중간-0.375. 나머지 사용자 가정 명시.
- 품목 변경 시 정책·탄력성·조건 확인 초기화. JSON에 HTS·검토일·조건·출처·탄력성 근거 유지.
- 화면 스크린샷의 타이어 12.5→25%는 테스트에서 직접 입력한 가정이며 현행 25%라는 뜻이 아님.
- 기준 구매액의 관세 포함·백만 달러·미국산 국내 구매 정의를 표 바로 위에 설명. 50/25/25는 가상 초기값.
- σ와 η 각각의 적용 근거·원문을 분리 표시. 메모리 η=-1은 사용자 가정임을 명확히 표시. 문헌 범위 중간값과 사용자 수정값을 구분. Node32 및 문헌/가정 전환·출처·360px 브라우저 검증 통과.
- 기업 탭: 한 기업·제품·원산지의 단가·물량·변동원가·고정비·관세·흡수율·계약·경쟁 가정. 제품 손익·손익분기·원가 한도·흡수율 비교.
- 국가 결과는 연결 시점 스냅샷을 다시 계산해 원산지 평균 가격·물량을 적용. 수동 반응과 중복 적용하지 않으며 품목/관세 불일치 거부. 실제 기업 예측으로 표시하지 않음.
- 기업 source·HTS·정책 검토일·국가 입력·회계 잔차 JSON 저장, 이전 결과 보호, 원문 링크, 가상 기업 초기값. 신규 모델12 + 기존32 =44개 통과. 전용 회사 브라우저 검증 포함.
