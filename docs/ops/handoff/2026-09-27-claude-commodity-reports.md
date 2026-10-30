# 인수인계 2026-09-27 — claude (commodity_reports)

## 오늘 들어간 것

- **보고서 패널 페이지 + 12주 아카이브** (#399, 배포됨)
  - 창마다 고정 개수를 두지 않는다. 피드에서 밀려난 발표도 84일 동안 스냅샷에 남는다(`ARCHIVE_DAYS`).
  - `/api/commodity-reports`에 `offset`을 추가했고, 응답에 `total`이 들어간다.
  - 우측 패널은 화면 높이에 맞춰 쪽을 나눈다. 60건씩 받고, 마지막 쪽에서 `›`를 누르면 다음 묶음을 받는다.
  - 프로덕션 스모크: feed-probe run 36286712931. 이 세션에서는 workers.dev에 직접 닿지 않는다.
- **`2026-09-27-claude-commodity-reports-tagging-review.md`(signup 세션 작성) 처리 결과**
  - 사실관계 전부 확인: 소스 44개(꺼진 것 11개), 실패 3건, `ar_bcr` → oil 오탐. 문서의 "133건"은 옛 스냅샷 기준이고 지금은 70건 안팎이다.
  - 출처 옵션 `commodity_scope`를 신설했다. 출처를 목록 안 품목으로만 분류하고, 목록 밖 품목만 잡힌 글은 버린다.
    - `ar_bcr`에 soybeans·corn·wheat로 걸었다.
    - 다른 출처는 스캔해 보니 목록 밖 태깅이 없어서 건드리지 않았다. Silver Institute의 gold, Cochilco의 lithium은 실제로 다루는 품목이다.
  - `jp_meti_en`, `int_spglobal_energy`를 껐다. 35회 빌드 동안 403으로 한 번도 성공하지 못했다.
  - `cn_mofcom_en`을 껐다. 14회 빌드 모두 connection reset이었다.
    - 프로브의 200은 curl_cffi가 Chrome TLS 핸드셰이크를 흉내 내서 받은 것이고, 파이프라인의 urllib로는 재현되지 않는다.
    - 다시 켜려면 TLS를 흉내 내는 fetch 경로가 필요하다. 그 전까지 갈륨·게르마늄 등 수출통제 뉴스는 이 파이프라인에 없다.

## 남은 것

- **MOFCOM:** 수출통제 공고를 다시 받을 경로를 찾아야 한다. 후보는 두 가지다.
  - Worker 프록시(OPEC MOMR과 같은 경로)
  - Actions에서 curl_cffi로 받기
- **OPEC MOMR:** Actions 러너에서는 Cloudflare 403으로 막힌다. 여전히 Worker를 거치는 fetch만 가능성이 있다.
- **첫 실제 다이제스트 메일:** 월요일 08:00 KST 발송분의 결과를 확인해야 한다(Resend 실발송 미검증).
