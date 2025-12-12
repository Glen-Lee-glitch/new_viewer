import pymysql
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
                        "SELECT worker, status FROM subsidy_applications "
                        "WHERE RN = %s FOR UPDATE"
                    )
                    cursor.execute(lock_query, (rn,))
                    row = cursor.fetchone()

                    if row is None:
                        connection.rollback()
                        return False

                    existing_worker = row[0]
                    existing_status = row[1] if len(row) > 1 else None
                    
                    if existing_worker:
                        connection.rollback()
                        return existing_worker == worker

                    # status가 '이메일 전송' 또는 '요청메일 전송'이면 status는 변경하지 않음
                    if existing_status in ('이메일 전송', '요청메일 전송'):
                        update_query = (
                            "UPDATE subsidy_applications SET worker = %s "
                            "WHERE RN = %s"
                        )
                        cursor.execute(update_query, (worker, rn))
                    else:
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

def _build_subsidy_query_base():
    """지원금 신청 데이터 조회용 기본 쿼리 문자열을 반환한다."""
    return (
        "SELECT sa.RN, sa.region, sa.worker, sa.name, sa.special_note, sa.recent_received_date, "
        "       sa.finished_file_path, " # finished_file_path 추가
        # "       CASE WHEN e.attached_file = 1 THEN '여' ELSE '부' END AS file_status, "  # 주석 처리됨
        "       e.attached_file_path AS original_filepath, "
        "       sa.recent_thread_id, "
        "       e.file_rendered, "
        "       gr.구매계약서, "
        "       gr.초본, "
        "       gr.공동명의, "
        "       gr.다자녀, "
        "       sa.urgent, "
        "       sa.mail_count, "
        "       d.child_birth_date, "
        "       cb.issue_date, "
        "       cb.chobon, "
        "       c.ai_계약일자, c.ai_이름, c.전화번호, c.이메일, c.차종, c.page_number, "
        "       cb.name AS chobon_name, cb.birth_date AS chobon_birth_date, cb.address_1 AS chobon_address_1, "
        "       biz.is_법인, "
        "       CASE "
        "           WHEN gr.구매계약서 = 1 AND (gr.초본 = 1 OR gr.공동명의 = 1) THEN "
        "               CASE "
        "                   WHEN (gr.구매계약서 = 1 AND (c.ai_계약일자 IS NULL OR c.ai_이름 IS NULL OR c.전화번호 IS NULL OR c.이메일 IS NULL OR c.ai_계약일자 < '2025-01-01')) "
        "                   OR (gr.초본 = 1 AND (cb.name IS NULL OR cb.birth_date IS NULL OR cb.address_1 IS NULL OR cb.chobon = 0)) "
        "                   OR (gr.청년생애 = 1 AND (y.local_name IS NULL OR y.range_date IS NULL)) "
        "                   THEN 'O' "
        "                   ELSE 'X' "
        "               END "
        "           ELSE '' "
        "       END AS outlier, "
        "       sa.status AS result "
        "FROM subsidy_applications sa "
        "LEFT JOIN emails e ON sa.recent_thread_id = e.thread_id "
        "LEFT JOIN gemini_results gr ON sa.RN COLLATE utf8mb4_unicode_ci = gr.RN COLLATE utf8mb4_unicode_ci "
        "LEFT JOIN test_ai_구매계약서 c ON sa.RN COLLATE utf8mb4_unicode_ci = c.RN COLLATE utf8mb4_unicode_ci "
        "LEFT JOIN test_ai_초본 cb ON sa.RN COLLATE utf8mb4_unicode_ci = cb.RN COLLATE utf8mb4_unicode_ci "
        "LEFT JOIN test_ai_청년생애 y ON sa.RN COLLATE utf8mb4_unicode_ci = y.RN COLLATE utf8mb4_unicode_ci "
        "LEFT JOIN test_ai_다자녀 d ON sa.RN COLLATE utf8mb4_unicode_ci = d.RN COLLATE utf8mb4_unicode_ci "
        "LEFT JOIN test_ai_사업자등록증 biz ON sa.RN COLLATE utf8mb4_unicode_ci = biz.RN COLLATE utf8mb4_unicode_ci "
    )

