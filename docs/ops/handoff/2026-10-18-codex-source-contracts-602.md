# #602 B01–B07 원천 계약 교정 — Claude 인수

작업: COMMODITY-SOURCE-602. 브랜치: `codex/commodity-source-contracts-602-recovered`.
UI 수정 #608과 별개다. UI·Worker·wrangler·workflow·Secrets는 변경하지 않았다.
학습 데이터·모델·계수·평가를 만들지 않았다. 병합·배포·운영 수집 실행은 하지 않았다.

## 교정 범위

| 항목 | 변경 | 검증 경계 |
|---|---|---|
| B01 | ERS 현재 월 E열의 값·연도만 읽음, D열 대체 제거 | 현재/비교 연도·결측·명시적 0·시트 제목 fallback 회귀시험 |
| B02 | JODI 하위제품을 전체 석유제품으로 저장하지 않음 | GASDIES 90개 분류 교정, 값 보존 |
| B03 | JODI primary/secondary의 같은 파일명 캐시 충돌 차단 | URL 식별·SHA256·길이 검사·중단 전송·같은 길이 변조 시험 |
| B04 | 노르웨이 HS 세번 완전성 확인, 중량·금액 독립 | 부분합은 진단만, 미지원 단위 세번 누락 시 총계 금지 |
| B05 | 한국 중량 결측 시 금액 보존 | XML 고정 입력 시험; 현재 환경 키 미연결로 실호출 미검증 |
| B06 | 브라질 니켈광/매트/금속 분리, 결측 중량 전파 | 고정 CSV 시험; 대용량 공식 브라질 원본 재대조는 미실시 |
| B07 | 함유 구리와 광석 순중량 비교·부분합 차단 | kg 환산 자체는 보존하되 함유 구리의 비교/순위 자격은 false |

추가 원천 의미 교정: `TOTCRUDE`는 원유+NGL+기타이므로 `crude_ngl_other`로
37개를 이동했다. `TOTPRODS` 총합도 HS2710과 같다고 주장하지 않는다.
니켈 매트·금속 및 JODI 하위제품은 `supplemental_commodities`에 보존하며
새 화면 메뉴를 만든 것은 아니다.

## 기존 공개 파일 교정

`repair_source_scopes.py`로 결정론적으로 생성했다. 원본 월별 파일 SHA256:
`e529a22e3217f424581fc903b2da291e48def8c902011e7e9c26cb16dd912287`.

- GASDIES 90개 + TOTCRUDE 37개 = 127개 재분류.
- 전체 1,872개 관측의 보고국·출처·원천 상품·월·단위·값 multiset 완전 일치.
- `generated_at` 보존, 두 번째 교정 결과 무변경(idempotent).
- Cochilco 12개는 측정 기준 메타데이터만 변경. 수치 자체는 그대로다.
- `source_scope_repair.is_source_refresh=false`. 수집 최신성 개선을 뜻하지 않는다.
- 현재 원천에서 달라진 값은 이 교정에 섞어 덮어쓰지 않는다.

## 원천 재대조의 한계

10월 17일 이전 실행에서 완전한 JODI 파일 4개를 확보해 839개를 대조했다.
815개 값 일치, 24개 현재 원천 값 차이가 있었고 재분류 후 잘못된 상품 버킷은 0개였다.
동일 실행에서 ERS 원본 E열의 기존 36개 값이 일치했다. SSB는 2026-06 수출 HS2709
한 건을 제어 조회해 세번 2/2, 6,949,078,498 kg / 37,211,007,639 NOK를 확인했다.
이는 전 국가·전 원천 재대조 완료가 아니다.

임시 작업 폴더 소실 후 10월 18일 패치를 실행 기록에서 복구했다. 위 과거 실행 결과를
새 실행으로 위장하지 않는다. 현재 코드 시험은 다시 실행했으며, 현재 확보한 원천의
새 대조 증빙은 아래 검증 기록에 분리해 둔다. 10월 18일 ERS 재다운로드는 DNS 실패
2회로 미완료다. 한국의 기존 서비스키/중계 환경도 이 로컬 프로세스에는 미연결이다.
키를 공개 파일·PR·채팅에 재기입하지 말고 기존 Secrets/환경 연결로 해결한다.

## Claude 소비자 확인 사항 (#608)

1. HS 코드/commodity ID가 같다는 이유만으로 비교하지 않는다. 원천 상품 범위와
   `measurement_basis`가 같아야 하고 `normalized.comparable_across_reporters`가
   false이면 함유 구리 등을 광석의 kg 비율·순위에 사용하지 않는다.
2. `comparison_policy.cross_reporter_numeric_comparison=not_allowed`와
   `requires_same_product_scope=true`를 준수한다. 숫자 환산 성공은 비교 허가가 아니다.
3. `supplemental_commodities`는 보존된 별도 원천 상품이다. GASDIES를 다시
   petroleum_products 전체로 되돌리거나 TOTCRUDE를 HS2709로 복귀시키지 않는다.
4. SSB의 NOK/한국의 USD fallback은 물량이 아니다. 중량을 0으로 대체하지 않는다.
5. source-contract PR과 #608 병합 후 소비자 통합시험·배포 확인을 별도로 한다.

## 검증 기록

- Python commodity: 190개 통과(신규 source-contract 41개 포함).
- JavaScript Comtrade/gateway/loader: 60개 통과.
- 소유권 회귀시험: 13개 통과. UI·Worker·workflow 변경 없음.
- `validate_release.py`: pass, JODI 839개 상품 분류 검사, 변환계수 관측/잘못된 질량 환산 0.
- 실제 데이터 보존·멱등성 검사 통과. `git diff --check` 통과.
- 10월 18일 공식 JODI CSV 4개를 다시 확보했다. 각 응답 범위·전체 바이트·원천
  ETag 안정성을 확인하고 SHA256을 기록했다. 원본 CSV/캐시는 커밋하지 않았다.
  `New for anti/scripts/commodity_trade/audits/jodi_capture_2026-10-18.json` 참조.
- 현재 원천 81,531개 수출 키와 동일 원단위 대조: JODI 815개 일치,
  24개 현재 원천 값 차이, 모호한 키 0개, 상품 버킷 불일치 0개.
  `audits/source_reconciliation_2026-10-18.json`에 해당 24개와 미공급 ERS 36개를
  분리 기록했다. 총 review_items 60개를 모두 오류라고 해석하면 안 된다.
- 대조 대상 교정 JSON SHA256:
  `34a55dd9d1b75bffa94a2f8aecd4cb6646cc681ba74cdfc67a253016f59846ae`.
  공식 원천 개정 차이 24개는 보존했으며 이번 PR에서 수치 갱신/배포하지 않는다.

## 병합 후 별도 운영 확인

기존 PR 검토·병합·배포 승인 절차를 따른다. 인증 및 스케줄 성공은 이 PR의
고정 입력 시험이나 코드 병합만으로 입증되지 않는다. 한국 실호출, 브라질 원본 전체 대조,
24개 원천 개정 차이의 처리, JODI 캐시 갱신 주기는 남은 검증 항목이다.
