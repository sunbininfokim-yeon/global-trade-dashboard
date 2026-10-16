# 인수인계 2026-10-16 — claude (보고서: 새 원자재 창)

## 한 일 (브랜치 `claude/reports-new-commodities`)

- 대시보드에 보크사이트·천연우라늄·우라늄광 메뉴가 생겨(Codex #587/#590) 보고서 창 키(`bauxite`, `uranium`, `uranium_ore`)가 필요했다. `commodities.json`에 추가.
  - 보크사이트는 알루미늄 창에서 뺐다(알루미나는 알루미늄에 남음).
  - 우라늄·우라늄광은 같은 별칭을 쓴다(둘 다 같은 시장 뉴스를 본다).
  - 망간에 "망간광" 별칭 추가.
- 출처 5곳 추가(2026-10-16 Actions 러너 점검, 모두 수집 성공):
  `int_wnn`(World Nuclear News), `int_iaea_topnews`, `ca_cameco_news`, `us_alcoa_press`, `fr_eramet_news`.
  미국 관보 JSON API 검색어에 `uranium`, `bauxite` 추가.
- 테스트 89개 통과(새 창 분류, 모든 출처의 hint·scope·default_country 존재 확인).

## 실제 수집 결과 (브랜치에서 `commodity_reports.yml` 1회)

- 우라늄 6건(WNN 3, 관보 3: NRC 우라늄 광산 재생·ISR 모니터링 등), 우라늄광 6건(동일).
- 보크사이트 0건, 망간 0건, IAEA·Cameco·Alcoa 0건 — 출처는 성공했지만 최근 헤드라인에 우라늄·보크사이트 단어나 시장어가 없었다. 오류가 아니라 보수적 태깅의 결과.
- 오탐 없음(관보의 흑연·크롬 건은 기존 창).

## 남은 것

- 쓸 수 없던 곳: NRC RSS(404), DOE RSS(404), WNA 보도자료(404), EIA 우라늄(403), IAEA 보도자료 목록·South32(Cloudflare 403), Hydro·Rio Tinto(목록에서 기사 링크 못 뽑음).
- Kazatomprom 미디어 목록은 열리지만 링크가 러시아어 슬러그라 제목을 못 만든다. 영문 제목 경로가 필요.
- 보크사이트·망간광은 여전히 건수가 적다. 기니·자메이카 광업부, IMnI는 피드 없음.
- WNN·Cameco·Alcoa·Eramet은 기업/산업 매체이지 정부기관이 아니다(출처 notes에 명시).
