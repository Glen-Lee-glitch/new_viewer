from typing import Any, Dict, Optional
from supabase import create_client, Client
from datetime import date, datetime
import sqlite3

# Supabase 연결 정보
url: str = "https://qehjythxhuaxkuotowjq.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFlaGp5dGh4aHVheGt1b3Rvd2pxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjA0ODYwMTYsImV4cCI6MjA3NjA2MjAxNn0.VbzUwkXInOUS4Afj11F0wu_mn244glyIXsDHmE7NDho"

db_path = r"\\DESKTOP-R4MM6IR\Users\HP\Desktop\그리트_공유\파일\data.db"

def insert_or_update(single_units: int, another_quarter_units: int) -> Optional[Dict[str, Any]]:
    """
    tesla_retail_pipeline 테이블에서 오늘 날짜의 행을 업데이트하거나 삽입합니다.
    
    Args:
        single_units: 단일 유닛 수
        another_quarter_units: 분기 외 유닛 수
    
    Returns:
        성공 시 업데이트/삽입된 데이터 딕셔너리, 실패 시 None
    """
    try:
        # Supabase 클라이언트 초기화
        supabase: Client = create_client(url, key)
        
        # 오늘 날짜 가져오기
        today = date.today()
        today_str = today.isoformat()
        
        # 먼저 해당 날짜의 데이터 조회
        existing_data = supabase.table('tesla_retail_pipeline')\
            .select('*')\
            .eq('date', today_str)\
            .execute()
        
        # 업데이트할 데이터
        data: Dict[str, Any] = {
            'date': today_str,
            'single_units': single_units,
            'another_quarter_units': another_quarter_units
        }
        
        # 기존 데이터가 있으면 업데이트, 없으면 삽입
        if existing_data.data and len(existing_data.data) > 0:
            # 업데이트
            response = supabase.table('tesla_retail_pipeline')\
                .update(data)\
                .eq('date', today_str)\
                .execute()
        else:
            # 삽입
            response = supabase.table('tesla_retail_pipeline')\
                .insert(data)\
                .execute()
        
        return response.data[0] if response.data else None
        
    except Exception as e:
        print(f"Error in insert_or_update: {e}")
        return None

def check_existing_data(rn_num: str) -> bool:
    """
    pipeline 테이블에서 RN 번호와 날짜를 확인하여 2025-09-30 이전 데이터 존재 여부를 확인합니다.
    
    Args:
        rn_num: 확인할 RN 번호
    
    Returns:
        True: 2025-09-30 이전 데이터가 존재하는 경우
        False: 그렇지 않은 경우
    """
    try:
        # SQLite 데이터베이스 연결 (읽기 전용 모드)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        # RN 번호와 날짜 조건으로 조회
        query = """
            SELECT COUNT(*) 
            FROM pipeline 
            WHERE RN = ? AND 날짜 < '2025-09-30'
        """
        
        cursor.execute(query, (rn_num,))
        result = cursor.fetchone()
        
        conn.close()
        
        # 결과가 0보다 크면 True 반환
        return result[0] > 0
        
    except Exception as e:
        print(f"Error in check_existing_data: {e}")
        return False


if __name__ == "__main__":
    # # 테스트 1: insert_or_update
    # print("=" * 50)
    # print("Testing insert_or_update with single_units=56, another_quarter_units=0...")
    # result = insert_or_update(single_units=56, another_quarter_units=0)
    
    # if result:
    #     print(f"✓ Success! Result: {result}")
    # else:
    #     print("✗ Failed or no data returned")
    
    # 테스트 2: check_existing_data
    print("=" * 50)
    print("Testing check_existing_data...")
    test_rn = "RN125846562"  # 테스트용 RN 번호, 실제로 확인할 번호로 변경 가능
    exists = check_existing_data(test_rn)
    
    if exists:
        print(f"Yes - Found data before 2025-09-30 for RN: {test_rn}")
    else:
        print(f"No - No data found before 2025-09-30 for RN: {test_rn}")
