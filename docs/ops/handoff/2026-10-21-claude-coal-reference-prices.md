# 인수인계 2026-10-21 — claude (석탄 기준가격: 인도네시아 HBA + 세계은행 월평균)

## 한 일 (브랜치 `claude/coal-reference-prices`)

사용자 요청: "HBA II(4,100 GAR)와 세계은행 CMO-Historical-Data-Monthly(호주·남아공 석탄 월별)를 석탄에 가격으로 붙여줄 수 있어?"

- `New for anti/scripts/coal_prices/collect.py` (표준 라이브러리만): 두 출처를 따로 읽어 `public/data/coal_prices_v1.json`에 쓴다. 숫자는 출처에서 읽은 것만, 읽지 못한 출처는 마지막 정상 데이터를 `status: error` + 사유로 표시(추정값 없음).
- `New for anti/coal-prices.js` + `trade.js` 훅 2줄 + `index.html`: 연료탄(`thermal_coal`) 세계 화면에서 선물가 카드 바로 아래에 "석탄 기준가격 · 선물가 아님" 카드. 국가 화면은 인도네시아=HBA, 호주=호주산, 남아공=남아공산만.
- `.github/workflows/coal_prices_refresh.yml`: 매일 01:23 UTC 수집(변동이 있을 때만 커밋; 실패한 출처가 있으면 스냅샷 저장 뒤 실패로 표시).
- `tools/ops/feed_probe.py`: 페이지 본문 맥락(`context`)과 PDF 앞부분(`pdf_text`) 출력 옵션 추가.

## 출처별 사실 (2026-10-21 Actions 러너에서 확인)

- **세계은행**: 안내 페이지(`worldbank.org/en/research/commodity-markets`)에서 xlsx 링크를 찾는다(주소의 해시가 매달 바뀜). `Monthly Prices` 시트, 헤더 행은 이름으로 찾고(`Coal, South African **`처럼 각주 표시가 붙음), 바로 아래 단위 행이 `($/mt)`가 아니면 거부. 2026-09: 호주 147.1, 남아공 98.2 $/mt. 한 달 정도 늦게 나온다.
- **HBA (ESDM 보도자료)**: 보도자료 한 문단에 등급 4개(HBA 6,322 / HBA I 5,300 / HBA II 4,100 / HBA III 3,400 GAR)가 있다(8월 상반기 HBA II = 65.48달러로 사용자 말과 일치). 그러나 **ESDM 뉴스 목록은 날짜순이 아니고 검색·피드가 없으며, 모든 반월 고시가 보도자료로 올라오지도 않는다.** 수집된 것은 8월 상반기 한 건뿐. 사이트의 방화벽은 짧은 시간에 여러 요청을 보내면 403 "Request Rejected"로 막는다(순차 + 2초 간격으로 해결).
- **광물총국 `minerba.esdm.go.id/harga_acuan`**: "시스템 점검 중" 페이지(2026-10-21).
- **JDIH(`jdih.esdm.go.id`)**: 결정문 PDF를 `dokumen/download?id=2026kmesdm{번호}k.pdf`로 직접 내려받을 수 있고 `pypdf`로 텍스트가 읽힌다(번호 179 = 5월 전반 결정문, 8쪽). 번호 384(10월 전반)는 3MB라 스캔본일 가능성, 401(10월 후반)은 아직 404(올라오는 데 시차). 목록은 `dokumen/peraturan?DokumenSearch[jenis_peraturan]=176`(Keputusan Menteri ESDM).

## 남은 것

- HBA의 최신 고시를 얻는 안정적인 경로(JDIH 결정문 PDF의 표 파싱, 또는 광물총국이 복구되면 그쪽). 그 전까지 HBA 행은 마지막으로 읽은 고시를 날짜와 함께 보여주고 24일이 지나면 "오래된 값" 표시.
- 세계은행 Description 시트에서 시리즈 정의를 읽어 보여 주려 했으나 이번 파일에서는 찾지 못했다(`definition` 없음) — 정의 문구는 하드코딩하지 않았다.
- `trade.js?v=agg-604`, `coal-prices.js?v=1`: `claude/reports-user-feeds`(PR #665)가 `trade.js?v=agg-603`/`style.css?v=agg-604`를 쓰므로 둘 중 늦게 병합되는 쪽에서 `index.html` 줄 충돌 시 버전만 올려 해결.
- 병합·배포는 하지 않았다(사용자 확인 대기).
