'use strict';
// Explicit operator import. Never runs when collecting or on module load.
const fs = require('node:fs');
const { loadEnvFile } = require('../lib/load-env');
const { request, SCHEMA } = require('./client.cjs');
async function main() {
  const args = process.argv.slice(2);
  const file = args[0];
  const envIndex = args.indexOf('--env-file');
  if (!file || envIndex < 0 || !args[envIndex + 1]) throw Error('collection.json --env-file PATH [--write]');
  loadEnvFile(args[envIndex + 1]);
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const taxonomy = require('./taxonomy.json');
  if (!Array.isArray(data.documents) || data.documents.length > 100) throw Error('Invalid bounded collection');
  const crypto = require('node:crypto');
  for (const d of data.documents) {
    if (d.country_code !== 'IDN' || d.legal_status !== 'unverified' ||
      crypto.createHash('sha256').update(d.text_content).digest('hex') !== d.content_hash) throw Error('Invalid source hash/country/status');
    // Curated retrieval tags survive historical-manifest reimports. No legal conclusion.
    d.topics = [...new Set([...d.topics, ...(taxonomy[d.document_id]?.tags || [])])].sort();
  }
  let changed = 0;
  if (args.includes('--write')) for (const d of data.documents) {
    const result = await request('rpc/idn_store_document', {method:'POST',body:{p_document:d}});
    changed += Number(result === true);
    console.log(JSON.stringify({id:d.document_id, new_version:result}));
  }
  if (args.includes('--write')) {
    const checks = [...data.documents.map(d=>({document_id:d.document_id,checked_at:data.checked_at,source_url:d.source_url,outcome:'collected',detail:d.content_kind+': '+(d.body_status||'metadata_only')})),
      ...(data.failures||[]).map(d=>({document_id:d.document_id,checked_at:data.checked_at,source_url:d.url,outcome:'failed',detail:d.error.slice(0,1000)}))];
    // Save each immutable check through a schema-local, idempotent function.
    for (const check of checks) await request('rpc/idn_store_source_check',{method:'POST',body:{p_check:check}});
  }
  console.log(JSON.stringify({schema:SCHEMA,mode:args.includes('--write')?'write':'preview',documents:data.documents.length,new_versions:changed,source_failures:data.failures?.length||0}));
}
main().catch(err=>{console.error(err.message);process.exitCode=1;});
