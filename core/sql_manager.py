import pymysql
from datetime import datetime, date
import pytz
import pandas as pd
import traceback
import json

from contextlib import closing

FETCH_EMAILS_COLUMNS = ['title', 'received_date', 'from_email_address', 'content']
FETCH_SUBSIDY_COLUMNS = ['RN', 'region', 'worker', 'name', 'special_note', 'file_status', 'original_filepath', 'recent_thread_id', 'file_rendered']  # 'file_status'는 주석 처리됨

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
                # "       CASE WHEN e.attached_file = 1 THEN '여' ELSE '부' END AS file_status, "  # 주석 처리됨
                "       e.attached_file_path AS original_filepath, "
                "       sa.recent_thread_id, "
                "       e.file_rendered, "
                "       gr.구매계약서, "
                "       gr.초본, "
                "       gr.공동명의, "
                "       gr.다자녀, "
                "       sa.urgent, "
                "       d.child_birth_date, "
                "       cb.issue_date, "
                "       CASE "
                "           WHEN gr.구매계약서 = 1 AND (gr.초본 = 1 OR gr.공동명의 = 1) THEN "
                "               CASE "
                "                   WHEN (gr.구매계약서 = 1 AND (c.ai_계약일자 IS NULL OR c.ai_이름 IS NULL OR c.전화번호 IS NULL OR c.이메일 IS NULL)) "
                "                   OR (gr.초본 = 1 AND (cb.name IS NULL OR cb.birth_date IS NULL OR cb.address_1 IS NULL)) "
                "                   OR (gr.청년생애 = 1 AND (y.local_name IS NULL OR y.range_date IS NULL)) "
                "                   THEN 'O' "
                "                   ELSE 'X' "
                "               END "
                "           ELSE '' "
                "       END AS outlier, "
                "       CASE "
                "           WHEN re.mail_type = '신청완료' THEN CAST(re.app_num AS CHAR) "
                "           WHEN re.mail_type = '서류미비' AND re.app_num IS NULL THEN '서류미비' "
                "           WHEN re.mail_type = '서류미비' AND re.app_num IS NOT NULL THEN CONCAT(re.app_num, '_미비') "
                "           ELSE NULL "
                "       END AS result "
                "FROM subsidy_applications sa "
                "LEFT JOIN emails e ON sa.recent_thread_id = e.thread_id "
                "LEFT JOIN gemini_results gr ON sa.RN COLLATE utf8mb4_unicode_ci = gr.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_구매계약서 c ON sa.RN COLLATE utf8mb4_unicode_ci = c.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_초본 cb ON sa.RN COLLATE utf8mb4_unicode_ci = cb.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_청년생애 y ON sa.RN COLLATE utf8mb4_unicode_ci = y.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_다자녀 d ON sa.RN COLLATE utf8mb4_unicode_ci = d.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN ("
                "    SELECT re1.RN, re1.mail_type, re1.app_num "
                "    FROM reply_emails re1 "
                "    INNER JOIN ("
                "        SELECT RN, MAX(id) AS max_id "
                "        FROM reply_emails "
                "        GROUP BY RN"
                "    ) re2 ON re1.RN = re2.RN AND re1.id = re2.max_id"
                ") re ON sa.RN COLLATE utf8mb4_unicode_ci = re.RN COLLATE utf8mb4_unicode_ci "
                "WHERE sa.recent_received_date >= %s "
                "ORDER BY sa.recent_received_date DESC "
                "LIMIT 20"
            )
            params = ('2025-09-30 09:00',)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            print('조회된 데이터가 없습니다.')
            return df

        def _is_child_over_18(birth_date_str: str) -> bool:
            """생년월일 문자열을 받아 만나이 18세를 초과하는지 (즉, 만 19세 이상인지) 확인한다."""
            try:
                birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                today = datetime.now().date()
                
                age = today.year - birth_date.year
                
                if age > 19:
                    return True
                if age < 19:
                    return False
                
                return (today.month, today.day) >= (birth_date.month, birth_date.day)

            except (ValueError, TypeError):
                return True

        def is_multichild_outlier(row) -> bool:
            """다자녀 관련 정보가 이상치인지 확인. 이상치이면 True 반환."""
            try:
                다자녀값 = row['다자녀']
                if pd.isna(다자녀값) or 다자녀값 != 1:
                    return False

                dates_str = row['child_birth_date']
                if pd.isna(dates_str) or not dates_str:
                    return True

                dates = json.loads(dates_str)
                if not isinstance(dates, list) or not dates:
                    return True

                return any(_is_child_over_18(d) for d in dates)
            except (json.JSONDecodeError, TypeError, KeyError):
                return True

        def is_chobon_issue_date_outlier(row) -> bool:
            """초본 issue_date가 31일 이상 전인지 확인. 이상치이면 True 반환."""
            try:
                # 초본 서류가 있는 경우에만 체크 (gr.초본 = 1)
                초본값 = row['초본']
                if pd.isna(초본값) or 초본값 != 1:
                    return False

                issue_date = row['issue_date']
                if pd.isna(issue_date) or issue_date is None:
                    return False

                # 한국 시간 기준으로 오늘 날짜 계산
                kst = pytz.timezone('Asia/Seoul')
                today = datetime.now(kst).date()
                
                # issue_date 파싱
                issue_date_obj = None
                if isinstance(issue_date, str):
                    # 문자열인 경우 여러 형식 시도
                    try:
                        issue_date_obj = datetime.strptime(issue_date, "%Y-%m-%d").date()
                    except ValueError:
                        # 다른 형식 시도 (예: "2025-10-10 00:00:00")
                        try:
                            issue_date_obj = datetime.strptime(issue_date.split()[0], "%Y-%m-%d").date()
                        except ValueError:
                            # ISO 형식 시도 (예: "2025-10-09T15:00:00.000Z")
                            try:
                                issue_date_obj = datetime.strptime(issue_date.split('T')[0], "%Y-%m-%d").date()
                            except ValueError:
                                return False
                elif isinstance(issue_date, datetime):
                    issue_date_obj = issue_date.date()
                elif isinstance(issue_date, date):
                    # 이미 date 객체인 경우
                    issue_date_obj = issue_date
                elif isinstance(issue_date, pd.Timestamp):
                    issue_date_obj = issue_date.date()
                else:
                    return False

                if issue_date_obj is None:
                    return False

                # 날짜 차이 계산 (오늘 - issue_date)
                days_diff = (today - issue_date_obj).days
                
                # 31일 이상 차이나면 이상치
                return days_diff >= 31
            except (ValueError, TypeError, AttributeError, KeyError):
                return False

        def update_outlier(row):
            """outlier 값을 업데이트하는 함수"""
            # 기존 outlier 값 확인
            current_outlier = row['outlier']
            
            # NaN이나 None 처리
            if pd.isna(current_outlier):
                current_outlier = ''
            
            # 문자열로 변환하여 비교
            current_outlier_str = str(current_outlier).strip()
            
            # 이미 'O'이면 그대로 반환
            if current_outlier_str == 'O':
                return 'O'
            
            # 다자녀 이상치 체크
            if is_multichild_outlier(row):
                return 'O'
            
            # 초본 issue_date 이상치 체크
            if is_chobon_issue_date_outlier(row):
                return 'O'
            
            # 이상치가 아니면 기존 값 반환 (문자열로 변환)
            return current_outlier_str if current_outlier_str else ''
        
        df['outlier'] = df.apply(update_outlier, axis=1)

        # 간단한 한 줄 디버그 출력
        print(f'새로고침 완료: {len(df)}개 데이터 조회됨')
        return df

    except Exception:  # pragma: no cover - 긴급 디버깅용
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
                "       e.attached_file_path AS original_filepath, "
                "       sa.recent_thread_id, "
                "       e.file_rendered, "
                "       sa.urgent, "
                "       gr.구매계약서, gr.초본, gr.공동명의, gr.다자녀, "
                "       d.child_birth_date, cb.issue_date "
                "FROM subsidy_applications sa "
                "LEFT JOIN emails e ON sa.recent_thread_id = e.thread_id "
                "LEFT JOIN gemini_results gr ON sa.RN COLLATE utf8mb4_unicode_ci = gr.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_다자녀 d ON sa.RN COLLATE utf8mb4_unicode_ci = d.RN COLLATE utf8mb4_unicode_ci "
                "LEFT JOIN test_ai_초본 cb ON sa.RN COLLATE utf8mb4_unicode_ci = cb.RN COLLATE utf8mb4_unicode_ci "
                "WHERE sa.RN = %s"
            )
            
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                columns = [col[0] for col in cursor.description]
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                result = dict(zip(columns, row))
                
                # 이상치(outlier) 계산 로직 (fetch_recent_subsidy_applications의 로직 간소화 적용)
                # 필요하다면 여기서 outlier 계산 로직을 추가하거나, 기본값만 설정
                result['outlier'] = '' 
                
                # 1. 다자녀 이상치 체크
                try:
                    import json
                    if result.get('다자녀') == 1 and result.get('child_birth_date'):
                        dates = json.loads(result['child_birth_date'])
                        today = datetime.now().date()
                        for d_str in dates:
                            try:
                                birth_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                                age = today.year - birth_date.year
                                if age > 19 or (age == 19 and (today.month, today.day) >= (birth_date.month, birth_date.day)):
                                    result['outlier'] = 'O'
                                    break
                            except ValueError:
                                pass
                except Exception:
                    pass

                # 2. 초본 issue_date 체크
                if result['outlier'] != 'O' and result.get('초본') == 1 and result.get('issue_date'):
                     try:
                        issue_date = result['issue_date']
                        kst = pytz.timezone('Asia/Seoul')
                        today = datetime.now(kst).date()
                        
                        if isinstance(issue_date, str):
                            issue_date_obj = datetime.strptime(issue_date.split()[0], "%Y-%m-%d").date()
                        elif isinstance(issue_date, (datetime, date)):
                             issue_date_obj = issue_date if isinstance(issue_date, date) else issue_date.date()
                        else:
                            issue_date_obj = None
                            
                        if issue_date_obj and (today - issue_date_obj).days >= 31:
                            result['outlier'] = 'O'
                     except Exception:
                         pass

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

