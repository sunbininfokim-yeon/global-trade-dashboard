"""
climate_global_v1.json 의 해양 신호 필드를 실데이터로 갱신한다.

이 JSON 은 원래 손으로 쓴 seed 였다. enso / iod / north_atlantic 세 블록은
대시보드 기후 화면 우측 패널이 그대로 읽어 쓰므로(app.js renderClimateWorldLeft),
seed 값이 실제와 어긋나면 화면이 틀린 상태를 단언하게 된다.

소스 (전부 공개 · 키 불필요):
  ONI  : NOAA CPC   계절별 Niño 3.4 편차
  DMI  : NOAA PSL   인도양 쌍극자 (HadISST 기반)
  NAO  : NOAA PSL   북대서양 진동 (CPC)
  SST  : NOAA OISST v2.1 편차장 (ERDDAP griddap) — 해역 박스 면적평균

north_atlantic 은 기존에 anomaly_c 단일 seed 뿐이었다. 여기서는 OISST 편차를
세 박스로 나눠 계산한다. 아열대/전체 북대서양이 양의 편차인데 아극환류(subpolar
gyre)만 음이면 그게 이른바 'cold blob' — 대서양이 전반적으로 데워지는 와중에
그린란드 남쪽만 차가워지는 패턴이다. cold_blob 플래그가 그 조건을 표시한다.

주의: 이 값들은 관측이지 예측이 아니다. AMOC/해류는 수십 년 스케일이라
단수(yield) 모델의 시즌 피처가 아니며, 배경 컨텍스트로만 쓸 것.

사용:
    python3 build_ocean_signals.py            # 갱신 후 파일 쓰기
    python3 build_ocean_signals.py --check    # 계산만 하고 출력 (쓰기 없음)
"""

import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "public" / "data" / "climate_global_v1.json"

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
NAO_URL = "https://psl.noaa.gov/data/correlation/nao.data"
ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg_LonPM180.csv"

TIMEOUT = 90

# PSL 계열 파일은 결측을 -99.9 / -99.99 로 채운다. 값이 그 근처면 결측.
MISSING = -90.0

# ONI 계절 코드 -> 중심 월. 시계열 라벨을 월 단위로 맞추기 위해 쓴다.
SEASON_CENTER = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}

