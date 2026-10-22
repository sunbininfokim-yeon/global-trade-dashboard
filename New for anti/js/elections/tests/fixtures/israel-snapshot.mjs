import { readFileSync } from 'node:fs';

// Historical assertions must not follow the next public snapshot update.
const root = new URL('../../../../scripts/election_watch/tests/fixtures/israel/2026-10-20/', import.meta.url);
export const readIsraelFixture = (name) => readFileSync(new URL(name, root), 'utf8');
