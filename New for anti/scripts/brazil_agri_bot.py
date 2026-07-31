import os
import json
import time
import requests
from datetime import datetime

# ==============================================================================
# Brazil Agri Data Extraction Bot (Nightly Workflow)
# Handles CONAB (Yield), CEPEA (Prices), and IBGE (Municipal)
# ==============================================================================

def fetch_brazil_data():
    """
    Simulates fetching and parsing from CONAB, CEPEA, and IBGE.
    Returns clean combined JSON data.
    """
    print("[BOT] Fetching latest CONAB, CEPEA, and IBGE data...")
    time.sleep(2)
    
    # Mock data representing the unified data
    mock_data = {
        "source": "CONAB_CEPEA_IBGE",
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "regions": {
            "Mato Grosso (Brazil)": {
                "crops": [
                    { 
                        "name": "soja", 
                        "avg_yield": "3,400 kg/ha", 
                        "pred_yield": "3,550 kg/ha", 
                        "change_pct": 4.4,
                        "cepea_price_brl": "135.50",
                        "cepea_price_usd": "27.10",
                        "cepea_trend": "+1.2%",
                        "ibge_top_municipalities": [
                            {"city": "Sorriso", "production_tonnes": "2,150,000"},
                            {"city": "Sinop", "production_tonnes": "1,820,000"},
                            {"city": "Nova Mutum", "production_tonnes": "1,550,000"}
                        ]
                    },
                    { 
                        "name": "milho", 
                        "avg_yield": "5,600 kg/ha", 
                        "pred_yield": "5,712 kg/ha", 
                        "change_pct": 2.0,
                        "cepea_price_brl": "62.30",
                        "cepea_price_usd": "12.46",
                        "cepea_trend": "-0.5%"
                    },
                ]
            },
            "Rio Grande do Sul (Brazil)": {
                "crops": [
                    { 
                        "name": "soja", 
                        "avg_yield": "3,100 kg/ha", 
                        "pred_yield": "2,400 kg/ha", 
                        "change_pct": -22.5,
                        "cepea_price_brl": "138.00",
                        "cepea_price_usd": "27.60",
                        "cepea_trend": "+2.1%",
                        "ibge_top_municipalities": [
                            {"city": "Tupanciretã", "production_tonnes": "850,000"},
                            {"city": "Cruz Alta", "production_tonnes": "720,000"}
                        ]
                    },
                ]
            }
        }
    }
    
    print(f"[BOT] Extracted combined data for {len(mock_data['regions'])} regions.")
    return mock_data

def upload_to_cloudflare_kv(data):
    """
    Uploads the parsed JSON data to Cloudflare KV.
    """
    account_id = os.environ.get("CF_ACCOUNT_ID")
    namespace_id = os.environ.get("CF_KV_NAMESPACE_ID")
    api_token = os.environ.get("CF_API_TOKEN")

    if not all([account_id, namespace_id, api_token]):
        print("[ERROR] Cloudflare credentials missing. Ensure CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID, and CF_API_TOKEN are set.")
        return

    print("[BOT] Uploading to Cloudflare KV...")
    # Change the KV key from conab_latest to brazil_agri_latest
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/brazil_agri_latest"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    response = requests.put(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        print("[BOT] Successfully uploaded data to Cloudflare KV.")
    else:
        print(f"[ERROR] Failed to upload: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("=== Starting Brazil Agri Nightly Bot ===")
    data = fetch_brazil_data()
    upload_to_cloudflare_kv(data)
    print("=== Finished ===")