# 면적평균할 해역. (lat_min, lat_max, lon_min, lon_max) — 경도는 -180..180.
BOXES = {
    # 북대서양 전체. 아열대 난수까지 포함하므로 보통 양의 편차가 나온다.
    "north_atlantic": (0.0, 60.0, -80.0, 0.0),
    # 아극환류 = 'warming hole' / cold blob 이 나타나는 자리.
    "subpolar_gyre": (45.0, 60.0, -50.0, -20.0),
    # 래브라도해. 심층수 형성 해역이라 열염순환 논의의 중심.
    "labrador_sea": (55.0, 65.0, -60.0, -45.0),
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard/ocean-signals"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# 지수 파서
# --------------------------------------------------------------------------

def parse_oni(text: str):
    """CPC ONI ascii -> [(year, season, anom)] 시간순."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0] not in SEASON_CENTER:
            continue  # 헤더 행
        try:
            rows.append((int(parts[1]), parts[0], float(parts[3])))
        except ValueError:
            continue
    return rows


def parse_psl_monthly(text: str):
    """PSL 월별 격자 포맷 -> [(year, month, value)]. 결측 제외.

    첫 줄이 '시작연도 끝연도', 이후 '연도 v1..v12', 마지막에 주석 꼬리표가 붙는다.
    """
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 13:
            continue  # 헤더 · 꼬리 주석 · 결측 마커 줄
        try:
            year = int(parts[0])
            vals = [float(v) for v in parts[1:]]
        except ValueError:
            continue
        for i, v in enumerate(vals):
            if v > MISSING:
                out.append((year, i + 1, v))
    return out


def enso_state(oni: float):
    """ONI 값 -> (한국어, 영어) 상태 문자열. CPC 통상 구분을 따른다."""
    a = abs(oni)
    if a < 0.5:
        return "중립 (Neutral)", "Neutral"
    if a < 1.0:
        strength_ko, strength_en = "약", "weak"
    elif a < 1.5:
        strength_ko, strength_en = "중", "moderate"
    elif a < 2.0:
        strength_ko, strength_en = "강", "strong"
    else:
        strength_ko, strength_en = "매우 강", "very strong"
    if oni > 0:
        return f"엘니뇨 · {strength_ko}", f"El Niño {strength_en}"
    return f"라니냐 · {strength_ko}", f"La Niña {strength_en}"


# --------------------------------------------------------------------------
# OISST 해역 면적평균
# --------------------------------------------------------------------------

def box_mean_anomaly(lat_min, lat_max, lon_min, lon_max, stride=4):
    """OISST v2.1 편차장의 최신 시점을 박스 면적평균한다.

    격자가 위경도 등간격이라 고위도 셀이 좁아진다. 위도 코사인으로 가중해야
    래브라도해처럼 고위도 박스에서 평균이 부풀지 않는다.

    반환: (평균 편차 °C, 관측일 ISO, 사용 격자점 수)
    """
    q = (
        f"{ERDDAP}?anom"
        f"%5B(last)%5D%5B(0.0)%5D"
        f"%5B({lat_min}):{stride}:({lat_max})%5D"
        f"%5B({lon_min}):{stride}:({lon_max})%5D"
    )
    text = fetch(q)
    lines = text.splitlines()
    if len(lines) < 3:
        raise RuntimeError(f"ERDDAP 응답이 비었음: {lat_min}..{lat_max}")

    wsum = 0.0
    vsum = 0.0
    n = 0
    obs_date = None
    for line in lines[2:]:  # 0=헤더 1=단위
        parts = line.split(",")
        if len(parts) != 5:
            continue
        t, _zlev, lat_s, _lon_s, val_s = parts
        if not val_s or val_s == "NaN":
            continue  # 육지 격자
        try:
            lat = float(lat_s)
            val = float(val_s)
        except ValueError:
            continue
        w = math.cos(math.radians(lat))
        vsum += val * w
        wsum += w
        n += 1
        if obs_date is None:
            obs_date = t.split("T")[0]

    if not n or wsum == 0:
        raise RuntimeError(f"유효 격자점 없음: {lat_min}..{lat_max}")
    return round(vsum / wsum, 3), obs_date, n


# --------------------------------------------------------------------------
# 블록 조립
# --------------------------------------------------------------------------

def build_enso():
    rows = parse_oni(fetch(ONI_URL))
    if not rows:
        raise RuntimeError("ONI 파싱 실패")
    recent = rows[-12:]
    series = []
    for year, season, anom in recent:
        month = SEASON_CENTER[season]
        # DJF 는 전년 12월~당해 2월이고 CPC 는 끝 연도로 표기한다. 중심월 1월이 맞다.
        series.append({"label": f"{year % 100:02d}-{month:02d}", "oni": anom})
    latest_year, latest_season, latest = recent[-1]
    ko, en = enso_state(latest)
    return {
        "index": "Niño 3.4 ONI",
        "source": "NOAA CPC (oni.ascii.txt)",
        "latest_c": latest,
        "latest_season": f"{latest_season} {latest_year}",
        "state_ko": ko,
        "state_en": en,
        # 지속 확률은 CPC 확률 예보 산출물이라 관측 시계열에서 유도할 수 없다.
        # 추정치를 넣느니 비워두고 UI 가 해당 줄을 생략하게 한다.
        "prob_continue_pct": None,
        "series": series,
    }


def build_iod():
    rows = parse_psl_monthly(fetch(DMI_URL))
    if not rows:
        raise RuntimeError("DMI 파싱 실패")
    year, month, val = rows[-1]
    val = round(val, 3)
    if val >= 0.4:
        state = "양성 (Positive)"
    elif val <= -0.4:
        state = "음성 (Negative)"
    else:
        state = "중립 (Neutral)"
    return {
        "index": "Indian Ocean Dipole DMI",
        "source": "NOAA PSL (dmi.had.long.data)",
        "latest": val,
        "latest_month": f"{year}-{month:02d}",
        "state_ko": state,
        "note_ko": "양의 IOD는 인도·호주 강수 패턴과 연동되는 경우가 많음",
    }


def build_north_atlantic():
    means = {}
    obs_date = None
    for name, (la, lb, lo, lc) in BOXES.items():
        mean, date, n = box_mean_anomaly(la, lb, lo, lc)
        means[name] = mean
        obs_date = obs_date or date
        print(f"  {name:16s} {mean:+.3f}°C  ({n} pts)", file=sys.stderr)

    na = means["north_atlantic"]
    spg = means["subpolar_gyre"]
    lab = means["labrador_sea"]

    # cold blob: 북대서양 전체는 데워졌는데 아극환류만 평년 이하인 패턴.
    cold_blob = na > 0 and spg < 0

    if cold_blob:
        state = "온난 편차 · 아극환류 한랭 (cold blob)"
    elif na >= 0.3:
        state = "온난 편차"
    elif na <= -0.3:
        state = "한랭 편차"
    else:
        state = "평년 수준"

    nao_rows = parse_psl_monthly(fetch(NAO_URL))
    nao = None
    if nao_rows:
        y, m, v = nao_rows[-1]
        nao = {"latest": round(v, 2), "latest_month": f"{y}-{m:02d}", "source": "NOAA PSL / CPC"}

    return {
        "index": "북대서양 SST 편차 (OISST v2.1)",
        "source": "NOAA OISST v2.1 via ERDDAP · 면적평균(위도 가중)",
        "obs_date": obs_date,
        "anomaly_c": na,
        "subpolar_gyre_anom_c": spg,
        "labrador_anom_c": lab,
        "cold_blob": cold_blob,
        "state_ko": state,
        "nao": nao,
        "boxes_note": "north_atlantic 0–60N/80W–0 · subpolar_gyre 45–60N/50–20W · labrador 55–65N/60–45W",
        "caveat_ko": "관측 편차이며 예측이 아님. 해류·AMOC는 수십 년 스케일로 시즌 단수 예측의 피처가 아니라 배경 컨텍스트.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="계산만 하고 파일에 쓰지 않음")
    args = ap.parse_args()

    if not DATA_FILE.exists():
        print(f"대상 파일 없음: {DATA_FILE}", file=sys.stderr)
        return 1

    doc = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    print("ENSO (CPC ONI)…", file=sys.stderr)
    enso = build_enso()
    print("IOD (PSL DMI)…", file=sys.stderr)
    iod = build_iod()
    print("북대서양 SST 편차 (OISST)…", file=sys.stderr)
    north_atlantic = build_north_atlantic()

    # 나머지 키(cities, map_temp_anomaly_seed 등)는 이 스크립트 소관이 아니므로 보존.
    doc["enso"] = enso
    doc["iod"] = iod
    doc["north_atlantic"] = north_atlantic
    doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["note"] = "해양 신호(enso/iod/north_atlantic)는 실관측. 그 외 필드는 아직 seed."

    summary = {
        "ONI": f"{enso['latest_c']:+.2f} ({enso['latest_season']}) {enso['state_en']}",
        "DMI": f"{iod['latest']:+.2f} ({iod['latest_month']}) {iod['state_ko']}",
        "North Atlantic": f"{north_atlantic['anomaly_c']:+.2f}°C",
        "Subpolar gyre": f"{north_atlantic['subpolar_gyre_anom_c']:+.2f}°C",
        "Labrador Sea": f"{north_atlantic['labrador_anom_c']:+.2f}°C",
        "cold_blob": north_atlantic["cold_blob"],
        "obs_date": north_atlantic["obs_date"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.check:
        print("--check: 파일 쓰지 않음", file=sys.stderr)
        return 0

    DATA_FILE.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"기록됨: {DATA_FILE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
