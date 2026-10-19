# 인도네시아 우선 원문 5건 복구

후속으로 [기관별 목록 수집·대조](indonesia-policy-catalogue-20261019.md)를 구현했고 새 원문2건을 추가했다. 아래는 이 단계의 이력이다.

2026-10-19. PR #633 후속. 운영 `policy_idn`에 실제 원문과 문서개요 벡터를 반영했다. 코드·목록은 같은 PR의 검토 대상이며 병합·사이트 배포는 Claude 인수 대상이다.

## 운영 결과

| 항목 | 이전 → 확인 결과 |
|---|---|
| 저장 문서 | 64 → 66 |
| 내용 버전 | 69 → 74 |
| 출처 확인 이력 | 129 → 141 |
| 원문·부속서 보유 | 45 → 50 (기존 일부 수집 2건 포함) |
| 메타데이터만 보유 | 19 → 16 |
| 현재 입력과 일치하는 개요 벡터 | 64 → 66 |
| 우선순위 1의 20개 | 원문 8·메타데이터 4·미저장 8 → 원문 13·메타데이터 1·미저장 6 |

원문 공백 12개 중 **5개를 복구**했다. 2개는 새 문서이고 3개는 기존 메타데이터 문서의 본문 보강이다. 새 본문은 모두 잘림 없이 추출되었으며 총 319,272자다. 기존 2개 일부 수집 문서를 완전한 원문으로 승격하지 않았다. 후보 목록 102개 중 36개는 여전히 문서 행이 없다. 현행 효력은 모두 `unverified`다.

## 확보한 원문

