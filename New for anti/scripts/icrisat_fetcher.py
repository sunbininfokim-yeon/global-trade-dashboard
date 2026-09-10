import json
import requests
import time
import sys
import os

# 이 스크립트는 목적지 파일을 직접 'wb' 로 열어 받아쓰고 있었다. 그래서 시도
# 시작 즉시 멀쩡한 기존 파일이 0바이트로 잘리고, 전송이 중간에 끊기면 잘린
# 조각이 그 자리에 남았다. 실패해도 __main__ 이 반환값을 버려 종료코드는 0
# 이었고, 워크플로는 그 조각을 그대로 커밋했다 -- 실제로 6,152,192바이트
# (정확히 4096 블록 경계)에서 문자열이 끊긴 JSON 이 저장소에 들어와 있었다.
#
# 그래서 받는 곳과 두는 곳을 분리한다. 임시 파일로 받아 크기와 JSON 파싱을
# 모두 통과한 것만 os.replace 로 원자적으로 올린다. 한 번도 성공하지 못하면
# 목적지는 손대지 않고 0이 아닌 코드로 끝내, 나쁜 파일이 커밋되는 대신
# 워크플로가 빨갛게 실패한다.
def download_icrisat_patiently(url, output_path):
    target_size = 13296709  # 13.3 MB
    max_retries = 10

    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp_path = output_path + ".part"

    print(f"[{url}] 다운로드 시작 (대상 경로: {output_path})")

    for attempt in range(1, max_retries + 1):
        print(f"[{attempt}/{max_retries}] 데이터 다운로드 시도 중... (인내심 모드)")
        try:
            # 타임아웃: 연결 30초, 읽기 대기 300초(5분)
            with requests.get(url, stream=True, timeout=(30, 300)) as r:
                r.raise_for_status()

                downloaded = 0
                with open(tmp_path, 'wb') as f:
                    # 8KB씩 천천히 읽어오며 연결 유지
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            sys.stdout.write(f"\r받은 용량: {downloaded / 1024 / 1024:.2f} MB")
                            sys.stdout.flush()

                print("\n")
                declared = int(r.headers.get('Content-Length', 0))
                if not (downloaded >= target_size or (declared and downloaded == declared)):
                    print(f"⚠️ 불완전한 파일 수신 (받은 바이트: {downloaded}). 다시 시도합니다...")
                    continue

                # 크기가 맞아도 내용이 JSON 이 아닐 수 있다. 잘린 응답이
                # 저장소에 들어온 경로가 정확히 이것이므로 여기서 막는다.
                try:
                    with open(tmp_path, 'rb') as f:
                        json.load(f)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"⚠️ JSON 파싱 실패 ({e}). 받은 파일을 버리고 다시 시도합니다...")
                    continue

                os.replace(tmp_path, output_path)
                print("✅ ICRISAT 데이터 다운로드 성공 및 검증 완료!")
                return True

        except requests.exceptions.RequestException as e:
            print(f"\n❌ 네트워크/타임아웃 오류 발생: {e}")

        # 지수 백오프
        sleep_time = min(120, 10 * attempt)
        print(f"{sleep_time}초 대기 후 재시도합니다...")
        time.sleep(sleep_time)

    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    print("🚨 최대 재시도 횟수를 초과하여 다운로드에 실패했습니다.")
    print("   기존 파일은 그대로 두었습니다.")
    return False

if __name__ == "__main__":
    # ICRISAT 비공개 API URL (1966년 기준 병합 데이터 - 작물 생산량)
    target_url = "http://data.icrisat.org/dldAPI/apportioned/area-production-yield"
    
    # 프로젝트 루트 기준 public/data 에 저장
    # 스크립트 위치가 scripts/ 내부에 있다고 가정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base_dir, "public", "data", "icrisat_crop_production.json")
    
    # 종료코드를 넘긴다. 이게 없어서 다운로드가 실패해도 워크플로는 성공으로
    # 보였고, 그 다음 단계가 잘린 파일을 커밋했다.
    sys.exit(0 if download_icrisat_patiently(target_url, out_path) else 1)
