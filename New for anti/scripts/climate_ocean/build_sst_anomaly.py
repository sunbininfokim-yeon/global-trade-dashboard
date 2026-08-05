"""
기후 세계지도에 깔 SST 편차 래스터(PNG)를 만든다.

왜 절대 수온이 아니라 편차인가:
절대 수온 지도는 '적도가 뜨겁다'는 정보밖에 없어서 예측에 쓸모가 없고, 색이
강해 육지 폴리곤·국가 핀을 덮어버린다. 편차(anomaly)를 쓰면 평년 대비 이상만
남으므로 라니냐/엘니뇨의 적도 태평양 혀, 북대서양 온난역, 아극환류 한랭역이
그대로 드러난다.

출력:
  public/data/sst_anomaly.png        1도 격자 RGBA. 육지·결측은 완전 투명.
  public/data/sst_anomaly_meta.json  관측일 · 지리 경계 · 색상 스케일

투명도 설계: 편차 0 근처를 투명하게 두고 |편차|에 비례해 알파를 올린다.
이러면 '평년과 같은 바다'는 아예 안 그려지고 이상역만 은은하게 뜬다.
BitmapLayer 쪽에서 opacity 를 한 번 더 낮춰 쓰는 걸 전제로 한 알파값이다.

의존성: numpy, Pillow (build_ocean_signals.py 와 달리 stdlib 만으로는 불가)

사용:
    python3 build_sst_anomaly.py
    python3 build_sst_anomaly.py --stride 8    # 더 거친 격자 (파일 축소)
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(f"의존성 없음 ({e}). pip install numpy Pillow", file=sys.stderr)
    raise SystemExit(1)

OUT_DIR = Path(__file__).resolve().parents[2] / "public" / "data"
PNG_PATH = OUT_DIR / "sst_anomaly.png"
META_PATH = OUT_DIR / "sst_anomaly_meta.json"

ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg_LonPM180.csv"
TIMEOUT = 300

# 색상 포화 기준. |편차| 가 이 값이면 팔레트 양끝. 3도면 실제 해양 편차 대부분을 담는다.
SCALE_C = 3.0

# 알파 상한. 255 를 다 쓰면 지도가 탁해진다. BitmapLayer opacity 와 곱해져 최종 농도가 된다.
ALPHA_MAX = 190

# 발산 팔레트 끝점 (한랭 ← → 온난). 채도를 낮춰 육지 핀과 경쟁하지 않게 했다.
COLD = (56, 132, 190)
WARM = (200, 86, 66)

# 위도 컷오프. 지도는 Web Mercator 라 ±85도에서 y 가 발산한다. 극지를 남겨두면
# BitmapLayer 가 세로로 무한히 늘어나므로 애초에 받지 않는다. 대상 산지·해역
# (래브라도해 최대 65N)은 전부 이 안에 들어온다.
LAT_LIMIT = 84.0


def fetch_global_anomaly(stride: int):
    """OISST v2.1 편차장 최신 시점을 전지구로 받아 (격자배열, 관측일, 경계) 반환."""
    q = (
        f"{ERDDAP}?anom"
        f"%5B(last)%5D%5B(0.0)%5D"
        f"%5B(-{LAT_LIMIT}):{stride}:({LAT_LIMIT})%5D"
        f"%5B(-179.875):{stride}:(179.875)%5D"
    )
    print(f"ERDDAP 요청 (stride={stride})…", file=sys.stderr)
    req = urllib.request.Request(q, headers={"User-Agent": "global-trade-dashboard/sst-anomaly"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        text = r.read().decode("utf-8", errors="replace")

    lats, lons, vals = [], [], []
    obs_date = None
    for line in text.splitlines()[2:]:  # 0=헤더 1=단위
        parts = line.split(",")
        if len(parts) != 5:
            continue
        t, _z, lat_s, lon_s, v_s = parts
        try:
            lat = float(lat_s)
            lon = float(lon_s)
        except ValueError:
            continue
        if obs_date is None:
            obs_date = t.split("T")[0]
        lats.append(lat)
        lons.append(lon)
        # 육지는 빈 문자열 또는 NaN 으로 온다.
        vals.append(np.nan if (not v_s or v_s == "NaN") else float(v_s))

    if not vals:
        raise RuntimeError("ERDDAP 응답에 격자점이 없음")

    lat_u = np.array(sorted(set(lats)))
    lon_u = np.array(sorted(set(lons)))
    grid = np.full((lat_u.size, lon_u.size), np.nan, dtype=np.float32)

    lat_idx = {v: i for i, v in enumerate(lat_u)}
    lon_idx = {v: i for i, v in enumerate(lon_u)}
    for la, lo, v in zip(lats, lons, vals):
        grid[lat_idx[la], lon_idx[lo]] = v

    # 격자 중심 -> 셀 경계. 중심값 그대로 쓰면 지도가 반 셀만큼 밀린다.
    cell_lat = float(lat_u[1] - lat_u[0]) if lat_u.size > 1 else 1.0
    cell_lon = float(lon_u[1] - lon_u[0]) if lon_u.size > 1 else 1.0
    bounds = [
        round(float(lon_u[0]) - cell_lon / 2, 4),   # west
        round(float(lat_u[0]) - cell_lat / 2, 4),   # south
        round(float(lon_u[-1]) + cell_lon / 2, 4),  # east
        round(float(lat_u[-1]) + cell_lat / 2, 4),  # north
    ]
    return grid, obs_date, bounds


def colorize(grid: np.ndarray) -> Image.Image:
    """편차 격자 -> RGBA 이미지. 0 근처 투명, |편차| 클수록 진해진다."""
    h, w = grid.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    valid = ~np.isnan(grid)
    # -1..1 정규화. 팔레트 끝을 넘는 값은 끝으로 잘라 색이 되돌아가지 않게 한다.
    norm = np.clip(np.nan_to_num(grid) / SCALE_C, -1.0, 1.0)
    mag = np.abs(norm)

    warm = norm >= 0
    for ch in range(3):
        # 중립(흰색 아님)에서 끝점으로 가는 대신, 흐린 회색 기준에서 끝점으로 보간한다.
        # 알파가 이미 농도를 담당하므로 RGB 는 색상만 유지하면 된다.
        rgba[..., ch] = np.where(warm, WARM[ch], COLD[ch])

    alpha = (mag * ALPHA_MAX).astype(np.uint8)
    alpha[~valid] = 0  # 육지 · 결측
    rgba[..., 3] = alpha

    # ERDDAP 는 위도 오름차순(남→북)으로 준다. 이미지 0행은 북쪽이어야 하므로 뒤집는다.
    rgba = np.flipud(rgba)
    return Image.fromarray(rgba, mode="RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=4,
                    help="OISST 0.25도 격자 추출 간격. 4 = 1도 (기본)")
    args = ap.parse_args()

    grid, obs_date, bounds = fetch_global_anomaly(args.stride)
    ocean = ~np.isnan(grid)
    print(f"격자 {grid.shape[0]}x{grid.shape[1]} · 해양 격자점 {int(ocean.sum())}", file=sys.stderr)

    img = colorize(grid)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(PNG_PATH, optimize=True)

    vals = grid[ocean]
    meta = {
        "schema_version": "sst_anomaly_v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "obs_date": obs_date,
        "source": "NOAA OISST v2.1 (ERDDAP ncdcOisst21Agg) · 편차 anomaly",
        "image": "sst_anomaly.png",
        "bounds": bounds,
        "scale_c": SCALE_C,
        "alpha_max": ALPHA_MAX,
        "cold_rgb": list(COLD),
        "warm_rgb": list(WARM),
        "grid": {"rows": int(grid.shape[0]), "cols": int(grid.shape[1]), "stride": args.stride},
        "stats": {
            "min_c": round(float(vals.min()), 2),
            "max_c": round(float(vals.max()), 2),
            "mean_c": round(float(vals.mean()), 3),
        },
        "caveat_ko": "평년 대비 편차이며 절대 수온이 아님. 관측이지 예측이 아님.",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "png": str(PNG_PATH.relative_to(OUT_DIR.parents[1])),
        "png_kb": round(PNG_PATH.stat().st_size / 1024, 1),
        "obs_date": obs_date,
        "bounds": bounds,
        "stats": meta["stats"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
