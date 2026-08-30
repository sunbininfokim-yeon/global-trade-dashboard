'use strict';

// Congress.gov only. We store official summaries and official text links, never bill text.
const crypto = require('node:crypto');
const {
  asArray, checkpointSyncState, createRequestGate, fetchJson, finishSyncRun, firstNonEmpty,
  geminiEmbeddings, geminiModelName, isOptionalEmbeddingError, mapWithConcurrency, parseDateOnly, parseTimestamp, requireEnv, slug,
  startSyncRun, supabaseGet, supabaseInsert, supabaseInsertIgnore, supabasePatch, supabaseRpc, supabaseUpsert,
  updateSyncState, enqueuePolicyItem, takePolicyQueue, markPolicyQueue,
} = require('./lib/sync-utils');

const API_BASE = 'https://api.congress.gov/v3';
const API_KEY = process.env.CONGRESS_API_KEY || process.env.DATA_GOV_API_KEY;
const RESOURCE = 'congress.gov:bills';
const MAX_BILLS = Number(process.env.MAX_BILLS || 200);
const CONCURRENCY = Number(process.env.DETAIL_CONCURRENCY || 2);
const REQUEST_INTERVAL_MS = Number(process.env.CONGRESS_REQUEST_INTERVAL_MS || 850);
const SKIP_EMBEDDINGS = process.env.SKIP_EMBEDDINGS === 'true';
const MAX_EMBEDDINGS = Number(process.env.MAX_EMBEDDINGS || 25);
const DISCOVERY_PAGE_SIZE = Math.min(250, Number(process.env.DISCOVERY_PAGE_SIZE || 250));

if (!API_KEY) throw new Error('Missing CONGRESS_API_KEY (DATA_GOV_API_KEY may be used as fallback).');
requireEnv('SUPABASE_URL');
requireEnv('SUPABASE_SERVICE_ROLE_KEY');

const gate = createRequestGate(REQUEST_INTERVAL_MS); // keeps sustained usage below 5,000 requests/hour
let subscriptions;
const memberCache = new Map();

function apiUrl(path, query = {}) {
  return `${API_BASE}${path}?${new URLSearchParams({ format: 'json', api_key: API_KEY, ...query })}`;
}

async function apiGet(path, query = {}, optional = false) {
  try {
    return await gate(() => fetchJson(apiUrl(path, query), {}, { label: `Congress.gov ${path}`, maxRetries: 6 }));
  } catch (error) {
    if (optional && /HTTP 404/.test(error.message)) return null;
    throw error;
  }
}

function idOf(congress, type, number) { return `${congress}-${String(type).toLowerCase()}-${number}`; }
function officialUrl(ref) { return `https://www.congress.gov/bill/${ref.congress}/${ref.type}/${ref.number}`; }
function asChamber(value) {
  const text = String(value || '').toLowerCase();
  if (text.startsWith('h')) return 'house';
  if (text.startsWith('s')) return 'senate';
  if (text.startsWith('j')) return 'joint';
  if (/president|executive/.test(text)) return 'executive';
  return null;
}
function origin(type) { return String(type).toLowerCase().startsWith('h') ? 'house' : 'senate'; }
function refFrom(item, fallbackCongress) {
  const match = String(item?.url || '').match(/\/bill\/(\d+)\/([^/]+)\/(\d+)/i);
  const congress = Number(firstNonEmpty(item?.congress, match?.[1], fallbackCongress));
  const type = String(firstNonEmpty(item?.type, match?.[2], '')).toLowerCase();
  const number = Number(firstNonEmpty(item?.number, match?.[3]));
  return Number.isInteger(congress) && type && Number.isInteger(number) ? { congress, type, number, listItem: item } : null;
}
function stage(text, billType) {
  const value = String(text || '').toLowerCase();
  if (/became (public|private) law|signed by president|enacted/.test(value)) return 'enacted';
  if (/veto/.test(value)) return 'vetoed';
  if (/failed|rejected|defeated|not agreed to/.test(value)) return 'failed';
  if (/presented to president/.test(value)) return 'presented_to_president';
  if (/conference|resolving differences|disagreeing votes/.test(value)) return 'resolving_differences';
  if (/agreed to by (the )?house and senate|passed both/.test(value)) return 'passed_both_chambers';
  if (/passed house|passed senate/.test(value)) {
    const passed = /passed house/.test(value) ? 'house' : 'senate';
    return passed === origin(billType) ? 'passed_origin_chamber' : 'second_chamber';
  }
  if (/reported|ordered to be reported/.test(value)) return 'reported';
  if (/subcommittee/.test(value)) return 'subcommittee';
  if (/committee/.test(value) && /consider|markup|hear/.test(value)) return 'committee_consideration';
  if (/referred/.test(value)) return 'referred';
  if (/introduced/.test(value)) return 'introduced';
  return 'other';
}
function actionId(billId, action, index) {
  return `ca_${crypto.createHash('sha256').update([billId, action.actionDate, action.actionTime, action.actionCode, action.text, index].join('|')).digest('hex').slice(0, 32)}`;
}
function withoutKey(url) {
  if (!url) return null;
  try { const parsed = new URL(url); parsed.searchParams.delete('api_key'); parsed.searchParams.delete('format'); return parsed.toString(); } catch { return url; }
}
function unique(items) {
  return [...new Map(items.map((item) => [idOf(item.congress, item.type, item.number), item])).values()];
}

