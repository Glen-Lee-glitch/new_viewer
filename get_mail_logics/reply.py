import os
import sys
import json
import base64
import psycopg2
import time
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

# Gmail API Scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Gmail Token File Path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, 'token111.json')

def get_gmail_service():
    """Gmail API 서비스 객체 생성"""
    print("🔄 Initializing Gmail Service...", flush=True)
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing token...", flush=True)
            creds.refresh(Request())
        else:
            print("❌ Token expired or invalid, and no refresh token available.", flush=True)
            return None
            
    service = build('gmail', 'v1', credentials=creds)
    print("✅ Gmail Service Initialized", flush=True)
    return service

# PostgreSQL Configuration
DB_CONFIG = {
    "host": "192.168.0.92",
    "database": "postgres",
    "user": "postgres",
    "password": "greet1202!@",
    "port": "5432",
    "connect_timeout": 3
}

def get_db_connection():
    """PostgreSQL 데이터베이스 연결 생성"""
    print("🔄 Connecting to Database...", flush=True)
    conn = psycopg2.connect(**DB_CONFIG)
    print("✅ Database Connected", flush=True)
    return conn

def get_recent_thread_id(conn, rn):
    """
    1. ev_rns 테이블과 rns 테이블을 조인하여 RN에 해당하는 recent_thread_id를 가져옵니다.
    """
    try:
        with conn.cursor() as cursor:
            # ev_rns의 rn과 rns의 RN을 매칭
            sql = """
                SELECT r.recent_thread_id 
                FROM rns r 
                JOIN ev_rns e ON r."RN" = e.rn 
                WHERE e.rn = %s
            """
            cursor.execute(sql, (rn,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return None
    except Exception as e:
        print(f"❌ Error getting thread_id for RN {rn}: {e}", flush=True)
        return None

def get_email_details(conn, thread_id):
    """
    3. emails 테이블에서 thread_id를 기준으로 sender_address, cc_address를 조회합니다.
    """
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT sender_address, cc_address 
                FROM emails 
                WHERE thread_id = %s
            """
            cursor.execute(sql, (thread_id,))
            result = cursor.fetchone()
            if result:
                return {
                    'thread_id': thread_id,
                    'sender_address': result[0],
                    'cc_address': result[1]
                }
            return None
    except Exception as e:
        print(f"❌ Error getting email details for thread {thread_id}: {e}", flush=True)
        return None

def update_status_both_tables(conn, rn, status):
    """
    rns 테이블과 ev_rns 테이블의 status 값을 모두 업데이트합니다.
    """
    try:
        with conn.cursor() as cursor:
            # rns 테이블 업데이트
            sql_rns = "UPDATE rns SET status = %s WHERE \"RN\" = %s"
            cursor.execute(sql_rns, (status, rn))
            
            # ev_rns 테이블 업데이트 (데이터가 있을 때만 업데이트됨)
            sql_ev_rns = "UPDATE ev_rns SET status = %s WHERE rn = %s"
            cursor.execute(sql_ev_rns, (status, rn))
            
            conn.commit()
            print(f"✅ DB Update Successful - RN: {rn}, Status: {status}", flush=True)
            return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to update status for RN {rn}: {e}", flush=True)
        return False

def send_reply_all_email(service, email_info, rn, apply_num, special_items=None, status=None):
    """
    5. 가져온 정보를 토대로 전체 답장 메일을 전송합니다.
    - status == '중복메일확인': "처리 완료하였습니다."
    - 그 외: "{apply_num} [{special}] 신청완료입니다."
    """
    if not email_info:
        print("❌ Email info is missing.", flush=True)
        return

    thread_id = email_info['thread_id']
    sender = email_info['sender_address']
    cc = email_info['cc_address']
    
    # 답장 내용 구성
    if status == '중복메일확인':
        message_text = "처리 완료하였습니다."
    else:
        if special_items and len(special_items) > 0:
            valid_items = [str(item) for item in special_items if item]
            special_text = "/".join(valid_items)
            message_text = f"#{apply_num} {special_text} 신청완료입니다."
        else:
            message_text = f"#{apply_num} 신청완료입니다."
    
    try:
        # Gmail API를 통해 스레드의 마지막 메시지 ID와 제목을 가져옴
        thread = service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread.get('messages', [])
        if not messages:
            print(f"⚠️ No messages found in thread {thread_id}", flush=True)
            return
            
        last_msg = messages[-1]
        
        # 헤더 정보 추출
        headers = last_msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
        message_id = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), '')
        references = next((h['value'] for h in headers if h['name'].lower() == 'references'), '')

        # MIME 메시지 생성
        message = MIMEText(message_text)
        
        # 수신자 설정
        message['To'] = sender
        if cc:
            message['Cc'] = cc
        
        # 제목 설정
        if not subject.lower().startswith('re:'):
            message['Subject'] = f"Re: {subject}"
        else:
            message['Subject'] = subject

        # 스레딩 헤더 설정
        if message_id:
            message['In-Reply-To'] = message_id
            message['References'] = f"{references} {message_id}".strip()

        # 인코딩
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        body = {'raw': raw_message, 'threadId': thread_id}

        # 전송
        sent_message = service.users().messages().send(userId='me', body=body).execute()
        print(f"✅ Reply sent successfully for RN {rn} (Apply Num: {apply_num}, Status: {status})", flush=True)
        return sent_message

    except Exception as e:
        print(f"❌ Failed to send reply: {e}", flush=True)

def fetch_pending_applications(conn):
    """
    1. ev_rns 테이블에서 status가 '신청완료' 또는 '중복메일확인'인 항목
    2. rns 테이블에서 status가 '중복메일확인'인 항목 (ev_rns에 없을 수도 있음)
    """
    print("🔄 Fetching pending applications...", flush=True)
    results = []
    try:
        with conn.cursor() as cursor:
            # 1. ev_rns 조회
            sql_ev = "SELECT rn, apply_num, special, status FROM ev_rns WHERE status IN ('신청완료', '중복메일확인')"
            cursor.execute(sql_ev)
            ev_rows = cursor.fetchall()
            results.extend(ev_rows)
            
            # 2. rns 조회 (중복메일확인) - ev_rns에 없는 것만 추가하거나, 중복 제거 로직 필요
            # 여기서는 간단하게 rns만 조회하되, 이미 results에 있는 RN은 제외
            existing_rns = {row[0] for row in results}
            
            sql_rns = "SELECT \"RN\", NULL as apply_num, NULL as special, status FROM rns WHERE status = '중복메일확인'"
            cursor.execute(sql_rns)
            rns_rows = cursor.fetchall()
            
            for row in rns_rows:
                if row[0] not in existing_rns:
                    results.append(row)
            
            print(f"📋 Fetched {len(results)} rows.", flush=True)
            return results  # [(rn, apply_num, special, status), ...]
    except Exception as e:
        print(f"❌ Error fetching pending applications: {e}", flush=True)
        return []

def process_single_application(service, conn, rn, apply_num, special_items=None, status=None):
    """
    단일 건에 대한 처리 로직
    """
    print(f"\n🚀 Starting process for RN: {rn}, Apply Num: {apply_num}, Status: {status}", flush=True)
    
    thread_id = get_recent_thread_id(conn, rn)
    if not thread_id:
        print(f"⚠️ Thread ID not found for RN: {rn}", flush=True)
        return

    email_info = get_email_details(conn, thread_id)
    if not email_info:
        print(f"⚠️ Email details not found for thread: {thread_id}", flush=True)
        return
    
    print(f"🔍 Found Info - Thread: {thread_id}, To: {email_info['sender_address']}", flush=True)

    sent_msg = send_reply_all_email(service, email_info, rn, apply_num, special_items, status)
    
    if sent_msg:
        update_status_both_tables(conn, rn, '이메일 전송')

def main():
    try:
        service = get_gmail_service()
        if not service:
            print("❌ Gmail service initialization failed.", flush=True)
            return
        
        conn = get_db_connection()
    except Exception as e:
        print(f"❌ Initialization error: {e}", flush=True)
        return

    try:
        pending_apps = fetch_pending_applications(conn)
        print(f"📋 Found {len(pending_apps)} pending applications.", flush=True)

        for row in pending_apps:
            rn = row[0]
            apply_num = row[1]
            special_items = row[2] if len(row) > 2 else None
            status = row[3]
            process_single_application(service, conn, rn, apply_num, special_items, status)
            
            # 5초 대기
            print("⏳ Waiting 5 seconds before next process...", flush=True)
            time.sleep(5)

    finally:
        if conn:
            conn.close()
        print("\n🎉 All processes completed.", flush=True)

if __name__ == "__main__":
    main()