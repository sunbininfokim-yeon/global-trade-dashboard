let partyChartPromise = null;

// 중국공산당 중앙 주요 직위의 조직 골격. 미국 EOP 조직도와 같은 성격이다 --
// 어떤 부서·판공실이 있는가는 당 조직 구조이지 매일 수집되는 값이 아니므로,
// 파이프라인 자산이 아니라 편집 가능한 콘텐츠 파일로 둔다. 실패하면 null 로
// 떨어지고 chn-org.js 가 모듈에 내장된 같은 골격을 쓴다.
export const loadCnPartyChart = () => {
    if (!partyChartPromise) {
        partyChartPromise = fetch('/public/data/elections_cn_party_v1.json', { cache: 'force-cache' })
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null);
    }
    return partyChartPromise;
};
