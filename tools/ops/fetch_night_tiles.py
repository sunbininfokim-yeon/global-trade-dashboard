#!/usr/bin/env python3
"""NASA VIIRS Black Marble 야간광 타일을 레포에 통째로 받아 둔다.

매크로 지도(`/macro_monitor`)의 베이스맵이다. Black Marble 은 2016(과 2012)
연간 합성이라 내용이 바뀌지 않고, NASA 이미지는 자유롭게 재배포할 수 있다 --
그래서 매번 받아 오는 대신 한 번 받아 커밋한다. 세계 지도 화면(z0-5)이
NASA 가용성과 무관해지고, 그보다 확대할 때만 워커 프록시(/api/night-tile)를
탄다.

사용:
    python3 tools/ops/fetch_night_tiles.py            # z0-5 를 받는다
    python3 tools/ops/fetch_night_tiles.py --max-zoom 4
    python3 tools/ops/fetch_night_tiles.py --force    # 이미 있는 타일도 다시

이미 받은 타일은 건너뛰므로 중간에 끊겨도 다시 돌리면 이어진다.
"""
import argparse
import math
import os
import sys
import time
import urllib.error
import urllib.request

BASE = ('https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/'
        'VIIRS_Black_Marble/default/{date}/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg')
DATES = ['2016-01-01', '2012-01-01']   # 앞의 합성이 없으면 뒤로 물러난다
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', '..', 'New for anti', 'public', 'night')

# 클라이언트(macro.js MM_NIGHT_EXTENT)가 남극을 잘라 내는 위도와 같아야 한다.
# 다르면 화면에 있는 타일을 안 받거나, 안 쓰는 타일을 받는다.
LAT_MIN, LAT_MAX = -58.0, 84.0


def lat_to_row(lat, z):
    """웹 메르카토르 위도 → 타일 행. 극지에서 발산하므로 범위를 물린다."""
    lat = max(min(lat, 85.0511), -85.0511)
    rad = math.radians(lat)
    n = 2 ** z
    y = (1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n
    return max(0, min(n - 1, int(y)))


def fetch(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as res:
                if res.status == 200:
                    return res.read()
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None          # 그 날짜에 없는 타일. 물러날 차례.
        except Exception:
            pass
        time.sleep(2 ** attempt)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-zoom', type=int, default=5,
                    help='받을 최대 줌 (기본 5). 한 단계 올릴 때마다 타일 수가 4배.')
    ap.add_argument('--force', action='store_true', help='이미 있는 타일도 다시 받는다')
    args = ap.parse_args()

    got = skipped = failed = total_bytes = 0
    for z in range(args.max_zoom + 1):
        y0, y1 = lat_to_row(LAT_MAX, z), lat_to_row(LAT_MIN, z)
        for y in range(y0, y1 + 1):
            for x in range(2 ** z):
                path = os.path.join(OUT_ROOT, str(z), str(y), f'{x}.jpg')
                if os.path.exists(path) and not args.force:
                    skipped += 1
                    total_bytes += os.path.getsize(path)
                    continue
                blob = None
                for date in DATES:
                    blob = fetch(BASE.format(date=date, z=z, y=y, x=x))
                    if blob:
                        break
                if not blob or not blob.startswith(b'\xff\xd8'):   # JPEG SOI
                    failed += 1
                    print(f'  실패 z{z}/{y}/{x}', file=sys.stderr)
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as fh:
                    fh.write(blob)
                got += 1
                total_bytes += len(blob)
        print(f'z{z} 완료 · 받음 {got} · 건너뜀 {skipped} · 실패 {failed} '
              f'· 누적 {total_bytes / 1e6:.1f}MB')

    print(f'\n끝. 받음 {got} · 건너뜀 {skipped} · 실패 {failed} '
          f'· 총 {total_bytes / 1e6:.1f}MB')
    print(f'저장 위치: {os.path.normpath(OUT_ROOT)}')
    if failed:
        print('실패분은 다시 돌리면 이어서 받는다.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