async function activeCongress() {
  if (process.env.CONGRESS_NUMBER) return Number(process.env.CONGRESS_NUMBER);
  const body = await apiGet('/congress/current');
  return Number(body?.congress?.number || 119);
}
async function loadState() {
  return (await supabaseGet('data_sync_state', { select: 'cursor,last_successful_at', sync_resource: `eq.${RESOURCE}`, limit: '1' }))?.[0] || null;
}
function lastFour(active) {
  return process.env.CONGRESS_NUMBERS
    ? process.env.CONGRESS_NUMBERS.split(',').map(Number).filter(Number.isInteger)
    : [active];
}
function congressDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) throw new Error(`Invalid Congress.gov datetime: ${value}`);
  // Congress.gov accepts UTC timestamps only to whole-second precision.
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}
function initialWindow(state) {
  if (state?.cursor?.mode === 'incremental' && state.cursor.window_from) return congressDateTime(state.cursor.window_from);
  if (process.env.FROM_DATE_TIME) return congressDateTime(process.env.FROM_DATE_TIME);
  const last = state?.last_successful_at ? new Date(state.last_successful_at).valueOf() : Date.now() - 7 * 86_400_000;
  return congressDateTime(last - 36 * 3_600_000); // overlap prevents boundary misses
}

function shouldBootstrap(state) {
  // Daily runs automatically continue a deliberately-started bootstrap until
  // the stored cursor is complete. This is what makes backfill truly resumable.
  return process.env.SYNC_MODE === 'bootstrap'
    || (state?.cursor?.mode === 'bootstrap' && !state.cursor.complete);
}

async function candidates(congresses, state, bootstrap) {
  const cursor = state?.cursor || {};
  if (bootstrap) {
    const congressIndex = Number(cursor.next_congress_index ?? cursor.page_congress_index ?? 0);
    const offset = Number(cursor.next_offset ?? cursor.page_offset ?? 0);
    const congress = congresses[congressIndex];
    if (!congress) return { refs: [], cursor: { mode: 'bootstrap', congresses, complete: true }, checkpointCursor: null };
    const body = await apiGet(`/bill/${congress}`, { limit: DISCOVERY_PAGE_SIZE, offset });
    const items = asArray(body?.bills);
    const next = items.length < DISCOVERY_PAGE_SIZE || !body?.pagination?.next
      ? { mode: 'bootstrap', congresses, next_congress_index: congressIndex + 1, next_offset: 0, complete: congressIndex + 1 >= congresses.length }
      : { mode: 'bootstrap', congresses, next_congress_index: congressIndex, next_offset: offset + items.length, complete: false };
    return {
      refs: unique(items.map((item) => refFrom(item, congress)).filter(Boolean)),
      cursor: next,
      checkpointCursor: null,
    };
  }
  const windowFrom = initialWindow(state);
  const items = [];
  for (const congress of congresses) {
    const body = await apiGet(`/bill/${congress}`, { limit: DISCOVERY_PAGE_SIZE, offset: 0, fromDateTime: windowFrom });
    items.push(...asArray(body?.bills).map((item) => refFrom(item, congress)).filter(Boolean));
  }
  return {
    refs: unique(items),
    cursor: { mode: 'incremental', congresses, window_from: windowFrom },
    checkpointCursor: null,
  };
}

