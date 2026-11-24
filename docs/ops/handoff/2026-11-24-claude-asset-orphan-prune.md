# 2026-11-24 Claude → 담당 세션: 정적 파일 정리 (Cloudflare 20,000개 한도)

## 한 줄

Cloudflare Workers Free는 버전 하나에 정적 파일을 **20,000개**까지만 올릴 수 있다. 11/24 main에는 20,119개가 있어서 배포가 계속 실패했다.
원인의 대부분은 **현재 어떤 인덱스에서도 가리키지 않는 옛 해시 파일**이다. 갱신할 때마다 새 해시 파일을 쓰면서 이전 파일을 지우지 않았다.
응급조치는 PR #1092다(`.assetsignore`로 `usa_election_state_evidence/` 제외). 여유가 1,200개뿐이라 근본적으로 정리해야 한다.

## 측정 (2026-11-24, origin/main)

인덱스에서 시작해 `.json` 참조를 재귀로 따라간 결과다.

| 폴더 | 파일 | 도달 가능 | 고아(옛 해시) | 생성 코드 / 워크플로 |
|---|---|---|---|---|
| `public/data/usa_election_finance/` | 9,532 | 1,234 | **8,298** | `scripts/election_watch/refresh_candidate_fundraising.py`, `build_board.py`, `refresh_superpac.py` / `us_superpac_refresh.yml` |
| `public/data/commodity_trade_bilateral_v1/parts/` | 7,809 | 641 | **7,168** | `scripts/commodity_trade/build_bilateral.py` / `commodity_trade_refresh.yml`, `commodity_trade_contracts.yml` |
| `public/data/usa_election_state_evidence/` | 1,324 | 50 | **1,274** | `scripts/election_watch/publish_polling_run.py`, `refresh_state_sequence.py` |
| `public/data/usa_superpac/` | 653 | 57 | **596** | `scripts/election_watch/build_superpac.py` / `us_superpac_refresh.yml` |

- 고아 파일은 약 **17,300개**다. 정리하면 정적 파일이 약 3,000개 수준으로 줄어든다.
- 인덱스 파일:
  - `usa_election_finance_index_v1.json`
  - `commodity_trade_bilateral_v1/index.json`
  - `usa_superpac_index_v1.json`
  - `usa_election_state_evidence_index_v1.json`
- 측정 스크립트(그대로 재사용 가능)는 아래 "검증"에 있다.

## 할 일

PR은 하나씩 따로 만든다. 선거 쪽과 무역 쪽은 소유가 다르다.

1. **도달성 확인부터 한다.** 파일명 해시를 브라우저나 다른 코드가 직접 조립하는지 찾는다.
   - 대상: `js/elections/data/*.js`, `trade-monthly.js`, `_worker.js`, `scripts/**`
   - 인덱스 경유가 아닌 참조가 있으면 그 파일도 "살아 있음"에 넣는다.
   - 다른 공개 JSON(예: `elections_board_v1.json`, `usa_election_state_sequence_v1.json`)이 해시 파일을 가리키는지도 `grep -r <hash>`로 확인한다.
2. **생성기 고치기 (근본 해결).** 새 해시 파일을 쓴 뒤 인덱스를 원자적으로 교체하고, 그 다음에 도달 불가 파일을 지운다.
   - 캐시된 옛 인덱스가 잠깐 옛 파일을 찾을 수 있으니, **직전 한 세대는 남긴다.** 예: 이전 인덱스가 가리키던 파일까지만 보존.
   - 삭제는 그 폴더 안에서만 한다. `git add --all -- <폴더>`가 삭제를 커밋하는지 워크플로에서 확인한다(`us_superpac_refresh.yml` 96행은 이미 `--all`).
3. **1회 정리.** 지금 쌓인 고아 파일을 지우는 PR을 만든다. 폴더별로 지운 개수와 남은 개수를 PR 본문에 적는다.
4. **재발 방지.** `guard` 또는 `validate` 검사에 다음 두 단계를 추가한다.
   - "배포 대상 정적 파일 수 ≤ 18,000" 경고. `.assetsignore`를 반영해서 센다.
   - 폴더별 고아 파일 0개 검사.
5. PR #1092의 `.assetsignore` 제외는 정리 뒤에도 그대로 둬도 된다. 브라우저가 쓰지 않는 자료라서다. 되돌릴지는 사용자가 판단한다.

## 하지 말 것

- 인덱스가 가리키는 파일 삭제, 데이터 내용 변경, 생성 로직의 수치 변경
- 한 PR에 선거와 무역을 섞는 것
- 전국 생성 JSON을 텍스트로 병합하는 것 (CLAUDE.md 선거 규칙)
- `main` 직접 push, force-push. 병합과 배포는 사용자가 확정한다.
- 유료 플랜 전환. 무료 자료·무료 플랜 원칙이다.

## 검증

정리 전후로 다음을 확인한다.

```bash
cd "New for anti"
python3 - <<'EOF'
import json, os, glob
def refs(o, acc):
    if isinstance(o, dict): [refs(v, acc) for v in o.values()]
    elif isinstance(o, list): [refs(v, acc) for v in o]
    elif isinstance(o, str) and o.endswith('.json'): acc.add(o)
for d, idx in [('usa_election_finance', 'usa_election_finance_index_v1.json'),
               ('commodity_trade_bilateral_v1', 'commodity_trade_bilateral_v1/index.json'),
               ('usa_superpac', 'usa_superpac_index_v1.json'),
               ('usa_election_state_evidence', 'usa_election_state_evidence_index_v1.json')]:
    files = set(glob.glob(f'public/data/{d}/**/*.json', recursive=True))
    base = {os.path.basename(f): f for f in files}
    seen, todo = set(), ['public/data/' + idx]
    while todo:
        p = todo.pop()
        if p in seen or not os.path.exists(p): continue
        seen.add(p); acc = set()
        refs(json.load(open(p)), acc)
        todo += [base[os.path.basename(r)] for r in acc if os.path.basename(r) in base]
    print(d, 'files', len(files), 'reachable', len(seen & files), 'orphan', len(files - seen))
EOF
# 배포 대상 개수 (assetsignore 반영은 wrangler deploy --dry-run 출력으로 확인)
```

- 화면 확인 대상:
  - 선거 화면: 미국 주별 자금·Super PAC·후보 대결
  - 무역 월간 화면: 품목별 상대국 분해
- 위 화면에서 콘솔 404가 없어야 한다. 배포 워크플로가 성공해야 한다.
- 결과는 `docs/ops/handoff/<날짜>-<에이전트>-asset-prune.md`로 넘긴다.
