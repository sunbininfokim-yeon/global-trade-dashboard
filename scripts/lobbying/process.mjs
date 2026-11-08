import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { embedTexts } from '../indonesia_policy/embeddings.mjs';
import { PROFILE, hash, passages, sourceVersion, extractionSchema, extractionInstruction, validateExtraction, ldaUnits } from './structure.mjs';

const extractionModel = process.env.LOBBYING_EXTRACTION_MODEL || 'gemini-3.8-flash';
const key = process.env.GEMINI_API_KEY || process.env.AI_STUDIO_API_KEY;

async function database(path, body) {
  const secret = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!secret || !process.env.SUPABASE_URL) throw Error('Missing database credentials');
  const headers = { apikey: secret, 'Content-Type': 'application/json' };
  if (secret.startsWith('eyJ')) headers.Authorization = 'Bearer ' + secret;
  const response = await fetch(process.env.SUPABASE_URL.replace(/\/$/, '') + '/rest/v1/' + path, {
    method: body === undefined ? 'GET' : 'POST', headers,
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(90000),
  });
  if (!response.ok) { await response.body?.cancel(); throw Error('Database HTTP ' + response.status); }
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}
const rpc = (name, args = {}) => database('rpc/' + name, args);

async function extract(passage) {
  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${extractionModel}:generateContent`, {
    method: 'POST', headers: { 'x-goog-api-key': key, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: extractionInstruction }] },
      contents: [{ role: 'user', parts: [{ text: passage.content }] }],
      generationConfig: { maxOutputTokens: 12000, responseMimeType: 'application/json', responseJsonSchema: extractionSchema },
    }), signal: AbortSignal.timeout(120000),
  });
  if (!response.ok) { await response.body?.cancel(); throw Error('Extraction provider HTTP ' + response.status); }
  const result = await response.json();
  const candidate = result.candidates?.[0];
  if (candidate?.finishReason !== 'STOP') throw Error('Extraction incomplete: ' + (candidate?.finishReason || 'no candidate'));
  return JSON.parse(candidate.content.parts.filter(part => !part.thought).map(part => part.text || '').join(''));
}

export async function main() {
  if (process.env.GITHUB_ACTIONS === 'true' && process.env.GITHUB_REF !== 'refs/heads/main') throw Error('Production processing is main-only');
  if (!key) throw Error('Missing Gemini credentials');
  const budget = Number(process.env.LOBBYING_PASSAGES_PER_RUN || 30);
  if (!Number.isInteger(budget) || budget < 1 || budget > 200) throw Error('Invalid passage budget');
  const owner = randomUUID();
  let processed = 0, failed = 0, documents = 0;
  const principalCount = await rpc('lobby_refresh_principals', { p_limit: 2000 });
  while (processed < budget && documents < 30) {
    const bytes = await rpc('lobby_database_bytes');
    if (bytes > Number(process.env.LOBBYING_DB_BUDGET_BYTES || 6 * 1024 ** 3)) throw Error('Database storage budget reached');
    const job = await rpc('lobby_claim_structure', { p_owner: owner, p_profile: PROFILE });
    if (!job) break;
    documents++;
    const identity = { p_owner: owner, p_record_id: job.record_id, p_version: job.source_version, p_profile: PROFILE };
    try {
      const [record] = await database('lobby_records?' + new URLSearchParams({
        record_id: 'eq.' + job.record_id, select: 'record_id,source,client_name,country_codes,payload_hash,body_sha256,pages,raw_payload', limit: '1',
      }));
      if (!record || sourceVersion(record) !== job.source_version) throw Error('Source changed after claim');
      const pieces = passages(record);
      let cursor = job.next_ordinal;
      while (cursor < pieces.length && processed < budget) {
        const passage = pieces[cursor];
        const extraction = record.source === 'lda' ? { units: ldaUnits(record, passage) } : await extract(passage);
        const units = record.source === 'lda' ? extraction.units : validateExtraction(extraction, passage);
        const [embedding] = await embedTexts([passage.content], key);
        await rpc('lobby_commit_structure', {
          ...identity,
          p_passage: {
            passage_id: hash([record.record_id, job.source_version, PROFILE, cursor]),
            ordinal: cursor, content: passage.content, locator: passage.locator,
            extraction_model: record.source === 'lda' ? 'official-json' : extractionModel,
            extraction, embedding,
          }, p_units: units,
        });
        processed++; cursor++;
        console.log(JSON.stringify({ record_id: record.record_id, passage: cursor, total_passages: pieces.length, units: units.length }));
      }
      await rpc('lobby_finish_structure', { ...identity, p_complete: cursor === pieces.length, p_error: null });
    } catch (error) {
      const safeError = error.message.slice(0, 200);
      await rpc('lobby_finish_structure', { ...identity, p_complete: false, p_error: safeError });
      console.error(JSON.stringify({ record_id: job.record_id, error: safeError }));
      failed++;
      // Provider and database failures are run-wide. Validation errors hold one
      // document and let subsequent documents make progress without false data.
      if (/HTTP|credentials|storage budget/.test(safeError)) break;
    }
  }
  console.log(JSON.stringify({ profile: PROFILE, principals: principalCount, documents, passages: processed, failed }));
  return failed ? 1 : 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().then(code => { process.exitCode = code; }).catch(error => { console.error(error.message); process.exitCode = 1; });
}
