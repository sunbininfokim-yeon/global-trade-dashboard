import os
import json
import time
import requests
from datetime import datetime

# ==============================================================================
# CONAB Data Extraction Bot (Nightly Workflow)
# ==============================================================================
# In a real environment, this would import `agrobr` to fetch live Excel files.
# For demonstration and initial setup, we extract a structured JSON payload 
# mocking the parsed output.
# ==============================================================================

def fetch_conab_data():
    """
    Simulates fetching and parsing the CONAB .xlsx file.
    Returns clean JSON data.
    """
    print("[BOT] Fetching latest CONAB boletim data...")
    # Simulate processing time
    time.sleep(2)
    
    # Mock data representing the latest harvest forecast for Mato Grosso (Soybeans/Corn)
    mock_data = {
        "source": "CONAB",
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "regions": {
            "Mato Grosso (Brazil)": {
                "crops": [
                    { "name": "soja", "avg_yield": "3,400 kg/ha", "pred_yield": "3,550 kg/ha", "change_pct": 4.4 },
                    { "name": "milho", "avg_yield": "5,600 kg/ha", "pred_yield": "5,712 kg/ha", "change_pct": 2.0 },
                ]
            },
            "Rio Grande do Sul (Brazil)": {
                "crops": [
                    { "name": "soja", "avg_yield": "3,100 kg/ha", "pred_yield": "2,400 kg/ha", "change_pct": -22.5 },
                ]
            }
        }
    }
    
    print(f"[BOT] Extracted {len(mock_data['regions'])} regions.")
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
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/conab_latest"
    
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
    print("=== Starting CONAB Nightly Bot ===")
    data = fetch_conab_data()
    upload_to_cloudflare_kv(data)
    print("=== Finished ===")
