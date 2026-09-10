import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createFinanceClient, selectCandidateSpending } from './superpac-map-client.mjs';
const publicDir = new URL('../../../public/data/', import.meta.url);
const client = createFinanceClient(async url => ({ok: true, json: async () => JSON.parse(await readFile(new URL(url, publicDir), 'utf8'))}), '');
const race = await client.getRace(2026, 'CA', 'house', '01');
assert.equal(race.race_id, 'USA:CA:house:01');
const primary = selectCandidateSpending(race, {phase: 'P2026'});
for (const candidate of primary) {
    assert(candidate.allocations.every(row => row.election_type === 'P2026' && row.category === 'super_pac'));
}
const governor = await client.getRace(2024, 'WA', 'governor');
assert(selectCandidateSpending(governor).every(c => c.support_cents === null));
const stateIE = selectCandidateSpending(governor, {category: 'state_independent_spender_unclassified'});
assert.equal(stateIE.reduce((v, c) => v + (c.support_cents ?? 0), 0), 71697344);
assert.equal(stateIE.reduce((v, c) => v + (c.oppose_cents ?? 0), 0), 7883385);
console.log(JSON.stringify({CA01_primary: primary.filter(c => c.support_cents !== null).map(({name,support_cents,oppose_cents}) => ({name,support_cents,oppose_cents})), WA2024: stateIE.map(({name,support_cents,oppose_cents}) => ({name,support_cents,oppose_cents}))}));
