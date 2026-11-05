# 2026-11-05 — Codex: AZ 공식 개표 출처 등록

## 상태와 의존성

- 담당: 애리조나(AZ)만. 연방 하원 9곳·주지사 1곳. 2026 상원 선거를 생성하지 않는다.
- worktree: `/Users/yeoninair/Documents/해운 데이터/us-AZ-official-results-20261105`
- branch: `codex/az-official-results-20261105`
- 시작 main: `7e67d8b026dbd1514d49778b341903491a546525`.
- 실제 기반: **#885** `codex/us-official-results-20261105`, `85dc98907d524a34697153ac3cb5222fb2d386ed`.
- 공용 기반을 먼저 병합하고 이 PR의 base를 main으로 변경해 검증한다. 미병합 타주 PR에 쌓지 않았다.
- 이 PR은 AZ 출처 JSON·AZ 전용 검사·이 인수 문서만 추가한다. 공용 코드·전국 생성물·polling packet·workflow·UI는 변경하지 않는다.
- 다른 주 작업은 시작하지 않았다. main 병합·배포·운영 workflow dispatch·재설정 클릭 없음.

## 신규 수집과 원래 기준일

- 공식 안내: <https://azsos.gov/press> (11/04 안내 확인, 11/05 웹 읽기 도구는 403).
- 실제 신규 요청 URL: <https://app.enhancedvoting.com/cdn/results/Arizona/export-110326GeneralElection.json>
- 원문 `electionDate=2026-11-03`, `results.name=Arizona` 확인.
- 원문 발행: `2026-11-05T03:50:47.2427526Z`.
- 다운로드 완료: `2026-11-05T12:15:54.070421+00:00`.
- 원문 SHA-256: `28830cab092badf79d30a0d3297ff36b0baa1a4c6e51c224f112790744c60de3` (72,592,544 bytes).
- 실제 요청은 한 번만 했다. 기반 PR의 축약 fixture와 로컬 preview 재생성은 신규 요청이 아니다.
- 상원·주지사·하원 여론조사와 선거자금 입력·기존 수집일은 수정하지 않았다. 여기서는 개표 관측만 연결한다.

## 연결 결과

원문에는 해당 하원 9곳과 주지사 후보별 득표가 모두 있다. 보드의 AZ 10 race ID에 정확히 대응한다. 카운티 15곳의 `localResults`에서 선거별 투표구 수를 합산한다. 카운티 수를 투표구 수로 표시하지 않고 투표구 보고 비중을 예상 총투표 대비 개표율로 해석하지 않는다.

예시(위 원문 기준, **당선 선언 아님**):

| 선거 | 관측 상위 후보 | 보고된 투표구 |
|---|---|---|
| 주지사 | Katie Hobbs 1,235,630표 / Andy Biggs 949,421표 | 1,384 / 1,762 |
| 하원 1구 | Amish Shah 167,807표 / Thomas “Jay” Feely IV 145,313표 | 206 / 210 |
| 하원 6구 | JoAnna Mendoza 163,197표 / Juan Ciscomani 138,235표 | 97 / 248 |

실제 기타 후보·기명투표 합계를 분모에 보존한다. 후보 source ID는 FEC ID가 아니다. 공식 인증·언론 선언·지도 승자색·의석 집계는 바꾸지 않는다.

## 자동 수집과 배포

- 출처 경로: `config/official_results_sources/2026/AZ.json`.
- #885의 `load_config()`가 이를 읽으므로 기존 `official_results_refresh.yml` 수정은 필요 없다.
- 기존 cron 설정은 20분이며 AZ 안내의 최소 2분 요청 간격보다 느리다. 직접 HTTP 실패 후 브라우저로 즉시 재요청하지 않게 `render_fallback=false`다.
- **아직 운영 반영 아님:** #885 → 이 PR 순서로 main에 반영된 뒤 정기 수집이 새로 받는다. workflow 예약 실행 간격은 실제로 지연될 수 있다.
- 기존 UI의 `officialResults` 계약을 그대로 쓰므로 추가 UI 수정 없이 개표 줄을 표시할 수 있다. 실제 공개 파일·브라우저 확인은 발행 후 필요하다.
- 실패 시 직전 AZ 결과와 원래 발행·수집 시각을 보존하고 갱신 지연으로 남긴다. 최초 수집부터 실패하면 자료 없음이며 0표로 만들지 않는다.

## 검증

아래 명령을 기반과 AZ 입력을 합친 전용 worktree에서 실행한다.

```sh
cd 'New for anti/scripts/election_watch'
python3 -m unittest tests.test_official_results tests.test_poll_az_official_results -q
python3 check_state_packet_changes.py --base-ref 85dc98907d524a34697153ac3cb5222fb2d386ed --head-ref HEAD --branch codex/az-official-results-20261105
```

검증 결과:

- 공식 개표·주별 범위·AZ 연결 검사 총 27개 통과.
- 실제 73 MB 원문 전체를 다시 읽어 기존 공개 보드의 race ID와 대조했으며 AZ 10선거가 `ok`다. 축약 fixture를 읽은 결과와 10선거의 모든 파싱 값이 같다.
- 비게시 로컬 재생성: `/tmp/us-results-preview-20261105/AZ.json`. 원래 다운로드 완료 시각으로 재생성해 새 수집으로 위장하지 않았다.
- 원문 발행 시각·원래 수집 시각·원문 SHA-256이 그대로 보존됐다.
- 시작 main 대비 UI·workflow·전국 public/data 파일 변경 없음 확인.
- 커밋 후 주별 입력 범위 검사도 실행한다. GitHub CI·공개 사이트 갱신은 별도 확인이 필요하다.

API 키가 필요하지 않았으며 유료 자료나 AP 비공개 피드를 사용하지 않았다.