def fetch_recent_subsidy_applications():
    """최근 접수된 지원금 신청 데이터를 조회하고 출력한다."""
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = _build_subsidy_query_base() + (
                "WHERE sa.recent_received_date >= %s "
                "ORDER BY sa.recent_received_date DESC "
                "LIMIT 30"
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

        def is_contract_date_outlier(row) -> bool:
            """ai_계약일자가 오늘-4일보다 나중인 경우 True 반환"""
            try:
                contract_date_val = row['ai_계약일자']
                if pd.isna(contract_date_val) or contract_date_val is None:
                    return False
                
                contract_date = None
                if isinstance(contract_date_val, str):
                    try:
                        contract_date = datetime.strptime(contract_date_val.split()[0], "%Y-%m-%d").date()
                    except ValueError:
                        return False
                elif isinstance(contract_date_val, datetime):
                    contract_date = contract_date_val.date()
                elif isinstance(contract_date_val, date):
                    contract_date = contract_date_val
                elif isinstance(contract_date_val, pd.Timestamp):
                    contract_date = contract_date_val.date()
                else:
                    return False

                today = datetime.now().date()
                four_days_ago = today - timedelta(days=4)
                
                return contract_date > four_days_ago
            except (ValueError, TypeError, AttributeError, KeyError):
                return False

        def is_chobon_address_outlier(row) -> bool:
            """초본 address_1에 region 문자열이 포함되어 있지 않으면 True 반환"""
            try:
                초본값 = row.get('초본')
                region = row.get('region')
                address_1 = row.get('address_1')

                # 초본 서류가 있고, region과 address_1이 유효한 경우에만 체크
                if pd.notna(초본값) and 초본값 == 1 and region and address_1:
                    # region이 address_1에 포함되어 있지 않으면 이상치
                    return region not in address_1
                return False
            except (ValueError, TypeError, KeyError, AttributeError):
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
            
            # 계약일자 이상치 체크
            if is_contract_date_outlier(row):
                return 'O'

            # 다자녀 이상치 체크
            if is_multichild_outlier(row):
                return 'O'
            
            # 초본 issue_date 이상치 체크
            if is_chobon_issue_date_outlier(row):
                return 'O'
            
            # 초본 chobon == 0 이상치 체크
            try:
                초본값 = row.get('초본', 0)
                chobon값 = row.get('chobon')
                if (pd.notna(초본값) and 초본값 == 1) and (pd.notna(chobon값) and chobon값 == 0):
                    return 'O'
            except (ValueError, TypeError, KeyError):
                pass
            
            # 초본 address_1 지역 불일치 이상치 체크
            if is_chobon_address_outlier(row):
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

def fetch_today_subsidy_applications_by_worker(worker_name: str):
    """이전 영업일 18시 이후의 지원금 신청 데이터 중 특정 작업자에게 할당된 데이터를 조회한다."""
    if not worker_name:
        return pd.DataFrame()
    
    try:
        # 이전 영업일 18시 이후 시간 계산
        cutoff_datetime = get_previous_business_day_after_18h()
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = _build_subsidy_query_base() + (
                "WHERE sa.recent_received_date >= %s "
                "AND sa.worker = %s "
                "ORDER BY sa.recent_received_date DESC "
                "LIMIT 30"
            )
            params = (cutoff_datetime, worker_name)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            return df

        # 이상치 계산 로직 (fetch_recent_subsidy_applications와 동일)
        def _is_child_over_18(birth_date_str: str) -> bool:
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
            try:
                초본값 = row['초본']
                if pd.isna(초본값) or 초본값 != 1:
                    return False
                issue_date = row['issue_date']
                if pd.isna(issue_date) or issue_date is None:
                    return False
                kst = pytz.timezone('Asia/Seoul')
                today = datetime.now(kst).date()
                issue_date_obj = None
                if isinstance(issue_date, str):
                    try:
                        issue_date_obj = datetime.strptime(issue_date, "%Y-%m-%d").date()
                    except ValueError:
                        try:
                            issue_date_obj = datetime.strptime(issue_date.split()[0], "%Y-%m-%d").date()
                        except ValueError:
                            try:
                                issue_date_obj = datetime.strptime(issue_date.split('T')[0], "%Y-%m-%d").date()
                            except ValueError:
                                return False
                elif isinstance(issue_date, datetime):
                    issue_date_obj = issue_date.date()
                elif isinstance(issue_date, date):
                    issue_date_obj = issue_date
                elif isinstance(issue_date, pd.Timestamp):
                    issue_date_obj = issue_date.date()
                else:
                    return False
                if issue_date_obj is None:
                    return False
                days_diff = (today - issue_date_obj).days
                return days_diff >= 31
            except (ValueError, TypeError, AttributeError, KeyError):
                return False

        def is_contract_date_outlier(row) -> bool:
            """ai_계약일자가 오늘-4일보다 나중인 경우 True 반환"""
            try:
                contract_date_val = row['ai_계약일자']
                if pd.isna(contract_date_val) or contract_date_val is None:
                    return False
                
                contract_date = None
                if isinstance(contract_date_val, str):
                    try:
                        contract_date = datetime.strptime(contract_date_val.split()[0], "%Y-%m-%d").date()
                    except ValueError:
                        return False
                elif isinstance(contract_date_val, datetime):
                    contract_date = contract_date_val.date()
                elif isinstance(contract_date_val, date):
                    contract_date = contract_date_val
                elif isinstance(contract_date_val, pd.Timestamp):
                    contract_date = contract_date_val.date()
                else:
                    return False

                today = datetime.now().date()
                four_days_ago = today - timedelta(days=4)
                
                return contract_date > four_days_ago
            except (ValueError, TypeError, AttributeError, KeyError):
                return False

        def is_chobon_address_outlier(row) -> bool:
            """초본 address_1에 region 문자열이 포함되어 있지 않으면 True 반환"""
            try:
                초본값 = row.get('초본')
                region = row.get('region')
                address_1 = row.get('address_1')

                # 초본 서류가 있고, region과 address_1이 유효한 경우에만 체크
                if pd.notna(초본값) and 초본값 == 1 and region and address_1:
                    # region이 address_1에 포함되어 있지 않으면 이상치
                    return region not in address_1
                return False
            except (ValueError, TypeError, KeyError, AttributeError):
                return False

        def update_outlier(row):
            current_outlier = row['outlier']
            if pd.isna(current_outlier):
                current_outlier = ''
            current_outlier_str = str(current_outlier).strip()
            if current_outlier_str == 'O':
                return 'O'
            if is_multichild_outlier(row):
                return 'O'
            if is_chobon_issue_date_outlier(row):
                return 'O'
            # 초본 chobon == 0 이상치 체크
            try:
                초본값 = row.get('초본', 0)
                chobon값 = row.get('chobon')
                if (pd.notna(초본값) and 초본값 == 1) and (pd.notna(chobon값) and chobon값 == 0):
                    return 'O'
            except (ValueError, TypeError, KeyError):
                pass
            
            # 초본 address_1 지역 불일치 이상치 체크
            if is_chobon_address_outlier(row):
                return 'O'
            return current_outlier_str if current_outlier_str else ''
        
        df['outlier'] = df.apply(update_outlier, axis=1)
        return df

    except Exception:
        traceback.print_exc()
        return pd.DataFrame()

def fetch_today_unfinished_subsidy_applications():
    """이전 영업일 18시 이후의 지원금 신청 데이터 중 작업자가 할당되지 않은 데이터를 조회한다."""
    try:
        # 이전 영업일 18시 이후 시간 계산
        cutoff_datetime = get_previous_business_day_after_18h()
        
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = _build_subsidy_query_base() + (
                "WHERE sa.recent_received_date >= %s "
                "AND (sa.worker IS NULL OR sa.worker = '') "
                "ORDER BY sa.recent_received_date DESC "
                "LIMIT 30"
            )
            params = (cutoff_datetime,)
            df = pd.read_sql(query, connection, params=params)

        if df.empty:
            return df

        # 이상치 계산 로직 (fetch_recent_subsidy_applications와 동일)
        def _is_child_over_18(birth_date_str: str) -> bool:
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
            try:
                초본값 = row['초본']
                if pd.isna(초본값) or 초본값 != 1:
                    return False
                issue_date = row['issue_date']
                if pd.isna(issue_date) or issue_date is None:
                    return False
                kst = pytz.timezone('Asia/Seoul')
                today = datetime.now(kst).date()
                issue_date_obj = None
                if isinstance(issue_date, str):
                    try:
                        issue_date_obj = datetime.strptime(issue_date, "%Y-%m-%d").date()
                    except ValueError:
                        try:
                            issue_date_obj = datetime.strptime(issue_date.split()[0], "%Y-%m-%d").date()
                        except ValueError:
                            try:
                                issue_date_obj = datetime.strptime(issue_date.split('T')[0], "%Y-%m-%d").date()
                            except ValueError:
                                return False
                elif isinstance(issue_date, datetime):
                    issue_date_obj = issue_date.date()
                elif isinstance(issue_date, date):
                    issue_date_obj = issue_date
                elif isinstance(issue_date, pd.Timestamp):
                    issue_date_obj = issue_date.date()
                else:
                    return False
                if issue_date_obj is None:
                    return False
                days_diff = (today - issue_date_obj).days
                return days_diff >= 31
            except (ValueError, TypeError, AttributeError, KeyError):
                return False

        def is_contract_date_outlier(row) -> bool:
            """ai_계약일자가 오늘-4일보다 나중인 경우 True 반환"""
            try:
                contract_date_val = row['ai_계약일자']
                if pd.isna(contract_date_val) or contract_date_val is None:
                    return False
                
                contract_date = None
                if isinstance(contract_date_val, str):
                    try:
                        contract_date = datetime.strptime(contract_date_val.split()[0], "%Y-%m-%d").date()
                    except ValueError:
                        return False
                elif isinstance(contract_date_val, datetime):
                    contract_date = contract_date_val.date()
                elif isinstance(contract_date_val, date):
                    contract_date = contract_date_val
                elif isinstance(contract_date_val, pd.Timestamp):
                    contract_date = contract_date_val.date()
                else:
                    return False

                today = datetime.now().date()
                four_days_ago = today - timedelta(days=4)
                
                return contract_date > four_days_ago
            except (ValueError, TypeError, AttributeError, KeyError):
                return False

        def is_chobon_address_outlier(row) -> bool:
            """초본 address_1에 region 문자열이 포함되어 있지 않으면 True 반환"""
            try:
                초본값 = row.get('초본')
                region = row.get('region')
                address_1 = row.get('address_1')

                # 초본 서류가 있고, region과 address_1이 유효한 경우에만 체크
                if pd.notna(초본값) and 초본값 == 1 and region and address_1:
                    # region이 address_1에 포함되어 있지 않으면 이상치
                    return region not in address_1
                return False
            except (ValueError, TypeError, KeyError, AttributeError):
                return False

        def update_outlier(row):
            current_outlier = row['outlier']
            if pd.isna(current_outlier):
                current_outlier = ''
            current_outlier_str = str(current_outlier).strip()
            if current_outlier_str == 'O':
                return 'O'
            if is_multichild_outlier(row):
                return 'O'
            if is_chobon_issue_date_outlier(row):
                return 'O'
            # 초본 chobon == 0 이상치 체크
            try:
                초본값 = row.get('초본', 0)
                chobon값 = row.get('chobon')
                if (pd.notna(초본값) and 초본값 == 1) and (pd.notna(chobon값) and chobon값 == 0):
                    return 'O'
            except (ValueError, TypeError, KeyError):
                pass

            # 초본 address_1 지역 불일치 이상치 체크
            if is_chobon_address_outlier(row):
                return 'O'
            return current_outlier_str if current_outlier_str else ''
        
        df['outlier'] = df.apply(update_outlier, axis=1)
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

def get_email_by_thread_id(thread_id: str) -> dict | None:
    """
    thread_id로 emails 테이블에서 title과 content를 조회하여 딕셔너리로 반환한다.
    
    Args:
        thread_id: 이메일 thread_id
        
    Returns:
        {'title': str, 'content': str} 또는 None
    """
    if not thread_id:
        return None
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
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
                SELECT name, birth_date, address_1, address_2, gender
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
                        'address_2': row[3],
                        'gender': row[4]
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_multichild_results(rn: str) -> dict:
    """
    test_ai_다자녀 테이블에서 RN으로 데이터를 조회한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT child_birth_date
                FROM test_ai_다자녀
                WHERE RN = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    import json
                    return {
                        'child_birth_date': json.loads(row[0]) if row[0] else []
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_business_results(rn: str) -> dict:
    """
    test_ai_사업자등록증 테이블에서 RN으로 데이터를 조회한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT is_법인, 법인명, 대표자, 등록번호, 사업자등록번호, 사업자명, 법인주소
                FROM test_ai_사업자등록증
                WHERE RN = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        'is_법인': bool(row[0]) if row[0] is not None else False,
                        '기관명': row[1],  # 법인명을 기관명으로 매핑
                        '대표자': row[2],
                        '법인등록번호': row[3],  # 등록번호를 법인등록번호로 매핑
                        '사업자등록번호': row[4],
                        '개인사업자명': row[5],  # 사업자명을 개인사업자명으로 매핑
                        '법인주소': row[6]  # 법인주소 추가
                    }
                return {}
    except Exception:
        traceback.print_exc()
        return {}

