# 인수인계 2026-10-21 — claude (석탄 기준가격: 인도네시아 HBA + 세계은행 월평균)

## 한 일 (브랜치 `claude/coal-reference-prices`)

사용자 요청: "HBA II(4,100 GAR)와 세계은행 CMO-Historical-Data-Monthly(호주·남아공 석탄 월별)를 석탄에 가격으로 붙여줄 수 있어?"

- `New for anti/scripts/coal_prices/collect.py` (표준 라이브러리만): 두 출처를 따로 읽어 `public/data/coal_prices_v1.json`에 쓴다. 숫자는 출처에서 읽은 것만, 읽지 못한 출처는 마지막 정상 데이터를 `status: error` + 사유로 표시(추정값 없음).
- `New for anti/coal-prices.js` + `trade.js` 훅 2줄 + `index.html`: 연료탄(`thermal_coal`) 세계 화면에서 선물가 카드 바로 아래에 "석탄 기준가격 · 선물가 아님" 카드. 국가 화면은 인도네시아=HBA, 호주=호주산, 남아공=남아공산만.
- `.github/workflows/coal_prices_refresh.yml`: 매일 01:23 UTC 수집(변동이 있을 때만 커밋; 실패한 출처가 있으면 스냅샷 저장 뒤 실패로 표시).
- `tools/ops/feed_probe.py`: 페이지 본문 맥락(`context`)과 PDF 앞부분(`pdf_text`) 출력 옵션 추가.

## 출처별 사실 (2026-10-21 Actions 러너에서 확인)

- **세계은행**: 안내 페이지(`worldbank.org/en/research/commodity-markets`)에서 xlsx 링크를 찾는다(주소의 해시가 매달 바뀜). `Monthly Prices` 시트, 헤더 행은 이름으로 찾고(`Coal, South African **`처럼 각주 표시가 붙음), 바로 아래 단위 행이 `($/mt)`가 아니면 거부. 2026-09: 호주 147.1, 남아공 98.2 $/mt. 한 달 정도 늦게 나온다.
- **HBA — ESDM 보도자료는 쓰지 않는다**: 보도자료 한 문단에 등급 4개가 있고(8월 상반기 HBA II = 65.48달러로 사용자 말과 일치) 읽히지만, **ESDM 뉴스 목록은 날짜순이 아니고 검색·피드가 없으며 모든 반월 고시가 보도자료로 올라오지도 않는다**(8월 상반기 한 건뿐). 사이트 방화벽은 짧은 시간에 여러 요청을 보내면 403 "Request Rejected"로 막는다.
- **HBA — JDIH 장관결정문 PDF(채택)**: `jdih.esdm.go.id/dokumen/peraturan?DokumenSearch[jenis_peraturan]=176`(Keputusan Menteri ESDM)이 최신순 5건씩 나오고, 각 행의 "Dokumen" 링크(`dokumen/download?id=2026kmesdm{번호}k.pdf`)가 PDF다. 제목에 "Harga Batubara Acuan"이 든 행만 골라 PDF를 받아 `pypdf`로 읽으면 끝의 **부록 II**에 `Batubara (6.322 GAR) USD/ton 122,52` … 표가 있다(384.K = 10월 전반: 122.52 / 90.60 / 63.45 / 43.84). PDF는 스캔본 + 텍스트 층이라 OCR 잡음이 있어(예: `12 26%`) 파서는 엄격하다: 4개 열량 등급이 기대값(6,322/5,300/4,100/3,400)이어야 하고 가격이 등급 순으로 내려가야 하며, 부록 제목의 반월이 결정문의 "mulai berlaku pada tanggal" 시행일과 맞아야 채택한다. 하나라도 어긋나면 그 결정문은 건너뛰고 `skipped`에 이름과 사유를 남긴다. 직전 반월 대비 변화는 두 발표값에서 계산한다(보도 기사 값을 베끼지 않음).
- **게재 시차**: 결정문은 시행일 후 며칠 뒤 JDIH에 올라온다. 2026-10-21 현재 10월 후반(401.K)은 404, 가장 최신은 10월 전반. 화면은 "적용 기간이 끝났습니다 — 다음 고시는 아직 공개 문서에 올라오지 않았습니다"를 표시한다.
- **스캔본 결정문**: 2026-10-22 기준 JDIH 결정문 중 8건(227·253·274·285·312·336·348·364.K)은 글자 층이 없는 이미지 스캔(텍스트 7자)이라 거부되고 `refused`에 남는다. 읽으려면 OCR 단계가 필요하고, 표 숫자 오독 위험 때문에 이번에는 넣지 않았다. 읽힌 반월: 5월 전반(179.K), 5월 후반(204.K), 10월 전반(384.K) + ESDM 보도자료로 읽었던 8월 전반.
- **결정문 번호**는 목록의 제목에서 읽는다(본문은 다른 결정문 268.K/2025를 인용한다).
- **광물총국 `minerba.esdm.go.id/harga_acuan`**: "시스템 점검 중" 페이지(2026-10-21). 복구되면 더 빠른 경로가 될 수 있다.

## 남은 것

- 10월 후반 이후 결정문은 JDIH에 올라오는 대로 일일 수집이 자동으로 읽는다. 시차가 길면 광물총국 페이지(복구 시)를 보조 경로로 검토.
- 세계은행 Description 시트에서 시리즈 정의를 읽어 보여 주려 했으나 이번 파일에서는 찾지 못했다(`definition` 없음) — 정의 문구는 하드코딩하지 않았다.
- `trade.js?v=agg-604`, `coal-prices.js?v=1`: `claude/reports-user-feeds`(PR #665)가 `trade.js?v=agg-603`/`style.css?v=agg-604`를 쓰므로, 둘 중 늦게 병합되는 쪽에서 `index.html` 줄이 충돌하면 버전만 올려 해결.
- 병합·배포는 하지 않았다(사용자 확인 대기). 병합하면 `coal_prices_refresh.yml`이 main에서 매일 01:23 UTC에 돈다.
