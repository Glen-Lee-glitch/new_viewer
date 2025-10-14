import os
import re
import base64
import time
import tempfile
import threading
from queue import Queue
from datetime import datetime, timedelta

import mysql.connector
from mysql.connector import Error
import pytz
from filelock import FileLock

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

# --- 전역 설정 ---
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
MYSQL_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'database': 'greetlounge',
    'charset': 'utf8mb4'
}
CREDENTIALS_FILE = 'credentials_3.json'
TOKEN_FILE = 'token123.json'
ATTACHMENT_SAVE_DIR = "C:\\Users\\HP\\Desktop\\greet_db\\files\\new"

# 스레드 간 통신을 위한 공유 큐
download_queue = Queue()
preprocess_queue = Queue()  # 전처리 큐 추가

# 전처리 임계값 설정
PREPROCESS_THRESHOLD_MB = 3.0  # 3MB 초과 시에만 전처리
PROCESSED_DIR = "C:\\Users\\HP\\Desktop\\greet_db\\files\\processed"

# --- DB 및 Gmail API 연결 ---

def get_database_connection():
    """MySQL 데이터베이스 연결 반환 (스레드별로 호출)"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        print(f"❌ MySQL 연결 실패: {e}")
        return None

def get_service(credentials_file, token_file):
    """Gmail 서비스 인증 (토큰 파일 잠금 기능 추가)"""
    creds = None
    token_lock_file = f"{token_file}.lock"
    lock = FileLock(token_lock_file)

    with lock:
        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("🔄 Gmail 토큰 갱신 중...")
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        print("✅ Gmail 서비스 인증 성공")
        return service
    except Exception as e:
        print(f"❌ Gmail 서비스 생성 실패: {e}")
        return None

# --- 메일 수집 스레드(db_mail_thread)용 함수 ---

def has_attachment(payload):
    """첨부파일 존재 여부만 빠르게 확인 (다운로드 안함)"""
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('filename') or part.get('body', {}).get('attachmentId'):
                return True
            # 재귀적으로 내부 part도 확인
            if 'parts' in part and has_attachment(part):
                return True
    if payload.get('body', {}).get('attachmentId'):
        return True
    return False

def save_email_to_db(conn, thread_id, title, content, from_address, received_date, has_attach):
    """emails 테이블에 메일 정보 저장"""
    # (db_mail.py의 save_email_to_db 함수와 동일)
    cursor = conn.cursor()
    try:
        sql = """
            INSERT INTO emails (thread_id, received_date, from_email_address, title, content, attached_file)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                received_date=VALUES(received_date), from_email_address=VALUES(from_email_address),
                title=VALUES(title), content=VALUES(content), attached_file=VALUES(attached_file)
        """
        cursor.execute(sql, (thread_id, received_date, from_address, title, content, 1 if has_attach else 0))
        # print(f"✅ (DB) 메일 정보 저장: {thread_id}")
        return True
    except Error as e:
        print(f"❌ (DB) 메일 정보 저장 실패: {e}")
        return False

def insert_new_application(conn, rn, received_date, thread_id, region, delivery_date, name, special_note):
    """subsidy_applications 테이블에 신규 신청 건 삽입"""
    # (db_mail.py의 insert_new_application 함수와 동일, region NULL 처리 포함)
    cursor = conn.cursor()
    try:
        sql = """
            INSERT INTO subsidy_applications 
            (RN, mail_count, recent_received_date, recent_thread_id, region, delivery_date, name, special_note, status, status_updated_at)
            VALUES (%s, 1, %s, %s, %s, %s, %s, %s, '신규', %s)
        """
        if not delivery_date: delivery_date = None
        if not region: region = None
        now_kst = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(sql, (rn, received_date, thread_id, region, delivery_date, name, special_note, now_kst))
        # print(f"✅ (DB) 신규 신청 건 저장: {rn}")
        return True
    except Error as e:
        print(f"❌ (DB) 신규 신청 건 저장 실패: {e}")
        return False

def update_duplicate_application(conn, rn, new_thread_id, new_received_date):
    """중복 RN 업데이트"""
    # (db_mail.py의 update_duplicate_application 함수와 동일)
    cursor = conn.cursor()
    try:
        update_sql = "UPDATE subsidy_applications SET mail_count = mail_count + 1, recent_received_date = %s, recent_thread_id = %s WHERE RN = %s"
        cursor.execute(update_sql, (new_received_date, new_thread_id, rn))
        insert_sql = "INSERT INTO duplicated_rn (thread_id, RN, received_date) VALUES (%s, %s, %s)"
        cursor.execute(insert_sql, (new_thread_id, rn, new_received_date))
        # print(f"✅ (DB) 중복 신청 건 업데이트: {rn}")
        return True
    except Error as e:
        print(f"❌ (DB) 중복 신청 건 업데이트 실패: {e}")
        return False

# --- 공통 유틸리티 함수 ---
# (db_mail.py의 함수들, 일부는 간소화)
def get_existing_rn_numbers(conn):
    cursor = conn.cursor()
    cursor.execute('SELECT RN FROM subsidy_applications')
    return {row[0] for row in cursor.fetchall()}

def get_label_id(service, label_name='RN붙임'):
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])
    return next((label['id'] for label in labels if label['name'] == label_name), None)

def safe_modify_message(service, msg_id, label_id):
    try:
        service.users().messages().modify(userId='me', id=msg_id, body={'addLabelIds': [label_id]}).execute()
        return True
    except Exception as e:
        print(f"⚠️ 라벨 추가 실패: {e}")
        return False

def extract_text_from_payload(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            result = extract_text_from_payload(part)
            if result: return result
    elif payload.get('mimeType') in ['text/plain', 'text/html']:
        data = payload.get('body', {}).get('data', '')
        if data:
            try:
                text = base64.urlsafe_b64decode(data).decode('utf-8')
                if payload['mimeType'] == 'text/html':
                    text = re.sub(r'<[^>]+>', '', text)
                return re.sub(r'[ \t]+', ' ', text).strip()[:1000]
            except: return "내용 디코딩 실패"
    return ""

def extract_info_from_subject(subject):
    rn_match = re.search(r'RN\d{9}', subject)
    if not rn_match: return None
    rn_num = rn_match.group()
    date_match = re.search(r'\[(\d{1,2})/(\d{1,2})\]', subject)
    date_str = f'2025-{int(date_match.group(1)):02d}-{int(date_match.group(2)):02d}' if date_match else None
    region_match = re.search(r'RN\d{9}\s*/\s*([^/]+)', subject)
    region = region_match.group(1).strip() if region_match else None
    if region and any(word in region for word in ['리스', '캐피탈']): region = '한국환경공단'
    applier = None
    try:
        parts = [p.strip() for p in subject.split('/')]
        model_index = next((i for i, part in enumerate(parts) if 'Model' in part), -1)
        if model_index != -1 and model_index + 1 < len(parts) and parts[model_index + 1]:
            applier = parts[model_index + 1]
    except: pass
    return {'rn_num': rn_num, 'date': date_str, 'region': region, 'applier': applier}

def extract_special_note_from_content(content):
    if not content: return ''
    patterns = [r'\d+\.\s*특이사항\s*:\s*([^\n\r]+)', r'특이사항\s*:\s*([^\n\r]+)', r'특이사항\s+([^\n\r]+)']
    for p in patterns:
        match = re.search(p, content)
        if match: return match.group(1).strip()
    return ''

def parsing_special(text):
    return '' if text.startswith('감사') else text

# --- 다운로드 워커 스레드(download_worker_thread)용 함수 ---

def download_attachment(gmail_service, msg_id, part, save_dir, new_filename=None):
    """단일 첨부파일 다운로드"""
    try:
        filename = part.get('filename', '')
        if not filename: return None
        if 'attachmentId' in part.get('body', {}):
            attachment_id = part['body']['attachmentId']
            attachment = gmail_service.users().messages().attachments().get(
                userId='me', messageId=msg_id, id=attachment_id
            ).execute()
            file_data = base64.urlsafe_b64decode(attachment['data'])
            
            # 새 파일명이 지정된 경우 사용, 아니면 원본 파일명 사용
            if new_filename:
                # 원본 파일의 확장자 유지
                _, ext = os.path.splitext(filename)
                final_filename = f"{new_filename}{ext}"
            else:
                base_name, ext = os.path.splitext(filename)
                final_filename = filename
            
            # 파일명 중복 방지
            counter = 1
            temp_filename = final_filename
            while os.path.exists(os.path.join(save_dir, temp_filename)):
                if new_filename:
                    temp_filename = f"{new_filename}_{counter}{ext}"
                else:
                    temp_filename = f"{base_name}_{counter}{ext}"
                counter += 1
            final_filename = temp_filename
            
            file_path = os.path.join(save_dir, final_filename)
            with open(file_path, 'wb') as f: f.write(file_data)
            print(f"  ➡️ 파일 저장: {file_path}")
            return file_path
        return None
    except Exception as e:
        print(f"  ⚠️ 첨부파일 다운로드 실패: {e}")
        return None

def download_and_process_attachments(gmail_service, msg_id, payload, thread_id, save_dir, subject):
    """payload에서 모든 첨부파일을 찾아 다운로드하고 필요시 병합"""
    # (db_mail.py의 check_attached_file 로직을 재구성)
    if not os.path.exists(save_dir): os.makedirs(save_dir)
    
    # 제목에서 RN, name, region 추출
    info = extract_info_from_subject(subject)
    new_filename = None
    
    if info and info.get('rn_num'):
        # {RN}_{name}_{region} 형식으로 파일명 생성
        parts = [info['rn_num']]
        if info.get('applier'):
            parts.append(info['applier'])
        if info.get('region'):
            parts.append(info['region'])
        new_filename = '_'.join(parts)
        print(f"  📝 새 파일명: {new_filename}")
    
    attachment_paths = []
    
    def find_attachments_recursive(part_or_payload):
        """재귀적으로 첨부파일 part를 찾아서 다운로드"""
        if 'parts' in part_or_payload:
            for sub_part in part_or_payload['parts']:
                find_attachments_recursive(sub_part)
        
        if part_or_payload.get('filename') or part_or_payload.get('body', {}).get('attachmentId'):
            file_path = download_attachment(gmail_service, msg_id, part_or_payload, save_dir, new_filename)
            if file_path:
                attachment_paths.append(file_path)

    find_attachments_recursive(payload)

    if not attachment_paths: return 'N'
    
    unique_paths = list(set(attachment_paths))
    
    # PDF 병합 로직은 생략 (필요 시 db_mail.py에서 가져와 추가)
    # 현재는 파일 경로를 세미콜론으로 연결하여 반환
    return ';'.join(unique_paths)

def update_email_attachment_path(conn, thread_id, file_path, file_rendered=0):
    """emails 테이블에 최종 첨부파일 경로 업데이트 및 file_rendered 설정"""
    cursor = conn.cursor()
    try:
        sql = """UPDATE emails 
                 SET attached_file = 1, 
                     attached_file_path = %s,
                     file_rendered = %s
                 WHERE thread_id = %s"""
        cursor.execute(sql, (file_path, file_rendered, thread_id))
        conn.commit()
        print(f"  ✅ (DB) 첨부파일 정보 저장: {thread_id} (file_rendered={file_rendered})")
    except Error as e:
        print(f"  ❌ (DB) 첨부파일 경로 업데이트 실패: {e}")
        conn.rollback()

# --- 스레드 메인 함수 ---

def db_mail_thread(poll_interval=20):
    """20초마다 새 메일을 확인하고 DB에 저장, 다운로드 큐에 추가"""
    print("🚀 메일 수집 스레드 시작")
    gmail_service = get_service(CREDENTIALS_FILE, TOKEN_FILE)
    if not gmail_service: return
    
    label_id = get_label_id(gmail_service)
    if not label_id:
        print("❌ 'RN붙임' 라벨을 찾을 수 없습니다. 스레드를 종료합니다.")
        return

    while True:
        print(f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        print("📬 새 메일 확인 중...")
        
        conn = get_database_connection()
        if not conn:
            time.sleep(poll_interval)
            continue

        try:
            results = gmail_service.users().messages().list(
                userId='me', q='newer_than:2h -label:RN붙임', maxResults=25
            ).execute()
            messages = results.get('messages', [])

            if not messages:
                print("✅ 처리할 새 메일이 없습니다.")
            else:
                print(f"🔍 {len(messages)}개의 새 메일 스레드 발견. 처리 시작...")
                existing_rns = get_existing_rn_numbers(conn)
                
                for msg in reversed(messages):
                    try:
                        msg_detail = gmail_service.users().messages().get(
                            userId='me', id=msg['id'], format='full'
                        ).execute()
                        
                        if msg_detail['id'] != msg_detail['threadId']: continue

                        payload = msg_detail.get('payload', {})
                        headers = payload.get('headers', [])
                        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                        thread_id = msg_detail['threadId']
                        
                        # 1. 메일 정보 추출 및 DB 저장
                        content = extract_text_from_payload(payload)
                        ts = int(msg_detail.get('internalDate')) / 1000
                        received_dt = datetime.fromtimestamp(ts, pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
                        from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                        from_address = re.search(r'<(.+?)>', from_header).group(1) if re.search(r'<(.+?)>', from_header) else from_header

                        has_attach = has_attachment(payload)
                        save_email_to_db(conn, thread_id, subject, content, from_address, received_dt, False)  # 다운로드 완료 전까지 0

                        # 2. RN 정보 추출 및 subsidy_applications 저장
                        info = extract_info_from_subject(subject)
                        if info and info.get('rn_num'):
                            rn_num = info['rn_num']
                            special_note = parsing_special(extract_special_note_from_content(content))
                            
                            if rn_num in existing_rns:
                                update_duplicate_application(conn, rn_num, thread_id, received_dt)
                            else:
                                insert_new_application(conn, rn_num, received_dt, thread_id, info.get('region'), info.get('date'), info.get('applier'), special_note)
                                existing_rns.add(rn_num)
                        
                        # 3. 라벨 부착
                        safe_modify_message(gmail_service, msg['id'], label_id)

                        # 4. 첨부파일이 있으면 다운로드 큐에 추가
                        if has_attach:
                            download_queue.put({
                                'msg_id': msg['id'],
                                'thread_id': thread_id,
                            })
                            print(f"📎 다운로드 큐에 추가: {thread_id}")

                    except HttpError as e:
                        if e.resp.status == 404: print(f"⚠️ 404 - 삭제된 메일: {msg['id']}")
                        else: print(f"❌ HTTP 오류: {e}")
                    except Exception as e:
                        print(f"❌ 메일 처리 중 예외 발생: {e}")
                
                conn.commit()
                print("🎉 메일 처리 완료.")

        except Exception as e:
            print(f"❌ 메인 루프 오류: {e}")
            if conn.is_connected(): conn.rollback()
        finally:
            if conn.is_connected(): conn.close()

        print(f"⏰ {poll_interval}초 후에 다시 실행합니다.")
        time.sleep(poll_interval)

def download_worker_thread():
    """다운로드 큐를 감시하고 첨부파일을 다운로드 (전처리는 별도 스레드에서)"""
    print("🚀 다운로드 워커 스레드 시작")
    gmail_service = get_service(CREDENTIALS_FILE, TOKEN_FILE)
    if not gmail_service: return

    while True:
        try:
            task = download_queue.get()
            msg_id = task['msg_id']
            thread_id = task['thread_id']
            
            print(f"⬇️ 다운로드 시작: {thread_id}")

            conn = get_database_connection()
            if not conn:
                # DB 연결 실패 시 작업을 다시 큐에 넣고 대기
                print("  ⚠️ DB 연결 실패. 작업을 큐에 다시 추가합니다.")
                download_queue.put(task)
                time.sleep(10)
                continue

            try:
                msg_detail = gmail_service.users().messages().get(
                    userId='me', id=msg_id, format='full'
                ).execute()
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                
                # 다운로드 수행
                final_path = download_and_process_attachments(
                    gmail_service, msg_id, payload, thread_id, ATTACHMENT_SAVE_DIR, subject
                )
                
                if final_path != 'N':
                    # 세미콜론으로 구분된 여러 파일 확인
                    file_paths = final_path.split(';')
                    file_paths = [p.strip() for p in file_paths if p.strip()]
                    
                    # PDF 파일들만 필터링
                    pdf_files = [p for p in file_paths if p.lower().endswith('.pdf')]
                    
                    # 전체 용량 계산 (PDF만)
                    total_size_mb = sum(os.path.getsize(p) / (1024 * 1024) for p in pdf_files)
                    
                    needs_preprocess = False
                    
                    # PDF가 1개 이상이고 전체 용량이 3MB 초과 시 전처리 필요
                    if pdf_files and total_size_mb > PREPROCESS_THRESHOLD_MB:
                        needs_preprocess = True
                        print(f"  📏 PDF 파일 {len(pdf_files)}개, 총 크기: {total_size_mb:.2f} MB → 전처리 필요")
                        
                        # 전처리 큐에 추가 (여러 파일을 리스트로 전달)
                        preprocess_queue.put({
                            'thread_id': thread_id,
                            'original_paths': pdf_files  # 여러 파일을 리스트로
                        })
                        print(f"  📋 전처리 큐에 추가: {len(pdf_files)}개 파일 병합 예정")
                    else:
                        if pdf_files:
                            print(f"  📏 PDF 파일 {len(pdf_files)}개, 총 크기: {total_size_mb:.2f} MB → 전처리 불필요")
                        else:
                            print(f"  📏 PDF 파일 없음 → 전처리 불필요")
                    
                    # DB 업데이트: file_rendered = 0 (아직 전처리 안됨)
                    final_paths_str = ';'.join(file_paths)
                    update_email_attachment_path(conn, thread_id, final_paths_str, file_rendered=0)
                
                print(f"✅ 다운로드 완료: {thread_id}")

            except Exception as e:
                print(f"❌ 다운로드 처리 중 예외 발생: {thread_id}, {e}")
            finally:
                if conn.is_connected(): conn.close()
                download_queue.task_done()

        except Exception as e:
            # 큐 자체의 문제 등 예상치 못한 오류
            print(f"❌ 워커 스레드 오류: {e}")
            time.sleep(5)


def preprocess_worker_thread():
    """✨ 전처리 큐를 감시하고 대용량 PDF 최적화 수행 (여러 파일 병합)"""
    print("🚀 전처리 워커 스레드 시작")
    
    # 전처리 디렉토리 생성
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    while True:
        try:
            task = preprocess_queue.get()
            thread_id = task['thread_id']
            original_paths = task.get('original_paths', [])  # 리스트로 받음
            
            # 단일 파일인 경우 리스트로 변환 (하위 호환성)
            if not isinstance(original_paths, list):
                original_paths = [original_paths]
            
            if not original_paths:
                preprocess_queue.task_done()
                continue
            
            # 전체 파일 크기 계산
            total_size_mb = sum(os.path.getsize(p) / (1024 * 1024) for p in original_paths)
            print(f"🔧 전처리 시작: {len(original_paths)}개 파일, 총 {total_size_mb:.2f} MB")
            
            try:
                # 여러 PDF를 하나로 병합 + 전처리
                merged_processed_path = merge_and_preprocess_pdfs(original_paths, PROCESSED_DIR, thread_id)
                
                if merged_processed_path:
                    # ✨ DB 업데이트: 병합된 파일 하나의 경로로 교체
                    conn = get_database_connection()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            
                            # 전처리된 파일 크기
                            processed_size_mb = os.path.getsize(merged_processed_path) / (1024 * 1024)
                            
                            # DB 업데이트: 병합된 파일 경로만 저장
                            sql = """UPDATE emails 
                                     SET attached_file_path = %s,
                                         file_rendered = 1
                                     WHERE thread_id = %s"""
                            cursor.execute(sql, (merged_processed_path, thread_id))
                            conn.commit()
                            
                            print(f"  ✅ 병합 및 전처리 완료:")
                            print(f"     원본: {len(original_paths)}개 파일, {total_size_mb:.2f} MB")
                            print(f"     전처리: 1개 파일, {processed_size_mb:.2f} MB")
                            print(f"     저장 경로: {merged_processed_path}")
                            
                        except Error as e:
                            print(f"  ⚠️ DB 업데이트 실패: {e}")
                            conn.rollback()
                        finally:
                            if conn.is_connected():
                                conn.close()
                else:
                    print(f"  ⚠️ 전처리 실패: (원본 파일 사용)")
                
            except Exception as e:
                print(f"  ❌ 전처리 중 예외 발생: {e}")
                import traceback
                traceback.print_exc()
            finally:
                preprocess_queue.task_done()
                
        except Exception as e:
            print(f"❌ 전처리 워커 오류: {e}")
            time.sleep(5)


def merge_and_preprocess_pdfs(pdf_paths: list, processed_dir: str, thread_id: str) -> str | None:
    """여러 PDF 파일을 하나로 병합하고 최적화 (벡터 유지)
    
    Args:
        pdf_paths: 병합할 PDF 파일 경로 리스트
        processed_dir: 처리된 파일을 저장할 디렉토리
        thread_id: 메일 스레드 ID (파일명 생성용)
    
    Returns:
        병합 및 최적화된 PDF 파일 경로 (실패 시 None)
    """
    try:
        from pathlib import Path
        import pymupdf
        
        if not pdf_paths:
            return None
        
        # 단일 파일인 경우 기존 함수 사용
        if len(pdf_paths) == 1:
            return preprocess_pdf_for_rendering(pdf_paths[0], processed_dir)
        
        # 병합된 파일명 생성: thread_id 기반
        merged_filename = f"{thread_id}_merged_processed.pdf"
        merged_path = os.path.join(processed_dir, merged_filename)
        
        # 이미 처리된 파일이 있는지 확인
        if os.path.exists(merged_path):
            # 모든 원본 파일보다 최신인지 확인
            merged_mtime = os.path.getmtime(merged_path)
            if all(merged_mtime >= os.path.getmtime(p) for p in pdf_paths if os.path.exists(p)):
                print(f"  ⚡ 이미 병합 전처리됨: {merged_filename}")
                return merged_path
        
        print(f"  🔧 {len(pdf_paths)}개 PDF 병합 및 최적화 중...")
        
        # 병합 및 A4 최적화
        merged_doc = pymupdf.open()
        
        for idx, pdf_path in enumerate(pdf_paths):
            print(f"    - [{idx+1}/{len(pdf_paths)}] {os.path.basename(pdf_path)}")
            
            try:
                with pymupdf.open(pdf_path) as source_doc:
                    # 각 페이지를 A4로 변환하여 병합
                    for page_num in range(len(source_doc)):
                        page = source_doc[page_num]
                        bounds = page.bound()
                        is_landscape = bounds.width > bounds.height
                        
                        if is_landscape:
                            a4_rect = pymupdf.paper_rect("a4-l")
                        else:
                            a4_rect = pymupdf.paper_rect("a4")
                        
                        # 새 A4 페이지 생성
                        new_page = merged_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                        
                        # 벡터 기반으로 페이지 복사
                        new_page.show_pdf_page(new_page.rect, source_doc, page_num)
            
            except Exception as e:
                print(f"    ⚠️ 파일 병합 실패: {os.path.basename(pdf_path)} - {e}")
                continue
        
        # 병합된 PDF 저장 (최적화)
        merged_doc.save(
            merged_path,
            garbage=4,
            deflate=True,
            clean=True,
            pretty=False,
            linear=False,
        )
        merged_doc.close()
        
        print(f"  ✅ 병합 완료: {merged_filename}")
        return merged_path
        
    except Exception as e:
        print(f"  ⚠️ 병합 및 전처리 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def preprocess_pdf_for_rendering(original_path: str, processed_dir: str) -> str | None:
    """PDF를 렌더링에 최적화된 형태로 전처리 (3MB 초과 파일용)
    
    전략: 벡터 기반 페이지는 그대로 복사, 이미지가 많은 페이지만 최적화
    """
    try:
        from pathlib import Path
        import pymupdf
        
        # 파일명 생성
        base_name = Path(original_path).stem
        processed_filename = f"{base_name}_processed.pdf"
        processed_path = os.path.join(processed_dir, processed_filename)
        
        # 이미 처리된 파일이 있고 최신이면 스킵
        if os.path.exists(processed_path):
            if os.path.getmtime(processed_path) >= os.path.getmtime(original_path):
                print(f"  ⚡ 이미 전처리됨: {processed_filename}")
                return processed_path
        
        print(f"  🔧 PDF 최적화 중: {base_name}")
        
        # 단순 최적화: garbage collection + deflate + clean
        # 벡터 데이터는 유지하면서 불필요한 객체만 제거
        with pymupdf.open(original_path) as source_doc:
            # A4 규격으로 변환하되, 벡터 데이터를 유지하는 방식
            new_doc = pymupdf.open()
            
            for page_num in range(len(source_doc)):
                page = source_doc[page_num]
                bounds = page.bound()
                is_landscape = bounds.width > bounds.height
                
                if is_landscape:
                    a4_rect = pymupdf.paper_rect("a4-l")
                else:
                    a4_rect = pymupdf.paper_rect("a4")
                
                # 새 A4 페이지 생성
                new_page = new_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                
                # show_pdf_page: 벡터 기반으로 페이지를 복사 (이미지로 변환하지 않음)
                new_page.show_pdf_page(new_page.rect, source_doc, page_num)
            
            # 강력한 최적화 옵션으로 저장
            new_doc.save(
                processed_path,
                garbage=4,          # 최대 garbage collection
                deflate=True,       # 압축 활성화
                clean=True,         # 불필요한 객체 제거
                pretty=False,       # 가독성 제거 (크기 감소)
                linear=False,       # 선형화 비활성화 (웹 최적화 불필요)
            )
            new_doc.close()
        
        return processed_path
        
    except Exception as e:
        print(f"  ⚠️ 전처리 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("="*50)
    print(" 메일 수집 및 첨부파일 다운로드 서비스 시작")
    print(f" 전처리 임계값: {PREPROCESS_THRESHOLD_MB} MB 초과")
    print("="*50)

    # 1. 메일 수집 스레드 (20초 주기)
    mail_collector = threading.Thread(target=db_mail_thread, daemon=True)
    mail_collector.start()

    # 2. 다운로드 워커 스레드
    attachment_downloader = threading.Thread(target=download_worker_thread, daemon=True)
    attachment_downloader.start()

    # 3. 전처리 워커 스레드 (새로 추가!)
    pdf_preprocessor = threading.Thread(target=preprocess_worker_thread, daemon=True)
    pdf_preprocessor.start()

    # 메인 스레드는 데몬 스레드가 종료되지 않도록 유지
    try:
        # 스레드가 살아있는지 주기적으로 확인
        while (mail_collector.is_alive() and 
               attachment_downloader.is_alive() and 
               pdf_preprocessor.is_alive()):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🚫 서비스를 종료합니다.")