function detailLevel(currentStage) {
  if (['passed_origin_chamber', 'second_chamber', 'resolving_differences', 'passed_both_chambers', 'presented_to_president', 'enacted'].includes(currentStage)) return 'enriched';
  // "상임위 보고"부터 상세 추적한다. 회부·청문·소위원회 심사 단계는
  // 현재 119대의 폭넓은 법안 지도를 만들기 위한 index 행으로만 유지한다.
  if (currentStage === 'reported') return 'tracked';
  return 'index';
}

async function stageCandidates(refs) {
  let inserted = 0;
  for (const ref of refs) {
    const sourceUpdatedAt = firstNonEmpty(ref.listItem?.updateDate, ref.listItem?.updateDateIncludingText);
    const priority = detailLevel(stage(firstNonEmpty(ref.listItem?.latestAction?.text, ''), ref.type)) === 'enriched' ? 20 : 0;
    const result = await enqueuePolicyItem(RESOURCE, idOf(ref.congress, ref.type, ref.number), {
      congress: ref.congress, type: ref.type, number: ref.number, list_item: ref.listItem || null,
    }, { sourceUpdatedAt, priority });
    if (result !== 'unchanged') inserted += 1;
  }
  return inserted;
}

async function memberName(bioguideId) {
  if (!bioguideId) return null;
  if (memberCache.has(bioguideId)) return memberCache.get(bioguideId);
  const body = await apiGet(`/member/${bioguideId}`, {}, true);
  const result = firstNonEmpty(body?.member?.directOrderName, body?.member?.officialName);
  memberCache.set(bioguideId, result);
  return result;
}

