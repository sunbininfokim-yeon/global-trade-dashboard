# 미국 선거 당일 밤 운영 (2026-11-03)

화면은 2026-11-04 12:00 UTC(미 동부 07:00)부터 선거 후 모드로 바뀝니다. 그때부터는
여론조사·Cook 가정을 쓰지 않고 **공식 인증 결과**만 칠합니다. 인증은 주마다 2~4주 걸리므로
그 사이는 **언론 당선 선언(비공식)** 으로 채웁니다.

## 우선순위

1. 주 공식 인증 결과 `scripts/election_watch/config/usa_polls/results_2026.json` (기존 계약)
2. 언론 당선 선언 `public/data/usa_election_media_calls_v1.json` (이 문서)
3. 둘 다 없으면 미정(선거 후) / 여론조사·Cook 전망(선거 전)

선언이 있으면 선거 전(12:00 UTC 전)이어도 해당 선거는 선언대로 칠합니다.
화면 표기: 카드 "언론 당선 선언 N곳 포함 · 비공식(주 인증 전)", 선거별 "AP 당선 선언 · 비공식",
하원 지도는 같은 정당색을 조금 옅게.

## 기록 방법

```bash
cd "New for anti/scripts/election_watch"
python3 add_media_call.py USA:PA:governor "Josh Shapiro" DEM --by AP --at 2026-11-04T01:12Z --url https://apnews.com/...
python3 add_media_call.py USA:GA:senate --runoff --by AP --at ... --url ...     # 결선 투표로
python3 add_media_call.py USA:AZ:senate --retract --by AP --at ... --url ...    # 선언 철회
```

- 도구가 파일 전체를 검증합니다: 2026 선거 목록에 있는 race_id, 정당 DEM/REP/IND, 첫 투표 마감
  (2026-11-03 23:00 UTC) 이후·현재 이전 시각, https 원문, 공식 인증과 충돌 없음. 하나라도 틀리면 저장 안 함.
- **원문 링크는 실제 선언 기사/결과 페이지**. 개표 선두·출구조사·예측 모델은 넣지 않습니다.
- 한 선거에 한 줄. 같은 race_id를 다시 넣으면 덮어씁니다(철회·결선 전환 포함).
- 여러 언론이 선언하면 `--by AP --by NBC`.
- 알래스카·메인은 순위선택투표라 선언이 며칠 늦을 수 있습니다. 조지아·루이지애나는 결선 가능.

## 반영 경로

`public/data/` 파일이라 **main 병합 = 배포**(별도 발행 워크플로 불필요). 몇 건씩 묶어 PR → CI
(`test_poll_media_calls`) 통과 → 병합. 주별 packet 규칙과 무관한 단일 파일입니다.

## 누가

- 선언 입력: Claude 또는 Codex 누구든. 같은 시간대에 둘이 같은 파일을 고치면 충돌하므로
  한 명이 입력하고 다른 쪽은 원문 대조만 합니다.
- 공식 인증 결과(`results_2026.json`)는 기존대로 원문·인증일 검토 후 추가합니다.
