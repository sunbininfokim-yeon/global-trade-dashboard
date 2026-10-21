# 인도네시아 미완료 처리와 필리핀 구리 확장 판단

2026-10-20. 사용자의 “미완료 한번 해보고 더 보강 가능한지 아니면 필리핀 구리 등으로 넘어갈지” 요청에 대한 실행·조사 결과다. 인도네시아 DB는 실제 갱신했고 필리핀은 출처·수집 가능성 조사만 했다. 국가 간 데이터를 섞거나 필리핀 운영 스키마·화면을 만들지 않았다.

## 이번에 완료한 작업

| 항목 | 실제 결과 |
|---|---|
| 기존 임베딩 대기 | Gemini `gemini-embedding-001`, 1536차원으로 개요 4·선택 조문 13건 생성·저장 |
| PMK 26/2020 OCR | 기존 공식 PDF를 Apple Vision으로 로컬 처리. 17쪽·21,614자 저장. 표지·정의·공포 쪽을 원본과 대조 |
| OCR 조문·임베딩 | 정의 조문에 적용범위·선택 발췌 2건, 개요·조문 벡터 각 1건 추가 |
| 최종 벡터 상태 | 문서개요 73·선택 조문 26건 저장, 각 대기열 0건 |
| 키워드 검색 | `석탄, 벌크통관`에서 PMK 26/2020과 검토 조문 연결. 총 7개 실 DB 평가 통과 |
| 로컬 의미검색 | `석탄혼합`·`복구보증금` 2개 hybrid 질의에서 기대 문서가 각각 1위로 반환 |

이번 생성 입력은 개요 5개·조문 14개, 총 42,740자다. 기존 전체 벡터를 재생성하지 않았다. 검색용 질의 2개는 별도다. 실제 청구 토큰·원화는 측정하지 않았다. 공개 사이트의 유료 질의 활성화·Secret·배포 설정은 변경하지 않았다.

운영 상태는 문서 73·버전 81·검토 근거 59·효력 근거 41·검토 목록 119개다. 모든 문서의 현행 효력은 계속 `unverified`다. 같은 검토 입력 재실행은 신규 0건이다.

## OCR의 의미와 재실행

