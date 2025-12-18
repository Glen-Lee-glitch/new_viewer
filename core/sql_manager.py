import pymysql
import psycopg2
import psycopg2.extras
from core.data_manage import DB_CONFIG
from datetime import datetime, date, time, timedelta
import pytz
import pandas as pd
import traceback
import json
import warnings

from contextlib import closing

# pandas read_sql 경고 억제
warnings.filterwarnings('ignore', message='pandas only supports SQLAlchemy', category=UserWarning)

FETCH_EMAILS_COLUMNS = ['title', 'received_date', 'from_email_address', 'content']
FETCH_SUBSIDY_COLUMNS = ['RN', 'region', 'worker', 'name', 'special_note', 'file_status', 'original_filepath', 'recent_thread_id', 'file_rendered']

def claim_subsidy_work(rn: str, worker_id: int) -> bool:
    """
    지원 테이블에서 작업을 클레임(할당)한다.
    
    Args:
        rn: RN 번호
        worker_id: 작업자 ID
        
    Returns:
        True: 작업 할당 성공 (NULL이었거나 자신이 이미 할당된 경우)
        False: 다른 작업자가 이미 할당된 경우
    """
    if not rn or worker_id is None:
        return False
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # psycopg2는 자동으로 트랜잭션을 시작하므로 begin() 호출 불필요
            try:
                with connection.cursor() as cursor:
                    # 현재 worker_id 조회
                    select_query = "SELECT worker_id FROM rns WHERE \"RN\" = %s"
                    cursor.execute(select_query, (rn,))
                    row = cursor.fetchone()
                    
                    if not row:
                        # RN이 존재하지 않음
                        connection.rollback()
                        return False
                    
                    current_worker_id = row[0]
                    
                    # worker_id가 NULL이면 현재 작업자로 할당
                    if current_worker_id is None:
                        update_query = "UPDATE rns SET worker_id = %s WHERE \"RN\" = %s"
                        cursor.execute(update_query, (worker_id, rn))
                        connection.commit()
                        print(f"[작업 할당] RN: {rn}, worker_id: {worker_id} (NULL -> 할당)")
                        return True
                    
                    # 이미 자신이 할당된 경우
                    if current_worker_id == worker_id:
                        print(f"[작업 할당] RN: {rn}, worker_id: {worker_id} (이미 할당됨)")
                        connection.rollback()  # 커밋 불필요
                        return True
                    
                    # 다른 작업자가 할당된 경우
                    print(f"[작업 할당 실패] RN: {rn}, 현재 worker_id: {current_worker_id}, 요청 worker_id: {worker_id}")
                    connection.rollback()
                    return False
            except Exception:
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False


def _build_subsidy_query_base():
    """지원금 신청 데이터 조회용 기본 쿼리 문자열을 반환한다. (PostgreSQL 버전)"""
    return (
        'SELECT '
        '  r."RN" AS "RN", '
        '  r.region, '
        '  w.worker_name AS worker, '
        '  r.customer AS name, '
        '  array_to_string(r.special, \', \') AS special_note, '
        '  r.last_received_date AS recent_received_date, '
        '  r.file_path AS finished_file_path, '
        '  e.original_pdf_path AS original_filepath, '
        '  r.recent_thread_id, '
        '  0 AS file_rendered, '
        '  0 AS "구매계약서", '
        '  0 AS "초본", '
        '  0 AS "공동명의", '
        '  0 AS "다자녀", '
        '  CASE WHEN r.is_urgent THEN 1 ELSE 0 END AS urgent, '
        '  r.mail_count, '
        '  NULL AS child_birth_date, '
        '  NULL AS issue_date, '
        '  0 AS chobon, '
        '  NULL AS ai_계약일자, '
        '  NULL AS ai_이름, '
        '  NULL AS 전화번호, '
        '  NULL AS 이메일, '
        '  r.model AS 차종, '
        '  NULL AS page_number, '
        '  NULL AS chobon_name, '
        '  NULL AS chobon_birth_date, '
        '  NULL AS chobon_address_1, '
        '  0 AS is_법인, '
        '  CASE WHEN r.all_ai THEN 1 ELSE 0 END AS all_ai, '
        '  \'\' AS outlier, '
        '  \'\' AS result '
        'FROM rns r '
        'LEFT JOIN emails e ON r.recent_thread_id = e.thread_id '
        'LEFT JOIN workers w ON r.worker_id = w.worker_id '
    )

def fetch_recent_subsidy_applications():
    """최근 접수된 지원금 신청 데이터를 조회하고 출력한다. (PostgreSQL 버전)"""
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = _build_subsidy_query_base() + (
                'WHERE r.last_received_date >= %s '
                'ORDER BY r.last_received_date DESC '
                'LIMIT 30'
            )
            params = ('2025-01-01 00:00:00',)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            print('조회된 데이터가 없습니다.')
            return df

        return df

    except Exception:
        traceback.print_exc()
        return pd.DataFrame()


def fetch_today_subsidy_applications_by_worker(worker_id: int) -> pd.DataFrame:
    """
    이전 영업일 18시 이후의 지원금 신청 데이터 중
    특정 작업자(worker_id)에 할당된 데이터를 조회한다. (PostgreSQL 버전)
    """
    if worker_id is None:
        return pd.DataFrame()

    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            threshold_dt = get_previous_business_day_after_18h()
            if threshold_dt is not None:
                threshold_str = threshold_dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # fallback: 어제 18시
                fallback_dt = datetime.now() - timedelta(days=1)
                threshold_str = fallback_dt.replace(hour=18, minute=0, second=0, microsecond=0).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            query = _build_subsidy_query_base() + (
                'WHERE r.last_received_date >= %s '
                '  AND r.worker_id = %s '
                'ORDER BY r.last_received_date DESC '
                'LIMIT 30'
            )
            params = (threshold_str, worker_id)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            print('조회된 데이터가 없습니다.')
            return df

        return df

    except Exception:
        traceback.print_exc()
        return pd.DataFrame()


def fetch_today_unfinished_subsidy_applications() -> pd.DataFrame:
    """
    이전 영업일 18시 이후의 지원금 신청 데이터 중
    작업자가 할당되지 않은 데이터를 조회한다. (PostgreSQL 버전)
    """
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            threshold_dt = get_previous_business_day_after_18h()
            if threshold_dt is not None:
                threshold_str = threshold_dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # fallback: 어제 18시
                fallback_dt = datetime.now() - timedelta(days=1)
                threshold_str = fallback_dt.replace(hour=18, minute=0, second=0, microsecond=0).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            query = _build_subsidy_query_base() + (
                'WHERE r.last_received_date >= %s '
                '  AND r.worker_id IS NULL '
                'ORDER BY r.last_received_date DESC '
                'LIMIT 30'
            )
            params = (threshold_str,)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            print('조회된 데이터가 없습니다.')
            return df

        return df

    except Exception:
        traceback.print_exc()
        return pd.DataFrame()


