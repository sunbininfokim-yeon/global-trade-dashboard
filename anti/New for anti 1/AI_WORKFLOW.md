# AI Agent Collaboration Workflow

> **운영 정본(2026-08 갱신):** 저장소 루트 `docs/ops/README.md`  
> 역할: **Cursor**=ops+ML · **Claude Code**=UI/앱+코드리뷰 · **Codex**=좁은 모델/데이터 · **Antigravity**=문헌만  
> 터미널: `./tools/ops/status.sh` · 데이터 계약: `scripts/yield_model/DATA_LAYOUT.md`

This repository uses a multi-agent workflow. Depending on your assigned role, please follow the instructions below.

## 1. App & UI Lead + Reviewer (Claude Code)
- **Role**: Web architecture (`app.js`, `data.js`, Cloudflare `_worker.js`), frontend UI, map rendering; also reviews other agents’ PRs.
- **Responsibility**: Integrate standardized JSON from model/data agents. Do not expand scope into random scrapers when a dedicated task owner exists.

## 2. Orchestrator / ML (Cursor)
- **Role**: `docs/ops`, task board, Git/Cloudflare pipeline hygiene; yield-model experiments when not conflicting with UI WIP.
- **Responsibility**: Keep GOAL/TASKS/OWNERS current; merge policy and DATA_LAYOUT discipline.

## 3. Commodity Data Sub-Agents (Specialized Scrapers)
- **Role**: Dedicated to a specific agricultural commodity (e.g., Wheat, Soybeans, Sugar).
- **Responsibility**: Write Python scripts (using tools like `agrobr`, USDA API, UN Comtrade) to fetch, parse, and clean data.
- **CRITICAL**: The final output of your scripts MUST strictly follow this JSON schema. The Main Architect relies on this exact structure to render the dashboard.

### 📌 Required JSON Schema (`live_override.json`)
```json
{
  "commodity": "soybeans",
  "metadata": {
    "last_updated": "YYYY-MM-DD",
    "sources": ["Brazil Comex Stat", "USDA PSD"]
  },
  "trade_routes": [
    {
      "source_country": "Brazil",
      "target_country": "China",
      "volume_m_usd": 2000, 
      "net_weight_m_mt": 50,
      "data_source_label": "Brazil Comex Stat (Live Monthly)"
    }
  ],
  "country_stats": [
    {
      "country": "China",
      "production_k_mt": 20000,
      "import_k_mt": 105000,
      "consumption_k_mt": 115000,
      "ending_stocks_k_mt": 37800,
      "price_usd_mt": 450.5,
      "data_source_label": "USDA PSD API"
    }
  ]
}
```
*Note: Any output JSON must be placed in `public/data/` so the frontend can fetch it.*