| 규정 | 검토 주제 | 공식 재게시 PDF | 추출 문자 |
|---|---|---|---|
| UU3/2020 | 광물·석탄 광업법 개정 | [중앙자바 ESDM](https://ppidnew.esdm.jatengprov.go.id/pdf/regulasi/regulasi-6a11374c428cd.pdf) | 119,787 |
| UU2/2025 | 광업법 제4차 개정 | [중앙자바 ESDM](https://ppidnew.esdm.jatengprov.go.id/pdf/regulasi/regulasi-6a113a8289448.pdf) | 56,728 |
| PP19/2025 | ESDM 비조세 수입·로열티 및 부속서 | [중앙자바 ESDM](https://ppidnew.esdm.jatengprov.go.id/pdf/regulasi/regulasi-6a114366a30c6.pdf) | 78,714 |
| PP78/2010 | 광산 복구·폐광 후 관리 | [방카블리퉁 정부](https://jdih.babelprov.go.id/sites/default/files/produk-hukum/PP%20No.78%20TH%202010.pdf) | 36,867 |
| Permendag15/2026 | 전략자원 석탄 수출 체계 | [관세청](https://repository.beacukai.go.id/peraturan/2026/06/8df49571e74f8ddbb14451f675ea5879-permendag-15-2026.pdf) | 27,176 |

지방정부가 중앙 법령을 재게시했어도 발행기관·관할은 중앙으로 유지했다. 로열티 표의 OCR 수치를 요율 계산 모델이나 확정 의무로 변환하지 않았다. 여러 개정령·경과조치를 합친 현행 통합법이 아니다.

## 자동 식별의 오탐 보정

**UU3/2020:** 인쇄 연도는 2020이지만 추출 계층에는 `NOMOR 3 TAHUN 2O2O`로 나온다. 앞장을 렌더링해 대조하고 이 출처의 식별 문구만 보정했다. 일반적인 O/0 변환이나 원문·추출 텍스트 수정은 없다. 최초 실패 이력도 보존했다.

**Permendag15/2026:** 추출 계층 맨 앞의 `RANCANGAN` 때문에 최초 검사는 초안으로 거부했다. 화면 대조 결과 이 단어는 흰색(RGB FFFFFF) 템플릿 잔여 텍스트로 첫 장에 보이지 않는다. 9쪽에는 제정·공포일 2026-05-29, 관보 2026년347호 및 전자서명 표기가 있고 18쪽은 서명 표기된 부속서 끝이다. [관세청 상세 목록](https://peraturan.beacukai.go.id/regulasi/index.html?page=detail/penerbit/43/1555/peraturan-menteri-perdagangan/mdag-15-2026/peraturan-menteri-perdagangan-nomor-15-tahun-2026-tentang-kebijakan-dan-pengaturan-ekspor-komoditas-sumber-daya-alam-strategis-batubara.html)과 식별을 대조했다. 전자서명의 암호학적 유효성이나 현행 효력은 판정하지 않았다.

수집기의 `pdf_review`는 수동 화면 검토를 **정확한 원본 SHA256에만** 묶는다. 원본이 바뀌면 `invalid_or_stale_pdf_review`로 중단한다. 문서번호·제목 식별도 별도로 통과해야 한다. 일반 초안은 계속 거부하며 추상·미분류 자료를 이 검토로 승격할 수 없다. 이유·페이지·해시는 버전 provenance에 보존한다. 원본과 숨김 텍스트를 삭제하지 않았다.

해시 고정 검토 대상: `6f9bd93a6317abac57f8bbf6459af096e2a4ec79dadbc08cb64f058c5580db2a`.

## 남은 우선 공백 7개

| 규정 | 현재 상태·이번 확인 |
|---|---|
| PermenESDM17/2025 RKAB 기본령 | 미저장. 식별된 공식 PDF 주소가 점검 HTML을 반환했다. 원본 응답 보존. |
| PermenESDM6/2026 RKAB 개정 | 미저장. 공식 목록·첨부 식별은 있지만 ESDM 점검 상태에서 같은 호스트를 반복하지 않았다. |
| PermenESDM3/2026 바이오에너지 ISPO | 미저장. 이전 공식 PDF 연결 시간 초과 미해결. |
| Permenperin38/2025 하류 ISPO | 미저장. 이전 공식 PDF 연결 시간 초과 미해결. |
| Permentan33/2025 농장 ISPO | 미저장. 농업부 대체 공식 목록도403. |
| Permentan5/2025 팜유 지원 | 미저장. 농업부 대체 공식 목록도403. |
| PP22/2021 환경 시행령 | 메타데이터만 보유. 원 부처 DNS 실패, 대체 정부 목록403, 서술라웨시 실제 PDF 다운로드 시간 제한. |

환경 시행령의 서술라웨시 다운로드 응답은 `location.href='../peraturan/2021pp022.pdf'`라는 문자열이었다. JavaScript 실행 없이 이 명시 주소를 확인했다. 일부 다운로드를 완전한 본문으로 저장하지 않았다. 정부 목록의 Drive 첨부파일이나 협회 사본으로 `.go.id` 경계를 완화하지 않았다. 차단을 우회하거나 보도자료·해설을 법령 본체로 대체하지 않았다.

추가 출처 확인12건은 성공·검토 완료5건, 실패 이력7건이다. 실패7회에는 이후 해소한 두 자동 판정 실패도 포함되어 미해결 문서 수와 같지 않다. URL 발견 단계의 목록 조회·403은 별도 `discovery.json`에 남겼다.

## 검색·임베딩·검증

- 실제 DB를 사용하는 API에서 `니켈, 로열티` 모든 조건 검색에 PP19/2025, `석탄, 광산복구`에 PP78/2010, `석탄, 수출`에 Permendag15/2026이 포함된다. 당시 총 결과는 각각6·14·13개다. 유료 질의 없이 키워드·동의어 경로로 검사했다.
- 상세 API의 UU3/2020과 Permendag15/2026은 `official_text`와 각각119,787·27,176자를 반환한다. 운영 사이트 배포 확인을 뜻하지 않는다.
- Gemini는 달라진 개요 **5개·17,905자**만 처리했다(4개14,507자+1개3,398자). 전체319,272자 번역·모든 조문 임베딩이 아니다. 청구 토큰·금액은 측정하지 않았다.
- 현재 개요 벡터66개, 개요/선택조문 대기0개다. 기존 선택조문 벡터12개와 근거24개를 유지했다. 새 원문의 조문·적용성 근거는 별도 검토가 필요하다.
- Python 수집 검사17개, Node DB/API/분리/벡터 검사18개, 소유권 검사14개 통과. 해시 변경 시 검토 거부, 일반 초안·추상/미분류 승격 거부, 문서 식별 유지, 원문 보존을 포함한다.
- 같은 결과 재적용 시 새 버전0개이며 DB는66문서·74버전·141출처 확인으로 유지된다. 기존 버전은 삭제하지 않았다.

## 보관·인수

비공개 루트는 `/Users/yeoninair/Documents/policy-downloads/indonesia-20261019/`다. PDF·본문·벡터는 Git에 넣지 않았다.

| 경로 | 내용 |
|---|---|
| `priority-recovery-1/` | PP78 성공, UU3 대체 주소·PP22 실패 |
| `priority-jateng/` | UU2·PP19 성공, UU3 최초 식별 실패, PDF·앞장 렌더 |
| `priority-uu3-reviewed-cache/` | 같은 원본·관측 시각의 UU3 식별 검토 import |
| `priority-secondary/` | PP22 리다이렉트, Permendag15 최초 거부, PDF·1/9/18쪽 렌더 |
| `priority-coal-export-reviewed-cache/` | 재다운로드 없이 같은 PDF를 검토한 수출 규정 import |
| `priority-environment/`, `priority-rkab/` | 환경 PDF 시간 제한·RKAB 점검 응답 |
| `priority-discovery*/` | 공식 목록·실제 첨부 주소·목록 해시·실패 |
| `embedding-cache/` | 비공개 벡터 캐시(디렉터리0700/파일0600) |

`sources-priority-*-20261019.json`은 이번 성공·실패 경로의 이력이다. 전부 정상 주소가 아니므로 한꺼번에 예약 실행하지 않는다. 기본 `sources.json`은 **확보한5개만** 성공 주소·식별 근거로 교체했고 후보99개를 유지했다. RKAB17/2025는 공백102개와 별도 시도 manifest에 있고 가짜 본문 행을 만들지 않았다.

운영 DDL·공유 Worker·공유 UI·메일·미국 데이터·상시 수집 설정은 바꾸지 않았다. 사이트 배포, 지역/역할 선택 UI, 새 조문·시행일·경과조치 검토 및 남은 공식 원문 회복은 아직 남아 있다.