def fetch_application_data_by_rn(rn: str) -> dict | None:
    """
    특정 RN 번호로 지원금 신청 및 이메일 정보를 조회하여 딕셔너리로 반환한다.
    (PdfLoadWidget에서 직접 열기 기능용)
    """
    if not rn:
        return None

    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = (
                "SELECT sa.RN, sa.region, sa.worker, sa.name, sa.special_note, "
                "       sa.finished_file_path, "  # finished_file_path 추가
                "       e.attached_file_path AS original_filepath, "
                "       sa.recent_thread_id, "
                "       e.file_rendered, "
                "       sa.urgent, "
                "       sa.mail_count, "
                "       gr.구매계약서, gr.초본, gr.공동명의, gr.다자녀, "
                "       d.child_birth_date, cb.issue_date AS issue_date, " # cb.issue_date를 issue_date로 명시적 앨리어싱
                "       cb.chobon, "
                "       c.ai_계약일자, c.ai_이름, c.전화번호, c.이메일, c.차종, c.page_number, "
                "       cb.name AS chobon_name, cb.birth_date AS chobon_birth_date, cb.address_1 AS chobon_address_1, "
                "       biz.is_법인 "
                "FROM subsidy_applications sa "
                "LEFT JOIN emails e ON sa.recent_thread_id = e.thread_id "
                "LEFT JOIN gemini_results gr ON sa.RN COLLATE utf8mb4_unicode_ci = gr.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_다자녀 d ON sa.RN COLLATE utf8mb4_unicode_ci = d.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_초본 cb ON sa.RN COLLATE utf8mb4_unicode_ci = cb.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_구매계약서 c ON sa.RN COLLATE utf8mb4_unicode_ci = c.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_사업자등록증 biz ON sa.RN COLLATE utf8mb4_unicode_ci = biz.RN COLLATE utf8mb4_unicode_ci "
                "WHERE sa.RN = %s"
            )
            
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                columns = [col[0].strip() for col in cursor.description]
                row = cursor.fetchone()
                
                print(f"[디버그 sql_manager] fetch_application_data_by_rn - SQL Columns: {columns}")
                print(f"[디버그 sql_manager] fetch_application_data_by_rn - SQL Row: {row}")

                if not row:
                    return None
                
                result = dict(zip(columns, row))
                
                # 이상치(outlier) 계산 로직 (fetch_recent_subsidy_applications의 로직 간소화 적용)
                # 필요하다면 여기서 outlier 계산 로직을 추가하거나, 기본값만 설정
                result['outlier'] = '' 
                # print(f"[디버그 sql_manager] fetch_application_data_by_rn - 초기 result[outlier]: {result['outlier']}")
                # print(f"[디버그 sql_manager] fetch_application_data_by_rn - issue_date in result: {'issue_date' in result}, issue_date value: {result.get('issue_date')}")

                # 계약일자 이상치 체크
                if result['outlier'] != 'O':
                    try:
                        ai_계약일자 = result.get('ai_계약일자')
                        # print(f"[디버그 sql_manager] ai_계약일자: {ai_계약일자}")
                        if ai_계약일자 and isinstance(ai_계약일자, (str, datetime, date, pd.Timestamp)):
                            contract_date_obj = None
                            if isinstance(ai_계약일자, str):
                                try:
                                    contract_date_obj = datetime.strptime(ai_계약일자.split()[0], "%Y-%m-%d").date()
                                except ValueError:
                                    pass
                            elif isinstance(ai_계약일자, (datetime, date)):
                                contract_date_obj = ai_계약일자 if isinstance(ai_계약일자, date) else ai_계약일자.date()
                            elif isinstance(ai_계약일자, pd.Timestamp):
                                contract_date_obj = ai_계약일자.date()

                            if contract_date_obj and contract_date_obj < date(2025, 1, 1):
                                result['outlier'] = 'O'
                    except Exception:
                        traceback.print_exc()

                # 2. 초본 issue_date 체크
                if result['outlier'] != 'O' and result.get('초본') == 1 and result.get('issue_date'):
                     try:
                        issue_date = result['issue_date']
                        kst = pytz.timezone('Asia/Seoul')
                        today = datetime.now(kst).date()
                        
                        issue_date_obj = None
                        if isinstance(issue_date, str):
                            try:
                                issue_date_obj = datetime.strptime(issue_date, "%Y-%m-%d").date() # ISO 형식 시도
                            except ValueError:
                                try:
                                    issue_date_obj = datetime.strptime(issue_date.split()[0], "%Y-%m-%d").date()
                                except ValueError:
                                    pass
                        elif isinstance(issue_date, (datetime, date)):
                            issue_date_obj = issue_date if isinstance(issue_date, date) else issue_date.date()
                        elif isinstance(issue_date, pd.Timestamp):
                            issue_date_obj = issue_date.date()

                        # print(f"[디버그 sql_manager] 초본 issue_date 체크 - issue_date_obj: {issue_date_obj}, today: {today}")
                        if issue_date_obj:
                            days_diff = (today - issue_date_obj).days
                            # print(f"[디버그 sql_manager] 초본 issue_date 체크 - days_diff: {days_diff}")
                            if days_diff >= 31:
                                result['outlier'] = 'O'
                                # print(f"[디버그 sql_manager] 초본 issue_date 체크 - outlier 설정됨: {result['outlier']}")
                     except Exception:
                         traceback.print_exc()

                # 3. 다자녀 이상치 체크 (2명 이상)
                # ... existing code ...

                return result

    except Exception:
        traceback.print_exc()
        return None

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
    workers 테이블에서 모든 작업자 이름(worker_name) 리스트를 반환한다. (PostgreSQL 버전)
    """
    workers = []
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "SELECT worker_name FROM workers ORDER BY worker_name"
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                workers = [row[0] for row in rows]
    except Exception:
        traceback.print_exc()
    return workers

def get_worker_id_by_name(worker_name: str) -> int | None:
    """
    workers 테이블에서 작업자 이름(worker_name)으로 worker_id를 조회한다. (PostgreSQL 버전)
    
    Args:
        worker_name: 작업자 이름
        
    Returns:
        worker_id (int) 또는 None (존재하지 않는 경우)
    """
    if not worker_name:
        return None
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "SELECT worker_id FROM workers WHERE worker_name = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (worker_name,))
                row = cursor.fetchone()
                return row[0] if row else None
    except Exception:
        traceback.print_exc()
        return None

def get_mail_content_by_thread_id(thread_id: str) -> str:
    """
    thread_id로 emails 테이블에서 content를 조회한다. (PostgreSQL 버전)
    """
    if not thread_id:
        return ""
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "SELECT content FROM emails WHERE thread_id = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (thread_id,))
                row = cursor.fetchone()
                return row[0] if row else ""
    except Exception:
        traceback.print_exc()
        return ""

def get_email_by_thread_id(thread_id: str) -> dict | None:
    """
    thread_id로 emails 테이블에서 title과 content를 조회하여 딕셔너리로 반환한다. (PostgreSQL 버전)
    
    Args:
        thread_id: 이메일 thread_id
        
    Returns:
        {'title': str, 'content': str} 또는 None
    """
    if not thread_id:
        return None
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "SELECT title, content FROM emails WHERE thread_id = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (thread_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'title': row[0] if row[0] else '',
                        'content': row[1] if row[1] else ''
                    }
                return None
    except Exception:
        traceback.print_exc()
        return None

def get_daily_worker_progress():
    """
    daily_application 테이블에서 type이 '지원'인 것 중 작업자별 건수를 조회한다.
    """
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT worker, COUNT(*) as count 
                FROM daily_application 
                WHERE type = '지원' AND worker IS NOT NULL
                GROUP BY worker 
                ORDER BY count DESC
            """
            df = pd.read_sql(query, connection)
            return df
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def get_daily_worker_payment_progress():
    """
    daily_application 테이블에서 type이 '지급'인 것 중 작업자별 건수를 조회한다.
    """
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT worker, COUNT(*) as count 
                FROM daily_application 
                WHERE type = '지급' AND worker IS NOT NULL
                GROUP BY worker 
                ORDER BY count DESC
            """
            df = pd.read_sql(query, connection)
            return df
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def get_today_completed_subsidies(worker: str = None) -> list:
    """
    오늘 '지원' 처리된 지원금 신청 목록 (지역, 신청날짜)을 반환한다.
    daily_application 테이블에서 조회한다.
    
    Args:
        worker: 작업자 이름 (선택사항, 제공되면 해당 작업자만 필터링)
    
    Returns:
        오늘 완료된 (지역, 신청날짜) 튜플의 리스트
    """
    try:
        # 한국 시간 (KST) 생성
        kst = pytz.timezone('Asia/Seoul')
        today = datetime.now(kst).date()
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            # worker 파라미터에 따른 쿼리 분기
            if worker:
                query = """
                    SELECT region, apply_date
                    FROM daily_application 
                    WHERE type = '지원' 
                    AND DATE(apply_date) = %s
                    AND worker = %s
                    AND region IS NOT NULL
                    ORDER BY apply_date DESC, rn DESC
                """
                params = (today, worker)
            else:
                query = """
                    SELECT region, apply_date
                    FROM daily_application 
                    WHERE type = '지원' 
                    AND DATE(apply_date) = %s
                    AND region IS NOT NULL
                    ORDER BY apply_date DESC, rn DESC
                """
                params = (today,)
            
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return rows
                
    except Exception:
        traceback.print_exc()
        return []

def fetch_gemini_contract_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '구매계약서' JSONB 컬럼에서 RN으로 데이터를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # JSONB에서 필드 추출
            query = """
                SELECT 
                    "구매계약서"->>'order_date' AS ai_계약일자,
                    "구매계약서"->>'customer_name' AS ai_이름,
                    "구매계약서"->>'phone_number' AS 전화번호,
                    "구매계약서"->>'email' AS 이메일,
                    "구매계약서"->>'vehicle_config' AS vehicle_config
                FROM analysis_results
                WHERE "RN" = %s AND "구매계약서" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'ai_계약일자': row[0],
                        'ai_이름': row[1],
                        '전화번호': row[2],
                        '이메일': row[3],
                        'vehicle_config': row[4]
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def check_gemini_flags(rn: str) -> dict:
    """
    analysis_results 테이블과 rns 테이블에서 RN으로 플래그들을 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # 1. analysis_results 테이블의 JSONB 컬럼 존재 여부 확인
            # 2. rns 테이블의 special 배열에 특정 키워드가 포함되어 있는지 확인
            # 공동명의 여부는 rns.special 배열에 '공동명의'가 있거나, analysis_results."초본"->'second_person'이 존재하면 True
            query = """
                SELECT 
                    a."구매계약서" IS NOT NULL AS "구매계약서",
                    (a."청년생애" IS NOT NULL OR '청년생애' = ANY(r.special)) AS "청년생애",
                    (a."다자녀" IS NOT NULL OR '다자녀' = ANY(r.special)) AS "다자녀",
                    ('공동명의' = ANY(r.special) OR (a."초본" IS NOT NULL AND a."초본"->>'second_person' IS NOT NULL)) AS "공동명의",
                    a."초본" IS NOT NULL AS "초본",
                    ('개인사업자' = ANY(r.special)) AS "개인사업자",
                    ('법인' = ANY(r.special) OR a."법인" IS NOT NULL) AS "법인"
                FROM analysis_results a
                JOIN rns r ON a."RN" = r."RN"
                WHERE a."RN" = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        '구매계약서': bool(row[0]),
                        '청년생애': bool(row[1]),
                        '다자녀': bool(row[2]),
                        '공동명의': bool(row[3]),
                        '초본': bool(row[4]),
                        '개인사업자': bool(row[5]),
                        '법인': bool(row[6])
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_youth_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '청년생애' JSONB 컬럼에서 RN으로 데이터를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # JSONB 필드 추출
            query = """
                SELECT 
                    "청년생애"->'local_name',
                    "청년생애"->'range_date'
                FROM analysis_results
                WHERE "RN" = %s AND "청년생애" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    # JSONB는 자동으로 파이썬 객체로 변환됨
                    local_name = row[0]
                    range_date = row[1]
                    
                    # 만약 문자열로 온다면 파싱
                    if isinstance(local_name, str): local_name = json.loads(local_name)
                    if isinstance(range_date, str): range_date = json.loads(range_date)
                    
                    return {
                        'local_name': local_name if local_name else [],
                        'range_date': range_date if range_date else []
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_chobon_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '초본' JSONB 컬럼에서 RN으로 데이터를 조회한다. (PostgreSQL 버전)
    공동명의인 경우 'first_person' 내부 데이터를 사용한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # first_person 키가 있으면 그 안의 값을, 없으면 최상위 값을 조회
            query = """
                SELECT 
                    COALESCE("초본"->'first_person'->>'name', "초본"->>'name') AS name,
                    COALESCE("초본"->'first_person'->>'birth_date', "초본"->>'birth_date') AS birth_date,
                    COALESCE("초본"->'first_person'->>'address_1', "초본"->>'address_1') AS address_1,
                    COALESCE("초본"->'first_person'->>'address_2', "초본"->>'address_2') AS address_2,
                    COALESCE("초본"->'first_person'->>'gender', "초본"->>'gender') AS gender
                FROM analysis_results
                WHERE "RN" = %s AND "초본" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'name': row[0],
                        'birth_date': row[1],
                        'address_1': row[2],
                        'address_2': row[3],
                        'gender': row[4]
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_multichild_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '다자녀' JSONB 컬럼에서 RN으로 데이터를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # "다자녀"->'child_birth_date'를 추출 (JSONB 배열)
            query = """
                SELECT "다자녀"->'child_birth_date'
                FROM analysis_results
                WHERE "RN" = %s AND "다자녀" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    # row[0]는 이미 파이썬 리스트일 가능성이 높음 (psycopg2가 JSONB 변환 지원)
                    # 만약 문자열로 온다면 json.loads 필요
                    child_birth_date = row[0]
                    if isinstance(child_birth_date, str):
                        child_birth_date = json.loads(child_birth_date)
                    
                    return {
                        'child_birth_date': child_birth_date if child_birth_date else []
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_business_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '사업자등록증' JSONB 컬럼에서 RN으로 데이터를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # 실제 JSONB 키는 한글 키 사용 (대표자, 사업자명, 사업장주소, 사업자등록번호)
            query = """
                SELECT 
                    "사업자등록증"->>'is_corporation',
                    "사업자등록증"->>'corporation_name',
                    "사업자등록증"->>'대표자',
                    "사업자등록증"->>'registration_number',
                    "사업자등록증"->>'사업자등록번호',
                    "사업자등록증"->>'사업자명',
                    "사업자등록증"->>'사업장주소'
                FROM analysis_results
                WHERE "RN" = %s AND "사업자등록증" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    # is_법인 처리 (문자열 'true'/'false' 또는 불리언)
                    is_corp = row[0]
                    if isinstance(is_corp, str):
                        is_corp = is_corp.lower() == 'true'
                    elif is_corp is None:
                        is_corp = False
                    else:
                        is_corp = bool(is_corp)

                    # 한글 키와 영문 키 모두 처리 (하위 호환성)
                    기관명 = row[1] if row[1] else None
                    대표자 = row[2] if row[2] else None
                    법인등록번호 = row[3] if row[3] else None
                    사업자등록번호 = row[4] if row[4] else None
                    사업자명 = row[5] if row[5] else None
                    사업장주소 = row[6] if row[6] else None
                    
                    return {
                        'is_법인': is_corp,
                        '기관명': 기관명,  # 법인명을 기관명으로 매핑
                        '대표자': 대표자,
                        '법인등록번호': 법인등록번호,  # 등록번호를 법인등록번호로 매핑
                        '사업자등록번호': 사업자등록번호,
                        '개인사업자명': 사업자명,  # 사업자명을 개인사업자명으로 매핑
                        '법인주소': 사업장주소  # 사업장주소를 법인주소로 매핑
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_corporation_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '법인' JSONB 컬럼에서 RN으로 데이터를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT 
                    "법인"->>'법인명',
                    "법인"->>'등록번호',
                    "법인"->>'법인주소'
                FROM analysis_results
                WHERE "RN" = %s AND "법인" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        '법인명': row[0] if row[0] else '',
                        '등록번호': row[1] if row[1] else '',
                        '법인주소': row[2] if row[2] else ''
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_joint_results(rn: str) -> dict:
    """
    analysis_results 테이블의 '초본' JSONB 컬럼에서 공동명의 데이터를 조회한다. (PostgreSQL 버전)
    first_person과 second_person 정보를 모두 반환한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # 초본 JSONB에서 first_person, second_person 추출
            # second_person이 없거나 null이면 공동명의가 아닐 수 있음
            query = """
                SELECT 
                    "초본"->'first_person'->>'name' AS first_person_name,
                    "초본"->'first_person'->>'birth_date' AS first_person_birth_date,
                    "초본"->'first_person'->>'gender' AS first_person_gender,
                    "초본"->'first_person'->>'address_1' AS first_person_address_1,
                    "초본"->'first_person'->>'address_2' AS first_person_address_2,
                    "초본"->'second_person'->>'name' AS second_person_name,
                    "초본"->'second_person'->>'birth_date' AS second_person_birth_date,
                    "초본"->'second_person'->>'gender' AS second_person_gender,
                    "초본"->'second_person'->>'address_1' AS second_person_address_1,
                    "초본"->'second_person'->>'address_2' AS second_person_address_2
                FROM analysis_results
                WHERE "RN" = %s AND "초본" IS NOT NULL
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    # 데이터가 하나라도 있어야 의미 있음 (특히 second_person)
                    # 하지만 호출부에서 공동명의 플래그를 확인하고 호출하므로 그대로 반환
                    return {
                        'name': row[0],
                        'birth_date': row[1],
                        'gender': row[2],
                        'address_1': row[3],
                        'address_2': row[4],
                        'second_person_name': row[5],
                        'second_person_birth_date': row[6],
                        'second_person_gender': row[7],
                        'second_person_address_1': row[8],
                        'second_person_address_2': row[9]
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_subsidy_model(rn: str) -> str:
    """
    subsidy_applications 테이블에서 RN으로 차종(model) 정보를 조회한다.
    """
    if not rn:
        return ""
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT model FROM subsidy_applications WHERE RN = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                return row[0] if row and row[0] else ""
    except Exception:
        traceback.print_exc()
        return ""

def fetch_subsidy_region(rn: str) -> str:
    """
    rns 테이블에서 RN으로 지역(region) 정보를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return ""
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = 'SELECT region FROM rns WHERE "RN" = %s'
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                return row[0] if row and row[0] else ""
    except Exception:
        traceback.print_exc()
        return ""

def fetch_subsidy_amount(region: str, model: str, rn: str = None) -> str:
    """
    지역과 모델명으로 subsidy_amounts 테이블에서 보조금 금액을 조회한다.
    RN이 제공되면 다자녀 추가 보조금을 합산한다.
    
    Args:
        region: 지역명
        model: 모델명
        rn: RN 번호 (선택사항, 다자녀 확인용)
        
    Returns:
        포맷팅된 보조금 금액 문자열 (예: "1,230,000원") 또는 빈 문자열
    """
    if not region or not model:
        return ""
    
    # 모델명 매핑
    model_mapping = {
        'Model 3 R': 'model_3_rwd_2025',
        'Model Y R': 'model_y_new_rwd',
        'Model Y L': 'model_y_lr_battery_change',
        # 형식상 매핑
        'Model 3 L': 'model_3_lr',
        'Model 3 P': 'model_3_p',
        'Model Y P': 'model_y_p',
        'Model Y RWD 2024': 'model_y_rwd',
        'Model Y New LR': 'model_y_new_lr_launch',
        'Model Y LR 19': 'model_y_lr_19',
        'Model Y LR 20': 'model_y_lr_20',
    }
    
    # 모델명 정리 (좌우 공백 제거)
    model = model.strip()
    
    if model not in model_mapping:
        return ""
        
    target_column = model_mapping[model]
    
    # 만원 단위 표기 지역 목록
    만원_단위_지역 = ['성남시', '의정부시', '시흥시', '과천시']
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                # 1. 기본 보조금 조회
                # SQL Injection 방지를 위해 컬럼명은 포맷팅으로 넣지 않고 화이트리스트 검증(매핑) 사용
                query = f"SELECT {target_column} FROM subsidy_amounts WHERE region = %s"
                cursor.execute(query, (region,))
                row = cursor.fetchone()
                
                if not row or row[0] is None:
                    return ""
                
                base_amount = int(row[0])
                amount = int(row[0])
                
                # 2. 다자녀 및 청년생애 추가 보조금 계산
                if rn:
                    # 다자녀 및 청년생애 플래그 한 번에 조회
                    check_query = "SELECT 다자녀, 청년생애 FROM gemini_results WHERE RN = %s"
                    cursor.execute(check_query, (rn,))
                    flags_row = cursor.fetchone()
                    
                    if flags_row:
                        is_multichild = flags_row[0] == 1
                        is_youth = flags_row[1] == 1
                        
                        # 다자녀 추가 보조금
                        if is_multichild:
                            # 자녀 수 확인
                            count_query = "SELECT child_count FROM test_ai_다자녀 WHERE RN = %s"
                            cursor.execute(count_query, (rn,))
                            count_row = cursor.fetchone()
                            
                            if count_row and count_row[0]:
                                child_count = count_row[0]
                                additional_amount = 0
                                
                                if child_count == 2:
                                    additional_amount = 1000000
                                elif child_count == 3:
                                    additional_amount = 2000000
                                elif child_count >= 4:
                                    additional_amount = 3000000
                                
                                if additional_amount > 0:
                                    amount += additional_amount
                                    print(f"다자녀 추가 보조금 적용: +{additional_amount:,}원 (자녀수: {child_count}명)")
                        
                        # 청년생애 추가 보조금 (모델별 고정 금액)
                        if is_youth:
                            youth_additional_amounts = {
                                'Model Y L': 420000,
                                'Model Y R': 376000,
                                'Model 3 R': 372000,
                                'Model 3 L': 414000,
                            }
                            # model 변수는 함수 인자로 전달받은 값을 사용
                            additional_youth_amount = youth_additional_amounts.get(model.strip(), 0)
                            if additional_youth_amount > 0:
                                amount += additional_youth_amount
                                print(f"청년생애 추가 보조금 적용: +{additional_youth_amount:,}원 ({model.strip()})")

                # 3. 포맷팅 및 반환
                # 만원 단위 표기 지역 처리
                if region in 만원_단위_지역:
                    # 10000으로 나누기
                    amount_in_manwon = amount / 10000
                    
                    # 정수로 딱 떨어지면 정수로, 아니면 소수점까지 표시
                    if amount_in_manwon.is_integer():
                        return f"{int(amount_in_manwon)}"
                    else:
                        return f"{amount_in_manwon}"
                
                # 일반적인 경우 (천 단위 콤마 + 원)
                return f"{amount:,}원"
                
    except Exception:
        traceback.print_exc()
        return ""

def calculate_delivery_date(region: str) -> str:
    """
    오늘 날짜와 지역을 기반으로 출고예정일을 계산한다. (주말만 제외)
    
    Args:
        region: 지역명
        
    Returns:
        출고예정일 문자열 (YYYY-MM-DD 형식) 또는 빈 문자열
    """
    if not region:
        return ""
    
    try:
        # day_gap 조회
        day_gap = fetch_delivery_day_gap(region)
        if day_gap is None:
            return ""
        
        # 오늘 날짜 (한국 시간 기준)
        kst = pytz.timezone('Asia/Seoul')
        today = datetime.now(kst).date()
        
        # 1단계: 오늘 날짜 + day_gap일 (주말 포함해서 단순히 일수만 더함)
        delivery_date = today + timedelta(days=day_gap)
        
        # 2단계: 계산된 날짜가 주말이면 다음 영업일로 조정 (공휴일은 추후 추가 예정)
        max_iterations = 100
        iteration = 0
        
        while iteration < max_iterations:
            weekday = delivery_date.weekday()  # 월요일=0, 일요일=6
            is_weekend = weekday >= 5  # 토요일(5) 또는 일요일(6)
            
            # 주말이 아니면 반환
            if not is_weekend:
                break
            
            # 주말이면 다음 날로 이동
            delivery_date = delivery_date + timedelta(days=1)
            iteration += 1
        
        # 계산된 출고예정일을 문자열로 반환
        return delivery_date.strftime('%Y-%m-%d')
        
    except Exception:
        traceback.print_exc()
        return ""

def get_recent_thread_id_by_rn(rn: str) -> str | None:
    """
    RN으로 rns 테이블에서 recent_thread_id를 조회한다. (PostgreSQL 버전)
    """
    if not rn:
        return None

    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "SELECT recent_thread_id FROM rns WHERE \"RN\" = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                return row[0] if row else None
    except Exception:
        traceback.print_exc()
        return None

def insert_reply_email(
    thread_id: str | None,
    rn: str,
    worker: str,
    to_address: str,
    content: str,
    mail_type: str | None,
    app_num: int | None
) -> bool:
    """
    reply_emails 테이블에 이메일 답장 데이터를 삽입한다.
    """
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                query = """
                    INSERT INTO reply_emails (
                        thread_id, RN, worker, to_address, content, mail_type, app_num
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    )
                """
                cursor.execute(query, (
                    thread_id, rn, worker, to_address, content, mail_type, app_num
                ))
                connection.commit()
                return True
    except Exception:
        traceback.print_exc()
        return False

def get_current_status(rn: str) -> str | None:
    """
    RN으로 현재 status를 조회한다.
    """
    if not rn:
        return None
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT status FROM subsidy_applications WHERE RN = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                return row[0] if row else None
    except Exception:
        traceback.print_exc()
        return None

def insert_additional_note(
    rn: str,
    missing_docs: list | None,
    requirements: list | None,
    other_detail: str | None,
    target_status: str | None = None,
    detail_info: str | None = None
) -> bool:
    """
    additional_note 테이블에 특이사항 비고 데이터를 삽입하고, 
    조건에 따라 rns 테이블의 status를 업데이트한다. (PostgreSQL 버전)
    
    Args:
        rn: RN 번호 (필수)
        missing_docs: 서류미비 상세 항목 리스트 (JSON으로 변환됨)
        requirements: 요건 상세 항목 리스트 (JSON으로 변환됨)
        other_detail: 기타 대분류 상세 내용
        target_status: 업데이트할 상태값 (선택사항)
            - None이면 status 업데이트 안 함
            - '이메일 전송' 또는 '요청메일 전송' 상태인 경우 업데이트 안 함
            - 그 외의 경우 target_status로 업데이트
        detail_info: 서류미비 상세 사유 내용 (선택사항)
            - 내용이 있으면 저장, 없으면 NULL 유지
    
    Returns:
        삽입/업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    
    try:
        # 1. PostgreSQL - rns.status 업데이트 (target_status가 있는 경우)
        if target_status:
            try:
                with closing(psycopg2.connect(**DB_CONFIG)) as pg_conn:
                    with pg_conn.cursor() as pg_cursor:
                        # 현재 상태 조회
                        pg_cursor.execute("SELECT status FROM rns WHERE \"RN\" = %s", (rn,))
                        row = pg_cursor.fetchone()
                        current_status = row[0] if row else None
                        
                        # 상태 업데이트 조건 확인
                        if current_status not in ('이메일 전송', '요청메일 전송', '중복메일확인', '중복메일'):
                            update_query = """
                                UPDATE rns 
                                SET status = %s
                                WHERE "RN" = %s
                            """
                            pg_cursor.execute(update_query, (target_status, rn))
                            pg_conn.commit()
            except Exception as e:
                print(f"[insert_additional_note] PostgreSQL update failed: {e}")
                traceback.print_exc()
                # Status 업데이트 실패 시에도 additional_note 저장 시도는 계속 진행

        # 2. PostgreSQL - additional_note 저장 (내용이 있는 경우에만)
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # 특이사항 내용이 하나라도 있는 경우에만 저장
            if missing_docs or requirements or other_detail or detail_info:
                with connection.cursor() as cursor:
                    # 리스트를 JSON 문자열로 변환 (None이면 NULL)
                    missing_docs_json = json.dumps(missing_docs, ensure_ascii=False) if missing_docs else None
                    requirements_json = json.dumps(requirements, ensure_ascii=False) if requirements else None
                    # detail_info는 내용이 있으면 저장, 없으면 None (NULL 유지)
                    detail_info_value = detail_info.strip() if detail_info and detail_info.strip() else None
                    
                    # RN 기준으로 Upsert (기존 MySQL ON DUPLICATE KEY UPDATE 대응)
                    query = """
                        INSERT INTO additional_note (
                            "RN", missing_docs, requirements, other_detail, detail_info
                        ) VALUES (
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT ("RN") DO UPDATE
                        SET missing_docs = EXCLUDED.missing_docs,
                            requirements = EXCLUDED.requirements,
                            other_detail = EXCLUDED.other_detail,
                            detail_info = EXCLUDED.detail_info,
                            updated_at = CURRENT_TIMESTAMP
                    """
                    cursor.execute(query, (
                        rn, missing_docs_json, requirements_json, other_detail, detail_info_value
                    ))
            
            connection.commit()
            return True
            
    except Exception:
        traceback.print_exc()
        return False

def is_admin_user(worker_name: str) -> bool:
    """
    workers 테이블에서 사용자가 관리자인지 확인한다.
    affiliation이 '그리트라운지'이고 level이 ['매니저', '팀장', '이사']에 포함되는 경우 True를 반환한다.
    
    Args:
        worker_name: 확인할 작업자 이름
        
    Returns:
        관리자 여부 (True: 관리자, False: 일반 사용자)
    """
    if not worker_name:
        return False
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT name, level, affiliation
                FROM workers
                WHERE name = %s AND affiliation = '그리트라운지' AND level IN ('매니저', '팀장', '이사')
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (worker_name,))
                row = cursor.fetchone()
                return row is not None
    except Exception:
        traceback.print_exc()
        return False

def update_finished_file_path(rn: str, file_path: str) -> bool:
    """
    rns 테이블의 file_path를 업데이트한다. (PostgreSQL 버전)
    
    Args:
        rn: RN 번호
        file_path: 저장된 PDF 파일 경로
        
    Returns:
        업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    if not file_path:
        raise ValueError("file_path must be provided")
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # psycopg2는 자동으로 트랜잭션을 시작하므로 begin() 호출 불필요
            try:
                with connection.cursor() as cursor:
                    update_query = (
                        "UPDATE rns "
                        "SET file_path = %s "
                        "WHERE \"RN\" = %s"
                    )
                    cursor.execute(update_query, (file_path, rn))
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False

def fetch_preprocessed_data(worker_name: str) -> pd.DataFrame:
    """
    preprocessed_data 테이블에서 특정 신청자(worker_name)의 데이터를 조회한다.
    """
    if not worker_name:
        return pd.DataFrame()
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT * FROM preprocessed_data WHERE 신청자 = %s"
            df = pd.read_sql(query, connection, params=(worker_name,))
            return df
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def fetch_delivery_day_gap(region: str) -> int | None:
    """
    region_metadata 테이블에서 지역(region)에 해당하는 day_gap을 조회한다. (PostgreSQL 버전)
    """
    if not region:
        return None
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "SELECT day_gap FROM region_metadata WHERE region = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (region,))
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else None
    except Exception:
        traceback.print_exc()
        return None

def fetch_holidays() -> set[date]:
    """
    'greetlounge_holiday' 테이블에서 모든 공휴일을 조회하여 set으로 반환한다.
    테이블이 존재하지 않으면 빈 set을 반환한다.
    
    Returns:
        공휴일 date 객체들의 set
    """
    holidays = set()
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT date FROM greetlounge_holiday"
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    holiday_date = row[0]
                    # 날짜 형식 변환 (datetime, date, str 등 다양한 형식 처리)
                    if isinstance(holiday_date, date):
                        holidays.add(holiday_date)
                    elif isinstance(holiday_date, datetime):
                        holidays.add(holiday_date.date())
                    elif isinstance(holiday_date, str):
                        try:
                            holidays.add(datetime.strptime(holiday_date, "%Y-%m-%d").date())
                        except ValueError:
                            # 다른 형식 시도
                            try:
                                holidays.add(datetime.strptime(holiday_date.split()[0], "%Y-%m-%d").date())
                            except ValueError:
                                pass
    except pymysql.err.ProgrammingError as e:
        # 테이블이 존재하지 않는 경우 빈 set 반환
        if e.args[0] == 1146:  # Table doesn't exist
            return set()
        # 다른 프로그래밍 오류는 재발생
        raise
    except Exception:
        # 기타 오류는 로그만 출력하고 빈 set 반환
        traceback.print_exc()
    return holidays

def get_previous_business_day_after_18h() -> datetime:
    """
    이전 영업일(주말/공휴일 제외)의 18시 이후 시간을 반환한다.
    
    예시:
    - 오늘이 월요일 → 금요일 18:00:00
    - 오늘이 월요일이고 금요일이 공휴일 → 목요일 18:00:00
    
    Returns:
        이전 영업일 18시 이후의 datetime 객체 (KST 타임존)
    """
    kst = pytz.timezone('Asia/Seoul')
    today = datetime.now(kst).date()
    holidays = fetch_holidays()
    
    # 최대 30일까지 체크 (무한 루프 방지)
    max_iterations = 30
    iteration = 0
    check_date = today - timedelta(days=1)  # 어제부터 시작
    
    while iteration < max_iterations:
        weekday = check_date.weekday()  # 월요일=0, 일요일=6
        is_weekend = weekday >= 5  # 토요일(5) 또는 일요일(6)
        is_holiday = check_date in holidays
        
        # 주말이 아니고 공휴일도 아니면 영업일
        if not is_weekend and not is_holiday:
            # 해당 날짜의 18시 00분 00초로 datetime 생성
            result_datetime = datetime.combine(check_date, time(18, 0, 0))
            return kst.localize(result_datetime)
        
        # 주말이거나 공휴일이면 하루 더 전으로 이동
        check_date = check_date - timedelta(days=1)
        iteration += 1
    
    # 최대 반복 횟수에 도달한 경우 (에러 방지)
    # 어제 날짜의 18시로 반환
    fallback_date = today - timedelta(days=1)
    result_datetime = datetime.combine(fallback_date, time(18, 0, 0))
    return kst.localize(result_datetime)

def fetch_give_works() -> pd.DataFrame:
    """
    give_works 테이블에서 작업상태가 '완료'가 아닌 데이터를 조회한다.
    ['RN', '신청자', '지역', '메모'] 컬럼을 반환한다.
    """
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT RN, 신청자, 지역, 메모
                FROM give_works
                WHERE 작업상태 != '완료' OR 작업상태 IS NULL
                ORDER BY RN DESC
            """
            df = pd.read_sql(query, connection)
            return df
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def update_rns_worker_id(rn: str, worker_id: int) -> bool:
    """
    rns 테이블의 worker_id 필드를 업데이트한다.
    
    Args:
        rn: RN 번호
        worker_id: 작업자 ID
        
    Returns:
        업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    if worker_id is None:
        raise ValueError("worker_id must be provided")
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            # psycopg2는 자동으로 트랜잭션을 시작하므로 begin() 호출 불필요
            try:
                with connection.cursor() as cursor:
                    update_query = (
                        "UPDATE rns SET worker_id = %s "
                        "WHERE \"RN\" = %s"
                    )
                    cursor.execute(update_query, (worker_id, rn))
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False

def update_give_works_worker(rn: str, worker: str) -> bool:
    """
    give_works 테이블의 신청자(worker) 필드를 업데이트한다.
    
    Args:
        rn: RN 번호
        worker: 작업자 이름
        
    Returns:
        업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    if not worker:
        raise ValueError("worker must be provided")
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            connection.begin()
            try:
                with connection.cursor() as cursor:
                    update_query = (
                        "UPDATE give_works SET 신청자 = %s "
                        "WHERE RN = %s"
                    )
                    cursor.execute(update_query, (worker, rn))
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False

def update_give_works_memo(rn: str, memo: str) -> bool:
    """
    give_works 테이블의 메모 필드를 업데이트한다.
    
    Args:
        rn: RN 번호
        memo: 메모 내용
        
    Returns:
        업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            connection.begin()
            try:
                with connection.cursor() as cursor:
                    update_query = (
                        "UPDATE give_works SET 메모 = %s "
                        "WHERE RN = %s"
                    )
                    cursor.execute(update_query, (memo, rn))
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False

def update_give_works_on_save(rn: str, file_path: str, application_date: str) -> bool:
    """
    give_works 테이블의 파일명, 지급 신청일, 작업상태를 업데이트한다.
    
    Args:
        rn: RN 번호
        file_path: 저장된 PDF 파일 경로 (네트워크 경로)
        application_date: 지급 신청일 (MM/DD 형식)
        
    Returns:
        업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            connection.begin()
            try:
                with connection.cursor() as cursor:
                    print(f"Executing query: UPDATE give_works SET 파일명='{file_path}', 지급_신청일='{application_date}', 작업상태='완료' WHERE RN='{rn}'")
                    update_query = (
                        "UPDATE give_works "
                        "SET 파일명 = %s, 지급_신청일 = %s, 작업상태 = '완료' "
                        "WHERE RN = %s"
                    )
                    cursor.execute(update_query, (file_path, application_date, rn))
                connection.commit()
                
                if cursor.rowcount == 0:
                    print(f"[update_give_works_on_save] Warning: No rows updated for RN {rn}")
                    
                return True
            except Exception as e:
                print(f"[update_give_works_on_save] DB Error: {e}")
                connection.rollback()
                raise
    except Exception:
        traceback.print_exc()
        return False

def insert_delivery_day_gap(region: str, day_gap: int) -> bool:
    """
    '출고예정일' 테이블에 새로운 지역 데이터를 추가한다.
    이미 존재하는 경우 추가하지 않는다.
    
    Args:
        region: 지역명
        day_gap: 일수 차이
        
    Returns:
        추가 성공 여부 (이미 존재하는 경우 False)
    """
    if not region or region == 'X':
        return False
    
    if day_gap is None:
        return False
    
    try:
        # 한국 시간 (KST) 생성
        kst = pytz.timezone('Asia/Seoul')
        current_time = datetime.now(kst)
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                # 이미 존재하는지 확인
                check_query = "SELECT region FROM 출고예정일 WHERE region = %s"
                cursor.execute(check_query, (region,))
                if cursor.fetchone():
                    # 이미 존재하는 경우 추가하지 않음
                    return False
                
                # 새로 추가
                insert_query = """
                    INSERT INTO 출고예정일 (region, day_gap, updated_datetime)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(insert_query, (region, day_gap, current_time))
                connection.commit()
                return True
    except Exception:
        traceback.print_exc()
        return False

def fetch_ev_required_rns(worker_name: str) -> list[str]:
    """
    rns 테이블에서 조건에 맞는 RN 목록을 조회한다.
    조건: worker_id가 현재 작업자의 worker_id와 일치하고, status='서류미비 요청'
    
    Args:
        worker_name: 작업자 이름
        
    Returns:
        RN 목록 리스트
    """
    if not worker_name:
        return []
    
    try:
        # worker_name으로 worker_id 조회
        worker_id = get_worker_id_by_name(worker_name)
        if worker_id is None:
            return []
        
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT "RN"
                FROM rns
                WHERE worker_id = %s AND status = '서류미비 도착'
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (worker_id,))
                rows = cursor.fetchall()
                # 튜플의 첫 번째 요소인 RN만 추출하여 리스트로 반환
                return [row[0] for row in rows]
    except Exception:
        traceback.print_exc()
        return []

def fetch_duplicate_mail_rns(worker_name: str) -> list[str]:
    """
    rns 테이블에서 '중복메일' 상태인 RN 목록을 반환합니다. (PostgreSQL 버전)
    
    1. 관리자급('이경구', '이호형'): 전체 조회
    2. 일반 작업자:
       - 본인에게 할당된 건 (worker_id 일치)
       - 또는 worker_id가 NULL인 건 (미할당 건은 모두에게 노출)
    
    RN 기준 오름차순 정렬
    """
    if not worker_name:
        return []
    
    # 관리자 목록
    ADMIN_WORKERS = ['이경구', '이호형']
    
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                # 1. 관리자인 경우: 모든 '중복메일' 건 조회
                if worker_name in ADMIN_WORKERS:
                    query = """
                        SELECT "RN"
                        FROM rns
                        WHERE status = '중복메일'
                        ORDER BY "RN" ASC
                    """
                    cursor.execute(query)
                
                # 2. 일반 작업자인 경우
                else:
                    # 먼저 worker_name으로 worker_id 조회
                    cursor.execute("SELECT worker_id FROM workers WHERE worker_name = %s", (worker_name,))
                    row = cursor.fetchone()
                    
                    if not row:
                        # 작업자가 DB에 없으면 조회 불가
                        return []
                    
                    worker_id = row[0]
                    
                    # 본인 할당 건 OR 미할당(NULL) 건 조회
                    query = """
                        SELECT "RN"
                        FROM rns
                        WHERE status = '중복메일' 
                          AND (worker_id = %s OR worker_id IS NULL)
                        ORDER BY "RN" ASC
                    """
                    cursor.execute(query, (worker_id,))
                
                rows = cursor.fetchall()
                return [row[0] for row in rows]
                
    except Exception:
        traceback.print_exc()
        return []

def get_original_worker_by_rn(rn: str) -> str | None:
    """
    rns 테이블에서 해당 RN의 담당자(original_worker)를 조회한다. (PostgreSQL 버전)
    workers 테이블과 조인하여 worker_name을 반환.
    """
    if not rn:
        return None
        
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT w.worker_name 
                FROM rns r
                JOIN workers w ON r.worker_id = w.worker_id
                WHERE r."RN" = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                return row[0] if row else None
    except Exception:
        traceback.print_exc()
        return None

def update_subsidy_status(rn: str, status: str) -> bool:
    """
    rns 테이블에서 해당 RN의 status를 업데이트한다. (PostgreSQL 버전)
    """
    if not rn:
        return False
        
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            query = "UPDATE rns SET status = %s WHERE \"RN\" = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (status, rn))
                connection.commit()
                return True
    except Exception:
        traceback.print_exc()
        return False

def fetch_after_apply_counts() -> tuple[int, int]:
    """
    after_apply 테이블에서 오늘과 내일의 신청 건수를 조회한다.
    
    Returns:
        (오늘 건수, 내일 건수) 튜플
    """
    try:
        kst = pytz.timezone('Asia/Seoul')
        today = datetime.now(kst).date()
        tomorrow = today + timedelta(days=1)
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            # 오늘 건수 조회
            today_query = """
                SELECT COUNT(*) 
                FROM after_apply 
                WHERE DATE(after_date) = %s
            """
            # 내일 건수 조회
            tomorrow_query = """
                SELECT COUNT(*) 
                FROM after_apply 
                WHERE DATE(after_date) = %s
            """
            
            with connection.cursor() as cursor:
                cursor.execute(today_query, (today,))
                today_count = cursor.fetchone()[0] or 0
                
                cursor.execute(tomorrow_query, (tomorrow,))
                tomorrow_count = cursor.fetchone()[0] or 0
                
                return (today_count, tomorrow_count)
    except Exception:
        traceback.print_exc()
        return (0, 0)

def fetch_scheduled_regions() -> pd.DataFrame:
    """
    '출고예정일' 테이블의 모든 데이터를 조회하여 DataFrame으로 반환한다.
    
    Returns:
        DataFrame (region, plan_open_date, day_gap, updated_datetime 포함)
    """
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT region, plan_open_date, day_gap, updated_datetime FROM 출고예정일 ORDER BY region"
            df = pd.read_sql(query, connection)
            return df
    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def update_scheduled_region(region: str, plan_open_date: str | None) -> bool:
    """
    '출고예정일' 테이블에서 특정 지역의 plan_open_date를 업데이트한다.
    
    Args:
        region: 지역명
        plan_open_date: 출고예정일 (문자열 'YYYY-MM-DD' 또는 None)
        
    Returns:
        업데이트 성공 여부
    """
    if not region:
        return False
        
    try:
        # 한국 시간 (KST) 생성
        kst = pytz.timezone('Asia/Seoul')
        current_time = datetime.now(kst)
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                query = """
                    UPDATE 출고예정일 
                    SET plan_open_date = %s, updated_datetime = %s
                    WHERE region = %s
                """
                cursor.execute(query, (plan_open_date, current_time, region))
                connection.commit()
                return True
    except Exception:
        traceback.print_exc()
        return False

def get_original_pdf_path_by_rn(rn: str) -> str | None:
    """
    RN을 사용하여 emails 테이블에서 original_pdf_path를 조회하거나,
    없을 경우 rns 테이블에서 file_path를 조회하여 반환한다.
    """
    try:
        with closing(psycopg2.connect(**DB_CONFIG)) as connection:
            with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # 1. rns 테이블에서 recent_thread_id와 file_path 조회
                select_rns_query = "SELECT recent_thread_id, file_path FROM rns WHERE \"RN\" = %s"
                cursor.execute(select_rns_query, (rn,))
                rns_result = cursor.fetchone()

                if rns_result:
                    thread_id = rns_result.get('recent_thread_id')
                    
                    if thread_id:
                        # 2. emails 테이블에서 thread_id로 original_pdf_path 조회
                        select_emails_query = "SELECT original_pdf_path FROM emails WHERE thread_id = %s"
                        cursor.execute(select_emails_query, (thread_id,))
                        emails_result = cursor.fetchone()
                        if emails_result and emails_result['original_pdf_path']:
                            return emails_result['original_pdf_path']

                    # 3. emails에서 찾지 못했거나 thread_id가 없는 경우 rns 테이블에서 file_path 조회
                    if rns_result['file_path']:
                        return rns_result['file_path']
                
                return None

    except Exception as e:
        print(f"Error fetching original PDF path for RN {rn}: {e}")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # fetch_recent_subsidy_applications()
    # test_fetch_emails()
    print(get_worker_names())
    # get_mail_content()