def get_mail_content_by_thread_id(thread_id: str) -> str:
    """
    thread_id로 emails 테이블에서 content를 조회한다.
    """
    if not thread_id:
        return ""
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT content FROM emails WHERE thread_id = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (thread_id,))
                row = cursor.fetchone()
                return row[0] if row else ""
    except Exception:
        traceback.print_exc()
        return ""

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

def update_subsidy_status(rn: str, status: str) -> bool:
    """
    subsidy_applications 테이블의 status를 업데이트한다.
    
    Args:
        rn: RN 번호
        status: 업데이트할 상태값
        
    Returns:
        업데이트 성공 여부
    """
    if not rn:
        raise ValueError("rn must be provided")
    if not status:
        raise ValueError("status must be provided")
    
    try:
        # 한국 시간 (KST) 생성
        kst = pytz.timezone('Asia/Seoul')
        current_time = datetime.now(kst)
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                update_query = """
                    UPDATE subsidy_applications 
                    SET status = %s, status_updated_at = %s
                    WHERE RN = %s
                """
                cursor.execute(update_query, (status, current_time, rn))
                connection.commit()
                
                # 업데이트된 행 수 확인
                return cursor.rowcount > 0
                
    except Exception:
        traceback.print_exc()
        return False

def get_today_completed_subsidies(worker: str = None) -> list:
    """
    오늘 '지원완료' 처리된 지원금 신청 목록 (지역, 완료시간)을 반환한다.
    
    Args:
        worker: 작업자 이름 (선택사항, 제공되면 해당 작업자만 필터링)
    
    Returns:
        오늘 완료된 (지역, 완료시간) 튜플의 리스트
    """
    try:
        # 한국 시간 (KST) 생성
        kst = pytz.timezone('Asia/Seoul')
        today = datetime.now(kst).date()
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            # worker 파라미터에 따른 쿼리 분기
            if worker:
                query = """
                    SELECT region, status_updated_at
                    FROM subsidy_applications 
                    WHERE status = '지원완료' 
                    AND DATE(status_updated_at) = %s
                    AND worker = %s
                    AND region IS NOT NULL
                    ORDER BY status_updated_at DESC
                """
                params = (today, worker)
            else:
                query = """
                    SELECT region, status_updated_at
                    FROM subsidy_applications 
                    WHERE status = '지원완료' 
                    AND DATE(status_updated_at) = %s
                    AND region IS NOT NULL
                    ORDER BY status_updated_at DESC
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
    test_ai_구매계약서 테이블에서 RN으로 데이터를 조회한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT ai_계약일자, ai_이름, 전화번호, 이메일
                FROM test_ai_구매계약서
                WHERE RN = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'ai_계약일자': row[0],
                        'ai_이름': row[1],
                        '전화번호': row[2],
                        '이메일': row[3]
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def check_gemini_flags(rn: str) -> dict:
    """
    gemini_results 테이블에서 RN으로 플래그들을 조회한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT 구매계약서, 청년생애, 다자녀, 공동명의, 초본
                FROM gemini_results
                WHERE RN = %s
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
                        '초본': bool(row[4])
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_youth_results(rn: str) -> dict:
    """
    test_ai_청년생애 테이블에서 RN으로 데이터를 조회한다.
    JSON 칼럼을 파이썬 리스트로 변환하여 반환한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT local_name, range_date
                FROM test_ai_청년생애
                WHERE RN = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    import json
                    return {
                        'local_name': json.loads(row[0]) if row[0] else [],
                        'range_date': json.loads(row[1]) if row[1] else []
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_chobon_results(rn: str) -> dict:
    """
    test_ai_초본 테이블에서 RN으로 데이터를 조회한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT name, birth_date, address_1, address_2
                FROM test_ai_초본
                WHERE RN = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'name': row[0],
                        'birth_date': row[1],
                        'address_1': row[2],
                        'address_2': row[3]
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def get_recent_thread_id_by_rn(rn: str) -> str | None:
    """
    RN으로 subsidy_applications 테이블에서 recent_thread_id를 조회한다.
    """
    if not rn:
        return None

    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT recent_thread_id FROM subsidy_applications WHERE RN = %s"
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
    subsidy_applications 테이블의 finished_file_path를 업데이트한다.
    
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
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            with connection.cursor() as cursor:
                update_query = """
                    UPDATE subsidy_applications 
                    SET finished_file_path = %s
                    WHERE RN = %s
                """
                cursor.execute(update_query, (file_path, rn))
                connection.commit()
                
                # 업데이트된 행 수 확인
                return cursor.rowcount > 0
                
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
    '출고예정일' 테이블에서 지역(region)에 해당하는 day_gap을 조회한다.
    """
    if not region:
        return None
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT day_gap FROM 출고예정일 WHERE region = %s"
            with connection.cursor() as cursor:
                cursor.execute(query, (region,))
                row = cursor.fetchone()
                return row[0] if row else None
    except Exception:
        traceback.print_exc()
        return None

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

if __name__ == "__main__":
    # fetch_recent_subsidy_applications()
    # test_fetch_emails()
    print(get_worker_names())
    # get_mail_content()