def fetch_gemini_joint_results(rn: str) -> dict:
    """
    test_ai_공동명의 테이블에서 RN으로 데이터를 조회한다.
    first_person과 second_person 정보를 모두 반환한다.
    """
    if not rn:
        return {}
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT first_person_name, first_person_birth_date, first_person_gender, 
                       first_person_address_1, first_person_address_2,
                       second_person_name, second_person_birth_date, second_person_gender,
                       second_person_address_1, second_person_address_2
                FROM test_ai_공동명의
                WHERE RN = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                if row:
                    return {
                        # first_person 정보 (초본 데이터 대체용)
                        'name': row[0],
                        'birth_date': row[1],
                        'gender': row[2],
                        'address_1': row[3],
                        'address_2': row[4],
                        # second_person 정보
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
    subsidy_applications 테이블에서 RN으로 지역(region) 정보를 조회한다.
    """
    if not rn:
        return ""
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = "SELECT region FROM subsidy_applications WHERE RN = %s"
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
    오늘 날짜와 지역을 기반으로 출고예정일을 계산한다.
    
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
        
        # 공휴일 조회
        holidays = fetch_holidays()
        
        # 1단계: 오늘 날짜 + day_gap일 (주말/공휴일 포함해서 단순히 일수만 더함)
        delivery_date = today + timedelta(days=day_gap)
        
        # 2단계: 계산된 날짜가 주말/공휴일이면 다음 영업일로 조정
        max_iterations = 100
        iteration = 0
        
        while iteration < max_iterations:
            weekday = delivery_date.weekday()  # 월요일=0, 일요일=6
            is_weekend = weekday >= 5  # 토요일(5) 또는 일요일(6)
            is_holiday = delivery_date in holidays
            
            # 주말/공휴일이 아니면 반환
            if not is_weekend and not is_holiday:
                break
            
            # 주말/공휴일이면 다음 날로 이동
            delivery_date = delivery_date + timedelta(days=1)
            iteration += 1
        
        # 계산된 출고예정일을 문자열로 반환
        return delivery_date.strftime('%Y-%m-%d')
        
    except Exception:
        traceback.print_exc()
        return ""

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
    조건에 따라 subsidy_applications 테이블의 status를 업데이트한다.
    
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
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            # 1. 특이사항 저장 (내용이 있는 경우에만)
            if missing_docs or requirements or other_detail or detail_info:
                with connection.cursor() as cursor:
                    # 리스트를 JSON 문자열로 변환 (None이면 NULL)
                    missing_docs_json = json.dumps(missing_docs, ensure_ascii=False) if missing_docs else None
                    requirements_json = json.dumps(requirements, ensure_ascii=False) if requirements else None
                    # detail_info는 내용이 있으면 저장, 없으면 None (NULL 유지)
                    detail_info_value = detail_info.strip() if detail_info and detail_info.strip() else None
                    
                    query = """
                        INSERT INTO additional_note (
                            RN, missing_docs, requirements, other_detail, detail_info
                        ) VALUES (
                            %s, %s, %s, %s, %s
                        )
                        ON DUPLICATE KEY UPDATE
                            missing_docs = VALUES(missing_docs),
                            requirements = VALUES(requirements),
                            other_detail = VALUES(other_detail),
                            detail_info = VALUES(detail_info),
                            updated_at = CURRENT_TIMESTAMP
                    """
                    cursor.execute(query, (
                        rn, missing_docs_json, requirements_json, other_detail, detail_info_value
                    ))
            
            # 2. Status 업데이트 (target_status가 있는 경우)
            if target_status:
                # 현재 상태 조회
                current_status = None
                with connection.cursor() as cursor:
                    cursor.execute("SELECT status FROM subsidy_applications WHERE RN = %s", (rn,))
                    row = cursor.fetchone()
                    current_status = row[0] if row else None
                
                # 상태 업데이트 조건 확인
                if current_status not in ('이메일 전송', '요청메일 전송'):
                    with connection.cursor() as cursor:
                        kst = pytz.timezone('Asia/Seoul')
                        current_time = datetime.now(kst)
                        
                        update_query = """
                            UPDATE subsidy_applications 
                            SET status = %s, status_updated_at = %s
                            WHERE RN = %s
                        """
                        cursor.execute(update_query, (target_status, current_time, rn))
            
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
    ev_required 테이블에서 조건에 맞는 RN 목록을 조회한다.
    조건: status='신규', step!='지급보완', worker=worker_name
    
    Args:
        worker_name: 작업자 이름
        
    Returns:
        RN 목록 리스트
    """
    if not worker_name:
        return []
    
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT RN
                FROM ev_required
                WHERE status = '신규' AND step != '지급보완' AND worker = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (worker_name,))
                rows = cursor.fetchall()
                # 튜플의 첫 번째 요소인 RN만 추출하여 리스트로 반환
                return [row[0] for row in rows]
    except Exception:
        traceback.print_exc()
        return []

