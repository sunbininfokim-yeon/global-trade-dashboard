import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const data = new URL('../../../public/data/', import.meta.url);
const body = readFileSync(new URL('israel_election_analysis_v1.json', data), 'utf8');
const status = JSON.parse(readFileSync(new URL('israel_election_analysis_status_v1.json', data)));
const response = (ok = true, statusOverride = status, text = body) => async url => ({
    ok, text: async () => text, json: async () => statusOverride,
});
test('paired source data and health must match exact body hash', async () => {
    const previous = globalThis.fetch;
    try {
        globalThis.fetch = response();
        const { loadIsraelElectionAnalysis } = await import('../data/israel-service.js?case=ok');
        const result = await loadIsraelElectionAnalysis();
        assert.equal(result.board?.coverage.accepted_seat_polls, 8);assert.equal(result.error, null);
    } finally { globalThis.fetch = previous; }
});
test('transport failure returns unavailable, never an empty polling board', async () => {
    const previous = globalThis.fetch;
    try {
        globalThis.fetch = response(false);
        const { loadIsraelElectionAnalysis } = await import('../data/israel-service.js?case=transport');
        const result = await loadIsraelElectionAnalysis();
        assert.equal(result.board, null);assert(result.error);
    } finally { globalThis.fetch = previous; }
});
test('mismatched publication versions cannot publish calculations', async () => {
    const previous = globalThis.fetch;
    try {
        globalThis.fetch = response(true, { ...status, board_sha256: 'wrong' });
        const { loadIsraelElectionAnalysis } = await import('../data/israel-service.js?case=hash');
        const result = await loadIsraelElectionAnalysis();
        assert.equal(result.board, null);assert.match(result.error, /버전/);
    } finally { globalThis.fetch = previous; }
});
