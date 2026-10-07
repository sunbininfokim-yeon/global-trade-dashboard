import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

test('archive and collector requests support secret keys and legacy JWTs', async (t) => {
  const previous = { url: process.env.SUPABASE_URL, key: process.env.SUPABASE_SERVICE_ROLE_KEY };
  t.after(() => {
    for (const [name, value] of [['SUPABASE_URL', previous.url], ['SUPABASE_SERVICE_ROLE_KEY', previous.key]]) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
  });
  process.env.SUPABASE_URL = 'https://example.test';
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'sb_secret_test_only';
  const { supabaseUpsert } = require('../../../scripts/lib/sync-utils.js');
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    return new Response(null, { status: 204 });
  });
  await supabaseUpsert('mailing_reports', [{ report_id: 'test' }], 'report_id');
  assert.equal(requests[0].options.headers.apikey, 'sb_secret_test_only');
  assert.equal(requests[0].options.headers.Authorization, undefined);
  process.env.SUPABASE_SERVICE_ROLE_KEY = 'eyJ.test.legacy';
  await supabaseUpsert('mailing_reports', [{ report_id: 'test' }], 'report_id');
  assert.equal(requests[1].options.headers.Authorization, 'Bearer eyJ.test.legacy');
  assert.equal(requests[1].options.headers.apikey, 'eyJ.test.legacy');
});
