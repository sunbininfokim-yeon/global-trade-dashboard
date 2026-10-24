# 2026-10-24 Claude: 운영 DB 쓰는 workflow를 main 전용으로 제한

#706(Codex 감사, `2026-10-24-codex-mailing-archive-audit.md` 3절) 후속.

## 변경
운영 `SUPABASE_SERVICE_ROLE_KEY`를 쓰는 job에 `if: github.ref == 'refs/heads/main'`을 추가했다.
브랜치에서 수동 실행하면 job이 건너뛰어진다(skipped).

| workflow | job | 상태 |
|---|---|---|
| `sync-congress.yml` | sync-government-policy | 활성 |
| `sync-indonesia-policy.yml` | sync | 활성 |
| `rollover-congress.yml` | rollover | 활성. dry-run 기본값과 `allow_purge` 승인은 그대로 |
| `sync-policy-reference-monthly.yml` | sync-reference-data | 꺼져 있음. 다시 켜도 main 전용 |
| `commodity-digest.yml` | send-digest | 꺼져 있음. **다시 켜지 말 것** |

`commodity_reports.yml`의 보관 단계와 `deploy-mailing.yml`은 이미 main 조건이 있고, 보관 스크립트는 #706에서 자체 검사도 한다.

## 남은 일 (사용자가 GitHub 설정에서 직접)
이 조건은 실수 방지용이다. 브랜치 코드가 조건 자체를 지우는 경우까지 막으려면:
1. Settings → Environments에 `production`을 만들고, Deployment branches를 `main`만 허용한다.
2. `SUPABASE_SERVICE_ROLE_KEY` 같은 운영 키를 repository secret에서 그 environment secret으로 옮긴다. repository에 같은 키가 남아 있으면 소용없다.
3. 위 job들에 `environment: production`을 붙인다. Claude가 별도 PR로 처리한다. **2번보다 먼저 붙이면 안 된다.**
