# 2026-10-02 Claude → Cursor: 수출통제 주간 확인 정기 예약

## 목적

매주 한 번, 수출통제 카탈로그(`New for anti/public/data/export_controls/`)의 **확인 작업**을
Cursor 가 정기 예약으로 돌리고, 그 결과를 Claude 가 바로 판단·반영할 수 있는 형식으로 남긴다.
Claude 는 결과 파일만 읽고 카탈로그 수정 PR 과 화면 반영을 한다.

## 언제

매주 월요일 12:00 KST (GitHub Actions 주간 점검 11:00 KST 이후).
입력은 그 주 결과표 PR(`cursor/export-controls-weekly-survey`, 본문 = `surveys/reports/latest.md`).

## Cursor 가 할 일 (매주)

1. 최신 main 을 받고 `surveys/reports/latest.md` 를 읽는다.
2. 결과표의 세 칸을 원문으로 확인한다.
   - **① 기한**: 지난·임박 행마다 발표 기관 원문에서 연장·해제·변경 여부를 찾는다.
   - **② 링크**: 「깨짐」은 대체 원문을 찾는다. 「자동 확인 불가」 중 언론 출처는
     정부 원문(고시·결의·공고 PDF)으로 바꿀 수 있는지 찾는다.
   - **③ 후보**: 갱신 후보·신규 후보마다 공고 원문을 열어 단계를 정한다.
3. 아래 형식의 파일 하나를 쓴다. **카탈로그 JSON 은 고치지 않는다** (Claude 가 고친다).
4. `cursor/export-controls-review-<YYYY-Www>` 브랜치로 PR 을 연다. 제목:
   `수출통제 주간 확인 <YYYY-Www>`. main push 금지.

## 결과 파일 형식

경로: `New for anti/scripts/export_controls/surveys/review/<YYYY-Www>.md`

```markdown
# 수출통제 주간 확인 2026-W41

## 요약
- 바꿀 행 N건 · 새 행 N건 · 그대로 N건 · 판단 보류 N건

## 판단 (행 하나에 한 블록)

### rus-fuel-products — 바꿈
- 판단: 기간 연장 | 해제 | 단계 변경 | 출처 교체 | 그대로 | 보류
- 단계: prohibited → prohibited        # 금지/제한/검토/해제 중 무엇인지가 핵심
- 조치 유형: ban                      # ban / quota / duty / licensing / state_trading / levy / min_price
- 기간: since 2026-08 · until 2027-03-31 (원문 날짜 그대로)
- 원문: <정부 원문 URL>  (기관 · 문서 번호 · 발표일)
- 근거 인용: "..." (원문 한 문장, 원어 그대로, 30단어 이내)
- 신뢰도: high(정부 원문) | medium(공식 보도자료·통신사) | low
- 바꿀 필드: until, url, verified_at, needs_reconfirm=false

### ind-onions — 새 행
- (위와 같은 항목 + country / iso / category / commodities / HS 코드가 원문에 있으면)

## 보류와 이유
- <행 id>: 원문을 못 찾음 / 원문끼리 충돌 / 접속 차단 — 무엇을 시도했는지

## 열린 질문 갱신
- 닫힌 질문, 새 질문
```

## 규칙

- **원문이 없으면 high 금지.** 언론만 있으면 medium, 추정이면 보류.
- **수출세를 금지로 올리지 않는다.** 금지 = 수출 자체를 막음, 제한 = 쿼터·허가·수출세·최저수출가·국영 창구,
  검토 = 논의·경고 단계.
- HS 코드는 원문에 적힌 것만. 추측 금지.
- 날짜는 원문 그대로 (YYYY-MM-DD). "곧", "연말" 같은 표현은 보류로.
- 반도체·무기 등 원자재가 아닌 기술 통제와 개인·기업 제재는 다루지 않는다.
- 유료 데이터·로그인 필요한 소스 금지.
- 한 주에 다 못 하면 한 것만 쓰고 나머지는 「보류」에 남긴다. 빈 주에도 파일은 쓴다(“변경 없음”).

## Claude 가 받아서 하는 일

결과 파일의 「바꿈」「새 행」을 카탈로그 모듈 파일(agri/energy/minerals.json)에 반영하고
`python3 -m export_controls.validate` 통과 후 PR, 화면 확인, 배포 전 설명.

## 참고

- 결과표 생성: `New for anti/scripts/export_controls/report.py` (README 「주간 결과표」)
- 공고 수집원: `New for anti/scripts/commodity_reports/config/sources.json` 중 `"board": "export_controls"`
- 카탈로그 계약: `New for anti/scripts/export_controls/README.md`, `validate.py`