PDF 원본: [DJBC PMK 26/2020](https://repository.beacukai.go.id/download/2020/04/97915dbca97493564ef4c9a514192bb4-pmk-no--26-th-2020.pdf). SHA-256 `b2953a4a91648bacb03c745f8e2280f659bf7249283b56926023c47a6b5f185f`.

`ocr-pdf.swift`는 맥의 Apple Vision을 사용하고 PDF를 외부 서비스로 보내지 않는다. 25쪽·180초 제한과 원시 인식 결과를 사용했다. OCR 결과에는 오인식이 있으므로 본문 전체를 수작업 전사 검증한 것으로 표시하지 않는다. DB provenance의 `full_transcription_verified=false`, `body_status=local_ocr_selected_pages_reviewed`, 화면에 제공되는 한국어 `status_note`로 한계를 보존했다. 이번에는 숫자·요율·허용오차를 계산 규칙이나 법적 효력으로 만들지 않았다.

`prepare_ocr.py`는 PDF·OCR 출력 해시·선택 페이지 검토를 요구하고, 문서번호·최종 문서 표식·전체 페이지 누락 여부·본문 길이를 검사한다. 초안·다른 문서·변경된 출력·누락 페이지는 거부한다. DB/AI 호출은 없고 새 비공개 실행 경로에 collection만 만든다. 원문 관측·OCR 본문·임베딩은 별개 단계다.

```sh
swift -module-cache-path /tmp/idn-swift-module-cache scripts/indonesia_policy/ocr-pdf.swift /ABS/RAW_PDF /ABS/ocr.json
# 출력이 바뀌면 자동 재승격하지 않고 해시와 선택 페이지 검토를 다시 수행
python3 scripts/indonesia_policy/prepare_ocr.py --manifest scripts/indonesia_policy/sources-coal-core-20261020.json --document-id idn-pmk-26-2020 --pdf-file /ABS/RAW_PDF --ocr-json /ABS/ocr.json --review-file scripts/indonesia_policy/ocr-review-pmk26-20261020.json --output-dir /ABS/NEW_PRIVATE_RUN
```

## 인도네시아에서 남은 중요한 보강

| 우선순위 | 남은 대상 | 판단 |
|---|---|---|
| 1 | DMO 267/2022·399/2023 | 공식 목록 관계·대체 BPHN 메타데이터 확인. 본문 링크는 점검 중인 ESDM을 가리켜 보류 |
| 1 | 판매 기준가격 268/2025·144/2026·363/2026 | [공식 목록의 개정 이력](https://jdih.esdm.go.id/dokumen/view?id=2601) 확인, 원문 미확보. 이번에 후보 3건 추가. 오래된 기본 산식을 현재 산식으로 제공하지 않음 |
| 1 | 환경 PP 22/2021 | 현재 DB는 메타데이터만 있음. 환경 승인·AMDAL·폐수/폐기물 판단에 필요한 본문·부속서 보강 가치가 큼 |
| 1 | 25/2018·7/2020의 잔존 조문·개정 연결 | 일부 폐지된 규정이므로 전체를 역사 자료로 치부할 수 없음. [25/2018 공식 목록](https://peraturan.bpk.go.id/Details/142233/permen-esdm-no-25-tahun-2018)에 추가 개정 이력 존재 |
| 사업별 | 광구·사업 소재지의 지방 조례·산림·운송·항만·실제 허가 | 일반 법규를 더 쌓는 것보다 특정 지역·사업 단위의 적용성 검토가 유용 |

석탄 우선 검토 후보 29개 중 잘림 없이 추출한 본문 15·메타데이터 1·미저장 13개다. 이는 전국 전체 법규의 수집률이 아니다. 미저장에는 이미 폐지된 10/2023·15/2024·259/2016·PP26/2022 같은 역사적 관계 대상도 있다. 원문이 없다고 규제가 없는 것은 아니며, 이 후보들을 모두 현행 필수 공백으로 세지도 않는다.

니켈·팜유·바이오연료의 우선 후보 공백도 남아 있다. 따라서 인도네시아 전체 구축 완료라고 부르지 않는다. 석탄 검색·핵심 운영 근거는 사용 가능한 부분 검토 단계다.

## 필리핀 구리: 실제 확인한 수집 가능성

기계 판독 기록은 [출처 감사 JSON](philippines-copper-source-audit-20261020.json)에 있다.

| 출처 | 직접 확인한 상태 | 용도 |
|---|---|---|
| [대법원 RA 7942](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/3617) | HTTP 200, 조문 포함 HTML 약 8.2만 자 | 광업 허가·개발·환경·사업자 검토의 기본 틀 |
| [대법원 RA 8371](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/2562) | HTTP 200, HTML 74,681자 | 원주민·조상영역 권리 및 동의 관련 검토 |
| [대법원 RA 12253](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/99695) | HTTP 200, HTML 23,683자 | 대규모 금속광업 세제의 2025년 개편 |
| [DAO 2010-21 등록](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/10/67619) | HTTP 200이지만 본문 없이 등록 메타데이터 552자. 다른 등록본도 메타데이터만 있음 | 광업법 IRR 원문 별도 확보 필요 |
| [DENR DAO 2021-40](https://apidb.denr.gov.ph/infores/uploads/DAO-2021-40.pdf) | HTTP 200, 실제 PDF 9쪽 확보, 텍스트 추출 공백 | 구리 등 노천채굴 관련 규정. OCR·후속 변경 검토 필요 |
| [RA 12253 세제 IRR](https://www.dof.gov.ph/wp-content/uploads/2025/12/MINING-IRR.pdf) | 웹 도구에서 본문 확인, 로컬 HTTP 403 | 실제 수집기 관점에서는 미확보로 보존 |
| MGB Region X | HTTP 403 | 지역 포털의 차단·개별 어댑터 검증 필요 |

### 공식 목록의 JSON 검색은 가능

대법원 [Republic Acts 목록](https://elibrary.judiciary.gov.ph/republic_acts)의 실제 JavaScript에서 DataTables POST endpoint와 동일 세션의 공개 폼 토큰 사용을 확인했다. 그 흐름을 그대로 사용한 RA 7942 조회는 strict JSON·HTTP 200, `recordsFiltered=1`, 정확한 문서 링크를 반환했다. 당시 `recordsTotal=12468`은 전체 Republic Acts 목록이며 구리 규정 수가 아니다.

입력 없이 GET하면 PHP Notice가 JSON 앞에 붙는다. GET 파라미터만으로도 해결되지 않아 그 응답을 정상 목록으로 승인하지 않았다. 공식 페이지의 POST·세션·토큰 흐름으로 성공했다. 공개 제품용 API 계약이나 장기 안정성을 보증하는 endpoint는 아니므로 세션 갱신·JSON 스키마·페이지 범위·관측 시각·누락 및 재개 검증이 필요하다. DENR·MGB·지방 조례까지 이 목록 하나로 수집할 수 있다는 뜻도 아니다.

## 권장 결정

**인도네시아는 현재 검색·근거를 유지하고 중요 공백을 추적하면서, 필리핀 구리는 중앙 규정 10–15건의 별도 파일럿으로 확장하는 것을 권한다.** 인도네시아 전수 완성을 기다리기보다 수집 가능한 중앙 원문에서 새 국가의 법적 위험 검색 가치를 검증할 수 있다. ESDM 점검 화면에 반복 요청하거나 기존 문서를 재임베딩하는 데 비용을 쓰는 효익은 낮다.

필리핀 첫 범위는 구리 광업 허가·외국인 투자/계약 유형·2025년 세제·환경 승인/복구·원주민 동의·노천채굴 규정이다. 그 다음 실제 후보 사업 소재지 하나를 골라 지방 조례·구역·허가를 대조한다. 전국 모든 지방을 동시에 모으거나 중앙 규정만으로 지역 적용을 단정하지 않는다.

구현을 시작할 때는 별도 `policy_phl` 스키마·`phl-*` ID·전용 RPC·기관별 출처 허용 목록을 사용한다. 인도네시아의 `.go.id` 제한을 전역으로 풀지 않고 미국·인도네시아 검색과 자동 UNION/fallback을 만들지 않는다. 문서·조문·시행/개폐·적용범위·출처실패를 분리한 계약은 재사용할 수 있다. 이번에는 필리핀 스키마·검색·임베딩을 실행하지 않았다.

## 검증·배포 상태

Python 34개·Node 18개·소유권 규칙 14개 통과. 실 DB 키워드 평가 7개 및 로컬 hybrid 2개 통과. OCR·벡터·근거는 운영 반영했고 코드·조사 문서는 PR #648에 추가한다. 공유 UI·Worker·워크플로·메일·예약 변경과 병합·배포는 없다. Claude 배포 후 사이트 검색을 별도 확인해야 한다.
