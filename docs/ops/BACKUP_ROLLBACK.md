# 백업 · 롤백 절차

전체 코드 점검을 하는 동안은 **손대기 전에 백업, 확인되면 백업 삭제**를 원칙으로 한다.

---

## 현재 백업

```
/Users/yeoninair/Documents/_backup_global-trade_20260805_2352/
  repo.git/        405M   git --mirror (모든 브랜치·태그·히스토리)
  uncommitted/            git으로 복구 불가능한 것만
    cursor_ml-ukraine-yield/   8건
    cursor_ml-vietnam-yield/  10건
```

**총 3.1G.** 점검이 끝나고 배포가 안정되면 통째로 지운다.

### 왜 두 종류인가

`repo.git`은 커밋된 모든 것을 되살린다. 하지만 **커밋 안 된 작업은 git 어디에도 없다.**
2026-08-05 기준 이 디스크에만 존재하던 것:

| 위치 | 내용 | 위험 |
|---|---|---|
| `cursor/ml-vietnam-yield` 워크트리 | `vietnam_mekong_risk_v1.json`, `PANEL_SIGNIFICANCE_KO.md` 등 10건 | 다른 터미널 진행 중 작업 |
| `cursor/ml-ukraine-yield` (메인 체크아웃) | `canada/`, `ukraine/` 폴더, forecast JSON 2개 | 아직 커밋 안 됨 |
| 브랜치 `claude/ui-globe`, `codex/au-cotton-area`, `cursor/ml-{canada,mena,ukraine}-yield` | 원격에 없음 | 디스크 고장 = 소실 |

---

## 롤백

### A. 파일 하나 되돌리기

```bash
cd "/Users/yeoninair/Documents/New for anti"
git checkout -- "New for anti/app.js"
```

### B. 브랜치를 특정 커밋으로

```bash
git reset --hard <커밋해시>
```

### C. 백업에서 전체 복원 (최후 수단)

```bash
cd /Users/yeoninair/Documents
mv "New for anti" "New for anti.broken"
git clone _backup_global-trade_20260805_2352/repo.git "New for anti"
cd "New for anti"
git checkout main
# 미커밋 작업 되돌리기
cp -R ../_backup_global-trade_20260805_2352/uncommitted/<브랜치>/* .
```

### D. 배포 롤백 (Cloudflare)

머지가 잘못됐을 때. **코드보다 이쪽이 급하다** — 사용자가 보는 화면이다.

```bash
# 1) main에서 문제 머지를 되돌린다
git checkout main && git pull
git revert -m 1 <머지커밋>
git push origin main       # → Worker 자동 재배포

# 2) 확인
curl -s https://global-trade-dashboard.sunbin-info-kim.workers.dev/api/ticker?limit=3
```

Cloudflare 대시보드의 **Deployments → Rollback** 으로 직전 버전으로 즉시 되돌릴 수도 있다.
git revert보다 빠르므로 장애 상황에서는 이쪽을 먼저 쓴다.

---

## 새 백업 만들기

```bash
BK="/Users/yeoninair/Documents/_backup_global-trade_$(date +%Y%m%d_%H%M)"
mkdir -p "$BK"
cd "/Users/yeoninair/Documents/New for anti"
git clone --mirror . "$BK/repo.git"
# 미커밋 작업은 워크트리별로 별도 복사 (tools/ops/backup.sh 참고)
```

---

## 점검 중 지켜야 할 것

1. **파괴적 작업 전에는 대상을 먼저 읽는다.**
   2026-08-05에 `모델링 결과/` 508MB를 "git 추적 대상 아님"으로 판단하고 지웠는데,
   실제로는 `cursor/ml-ukraine-yield`와 `claude/ui-deploy` **양쪽에 추적되고 있었다.**
   원인: `git ls-files`가 한글 경로를 `\353\252\250...`로 이스케이프해서 grep이 못 잡았다.
   → 한글 경로를 다룰 때는 반드시 `git -c core.quotepath=false`.

2. **남의 브랜치 워킹트리를 건드리지 않는다.**
   위 삭제로 Cursor 브랜치에 516건의 미커밋 삭제가 생겼다. `git checkout -- .`로 복구했다.
   워크트리를 분리해 두는 이유가 이것이다.

3. **원격에 없는 브랜치를 만들지 않는다.** 커밋 후 바로 push.

4. **삭제는 마지막에.** 지우기 전에 md5로 중복을 증명하고, 그 증명을 기록으로 남긴다.
