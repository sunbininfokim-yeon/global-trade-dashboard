# 인수인계 2026-10-16 — claude (보고서 새 창 검증 후 수정)

PR #593(`claude/reports-new-commodities`) 검증에서 확정된 집계 오류를 같은 브랜치에서 고쳤다. main 병합·배포는 하지 않았다.

## 고친 것

- **보크사이트 ↔ 알루미늄 이중 집계**: `commodities.json` 알루미늄에 `not_when` 추가.
  `aluminium ore(s)`·`aluminum ore(s)`·`铝土矿`·`알루미늄광`이 알루미늄 창에도 걸리던 문제
  (`铝土矿` 안의 `铝`, `알루미늄광` 안의 `알루미늄`이 부분 문자열로 걸림). 알루미나는 그대로 알루미늄.
- **우라늄 쌍 창 절단**: `tag_report`의 상품 3개 제한이 설정 순서로 잘라서, 우라늄+두 상품을 말하는
  기사는 `uranium`만 남고 `uranium_ore`가 빠졌다. 별칭 목록이 같은 창은 한 칸으로 센다
  (`CommodityTagger.slots` / `cap()`). 넘치면 둘이 같이 빠진다.
- **국가 귀속**
  - SEN·BFA·GNB 추가. FAS "Senegal: Cotton" 보고서가 Mali로만 귀속되던 문제
    (이번 PR에서 MLI만 들어가며 생김). 이제 SEN·BFA·MLI.
  - `Gulf of Guinea`, (Papua 없이) `New Guinea`는 기니가 아니다 → 국가 없음.
  - `New Mexico`는 지우던 방식에서 USA 지역으로 바꿨다. 지우면 미국까지 사라져
    WNN·NucNet(기본 국가 없음)의 뉴멕시코 기사가 `_global`로 갔다. 같은 원리로 `New England`
    (EIA 휘발유 표가 영국에 붙던 기존 문제)도 USA 지역.
- **로컬 시간대 의존**: `feeds.parse_date`가 시간대 없는 날짜(관보 `publication_date`)를
  기계의 로컬 시간으로 읽어, 서울에서 빌드하면 하루 당겨졌다. UTC로 고정.
  테스트 `FederalRegisterTests`가 KST에서만 실패하던 원인.

테스트: 100개(이전 92개; 인수인계 문서의 89개는 당시 수치). KST·UTC·뉴욕 모두 통과.

## 손대지 않은 것 (판단 필요)

- 우라늄·우라늄광 창의 `enriched uranium`·`haleu` 별칭: 현재 9건 중 5건이 농축·연료 기사
  (Urenco 농축, Framatome 연료, Bluecore UF6 등). "천연우라늄 / 광석·정광" 라벨과 맞는지 사용자 확인 필요.
- 출처가 다른 같은 기사(Bluecore: WNN+NucNet, NRC ISR 규칙: 관보+NRC 뉴스)는 `_dedupe`가
  URL·같은 출처 제목만 봐서 2건으로 센다.
- `/api/commodity-reports`의 음수 `limit`(slice가 끝에서 자름), 스냅샷 폴백의 소문자 국가코드 미정규화 — 기존 코드.
- 전부 대문자 `NIGER`는 대소문자 구분 별칭이라 안 잡힌다.
