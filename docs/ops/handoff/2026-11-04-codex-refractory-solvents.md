# T51 · 조선내화·후성 용제 반덤핑 품목 추가

- Checkout: `/Users/yeoninair/Documents/refractory-solvents-ad-20261104`
- Branch: `codex/refractory-solvents-ad-20261104`
- Base main: `8c0939a6d`. 이전 #585의 병합을 GitHub에서 재확인 후 새 main에서 시작.
- 구현/공식 근거/남은 확인: [내화재·용제 문서](../../refractory-solvents-ad-20261104.md).
- 기업2·품목7 추가: 조선내화(마그카본/고알루미나/부정형), 후성코퍼레이션(EA/MEK/DMF/아세톤).
- 선별 연결: 중국산 마그카본→미국 AD/CVD, 중국산 EA→한국 조사, 한국산 아세톤→미국. 역할/수입국/원산지/제품 경계를 유지. 신규 예치율은 전부 null, 자동 계산 미반영.
- 기존 미국 AD5 사건과 자동감시13사건·월1회 예약 보존. 자동수집 범위 확대 또는 KTC 수집은 미구현.
- Node135·소유권15, 실제 mount 산업/기업/원산지 전환 검사 통과. 실브라우저·운영 화면 미검증.
- .github/workflows·_worker·앱 공용 UI·DB·메일·운영 배포 미변경. 이전 checkout 사용자 .venv 삭제 등 미접촉.
- Claude 검토: 신규 산업/기업 배치, 수입국별 관련 사건의 문구, 원산지 변경 컨트롤, 한국 사례가 미국 예치 계산으로 연결되지 않는지 확인. 사용자 승인 후 병합/배포.
