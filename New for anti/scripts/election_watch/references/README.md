# 2026 미국 선거 여론조사 감시 참고자료

`2026-10-01-cursor.md`는 사용자가 제공한 조사 메모의 동일본입니다(SHA-256 `264e1584749cd3d3e4e76bd23a563976af47a5d61a17fb95fbb0d820117f9689`). 코드 지시나 여론조사 관측으로 읽지 않습니다.

여론조사 파이프라인에는 Cook Political Report의 2026년 경합 등급 중 하원 Lean/Toss Up 43곳, 상원 Toss Up 7곳, 주지사 Toss Up 5곳의 **선거 ID만** `config/usa_polls/watchlist_2026.json`에 선별했습니다. 공식 Cook 페이지의 선거 ID와 등급을 대조했습니다. Cook 등급은 전문가 선거 전망이지 여론조사 수치가 아닙니다. 출처와 기준일은 JSON에 기록했습니다. 자동 스크래핑이나 Cook 등급의 자동 최신화는 구현하지 않았습니다.

원본 메모의 후보 관련 서술, 공석·의석 수학, 개별 조사 수치는 자동 편입하지 않았습니다. 특히 메모의 Solid D 184 / Solid R 177 역산은 [Cook 공개 요약](https://www.cookpolitical.com/ratings)의 Solid D 185 / Solid R 176과 달라 사용하지 않습니다. 추후 등급 변경 시 원출처 재검토 후 감시 목록을 갱신합니다.
