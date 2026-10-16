# 검토된 후보 별칭의 여론조사 요약 누락 수정

Codex. 사용자의 “하원14일2곳” 점검·진행 지시에 따른 UI 계산 오류 수정. checkout /Users/yeoninair/Documents/해운 데이터/us-poll-summary-aliases-20261016, branch codex/poll-summary-aliases-20261016, base main77f52560. 주별 packet을 포함하지 않는 독립 UI PR.

MN01 명부의 Jacob "Jake" Johnson과 API의 Jake Johnson은 백엔드 candidates.canonical_name으로 같은 후보임이 검토돼 있었다. pollRaceAssessment만 required_candidates와 원문 답변 이름을 문자열로 직접 비교해, 유효한 문항을 요약/카드의 채택 조사에서 빼고 missing으로 계산했다. 원문 이름은 그대로 표시하면서 같은 레이스의 검토된 canonical_name으로만 대조한다. 별칭이 없는 비슷한 이름·같은 후보 별칭의 중복 답변은 집계하지 않는다.

편입 기준·모집단·기관별 최신 파동·7/14기간·지도 신호·원래 원자료·정당·공식 결과 우선순위는 바꾸지 않는다. 기존 accepted observation이 같은 카드와 요약에서 일관되게 계산되도록 한다.

JS92개(새 회귀2개), ops/소유권16개, 배포연결40workflow 통과. 실제10/16 API 입력과 별도 NY21 검토 packet의 재생성 JSON을 사용한 표시 검사에서 최근14일3지역구=수치상DEM2(CA48/MN01)+보고오차구간겹침1(NY21),GOP0. 이 숫자는 검증 사본의 제한된 확보 범위이며 전국 판세 예측이나 서비스 반영 결과가 아니다. NY21 원문 연결이 없는 main 입력에서는 CA48/MN01만 해당한다.

공용 게시 복구 #598은 별도. NY21 주별 입력도 별도 codex/ny21-primary-review-20261016. 이 PR은 데이터셋·국가 산출물·index.html·style.css·workflow·Worker를 수정하지 않는다. 병합·배포·운영 실행·사용자 전용 재설정 없음. 실제 서비스는 점검 시10/11 데이터였고 localhost8766은 연결되지 않아 그 미리보기 화면의 최종 검증은 하지 못했다.
