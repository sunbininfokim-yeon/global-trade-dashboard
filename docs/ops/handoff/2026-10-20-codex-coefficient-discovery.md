# co/efficient automatic release discovery/extraction — 2026-10-20

User authorized automatic discovery expansion after NE integration. Current workspace reused sequentially because disk quota blocked new worktrees: `/Users/yeoninair/Documents/해운 데이터/us-ne-research-integration-20261020`, current branch `codex/poll-coefficient-html-20261020`. Packet-free base11c74877d, prerequisite #644. NE changes remain committed/pushed on their original branch / #647 and were not reset, amended, or mixed into this shared branch. Other users' checkouts and source dossiers were read only. Our failed new checkout was removed; only unmodified copies in our worktree were sparse-excluded. Do not switch another agent's checkout.

## Implementation

`poll_coefficient_html.py` implements explicit state-owned opt-in contracts. It reads the publisher's public release index, selects exactly one same-host state link with a full release day, and extracts the ordinary statewide named-candidate Senate/governor question from the current public table. Dates/sample/mode/precision must agree between header and methodology. Geography must match the existing reviewed race subject; all named candidates and printed party labels must match the existing reviewed roster. Missing/malformed methods, unknown candidates/parties, generic and later forced-pair questions, future dates, nonnumeric percentages, response-total inconsistency, redirects or foreign URLs are held. New field dates produce a new stable wave ID without hand-entering new values. Noncandidate responses remain separately disclosed; no invented remainder or rounding to100.

The adapter dispatches through the existing `merge_html_tables` → `bind_html_reviews` → `normalize` → history/7/14-day path. No new parallel public JSON, UI, workflow or deployed endpoint. New automated releases are reference-only pending question-order/commissioner context review; the adapter does not approve all future pollster output as voting signals. Each source receives parsed/retained/reference/eligible counts and failure reasons. One source's acquisition/parsing failure does not block successful sources. Prior wave values/dates remain on outage; a same-wave revised answer/sample/publication snapshot is held for review, not silently replaced. Later API duplicates/conflicts use the existing same-wave guard.

## Verification

77 focused polling/primary regressions pass, including10 synthetic adapter cases. Synthetic fixtures never become published observations. Existing CNU parser tests remain included. Actual saved NE original HTML replay (not a network collection) extracted Sept28–30, n1113, Ricketts45/Osborn40/Marvin2/Richards1/Conboy1/undecided11, exactly matching the source; proposed NE opt-in packet validates. Election JS114, ownership14 and deploy-chain42 checks pass. No need to repeat unchanged finance suites: previous NE finance33 passed and this shared diff does not edit finance code or assets. Full discover suite is not claimed passed.

The public index was independently opened via the web tool and labels Nebraska October2,2026 (more precise than the standalone article's October2026). That date is accepted only when the live index and article are both fetched successfully with consistent field dates; it is not substituted from review/capture date. Index URL: https://battlegrounds.coefficient.org/ ; article https://battlegrounds.coefficient.org/ne/ .

## Live limitations and next integration

Initial default urllib returned403; after the approval review became available, the declared production client fetched the index and NE article successfully without challenge bypass. Actual live extraction yielded one Senate observation with published2026-10-02, field2026-09-28–30, n1113 and all five named candidates, exactly matching the primary table. Two live document hashes and check times are saved at /private/tmp/coefficient-live-ne-receipts.json. The real index also contains undated map links to the same page; discovery now selects only the uniquely dated release link and tests include the duplicate map links. GitHub runner network collection has not been dispatched. No API key is required.

No active source contract is installed in this packet-free common diff; activation belongs to the NE input PR. NE Senate opt-in is separately prepared at `/private/tmp/coefficient-ne-activation.patch`, based on #647's current packet. It must be applied/reviewed on that state branch after the common feature is available, and collected successfully before claiming live automated delivery. The existing NE governor page has the Lidstorm/Lindstrom identity discrepancy: do not enable that question by guessing the name. Other states need their own reviewed contracts and independent PRs. New publisher page layouts/URLs require parser/contract review.

NE data PR #647 must not be rebased onto another state. If this common PR is published, move #647's prerequisite base to that packet-free branch and add the NE-only opt-in change separately; preserve original API/document receipts. Never merge generated JSON. Existing scheduled collection will call the adapter once that contract is integrated; no schedule/deploy changes required. Main merge, deployment, workflow dispatch and resets remain unperformed. Common implementation is committed on its dedicated branch; remote PR/CI state must be checked separately. This handoff does not prove merge or deployment.

## 2026-10-21 main 동기화

- 최신 게시 main `96af0fca70f0e9b598e7d0f909a8205e19426420`과 #644를 합쳤다. TASKS 충돌은 co/efficient 행과 수집 복구 행을 모두 보존했다. 전국 생성물의 수동 병합·재수집·게시 없음.
- 합본 검증에서 가상 HTML 문서가 실제 오늘을 검토일로 받아 고정된 10/20 normalize에서 `future_quality_review`가 발생했다. synthetic capture clock만 10/20으로 고정하고 검토일 단언을 추가했다. 운영 수집일이나 future 검증은 변경하지 않았다.
- 최종 집중 검증: co/efficient10 + HTML/원문/복구42 = 52개 통과. #644는 원문/복구/intake35개 통과. 후속 NE 합본 전체 검사 결과는 후속 인수 문서에 기록한다.
- 반영 순서는 #644 → #649 → #647. 추가 병합·배포·workflow dispatch는 하지 않는다.

### 최종 공용 기반

#656의 공용 catalog-clock 회귀 수정을 포함했다. 반영 순서는 #656 → #644 → #649 → NE#647이며 #656/#644 순서는 교환 가능하다. 최종 합본 polling743·별도18(NE5중복)·finance77·선거JS114·ownership14·배포연결42 통과. 다른501선거·원래수집일·focus104·재생멱등 확인. 상세 원문6건 재검토와 미반영 항목은 `2026-10-21-codex-poll-recovery-followup.md`에 기록했다. 추가 병합/배포 없음.
