# Codex 개장전 일일 실행기 인계

사용자 진행 지시에 따라 수집→고정 추론→불변 기록→표시용 JSON까지 연결.
브랜치 codex/us-kr-preopen-runner-20261104, base main fe741a49e. 기존 #797 병합 확인.

run_us_kr_preopen.py: 정확한61일콜풋 보충(기존 parser 재사용),21일KR가격,2일US가격,
source/US 마감·08:30 cutoff 검사. 실제 수집 종료 뒤 생성시각으로 판정.
first.json 불변, revision 분리, unavailable/replay primary집계 제외.
대상일이 바뀌면 어제 점수를 이월하지 않으며 같은날 실패는 명시적으로 이전예측/실패상태를 표시.

공개 시세 실제 수집+추론 replay 성공, 새 public 자산 발행0.
오프라인 동일입력 계산 및 브라우저3카드/시점/과거재생/참고빈도 검토 완료.
원시가격/개별계약체인/대형일별예측은 PR에서 제외하고 소형 집계·입력해시만 포함.
모델은 학습10/22 cutoff, 생성11/4이며 11/2 시연은 과거재생(전향성적 아님).

Claude 소유 .github/workflows 및 운영 UI는 수정하지 않았다.
구체 패치안: scripts/market_microstructure/integration/us_kr_direction_preopen.proposed.yml.
UI/명령 계약: scripts/market_microstructure/US_KR_PREOPEN_RUNNER.md.
고정 deps: requirements-us-kr-preopen.txt. 일일 job에서는 predict만 호출, train 금지.

main 병합/정기실행 활성화/운영UI 연결/배포는 미완료. PR에서 코드와 패치안을 검토 후 적용.
