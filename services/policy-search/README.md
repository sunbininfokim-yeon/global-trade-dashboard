# Search contract checks

This package is only the test runtime; the dependency-free production indexer is `scripts/sync-policy-search.js`.

```sh
cd services/policy-search
npm ci
npm test
```

`corpus.test.cjs` runs the actual SQL migration twice against PostgreSQL/PGlite with the official pgvector extension and real 1536-dimension test vectors. `worker.test.cjs` executes the Worker search functions with bounded official-source fixtures. `source.test.cjs` checks official text freshness, private caching and blocked-source handling. No private environment, live DB or API key is required.

Operational contract and live verification: `docs/policy-search-corpus-20261005.md`.
