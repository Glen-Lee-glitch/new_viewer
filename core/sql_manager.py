import pymysql
from datetime import datetime
import pytz
import pandas as pd
import traceback

from contextlib import closing

# MySQL 연결 정보
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}

def fetch_recent_subsidy_applications():
    """최근 접수된 지원금 신청 데이터를 조회하고 출력한다."""
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = (
                "SELECT sa.RN, sa.region, sa.worker, "
                "       CASE WHEN fp.file_path IS NULL OR fp.file_path = '' "
                "            THEN '부' "
                "            ELSE '여' "
                "       END AS file_status "
                "FROM subsidy_applications sa "
                "LEFT JOIN filepath fp ON fp.RN = sa.RN "
                "WHERE recent_received_date >= %s "
                "ORDER BY recent_received_date DESC "
                "LIMIT 10"
            )
            params = ('2025-09-30 09:00',)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            print('조회된 데이터가 없습니다.')
            return df[['RN', 'region', 'worker', 'file_status']]

        print(df[['RN', 'region', 'worker', 'file_status']])
        return df[['RN', 'region', 'worker', 'file_status']]

    except Exception:  # pragma: no cover - 긴급 디버깅용
        traceback.print_exc()
        return pd.DataFrame(columns=['RN', 'region', 'worker', 'file_status'])

if __name__ == "__main__":
    fetch_recent_subsidy_applications()