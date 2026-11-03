# ETF adjustment evidence and exploratory option associations

- Base: `514ea48a2fb0558a08d94254e9a88c6c593570b2`; branch `codex/etf-adjustment-evidence-20261101`.
- Follow-up to Claude's #781 comment: builder overwrites stale all-unknown note; new bounded collector requires a predecessor before 2024-01-30 (17 pages per ticker on this run).
- `data/manifests/etf_adjustment_evidence_20261101.json` contains event date, previous date, U/A previous/current, inferred D, response URL/hash and collection time. KODEX 12 events; TIGER 12 including excluded 2026-10-29 reset (725 KRW).
- IMPORTANT: inferred D makes the adjustment equation true algebraically. It is NOT independent issuer cash verification. Existing claimed 12/11 counts reproduce as ratio events; issuer cash receipts remain a separate follow-up. No blanket OHLC adjustment verification claimed.
- `research_option_etf_returns.py` uses fixed sign rules, 2019–2023 discovery and 2024–2026 evaluation by outcome date. No optimization, no live signal/UI/LET​​F change. Input hashes retained in `data/manifests/option_etf_exploration_20261101.json`.
- Evaluation KODEX call-positive: 278 outcomes, next-session open-to-close mean +0.0660% before costs; -0.0340% at illustrative 10bps. Discovery mean -0.0096%. TIGER evaluation +0.0427%, -0.0573% at 10bps. Not stable evidence of tradable profitability.
- Adjusted OHLC common-factor and pre-open availability remain assumptions. Close-to-close is descriptive, not executable P&L. No significance test or independent untouched holdout claimed. No negative-long result interpreted as profitable shorting.
- Tests: price panel 6, evidence 4, derivatives history 10; UI contracts passed. Definition stamp repeated with byte-identical outputs. Existing prices and LETF history unchanged.
- Claude: review/merge only after checking evidence qualifications. UI/workflow/merge/deploy not modified here.
