import requests
import time
import sys
import os

def download_icrisat_patiently(url, output_path):
    target_size = 13296709  # 13.3 MB
    max_retries = 10
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"[{url}] 다운로드 시작 (대상 경로: {output_path})")
    
    for attempt in range(1, max_retries + 1):
        print(f"[{attempt}/{max_retries}] 데이터 다운로드 시도 중... (인내심 모드)")
        try:
            # 타임아웃: 연결 30초, 읽기 대기 300초(5분)
            with requests.get(url, stream=True, timeout=(30, 300)) as r:
                r.raise_for_status()
                
                downloaded = 0
                with open(output_path, 'wb') as f:
                    # 8KB씩 천천히 읽어오며 연결 유지
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            sys.stdout.write(f"\r받은 용량: {downloaded / 1024 / 1024:.2f} MB")
                            sys.stdout.flush()
                
                print("\n")
                if downloaded >= target_size or downloaded == int(r.headers.get('Content-Length', 0)):
                    print("✅ ICRISAT 데이터 다운로드 성공 및 검증 완료!")
                    return True
                else:
                    print(f"⚠️ 불완전한 파일 수신 (받은 바이트: {downloaded}). 다시 시도합니다...")
                    
        except requests.exceptions.RequestException as e:
            print(f"\n❌ 네트워크/타임아웃 오류 발생: {e}")
        
        # 지수 백오프
        sleep_time = min(120, 10 * attempt)
        print(f"{sleep_time}초 대기 후 재시도합니다...")
        time.sleep(sleep_time)

    print("🚨 최대 재시도 횟수를 초과하여 다운로드에 실패했습니다.")
    return False

if __name__ == "__main__":
    # ICRISAT 비공개 API URL (1966년 기준 병합 데이터 - 작물 생산량)
    target_url = "http://data.icrisat.org/dldAPI/apportioned/area-production-yield"
    
    # 프로젝트 루트 기준 public/data 에 저장
    # 스크립트 위치가 scripts/ 내부에 있다고 가정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base_dir, "public", "data", "icrisat_crop_production.json")
    
    download_icrisat_patiently(target_url, out_path)