def fetch_duplicate_mail_rns(worker_name: str) -> list[str]:
    """
    subsidy_applications 테이블에서 '중복메일' 상태인 RN 목록을 반환합니다.
    관리자급('이경구', '이호형')은 전체, 그 외에는 본인 것만 조회.
    RN 기준 오름차순 정렬
    """
    if not worker_name:
        return []

    admins = ['이경구', '이호형']

    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            if worker_name in admins:
                query = """
                    SELECT RN 
                    FROM subsidy_applications 
                    WHERE status = '중복메일'
                    ORDER BY RN ASC
                """
                args = ()
            else:
                # 일반 작업자는 duplicated_rn 테이블의 가장 최근 original_worker가 본인인 경우만 조회
                query = """
                    SELECT S.RN 
                    FROM subsidy_applications S
                    WHERE S.status = '중복메일'
                    AND (
                        SELECT D.original_worker
                        FROM duplicated_rn D
                        WHERE D.RN = S.RN
                        ORDER BY D.received_date DESC
                        LIMIT 1
                    ) = %s
                    ORDER BY S.RN ASC
                """
                args = (worker_name,)

            with connection.cursor() as cursor:
                cursor.execute(query, args)
                rows = cursor.fetchall()
                # 튜플의 첫 번째 요소인 RN만 추출하여 리스트로 반환
                return [row[0] for row in rows]
                
    except Exception:
        traceback.print_exc()
        return []

def get_original_worker_by_rn(rn: str) -> str | None:
    """
    duplicated_rn 테이블에서 해당 RN의 가장 최근 original_worker를 조회한다.
    """
    if not rn:
        return None
        
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT original_worker 
                FROM duplicated_rn 
                WHERE RN = %s 
                ORDER BY received_date DESC 
                LIMIT 1
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (rn,))
                row = cursor.fetchone()
                return row[0] if row else None
    except Exception:
        traceback.print_exc()
        return None

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

if __name__ == "__main__":
    # fetch_recent_subsidy_applications()
    # test_fetch_emails()
    print(get_worker_names())
    # get_mail_content()
