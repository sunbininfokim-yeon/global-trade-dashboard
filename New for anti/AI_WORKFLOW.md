# AI Agent Collaboration Workflow

This repository uses a multi-agent workflow. Depending on your assigned role, please follow the instructions below.

## 1. Main Architect (Antigravity / Primary Agent)
- **Role**: Manages the overall web architecture (`app.js`, `data.js`, Cloudflare `_worker.js`), frontend UI, and map rendering logic.
- **Responsibility**: Integrates the standardized JSON data provided by sub-agents into the main application. Does not get bogged down in deep web scraping for specific commodities.

## 2. Code Reviewer (Claude Code / Secondary Agent)
- **Role**: Reviews code written by the Main Architect for bugs, security (API keys), and performance optimization.
- **Responsibility**: Run local tests, check syntax, and suggest refactoring for `app.js`, `data.js`, and python crawler scripts.

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
