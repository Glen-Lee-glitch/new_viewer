import pymysql
from datetime import datetime
import pytz
import pandas as pd
import traceback

from contextlib import closing

FETCH_EMAILS_COLUMNS = ['title', 'received_date', 'from_email_address', 'content']
FETCH_SUBSIDY_COLUMNS = ['RN', 'region', 'worker', 'name', 'special_note', 'file_status', 'original_filepath']

# MySQL 연결 정보
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}

def claim_subsidy_work(rn: str, worker: str) -> bool:
    if not rn:
        raise ValueError("rn must be provided")
    if not worker:
        raise ValueError("worker must be provided")

    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            connection.begin()
            try:
                with connection.cursor() as cursor:
                    lock_query = (
                        "SELECT worker FROM subsidy_applications "
                        "WHERE RN = %s FOR UPDATE"
                    )
                    cursor.execute(lock_query, (rn,))
                    row = cursor.fetchone()

                    if row is None:
                        connection.rollback()
                        return False

                    existing_worker = row[0]
                    if existing_worker:
                        connection.rollback()
                        return existing_worker == worker

                    update_query = (
                        "UPDATE subsidy_applications SET worker = %s, status = %s "
                        "WHERE RN = %s"
                    )
                    cursor.execute(update_query, (worker, '처리중', rn))
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False
def fetch_recent_subsidy_applications():
    """최근 접수된 지원금 신청 데이터를 조회하고 출력한다."""
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = (
                "SELECT sa.RN, sa.region, sa.worker, sa.name, sa.special_note, "
                "       CASE WHEN fp.original_filepath IS NULL OR fp.original_filepath = '' "
                "            THEN '부' "
                "            ELSE '여' "
                "       END AS file_status, "
                "       fp.original_filepath "
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
            return df

        print(df)
        return df

    except Exception:  # pragma: no cover - 긴급 디버깅용
        traceback.print_exc()
        return pd.DataFrame()

def test_fetch_emails():
    """emails 테이블 테스트 조회"""
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = (
                "SELECT title FROM emails "
                "ORDER BY received_date DESC "
                "LIMIT 30"
            )
            df = pd.read_sql(query, connection)

        if df.empty:
            print('조회된 데이터가 없습니다.')
            return

        for title in df['title']:
            print(title)

    except Exception:
        traceback.print_exc()

def get_worker_names():
    """
    workers 테이블에서 모든 작업자 이름(name) 리스트를 반환한다.
    """
    workers = []
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT name FROM workers"
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                workers = [row[0] for row in rows]
    except Exception:
        traceback.print_exc()
    return workers


if __name__ == "__main__":
    # fetch_recent_subsidy_applications()
    # test_fetch_emails()
    print(get_worker_names())