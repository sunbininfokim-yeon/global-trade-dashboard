#!/usr/bin/env python3
"""NASA VIIRS Black Marble 야간광 타일을 레포에 통째로 받아 둔다.

매크로 지도(`/macro_monitor`)의 베이스맵이다. Black Marble 은 2016(과 2012)
연간 합성이라 내용이 바뀌지 않고, NASA 이미지는 자유롭게 재배포할 수 있다 --
그래서 매번 받아 오는 대신 한 번 받아 커밋한다. 세계 지도 화면(z1-5)이
NASA 가용성과 무관해지고, 그보다 확대할 때만 워커 프록시(/api/night-tile)를
탄다.

사용:
    python3 tools/ops/fetch_night_tiles.py            # z1-5 를 받는다
    python3 tools/ops/fetch_night_tiles.py --max-zoom 4
    python3 tools/ops/fetch_night_tiles.py --force    # 이미 있는 타일도 다시
    python3 tools/ops/fetch_night_tiles.py --check    # 조합별로 한 장씩 시험

이미 받은 타일은 건너뛰므로 중간에 끊겨도 다시 돌리면 이어진다.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

# 시간 자리가 비어 슬래시가 둘 연달아 붙는 게 맞다 (default//...) -- 연간 합성
# 이라 시간 차원이 없는 레이어의 GIBS 표기다. _worker.js 의 GIBS_TILE_VARIANTS
# 와 같은 순서를 유지할 것.
BASE = ('https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/'
        '{layer}/default/{time}/{matrix}/{z}/{y}/{x}.{ext}')
MATRIX = 'GoogleMapsCompatible_Level8'
VARIANTS = [
    ('citylights jpg', 'VIIRS_CityLights_2012', '', 'jpg'),
    ('blackmarble jpg', 'VIIRS_Black_Marble', '', 'jpg'),
    ('blackmarble png', 'VIIRS_Black_Marble', '', 'png'),
    ('blackmarble 2016', 'VIIRS_Black_Marble', '2016-01-01', 'png'),
    ('citylights png', 'VIIRS_CityLights_2012', '', 'png'),
]
MIN_Z = 1        # 이 합성은 z1 부터 발행된다
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


def is_image(blob):
    """JPEG(SOI) 또는 PNG 서명. GIBS 는 오류를 XML 로 주므로 확장자를 못 믿는다."""
    return blob.startswith(b'\xff\xd8') or blob.startswith(b'\x89PNG\r\n\x1a\n')


# 실패 이유를 삼키면 안 된다. 차단인지(연결 실패), URL 이 틀린 건지(404),
# 파이썬이 인증서를 못 읽는 건지(SSL) 구분이 안 되면 고칠 수가 없다.
LAST_ERROR = None


def fetch(url, tries=3):
    """타일 바이트를 준다. 실패하면 None 이고, 이유는 LAST_ERROR 에 남는다."""
    global LAST_ERROR
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as res:
                if res.status == 200:
                    return res.read()
                LAST_ERROR = f'HTTP {res.status}'
        except urllib.error.HTTPError as err:
            LAST_ERROR = f'HTTP {err.code} {err.reason}'
            if err.code == 404:
                return None          # 그 날짜에 없는 타일. 물러날 차례.
        except urllib.error.URLError as err:
            LAST_ERROR = f'{type(err.reason).__name__}: {err.reason}'
            if 'CERTIFICATE_VERIFY_FAILED' in str(err.reason):
                # macOS + conda 에서 흔하다. 재시도해도 같은 자리에서 막힌다.
                return None
        except Exception as err:
            LAST_ERROR = f'{type(err).__name__}: {err}'
        time.sleep(2 ** attempt)
    return None


def check():
    """타일 한 장으로 연결을 진단한다. 무엇이 막혔는지 사람 말로 찍는다."""
    for label, layer, when, ext in VARIANTS:
        url = BASE.format(layer=layer, time=when, matrix=MATRIX, ext=ext, z=1, y=0, x=0)
        blob = fetch(url, tries=1)
        print(f'{label:12s} {url}\n             → '
              f'{f"OK {len(blob)} bytes" if blob and is_image(blob) else (LAST_ERROR or "이미지 아님")}')
        if blob and is_image(blob):
            print('\n이 조합으로 받으면 된다.')
            return 0
    print()
    err = str(LAST_ERROR or '')
    if 'CERTIFICATE_VERIFY_FAILED' in err:
        print('파이썬이 인증서를 못 읽는 경우다. 네트워크는 멀쩡할 수 있다. 확인:')
        print(f'  curl -sS -o /dev/null -w "%{{http_code}}\\n" "{url}"')
        print('curl 이 200 이면 파이썬 쪽 문제다. macOS 기본 파이썬이면')
        print('  /Applications/Python\\ 3.*/Install\\ Certificates.command')
        print('conda 환경이면  pip install --upgrade certifi  후 다시.')
    elif err.startswith('HTTP 404'):
        print('URL 이 틀렸다 (레이어·날짜·타일매트릭스 이름). 무엇이 맞는지 확인:')
        print('  curl -s "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/'
              'WMTSCapabilities.xml" | grep -i -A2 black_marble | head -40')
    else:
        print('연결 자체가 안 된다 — 이 네트워크에서 NASA 가 막혔을 수 있다.')
        print('브라우저에서 위 URL 을 그대로 열어 보면 갈린다 (사진이 뜨면 파이썬 쪽 문제).')
        print('막힌 게 맞으면 이 스크립트는 건너뛰고 워커 프록시(/api/night-tile)로 간다.')
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-zoom', type=int, default=5,
                    help='받을 최대 줌 (기본 5). 한 단계 올릴 때마다 타일 수가 4배.')
    ap.add_argument('--force', action='store_true', help='이미 있는 타일도 다시 받는다')
    ap.add_argument('--check', action='store_true',
                    help='타일 한 장만 받아 보고 무엇이 막혔는지 진단한다')
    args = ap.parse_args()

    if args.check:
        return check()

    got = skipped = failed = total_bytes = 0
    # z0 은 어느 조합으로도 없다. 클라이언트도 minZoom 1 로 부른다.
    complete_z = MIN_Z - 1   # 한 장도 안 빠진 마지막 줌. 매니페스트에 이게 실린다.
    for z in range(MIN_Z, args.max_zoom + 1):
        failed_before = failed
        y0, y1 = lat_to_row(LAT_MAX, z), lat_to_row(LAT_MIN, z)
        for y in range(y0, y1 + 1):
            for x in range(2 ** z):
                path = os.path.join(OUT_ROOT, str(z), str(y), f'{x}.jpg')
                if os.path.exists(path) and not args.force:
                    skipped += 1
                    total_bytes += os.path.getsize(path)
                    continue
                blob = None
                for _, layer, when, ext in VARIANTS:
                    blob = fetch(BASE.format(layer=layer, time=when, matrix=MATRIX,
                                             ext=ext, z=z, y=y, x=x))
                    if blob and is_image(blob):
                        break
                    blob = None
                if not blob:
                    failed += 1
                    print(f'  실패 z{z}/{y}/{x} · {LAST_ERROR or "이유 불명"}', file=sys.stderr)
                    if failed == 1:
                        # 첫 실패에 바로 진단을 붙인다. 수백 줄 뒤에서 이유를
                        # 찾게 만들 이유가 없다.
                        print('  ↑ 진단: python3 tools/ops/fetch_night_tiles.py --check',
                              file=sys.stderr)
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as fh:
                    fh.write(blob)
                got += 1
                total_bytes += len(blob)
        if failed == failed_before and complete_z == z - 1:
            complete_z = z
        print(f'z{z} 완료 · 받음 {got} · 건너뜀 {skipped} · 실패 {failed} '
              f'· 누적 {total_bytes / 1e6:.1f}MB')

    # macro.js 는 이 매니페스트로 "받아 둔 타일이 어디까지 있나"를 판단한다.
    # 없으면 로컬 경로를 아예 건너뛰고 워커 프록시로 간다 -- 빠진 줌을 타일마다
    # 찔러 보는 낭비가 없다. 그래서 구멍 난 줌은 싣지 않는다.
    if complete_z >= MIN_Z:
        manifest = os.path.join(OUT_ROOT, 'manifest.json')
        os.makedirs(OUT_ROOT, exist_ok=True)
        with open(manifest, 'w') as fh:
            json.dump({
                'schema_version': 'night-tiles-v1',
                'source': 'NASA GIBS · VIIRS Black Marble',
                'variants_tried': [v[0] for v in VARIANTS],
                'min_zoom': MIN_Z,
                'max_zoom': complete_z,
                'lat_range': [LAT_MIN, LAT_MAX],
                'generated_at': time.strftime('%Y-%m-%d'),
            }, fh, indent=2)
        print(f'매니페스트: {os.path.normpath(manifest)} (max_zoom {complete_z})')

    print(f'\n끝. 받음 {got} · 건너뜀 {skipped} · 실패 {failed} '
          f'· 총 {total_bytes / 1e6:.1f}MB')
    print(f'저장 위치: {os.path.normpath(OUT_ROOT)}')
    if failed:
        print('실패분은 다시 돌리면 이어서 받는다.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
