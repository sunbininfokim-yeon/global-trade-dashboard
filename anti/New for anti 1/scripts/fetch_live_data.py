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
    #
    # NOTE: this feed is broken down by Brazilian state of origin (uf), NOT by
    # destination country -- agrobr's exportacao() takes no destination
    # argument. It therefore cannot produce trade routes; destination-level
    # Brazil trade comes from UN Comtrade. What it is good for is a monthly
    # national export total, so emit that aggregate alongside the raw rows.
    try:
        print("Fetching Comex Stat Export data for Brazil (Soybeans, 2024)...")
        df_comex = await comex_api.exportacao("soja", ano=2024, agregacao="mensal")

        if not df_comex.empty:
            comex_records = df_comex.to_dict(orient="records")
            output_data["comexstat"]["brazil_soybean_exports_2024"] = comex_records
            print(f"Successfully fetched {len(comex_records)} Comex Stat records.")

            monthly = (
                df_comex.groupby("mes", as_index=False)[["volume_ton", "valor_fob_usd"]]
                .sum()
                .sort_values("mes")
            )
            output_data["comexstat"]["brazil_soybean_monthly_2024"] = {
                "year": 2024,
                "months": monthly.to_dict(orient="records"),
                "total_volume_ton": float(monthly["volume_ton"].sum()),
                "total_value_usd": float(monthly["valor_fob_usd"].sum()),
                "data_source": "Brazil Comex Stat (monthly, national total)",
            }
            print(
                "Aggregated to national monthly totals: "
                f"{monthly['volume_ton'].sum() / 1e6:.1f} Mt / "
                f"${monthly['valor_fob_usd'].sum() / 1e9:.1f}B"
            )
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
