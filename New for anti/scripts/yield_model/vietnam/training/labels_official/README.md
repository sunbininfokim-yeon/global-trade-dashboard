# Official / best-effort labels (Vietnam)

## `mekong_rice_ws`

| Years | Source | Season / geography |
|-------|--------|--------------------|
| **2018–2023** | GSO Statistical Yearbook — *Yield of spring paddy by province*, row **Đồng bằng sông Cửu Long / Mekong River Delta** | True **Đông Xuân (WS/spring)** × Mekong region |
| **2017, 2024** | [mtnongnghiep.com trồng trọt](https://mtnongnghiep.com/index.php/du-lieu-trong-trot/) provincial Đông Xuân → Mekong-13 aggregate | GSO-style province×WS (not a live GSO API dump) |
| **1990–2016** | FAOSTAT Viet Nam Rice yield × overlap scale to Mekong WS | **Annual national**, all seasons — **not** GSO WS provincial |

Yearbook PDFs:

- 2022: https://www.gso.gov.vn/wp-content/uploads/2023/06/Sach-Nien-giam-TK-2022-final.pdf  
- 2023: https://www.gso.gov.vn/wp-content/uploads/2024/07/NG-TCTK-2023_Final.pdf  

NSO lists PxWeb table **V0617** (*Năng suất lúa đông xuân phân theo địa phương*), but the agriculture database is **not** exposed on `pxweb.nso.gov.vn/api/v1` (only Industry/Education/etc.). Do **not** claim a direct machine GSO API pull.

Units: GSO/MTN **tạ/ha × 100 → kg/ha**.

See `mekong_rice_ws.provenance.json` and `mekong_rice_ws_provincial_dong_xuan.csv`.
