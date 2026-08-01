import asyncio
import json
import os

from agrobr.usda import api as usda_api
from agrobr.comexstat import api as comex_api

async def main():
    print("Starting data extraction...")
    
    output_data = {
        "usda_psd": {},
        "comexstat": {}
    }

    # 1. Fetch USDA PSD Data for China (Soybeans)
    try:
        print("Fetching USDA PSD data for China (Soybeans)...")
        # 'soja' is the recognized commodity name for soybeans in agrobr/usda/models.py
        df_usda = await usda_api.psd("soja", country="CH", market_year=2023)
        
        # We want to extract 'estoque_final' (Ending Stocks), 'importacao' (Imports), 'producao' (Production)
        # Convert dataframe to a list of dicts for easier JSON serialization
        usda_records = df_usda.to_dict(orient="records")
        output_data["usda_psd"]["china_soybean"] = usda_records
        print(f"Successfully fetched {len(usda_records)} USDA records.")
    except Exception as e:
        print("Error fetching USDA data:", e)

    # 2. Fetch Comex Stat Data for Brazil Exports (Soybeans)
    try:
        print("Fetching Comex Stat Export data for Brazil (Soybeans, 2024)...")
        # 'soja' is the commodity.
        df_comex = await comex_api.exportacao("soja", ano=2024, agregacao="mensal")
        
        # Aggregate the data by destination country (CO_PAIS or NO_PAIS)
        # In Comex Stat, usually the columns include NO_PAIS (Country Name), SG_UF_NCM (State), VL_FOB (Value), KG_LIQUIDO (Weight)
        if not df_comex.empty:
            # Group by Country and sum the values
            # The exact column names depend on the parsed CSV, usually 'CO_PAIS', 'VL_FOB', 'KG_LIQUIDO'
            # Let's save the raw grouped data
            comex_records = df_comex.to_dict(orient="records")
            output_data["comexstat"]["brazil_soybean_exports_2024"] = comex_records
            print(f"Successfully fetched {len(comex_records)} Comex Stat records.")
    except Exception as e:
        print("Error fetching Comex Stat data:", e)

    # 3. Save to JSON
    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../public/data/live_override.json'))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # We will write a placeholder structure for now that the frontend can read.
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"Data successfully saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
