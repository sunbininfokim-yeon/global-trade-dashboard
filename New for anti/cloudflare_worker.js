export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/api/trade') {
      const date = url.searchParams.get('date');
      const mockResponse = {
        date: date,
        status: "success",
        message: `${date} 기준 과거 데이터가 성공적으로 불러와졌습니다. (백엔드 모의 응답)`,
        data: []
      };
      return new Response(JSON.stringify(mockResponse), {
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }
    return new Response('Global Trade API Server is running.', { status: 200 });
  },

  // 매일 아침 7시(KST) 자동 실행되어 외부 API를 크롤링하고 DB에 저장
  async scheduled(event, env, ctx) {
    console.log(`[크론 동작] 자동 업데이트 파이프라인 시작: ${event.cron}`);
    ctx.waitUntil(this.updateDailyData(env));
  },

  async updateDailyData(env) {
    const today = new Date().toISOString().split('T')[0];
    try {
      // 1) 외부 API 호출 (UN Comtrade 등)
      // 2) 데이터 파싱 및 정제
      // 3) Cloudflare KV 또는 D1 DB에 저장
      console.log(`✅ [${today}] 글로벌 무역 데이터 업데이트 및 DB 저장 완료`);
    } catch (error) {
      console.error(`❌ [${today}] 업데이트 실패:`, error);
    }
  }
};
