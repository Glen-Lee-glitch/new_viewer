import sqlite3
import os
import re
import base64
from datetime import datetime, timedelta
import pandas as pd
import pytz
import time
import socket
import tempfile

import mysql.connector
from mysql.connector import Error

from datetime import datetime, timedelta
import pandas as pd
import pytz
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from email.mime.text import MIMEText

# Gmail, read-only 권한
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/spreadsheets'
]

# db 위치 변경 -> 다른 로컬의 공유폴더
db_path = r"\\DESKTOP-KMJ\Users\HP\Desktop\greet_db\greetlounge.db"

MYSQL_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'database': 'greetlounge',
    'charset': 'utf8mb4'
}

def get_database_connection():
    """MySQL 데이터베이스 연결 반환"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except Error as e:
        print(f"❌ MySQL 연결 실패: {e}")
        return None

def insert_new_application(conn, rn, received_date, thread_id, region, delivery_date, name, special_note):
    """subsidy_applications 테이블에 신규 신청 건 삽입"""
    cursor = conn.cursor()
    
    try:
        sql = """
            INSERT INTO subsidy_applications 
            (RN, mail_count, recent_received_date, recent_thread_id, region, delivery_date, name, special_note, status)
            VALUES (%s, 1, %s, %s, %s, %s, %s, %s, '신규')
        """
        
        # delivery_date가 None이거나 빈 문자열일 경우 DB에 NULL로 들어가도록 처리
        if not delivery_date:
            delivery_date = None

        cursor.execute(sql, (
            rn,
            received_date,
            thread_id,
            region,
            delivery_date,
            name,
            special_note
        ))
        
        print(f"✅ 신규 신청 건 저장 완료 (MySQL): {rn}")
        return True

    except Error as e:
        # Primary Key 중복 에러(1062)는 중복 처리 로직에서 다루므로 여기선 실패로 간주
        print(f"❌ 신규 신청 건 저장 실패 (MySQL): {e}")
        return False

def update_duplicate_application(conn, rn, new_thread_id, new_received_date):
    """중복 RN 발생 시 subsidy_applications 업데이트 및 duplicated_rn에 이력 추가"""
    cursor = conn.cursor()
    
    try:
        # 1. subsidy_applications 테이블 업데이트
        update_sql = """
            UPDATE subsidy_applications
            SET
                mail_count = mail_count + 1,
                recent_received_date = %s,
                recent_thread_id = %s
            WHERE
                RN = %s
        """
        cursor.execute(update_sql, (new_received_date, new_thread_id, rn))
        
        # 2. duplicated_rn 테이블에 중복 이력 삽입
        insert_sql = """
            INSERT INTO duplicated_rn (thread_id, RN, received_date)
            VALUES (%s, %s, %s)
        """
        cursor.execute(insert_sql, (new_thread_id, rn, new_received_date))
        
        print(f"✅ 중복 신청 건 업데이트 완료 (MySQL): {rn}")
        return True

    except Error as e:
        print(f"❌ 중복 신청 건 업데이트 실패 (MySQL): {e}")
        # 한 작업이라도 실패하면 False 반환 (main 함수에서 rollback 처리)
        return False

def get_existing_rn_numbers():
    """기존 RN 번호 목록 조회 (subsidy_applications 테이블, MySQL 버전)"""
    conn = get_database_connection()
    if not conn:
        return set() # DB 연결 실패 시 빈 집합 반환
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT RN FROM subsidy_applications')
        # 튜플의 첫 번째 요소를 추출하여 집합(set)으로 만듦
        all_rns = {row[0] for row in cursor.fetchall()}
        return all_rns
    except Error as e:
        print(f"❌ RN 번호 목록 조회 실패 (MySQL): {e}")
        return set()
    finally:
        if conn.is_connected():
            conn.close()

def get_service(credentials_file, token_file):
    """Gmail 서비스 인증 및 서비스 객체 생성"""
    creds = None
    # token.json 파일이 이미 있는 경우, 저장된 인증 정보를 사용합니다.
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # 인증 정보가 없거나 유효하지 않은 경우, 새로 로그인합니다.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        # 새로운 인증 정보를 token.json 파일에 저장합니다.
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
    try:
        # build() 함수를 사용하여 실제 서비스 객체를 생성하고 반환합니다.
        service = build('gmail', 'v1', credentials=creds)
        print("✅ Gmail 서비스 인증 성공")
        return service
    except Exception as e:
        print(f"❌ Gmail 서비스 생성 실패: {e}")
        return None

def get_dynamic_search_epoch():
    """동적 검색 시간 생성"""
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    weekday = now.weekday()  # 0=월, ..., 6=일

    if weekday in [5, 6, 0]:  # 토(6), 일(0), 월(0)
        # 토~월은 3일 전 00:00
        base_time = now - timedelta(days=3)
        target_time = datetime(
            year=base_time.year, month=base_time.month, day=base_time.day,
            hour=0, minute=0, second=0, tzinfo=kst
        )
    else:
        # 나머지 요일은 16시간 전
        target_time = now - timedelta(hours=16)

    return int(target_time.timestamp())

def extract_info_from_subject(subject):
    """메일 제목에서 정보 추출"""
    rn_match = re.search(r'RN\d{9}', subject)
    if not rn_match:
        return None

    rn_num = rn_match.group()

    # 날짜 추출: [4/25], [5/8], 등 다양한 패턴에서도 추출 가능
    date_match = re.search(r'\[(\d{1,2})/(\d{1,2})\]', subject)
    date_str = None
    if date_match:
        month, day = map(int, date_match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            date_str = f'2025-{int(month):02d}-{int(day):02d}'
    else:
        date_str = None

    # '긴급' 텍스트 있는지 확인
    is_urgent = '긴급' in subject

    # 지역 추출: RN 다음의 / 뒤 첫 번째 구간
    region_match = re.search(r'RN\d{9}\s*/\s*([^/]+)', subject)
    region = region_match.group(1).strip() if region_match else None

    lease_word = ['리스', '캐피탈']

    if region and any(word in region for word in lease_word):
        region = '한국환경공단'

    # 신청인(성명) 추출: 네 번째 / 이후의 문자열
    applier_match = re.search(r'([^/]+/[^/]+/[^/]+/[^/]+/)\s*([^/]+)', subject)
    applier = applier_match.group(2).strip() if applier_match else None

    return {
        'date': date_str,
        'rn_num': rn_num,
        'region': region,
        'urgent': is_urgent,
        'applier': applier
    }

def get_label_id(service, label_name='RN붙임'):
    """Gmail 라벨 ID 가져오기"""
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])
    for label in labels:
        if label['name'] == label_name:
            return label['id']
    return None

def safe_modify_message(service, msg_id, label_id, max_retries=3):
    """메시지에 라벨 추가 (재시도 포함)"""
    for attempt in range(max_retries):
        try:
            service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={
                    'addLabelIds': [label_id]
                }
            ).execute()
            return True
        except Exception as e:
            print(f"⚠️ 라벨 추가 실패 (시도 {attempt+1}/{max_retries}): {e}")
            time.sleep(2)
    return False

def extract_email_content(msg_detail, gmail_service):
    """메일에서 제목, 본문, 발신자 이메일 주소 추출"""
    try:
        # 메일 상세 정보 가져오기 (전체 메시지)
        full_message = gmail_service.users().messages().get(
            userId='me',
            id=msg_detail['id'],
            format='full'
        ).execute()
        
        payload = full_message.get('payload', {})
        headers = payload.get('headers', [])
        
        # 제목 추출
        title = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
        
        # 발신자 이메일 주소 추출
        from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
        from_address = extract_email_from_header(from_header)
        
        # 본문 추출
        content = extract_text_from_payload(payload)
        
        return {
            'title': title,
            'content': content,
            'from_address': from_address
        }
        
    except Exception as e:
        print(f"⚠️ 메일 내용 추출 실패: {e}")
        return {
            'title': '',
            'content': '',
            'from_address': ''
        }

def extract_email_from_header(from_header):
    """From 헤더에서 이메일 주소만 추출"""
    try:
        print(f" extract_email_from_header 입력: {from_header}")
        
        # "Name <email@domain.com>" 형식 처리
        if '<' in from_header and '>' in from_header:
            start = from_header.find('<') + 1
            end = from_header.find('>')
            result = from_header[start:end].strip()
            print(f"🔍 패턴1 (꺾쇠괄호): {result}")
            print(f"🔍 패턴1 반환값: '{result}'")  # 디버깅 추가
            return result
        
        # "email@domain.com" 형식 처리
        elif '@' in from_header:
            # 이메일 주소 패턴으로 추출
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', from_header)
            if email_match:
                result = email_match.group()
                print(f"🔍 패턴2 (이메일 패턴): {result}")
                print(f"🔍 패턴2 반환값: '{result}'")  # 디버깅 추가
                return result
        
        print(f"🔍 패턴3 (원본 그대로): {from_header.strip()}")
        print(f"🔍 패턴3 반환값: '{from_header.strip()}'")  # 디버깅 추가
        return from_header.strip()
        
    except Exception as e:
        print(f"⚠️ 이메일 주소 추출 실패: {e}")
        print(f"🔍 예외 발생 시 반환값: '{from_header.strip()}'")  # 디버깅 추가
        return from_header.strip()

def extract_text_from_payload(payload):
    """메일 본문에서 텍스트 추출"""
    if 'parts' in payload:
        for part in payload['parts']:
            result = extract_text_from_payload(part)
            if result:
                return result
    else:
        mime = payload.get('mimeType', '')
        if mime in ['text/plain', 'text/html']:
            data = payload.get('body', {}).get('data', '')
            if data:
                try:
                    text = base64.urlsafe_b64decode(data).decode('utf-8')
                    if mime == 'text/html':
                        # HTML 태그 제거
                        text = re.sub(r'<[^>]+>', '', text)
                    
                    # 연속된 공백만 하나로, 줄바꿈은 유지
                    text = re.sub(r'[ \t]+', ' ', text).strip()
                    
                    # 너무 긴 텍스트는 자르기
                    if len(text) > 1000:
                        text = text[:997] + '...'
                    
                    return text
                except Exception:
                    return "내용 디코딩 실패"
    return None

def save_email_to_db(conn, thread_id, title, content, from_address, mail_received_date=None, has_attachment=False):
    """emails 테이블에 메일 정보 저장 (MySQL 버전)"""
    cursor = conn.cursor()
    
    try:
        # MySQL 스키마에 맞게 컬럼명과 데이터 조정
        sql = """
            INSERT INTO emails (thread_id, received_date, from_email_address, title, content, attached_file)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                received_date=VALUES(received_date), 
                from_email_address=VALUES(from_email_address),
                title=VALUES(title),
                content=VALUES(content),
                attached_file=VALUES(attached_file)
        """
        
        # Boolean을 tinyint에 맞게 0 또는 1로 변환
        attached_file_int = 1 if has_attachment else 0
        
        # 쿼리 실행
        cursor.execute(sql, (
            thread_id,
            mail_received_date,
            from_address,
            title,
            content,
            attached_file_int
        ))
        
        # conn.commit()은 main 함수에서 관리
        print(f"✅ 메일 정보 저장 완료 (MySQL): {thread_id}")
        return True
        
    except Error as e:
        print(f"❌ 메일 정보 저장 실패 (MySQL): {e}")
        return False

def extract_special_note_from_content(content):
    """메일 내용에서 특이사항 추출"""
    if not content:
        return ''
    
    try:
        # "특이사항:" 패턴으로 검색
        # 다양한 패턴 지원: "6. 특이사항:", "특이사항:", "특이사항 :" 등
        import re
        
        # 패턴 1: "숫자. 특이사항: 내용" 형식
        pattern1 = r'\d+\.\s*특이사항\s*:\s*([^\n\r]+)'
        match1 = re.search(pattern1, content)
        if match1:
            return match1.group(1).strip()
        
        # 패턴 2: "특이사항: 내용" 형식
        pattern2 = r'특이사항\s*:\s*([^\n\r]+)'
        match2 = re.search(pattern2, content)
        if match2:
            return match2.group(1).strip()
        
        # 패턴 3: "특이사항 내용" 형식 (콜론이 없는 경우)
        pattern3 = r'특이사항\s+([^\n\r]+)'
        match3 = re.search(pattern3, content)
        if match3:
            return match3.group(1).strip()
        
        return ''

    except Exception as e:
        print(f"⚠️ 특이사항 추출 실패: {e}")
        return ''

def parsing_special(text):
    """ '감사'로 시작할 경우 그냥 빈 값으로 바꿈 """
    if text.startswith('감사'):
        return ''
    return text

def check_attached_file(payload, gmail_service, msg_id, thread_id, save_dir="C:\\Users\\HP\\Desktop\\files"):
    """메일 payload에서 실제 첨부파일 존재 여부 확인 및 다운로드"""
    try:
        import os
        
        # 저장 디렉토리가 없으면 생성
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        attachment_paths = []
        
        # parts가 있으면 첨부파일이 있을 가능성이 높음
        if 'parts' in payload:
            for part in payload['parts']:
                # filename이 있거나 attachmentId가 있으면 첨부파일
                if part.get('filename') or part.get('body', {}).get('attachmentId'):
                    file_path = download_attachment(gmail_service, msg_id, part, save_dir)
                    if file_path:
                        attachment_paths.append(file_path)
                
                # 재귀적으로 하위 parts도 확인
                if 'parts' in part:
                    sub_paths = check_attached_file(part, gmail_service, msg_id, thread_id, save_dir)
                    if sub_paths and sub_paths != 'N':
                        attachment_paths.extend(sub_paths.split(';'))
        
        # parts가 없어도 body에 attachmentId가 있으면 첨부파일
        if payload.get('body', {}).get('attachmentId'):
            file_path = download_attachment(gmail_service, msg_id, payload, save_dir)
            if file_path:
                attachment_paths.append(file_path)
        
        # 첨부파일이 있으면 PDF로 병합
        if attachment_paths:
            # 중복 제거
            unique_paths = list(set(attachment_paths))
            
            if len(unique_paths) == 1:
                # 파일이 하나면 그대로 반환
                return unique_paths[0]
            else:
                # 파일이 여러 개면 PDF로 병합
                merged_pdf = merge_attachments_to_pdf(unique_paths, save_dir, thread_id)
                return merged_pdf if merged_pdf else ';'.join(unique_paths)
        else:
            return 'N'
        
    except Exception as e:
        print(f"⚠️ 첨부파일 확인 중 오류: {e}")
        return 'N'

def download_attachment(gmail_service, msg_id, part, save_dir):
    """첨부파일 다운로드"""
    try:
        filename = part.get('filename', '')
        if not filename:
            return None
        
        # attachmentId가 있으면 실제 파일 다운로드
        if 'attachmentId' in part.get('body', {}):
            attachment_id = part['body']['attachmentId']
            attachment = gmail_service.users().messages().attachments().get(
                userId='me', messageId=msg_id, id=attachment_id
            ).execute()
            
            file_data = base64.urlsafe_b64decode(attachment['data'])
            
            # 파일명 중복 방지 (같은 이름이 있으면 숫자 추가)
            base_name, ext = os.path.splitext(filename)
            counter = 1
            final_filename = filename
            
            while os.path.exists(os.path.join(save_dir, final_filename)):
                final_filename = f"{base_name}_{counter}{ext}"
                counter += 1
            
            file_path = os.path.join(save_dir, final_filename)
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            print(f"📎 첨부파일 다운로드 완료: {file_path}")
            return file_path
        
        return None
        
    except Exception as e:
        print(f"⚠️ 첨부파일 다운로드 실패: {e}")
        return None

def merge_attachments_to_pdf(attachment_paths, save_dir, thread_id):
    """여러 첨부파일을 하나의 PDF로 병합"""
    try:
        from PyPDF2 import PdfMerger
        from PIL import Image
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import tempfile
        
        merger = PdfMerger()
        temp_files = []
        
        for file_path in attachment_paths:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.pdf':
                # PDF 파일은 직접 병합
                merger.append(file_path)
            elif file_ext in ['.jpg', '.jpeg', '.png']:
                # 이미지 파일은 PDF로 변환 후 병합
                temp_pdf = convert_image_to_pdf(file_path)
                if temp_pdf:
                    merger.append(temp_pdf)
                    temp_files.append(temp_pdf)
        
        # 병합된 PDF 저장
        merged_filename = f"merged_{thread_id}_{int(time.time())}.pdf"
        merged_path = os.path.join(save_dir, merged_filename)
        
        with open(merged_path, 'wb') as output_file:
            merger.write(output_file)
        
        merger.close()
        
        # 임시 파일 정리
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except:
                pass
        
        print(f"📄 첨부파일 병합 완료: {merged_path}")
        return merged_path
        
    except Exception as e:
        print(f"⚠️ PDF 병합 실패: {e}")
        return None

def convert_image_to_pdf(image_path, output_path=None):
    """이미지 파일을 PDF로 변환"""
    try:
        from PIL import Image
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        if not output_path:
            # 임시 파일로 저장
            output_path = tempfile.mktemp(suffix='.pdf')
        
        # 이미지 열기
        img = Image.open(image_path)
        
        # PDF 생성
        c = canvas.Canvas(output_path, pagesize=letter)
        
        # 이미지 크기를 페이지에 맞게 조정
        img_width, img_height = img.size
        page_width, page_height = letter
        
        # 비율 유지하면서 페이지에 맞게 조정
        scale = min(page_width / img_width, page_height / img_height) * 0.9
        new_width = img_width * scale
        new_height = img_height * scale
        
        # 중앙 정렬
        x = (page_width - new_width) / 2
        y = (page_height - new_height) / 2
        
        # 이미지를 PDF에 삽입
        c.drawImage(image_path, x, y, width=new_width, height=new_height)
        c.save()
        
        return output_path
        
    except Exception as e:
        print(f"⚠️ 이미지 PDF 변환 실패: {e}")
        return None

def main(credentials_file, token_file):
    """메인 Gmail 처리 함수 - 속도와 안정성을 모두 고려한 로직"""
    gmail_service = get_service(credentials_file, token_file)
    if not gmail_service:
        return

    label_id = get_label_id(gmail_service)
    if not label_id:
        print("❌ 'RN붙임' 라벨을 찾을 수 없습니다. Gmail에서 라벨을 생성해주세요.")
        return
    
    query = 'newer_than:2h -label:RN붙임'
    print(f"🔍 검색 쿼리: '{query}'")
    
    try:
        # 한 번에 가져올 메일 수를 100개로 제한하여 불필요한 부하 감소
        results = gmail_service.users().messages().list(userId='me', q=query, maxResults=25).execute()
        messages = results.get('messages', [])
    except Exception as e:
        print(f"❌ API 호출 중 오류 발생: {e}")
        return

    if not messages:
        print("✅ 처리할 새 메일이 없습니다.")
        return
    
    print(f"🔍 처리할 메일 수: {len(messages)}")

    # 기존 RN 번호 목록을 한 번만 조회
    existing_rn_numbers = get_existing_rn_numbers()
    print(f"ℹ️ DB에 저장된 RN 수: {len(existing_rn_numbers)}")

    # 신규 메일 처리 로직
    new_data_count = 0

    conn = get_database_connection()
    try:
        # 오래된 메일부터 처리하기 위해 reversed() 사용
        for msg in reversed(messages):
            try:
                # 메일 상세 정보 전체를 한 번에 가져옴 (format='full')
                msg_detail = gmail_service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                
                # 스레드의 첫 메일이 아닌 경우(답장/전달 등)는 건너뛰기
                if msg_detail['id'] != msg_detail['threadId']:
                    continue

                # --- 1. 'emails' 테이블 저장을 위한 공통 정보 일괄 추출 ---
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                thread_id = msg_detail['threadId']
                content = extract_text_from_payload(payload)
                internal_ts = int(msg_detail.get('internalDate')) / 1000
                received_dt = datetime.fromtimestamp(internal_ts, pytz.timezone('Asia/Seoul'))
                received_str = received_dt.strftime('%Y-%m-%d %H:%M:%S')
                from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                from_address_match = re.search(r'<(.+?)>', from_header)
                from_address = from_address_match.group(1) if from_address_match else from_header
                
                # # Greetlounge에서 보낸 메일은 어떤 DB에도 저장하지 않고 라벨만 붙이고 건너뛰기
                # if from_address.endswith('@greetlounge.com'):
                #     print(f"🚫 Greetlounge 발신 메일({from_address})은 처리하지 않습니다. (제목: {subject})")
                #     safe_modify_message(gmail_service, msg['id'], label_id)
                #     continue
                
                # --- 2. RN 번호 유무와 관계없이 'emails' 테이블에 모두 저장 ---
                # (현재 첨부파일 로직은 비활성화 상태이므로 has_attachment=False 고정)
                save_email_to_db(conn, thread_id, subject, content, from_address, received_str, False)

                # --- 3. 'data' 테이블 저장을 위해 RN 번호 추출 시도 ---
                info = extract_info_from_subject(subject)
                
                # RN 번호가 없으면, 'emails' 테이블에는 이미 저장되었으므로 여기서 처리 중단.
                # 라벨을 붙여 다음 검색에서 제외하고 다음 메일로 넘어감.
                if not info or not info.get('rn_num'):
                    print(f"ℹ️ RN 번호 없음: '{subject[:30]}...'. 'emails' 테이블에만 저장하고 처리를 종료합니다.")
                    safe_modify_message(gmail_service, msg['id'], label_id)
                    continue
                
                # --- 4. RN 번호가 있는 경우, subsidy_applications 처리 로직 수행 ---
                rn_num = info['rn_num']
                
                special_note = extract_special_note_from_content(content)
                special_note = parsing_special(special_note)

                db_save_success = False
                if rn_num in existing_rn_numbers:
                    print(f"🔄 중복 RN 발견: {rn_num}. subsidy_applications를 업데이트하고 duplicated_rn에 기록합니다.")
                    db_save_success = update_duplicate_application(
                        conn=conn,
                        rn=rn_num,
                        new_thread_id=thread_id,
                        new_received_date=received_str
                    )
                else:
                    print(f"🆕 신규 RN 발견: {rn_num}")
                    db_save_success = insert_new_application(
                        conn=conn,
                        rn=rn_num,
                        received_date=received_str,
                        thread_id=thread_id,
                        region=info.get('region') or '',
                        delivery_date=info.get('date') or '',
                        name=info.get('applier') or '',
                        special_note=special_note
                    )

                # DB 저장이 성공한 경우에만 라벨 부착 및 카운트 증가
                if db_save_success:
                    safe_modify_message(gmail_service, msg['id'], label_id)
                    existing_rn_numbers.add(rn_num) 
                    new_data_count += 1
                    print(f"✅ {rn_num} 처리 완료 (subsidy_applications 저장 + 라벨 부착)")
                else:
                    # 실패 사유는 각 함수에서 출력되므로 여기서는 간단히 로그만 남김
                    print(f"❌ {rn_num} subsidy_applications 테이블 저장 실패 - 라벨 부착하지 않음")

            except HttpError as e:
                if e.resp.status == 404:
                    print(f"⚠️ 메일 {msg['id']}를 찾을 수 없습니다 (삭제된 메일일 수 있음). 건너뜁니다.")
                else:
                    print(f"❌ HTTP 오류 발생 (메일 ID: {msg.get('id')}): {e}")
            except Exception as e:
                print(f"❌ 메일 처리 중 예외 발생 (메일 ID: {msg.get('id')}): {e}")

        conn.commit() # 모든 메일 처리 후 한번에 commit
        print(f"\n🎉 총 {new_data_count}개의 신규 메일 스레드를 처리했습니다.")
    except Exception as e:
        conn.rollback()
        print(f"❌ 메인 처리 중 예외 발생: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Gmail 처리 실행
    main(
        credentials_file='credentials_3.json',
        token_file='token123.json'
    )
    pass