async function bundle(ref) {
  const path = `/bill/${ref.congress}/${ref.type}/${ref.number}`;
  const detailBody = await apiGet(path);
  const detail = detailBody?.bill || detailBody || {};
  const [summaryBody, subjectBody, committeeBody] = await Promise.all([
    apiGet(`${path}/summaries`, { limit: 250 }, true), apiGet(`${path}/subjects`, { limit: 250 }, true),
    apiGet(`${path}/committees`, { limit: 250 }, true),
  ]);
  const summaries = asArray(summaryBody?.summaries);
  const latestSummary = [...summaries].sort((a, b) => String(a.updateDate || '').localeCompare(String(b.updateDate || ''))).at(-1);
  const basicLatestAction = detail.latestAction || ref.listItem?.latestAction || {};
  const provisionalStage = stage(firstNonEmpty(basicLatestAction.text, 'Introduced'), ref.type);
  const level = detailLevel(provisionalStage);
  const [actionBody, textBody, relationBody] = level === 'index'
    ? [null, null, null]
    : await Promise.all([
      apiGet(`${path}/actions`, { limit: 250 }, true), apiGet(`${path}/text`, { limit: 250 }, true),
      apiGet(`${path}/relatedbills`, { limit: 250 }, true),
    ]);
  const actions = asArray(actionBody?.actions);
  const latestAction = actions.at(-1) || basicLatestAction;
  const sponsorItem = asArray(detail.sponsors?.item || detail.sponsors || detail.sponsor).at(0) || {};
  const sponsorId = firstNonEmpty(sponsorItem.bioguideId, sponsorItem.bioguide_id);
  const policyName = typeof detail.policyArea === 'string' ? detail.policyArea : detail.policyArea?.name;
  const policyAreaId = slug(policyName);
  const law = asArray(detail.laws?.item || detail.laws).at(0) || {};
  const lawType = String(law.type || '').toLowerCase().replace(' law', '');
  const billId = idOf(ref.congress, ref.type, ref.number);
  return {
    billId, ref, detail, summaries, actions, detailLevel: level,
    subjects: asArray(subjectBody?.subjects), committees: asArray(committeeBody?.committees),
    textVersions: asArray(textBody?.textVersions), relatedBills: asArray(relationBody?.relatedBills), law,
    policyArea: policyAreaId ? { policy_area_id: policyAreaId, name: policyName, source_url: withoutKey(detail.policyArea?.url) } : null,
    row: {
      bill_id: billId, congress_number: ref.congress, bill_type: ref.type, bill_number: ref.number,
      origin_chamber: origin(ref.type), current_chamber: (() => { const value = asChamber(firstNonEmpty(detail.currentChamber, latestAction.chamber)); return ['house', 'senate', 'conference', 'executive'].includes(value) ? value : null; })(),
      title: firstNonEmpty(detail.title, ref.listItem.title, `${ref.type.toUpperCase()} ${ref.number}`),
      sponsor: firstNonEmpty(sponsorItem.fullName, sponsorItem.name, await memberName(sponsorId)), sponsor_bioguide_id: sponsorId,
      introduced_date: parseDateOnly(detail.introducedDate), current_status: firstNonEmpty(latestAction.text, 'Introduced'),
      current_stage: stage(firstNonEmpty(latestAction.text, 'Introduced'), ref.type), status_updated_at: parseTimestamp(latestAction.actionDate),
      latest_action_date: parseDateOnly(latestAction.actionDate), latest_action_text: latestAction.text || null,
      policy_area_id: policyAreaId, summary: latestSummary?.text || null, summary_source: latestSummary ? 'Congress.gov CRS' : null,
      summary_updated_at: parseTimestamp(firstNonEmpty(latestSummary?.lastSummaryUpdateDate, latestSummary?.updateDate)),
      law_type: ['public', 'private'].includes(lawType) ? lawType : null, law_number: law.number ? String(law.number) : null,
      congress_url: officialUrl(ref), source_updated_at: parseTimestamp(firstNonEmpty(detail.updateDateIncludingText, detail.updateDate, ref.listItem.updateDate)),
      last_synced_at: new Date().toISOString(), raw_source: {
        source: 'congress.gov', api_url: withoutKey(detail.url || ref.listItem.url),
        update_date: detail.updateDate || ref.listItem.updateDate || null,
      },
      detail_level: level,
    },
  };
}

function committeeData(value, congress) {
  const match = String(value?.url || '').match(/\/committee\/(house|senate|joint)\/([^/?]+)/i);
  const committeeCode = String(firstNonEmpty(value?.systemCode, value?.code, match?.[2], '')).toLowerCase();
  const committeeChamber = asChamber(firstNonEmpty(value?.chamber, match?.[1]));
  return committeeCode && committeeChamber ? { id: `${congress}-${committeeChamber}-${committeeCode}`, committeeCode, committeeChamber } : null;
}

