# 공개 텍스트 조사·갱신 플로우

`build_board.py`는 이미 검토된 config/extracted 팩을 보드로 조립한다. 웹을 다시 읽어 사실을 자동으로 바꾸는 스크립트가 아니다. 원문 수집과 데이터 반영은 아래 두 단계로 분리한다.

1. 승인된 공식 페이지를 캐시한다.

```bash
cd "New for anti/scripts/election_watch"
python3 capture_sources.py --country IDN
python3 capture_sources.py --country IDN --fetch
```

첫 명령은 쓰기 없는 대상 확인이다. 두 번째 명령은 `raw/<iso3>/`에 원문과 `*.meta.json` 출처 사이드카를 저장한다. 기존 캐시는 의도적으로 덮어쓰지 않으며, 재수집이 필요할 때만 `--overwrite`를 사용한다.

2. 원문을 검토한 뒤 검증된 사실만 반영한다.

- 날짜·의석·득표·공식 명단은 선관위·의회·정부의 공개 원문으로 확인한다.
- 불확실한 인물·계파·야권 재편은 `confidence`와 출처를 남기고, 확인되지 않으면 `null`/`불명`으로 둔다.
- 요약·추정은 원문을 대체하지 않는다. LLM은 문서 구조화 보조만 하고 새 숫자·명단을 발명하지 않는다.
- 변경은 해당 `profiles/*.json`, `calendars/*.json`, 필요 시 `config/extracted/*.json`에 넣고 `as_of`·source URL을 함께 갱신한다.

3. 보드를 재생성하고 변경 범위를 확인한다.

```bash
python3 build_board.py --no-betting --print-stats
python3 build_calendar_master.py
```

현재 수집 대상은 보드에 새로 연결한 IDN·ZAF·NGA·IRN이다. 기존 1·2급 국가는 해당 국가의 기존 extractor와 `official_sources.json`을 우선 사용한다.

## 반복 갱신 실행기

```bash
# 대상과 예정 작업만 확인
python3 run_refresh_cycle.py --dry-run

# 공식 원문을 새로 캐시하고 검토 보고서 생성
python3 run_refresh_cycle.py --fetch --overwrite-raw

# 검토·config 반영이 끝난 뒤 파생 파일까지 재생성
python3 run_refresh_cycle.py --build-derived
```

`run_refresh_cycle.py`는 `config/extracted/source_refresh_report_v1.json`에 성공·실패·검토 대상을 남긴다. 403·로그인·봇 차단은 우회하지 않고 `not_captured_or_fetch_failed`로 남겨 대체 공개소스나 수동 검토 대상으로 넘긴다.
