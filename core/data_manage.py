import json
import os
from pathlib import Path

# 기본 DB 설정
DB_CONFIG = {
    "host": "192.168.0.92",
    "database": "postgres",
    "user": "postgres",
    "password": "greet1202!@",
    "port": "5432",
    "connect_timeout": 3
}

# 샘플 데이터 모드 플래그
USE_SAMPLE_DATA = False

def set_use_sample_data(use: bool):
    """샘플 데이터 사용 여부를 설정한다."""
    global USE_SAMPLE_DATA
    USE_SAMPLE_DATA = use
    if use:
        print("[INFO] 샘플 데이터 모드가 활성화되었습니다.")
    else:
        print("[INFO] 로컬 데이터베이스 모드가 활성화되었습니다.")

def is_sample_data_mode() -> bool:
    """현재 샘플 데이터 모드인지 확인한다."""
    return USE_SAMPLE_DATA

def get_sample_data() -> dict:
    """sample_data.json 파일을 읽어서 반환한다."""
    # sample 폴더 내의 sample_data.json 경로
    sample_path = Path(__file__).parent.parent / "sample" / "sample_data.json"
    if not sample_path.exists():
        print(f"[ERROR] 샘플 데이터 파일을 찾을 수 없습니다: {sample_path}")
        return {"rns": [], "emails": [], "workers": [], "analysis_results": []}
    
    try:
        with open(sample_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 샘플 데이터 로드 중 오류 발생: {e}")
        return {"rns": [], "emails": [], "workers": [], "analysis_results": []}

# db_key.json 파일이 있으면 설정을 덮어씌움
KEY_FILE_PATH = "db_key.json"
if os.path.exists(KEY_FILE_PATH):
    try:
        with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
            external_config = json.load(f)
            DB_CONFIG.update(external_config)
            print(f"[INFO] '{KEY_FILE_PATH}' 파일에서 DB 설정을 로드했습니다.")
    except Exception as e:
        print(f"[WARNING] '{KEY_FILE_PATH}' 로드 중 오류 발생: {e}")