async function saveBundle(data) {
  const previous = (await supabaseGet('bills', { select: 'title,summary,current_status,embedding', bill_id: `eq.${data.billId}`, limit: '1' }))?.[0];
  if (data.policyArea) await supabaseUpsert('policy_areas', [data.policyArea], 'policy_area_id');
  await supabaseUpsert('bills', [data.row], 'bill_id');
  for (const summary of data.summaries) {
    if (!summary.text) continue;
    const existing = await supabaseGet('bill_summaries', { select: 'bill_summary_id', bill_id: `eq.${data.billId}`, summary_text: `eq.${encodeURIComponent(summary.text)}`, limit: '1' });
    if (!existing?.length) await supabaseInsert('bill_summaries', {
      bill_id: data.billId, action_date: parseDateOnly(summary.actionDate), action_description: summary.actionDesc || null,
      version_code: summary.versionCode || null, summary_text: summary.text, source_updated_at: parseTimestamp(summary.updateDate),
    });
  }
  for (const subject of data.subjects) {
    const name = firstNonEmpty(subject.name, typeof subject === 'string' ? subject : null); const subjectId = slug(name);
    if (!subjectId) continue;
    await supabaseUpsert('legislative_subjects', [{ subject_id: subjectId, name, source_url: withoutKey(subject.url) }], 'subject_id');
    await supabaseInsertIgnore('bill_subjects', { bill_id: data.billId, subject_id: subjectId }, 'bill_id,subject_id');
  }
  for (const committee of data.committees) {
    const info = committeeData(committee, data.ref.congress); if (!info) continue;
    await supabaseUpsert('committees', [{ committee_id: info.id, congress_number: data.ref.congress, committee_code: info.committeeCode,
      chamber: info.committeeChamber, committee_type: committee.isSubcommittee ? 'subcommittee' : 'standing',
      name: firstNonEmpty(committee.name, info.committeeCode), official_url: withoutKey(committee.url), raw_source: committee }], 'committee_id');
    await supabaseUpsert('bill_committees', [{ bill_id: data.billId, committee_id: info.id,
      activity_names: asArray(committee.activities).map((item) => item.name || item).filter(Boolean), raw_source: committee }], 'bill_id,committee_id');
  }
  let latestActionId = null;
  for (let index = 0; index < data.actions.length; index += 1) {
    const action = data.actions[index]; const actionText = firstNonEmpty(action.text, 'Action recorded'); const id = actionId(data.billId, action, index);
    const actionDate = parseTimestamp(`${parseDateOnly(action.actionDate) || '1900-01-01'}T${action.actionTime || '00:00:00'}Z`);
    await supabaseUpsert('bill_actions', [{ bill_action_id: id, bill_id: data.billId, action_date: actionDate,
      action_code: action.actionCode || null, action_type: action.sourceSystem?.name || action.actionType || null,
      chamber: asChamber(action.chamber), action_text: actionText, normalized_stage: stage(actionText, data.ref.type),
      source_url: withoutKey(action.url), raw_source: {
        source: 'congress.gov', action_code: action.actionCode || null, recorded_vote_count: asArray(action.recordedVotes).length,
      } }], 'bill_action_id');
    latestActionId = id;
    for (const vote of asArray(action.recordedVotes)) await saveVote(data, action, vote);
  }
  if (latestActionId && (!previous || previous.current_status !== data.row.current_status)) await supabaseInsertIgnore('bill_status_history', { bill_id: data.billId, status: data.row.current_status,
    normalized_stage: data.row.current_stage, changed_at: data.row.status_updated_at || new Date().toISOString(), source_action_id: latestActionId }, 'bill_id,status,changed_at');
  for (const version of data.textVersions) {
    const formats = asArray(version.formats); const find = (pattern) => formats.find((format) => pattern.test(format.type || ''))?.url || null;
    const row = { bill_id: data.billId, version_code: firstNonEmpty(version.type, version.versionCode), version_name: version.typeName || null,
      issued_on: parseDateOnly(firstNonEmpty(version.date, version.issueDate)), html_url: find(/html/i), pdf_url: find(/pdf/i),
      xml_url: find(/xml/i), formatted_text_url: find(/formatted|text/i), source_url: withoutKey(firstNonEmpty(version.url, formats[0]?.url)),
      raw_source: { source: 'congress.gov', api_url: withoutKey(version.url) } };
    if (row.html_url || row.pdf_url || row.xml_url || row.formatted_text_url || row.source_url) {
      const existing = await supabaseGet('bill_text_versions', { select: 'bill_text_version_id', bill_id: `eq.${data.billId}`,
        version_code: row.version_code ? `eq.${encodeURIComponent(row.version_code)}` : 'is.null', issued_on: row.issued_on ? `eq.${row.issued_on}` : 'is.null', limit: '1' });
      if (!existing?.length) await supabaseInsert('bill_text_versions', row);
    }
  }
  for (const related of data.relatedBills) {
    const target = refFrom(related, data.ref.congress); if (!target) continue;
    const existing = await supabaseGet('bill_relations', { select: 'bill_relation_id', source_bill_id: `eq.${data.billId}`,
      target_congress_number: `eq.${target.congress}`, target_bill_type: `eq.${target.type}`, target_bill_number: `eq.${target.number}`,
      relation_type: `eq.${encodeURIComponent(firstNonEmpty(related.relationshipType, related.relationship, 'related'))}`, relation_origin: 'eq.official', limit: '1' });
    if (!existing?.length) await supabaseInsert('bill_relations', { source_bill_id: data.billId, target_congress_number: target.congress,
      target_bill_type: target.type, target_bill_number: target.number, relation_type: firstNonEmpty(related.relationshipType, related.relationship, 'related'),
      relation_origin: 'official', identified_by: 'Congress.gov related bills', source_url: withoutKey(related.url) });
  }
  const number = Number(String(data.law.number || '').match(/\d+$/)?.[0]); const type = String(data.law.type || '').toLowerCase().replace(' law', '');
  if (Number.isInteger(number) && ['public', 'private'].includes(type)) await supabaseUpsert('public_laws', [{ public_law_id: `${data.ref.congress}-${type}-${number}`,
    congress_number: data.ref.congress, law_number: number, law_title: data.row.title, enacted_date: data.row.latest_action_date,
    bill_id: data.billId, congress_url: officialUrl(data.ref) }], 'public_law_id');
  await queue(data.billId, data.row, { policy_area: data.row.policy_area_id, bill: data.billId });
  return data.detailLevel !== 'index' && (!previous || !previous.embedding || previous.title !== data.row.title || previous.summary !== data.row.summary);
}

