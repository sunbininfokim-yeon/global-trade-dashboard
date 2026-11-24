'use strict';

const { supabaseRpc, supabaseGet } = require('./lib/sync-utils');

function assessFreshness(status, lastVectorAt, now, maxIdleHours) {
  const { pending, failed, last_refreshed_at: lastRefreshAt } = status || {};
  if (!Number.isInteger(pending) || pending < 0 || !Number.isInteger(failed) || failed < 0) {
    throw new Error('invalid_queue_counts');
  }
  const refreshTime = lastRefreshAt == null ? null : Date.parse(lastRefreshAt);
  const vectorTime = lastVectorAt == null ? null : Date.parse(lastVectorAt);
  if ((refreshTime !== null && (!Number.isFinite(refreshTime) || refreshTime > now))
    || (vectorTime !== null && (!Number.isFinite(vectorTime) || vectorTime > now))) {
    throw new Error('invalid_index_timestamp');
  }
  const idleMinutes = refreshTime === null ? null : Math.floor((now - refreshTime) / 60000);
  // 변경 사항 없이 벡터를 재사용한 실행도 큐 진행으로 인정한다.
  const stalled = pending > 0 && (refreshTime === null || now - refreshTime >= maxIdleHours * 3600000);
  return {
    status: stalled ? 'stalled' : pending > 0 ? 'progressing' : failed > 0 ? 'failed_only' : 'idle',
    pending,
    failed,
    last_refreshed_at: lastRefreshAt ?? null,
    last_vector_at: lastVectorAt ?? null,
    idle_minutes: idleMinutes,
    max_idle_hours: maxIdleHours,
  };
}

async function run({ rpc = supabaseRpc, get = supabaseGet } = {}) {
  const maxIdleHours = Number(process.env.POLICY_SEARCH_MAX_IDLE_HOURS ?? 8);
  if (!Number.isFinite(maxIdleHours) || maxIdleHours <= 0) throw new Error('invalid_max_idle_hours');
  const [status, passages] = await Promise.all([
    rpc('policy_search_status', {}),
    get('policy_search_passages', {
      select: 'embedded_at', embedding: 'not.is.null', embedded_at: 'not.is.null',
      order: 'embedded_at.desc', limit: '1',
    }),
  ]);
  if (!Array.isArray(passages)) throw new Error('invalid_passage_response');
  return assessFreshness(status, passages[0]?.embedded_at, Date.now(), maxIdleHours);
}

module.exports = { assessFreshness, run };
if (require.main === module) {
  run().then(result => {
    console.log(JSON.stringify(result));
    if (['stalled', 'failed_only'].includes(result.status)) process.exitCode = 2;
  }).catch(() => {
    console.error('Policy search freshness is unavailable. Check the database connection and monitoring configuration.');
    process.exitCode = 1;
  });
}
