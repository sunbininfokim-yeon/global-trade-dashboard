# HANDOFF → Claude — 미국 백악관/EOP 월간 Actions

**날짜:** 2026-09-11  
**소유:** 데이터·추출 = Cursor (`scripts/election_watch/**`) · `.github/workflows/**` = Claude  
**요청:** 선빈. 백악관 수석급 명부를 매월 공식 페이지에서 갱신하고 GitHub Actions에 연결.

Cursor `cursor/*` 브랜치는 `ownership_guard.yml` 때문에 `.github/workflows/*`를 넣으면 PR이 실패한다. 아래 YAML을 **Claude 브랜치에서 루트로 복사**하면 월간 잡이 돈다.

## 할 일 (Claude)

1. `New for anti/scripts/election_watch/ci/elections_eop_monthly.yml` 내용을  
   **`.github/workflows/elections_eop_monthly.yml`** 로 그대로 복사 (내용 변경 없이).
2. `main`에 merge. 이후 매월 1일 10:00 UTC cron + `workflow_dispatch`.
3. UI는 아직 `executive_live.core` + `cabinet`만 읽는다. 수석·위원회는  
   `executive_live.white_house` 에 있다. 카드가 필요하면 그 객체를 읽으면 된다.  
   `app.js` 하드코딩 국가 목록은 만들지 말 것.

## 잡이 하는 일

```
python3 -m election_watch.extract_usa_eop --fetch --merge-tier12 --write-report
python3 build_board.py --no-betting
python3 build_ui_manifest.py
```

공식 출처만 인명을 덮어쓴다.

- `whitehouse.gov/administration/` — 대통령·부통령
- `whitehouse.gov/administration/cabinet/` — 각료 + OMB
- WHO 연례 직원보고서 PDF — 비서실장, NSA, NEC/DPC 실장, 대변인 등 Assistant to the President

자동으로 **넣지 않는 것:** 부통령 비서실장, CEQ 직무대행, CEA(공식 페이지 없을 때). 언론 보도로 빈칸을 채우지 않는다.

## 커밋되는 파일

- `scripts/election_watch/config/extracted/usa_eop.json`
- `scripts/election_watch/config/extracted/tier12_executives.json`
- `scripts/election_watch/config/extracted/usa_eop_refresh_report_v1.json`
- `public/data/elections_board_v1.json`
- `public/data/elections_ui_manifest_v1.json`

`raw/**` PDF/HTML은 gitignore. 커밋하지 말 것.

## 검증

```bash
cd "New for anti/scripts/election_watch"
python3 -m unittest discover -s tests -v
python3 -m election_watch.extract_usa_eop --merge-tier12 --write-report
```

보드 `countries[USA].executive_live.white_house.assistants_to_the_president` 에서 NSA가 Marco A. Rubio 인지 확인. Caleb Ruger가 남아 있으면 실패.