async function saveVote(data, action, vote) {
  const voteChamber = asChamber(vote.chamber || action.chamber); const roll = Number(vote.rollNumber || vote.roll_number);
  if (!['house', 'senate'].includes(voteChamber) || !Number.isInteger(roll)) return;
  const date = parseTimestamp(firstNonEmpty(vote.date, action.actionDate)); if (!date) return;
  const session = Number(vote.sessionNumber || vote.session) || null;
  await supabaseUpsert('bill_votes', [{ vote_id: `cv_${data.ref.congress}_${voteChamber}_${session || 0}_${roll}_${date.slice(0, 10)}`,
    bill_id: data.billId, chamber: voteChamber, congress_number: data.ref.congress, session_number: session, roll_number: roll, vote_date: date,
    question: firstNonEmpty(vote.question, action.text), result: vote.result || null, yea_count: Number(vote.yeaCount || vote.yeas) || null,
    nay_count: Number(vote.nayCount || vote.nays) || null, present_count: Number(vote.presentCount) || null,
    not_voting_count: Number(vote.notVotingCount) || null, vote_method: vote.method || null,
    source_url: withoutKey(firstNonEmpty(vote.url, action.url, officialUrl(data.ref))), raw_source: vote }], 'vote_id');
}

async function queue(billId, row, categories) {
  if (!subscriptions) subscriptions = await supabaseGet('subscriptions', { select: 'subscription_id,keyword,category_type,category_id', active: 'eq.true' });
  const source = `${row.title}\n${row.summary || ''}`.toLowerCase();
  for (const subscription of subscriptions) {
    if ((subscription.keyword && source.includes(subscription.keyword.toLowerCase())) ||
      (subscription.category_type && categories[subscription.category_type] === subscription.category_id)) {
      const existing = await supabaseGet('notifications_queued', { select: 'notification_id', subscription_id: `eq.${subscription.subscription_id}`, bill_id: `eq.${billId}`, limit: '1' });
      if (!existing?.length) await supabaseInsert('notifications_queued', { subscription_id: subscription.subscription_id, bill_id: billId });
    }
  }
}

async function embed(items) {
  if (SKIP_EMBEDDINGS || !items.length) return 0;
  try {
    const selected = items.slice(0, MAX_EMBEDDINGS);
    const key = requireEnv('GEMINI_API_KEY');
    for (let start = 0; start < selected.length; start += 50) {
      const group = selected.slice(start, start + 50); const vectors = await geminiEmbeddings(group.map((item) => `${item.row.title}\n\n${item.row.summary || ''}`), key);
      for (let index = 0; index < group.length; index += 1) await supabasePatch('bills', `bill_id=eq.${encodeURIComponent(group[index].billId)}`, {
        embedding: vectors[index], embedding_model: geminiModelName(), embedded_at: new Date().toISOString(),
      });
    }
    if (items.length > selected.length) console.warn(`Embedding cap reached: ${items.length - selected.length} bill embeddings deferred.`);
    return selected.length;
  } catch (error) {
    // Source records are more important than optional semantic search. A
    // missing or unfunded embedding account must never fail an API sync run.
    if (isOptionalEmbeddingError(error)) {
      console.warn(`Bill embeddings skipped: ${error.message}`);
      return 0;
    }
    throw error;
  }
}

async function run() {
  const state = await loadState(); const active = await activeCongress(); const congresses = lastFour(active);
  const bootstrap = shouldBootstrap(state);
  const runId = await startSyncRun(RESOURCE, { congresses, mode: bootstrap ? 'bootstrap' : 'incremental', max_bills: MAX_BILLS });
  let read = 0; let written = 0;
  try {
    const next = await candidates(congresses, state, bootstrap);
    const staged = await stageCandidates(next.refs);
    await checkpointSyncState(RESOURCE, next.cursor);
    const queued = await takePolicyQueue(RESOURCE, MAX_BILLS);
    read = queued.length;
    console.log(`Congress.gov: discovered ${next.refs.length}, staged ${staged}, processing ${read} queued bills for Congress ${congresses.join(', ')}.`);
    const claimed = await mapWithConcurrency(queued, CONCURRENCY, async (entry) => {
      await markPolicyQueue(entry.queue_id, { status: 'processing', claimed_at: new Date().toISOString(), attempts: entry.attempts + 1 });
      const payload = entry.payload || {};
      try {
        const item = await bundle({ congress: Number(payload.congress), type: payload.type, number: Number(payload.number), listItem: payload.list_item || null });
        return { entry, item };
      } catch (error) {
        const delayMs = Math.min(60 * 60 * 1000, 60_000 * (2 ** Math.min(entry.attempts, 5)));
        await markPolicyQueue(entry.queue_id, {
          status: 'pending', available_at: new Date(Date.now() + delayMs).toISOString(), last_error: error.message,
        });
        console.error(`Congress.gov queue item ${entry.source_key} deferred: ${error.message}`);
        return { entry, error };
      }
    });
    const embeds = [];
    for (const result of claimed) {
      if (result.error) continue;
      try {
        if (await saveBundle(result.item)) embeds.push(result.item);
        written += 1;
        await markPolicyQueue(result.entry.queue_id, { status: 'succeeded', completed_at: new Date().toISOString(), last_error: null });
      } catch (error) {
        await markPolicyQueue(result.entry.queue_id, { status: 'pending', available_at: new Date(Date.now() + 300_000).toISOString(), last_error: error.message });
        console.error(`Congress.gov write for ${result.entry.source_key} deferred: ${error.message}`);
      }
    }
    const embedded = await embed(embeds);
    await supabaseRpc('refresh_policy_lifecycle_tiers', { active_congress_number: active });
    await updateSyncState(RESOURCE, { ...next.cursor, completed_at: new Date().toISOString() });
    const status = written === read ? 'succeeded' : 'partial';
    await finishSyncRun(runId, { status, records_read: read, records_written: written, metadata: { cursor: next.cursor, staged, embedded } });
    console.log(`Congress.gov complete: ${written}/${read} queued records, ${embedded} embeddings.`);
  } catch (error) {
    await finishSyncRun(runId, { status: 'failed', records_read: read, records_written: written, error_summary: error.message });
    throw error;
  }
}
run().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
