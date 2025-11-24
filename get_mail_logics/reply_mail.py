## 주의사항: 경로 제대로 확인!!

import pandas as pd
import pymysql
import os
import json
import base64
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- 설정 및 상수 ---

# Gmail API 설정
TOKEN_FILE = 'test/token123.json'
CREDENTIALS_FILE = 'credentials_3.json'
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# 데이터베이스 설정
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}

# 엑셀 파일 경로
EXCEL_FILE_PATH = 'get_mail_logics/전기자동차 구매보조금 신청서.xls'

def get_gmail_service():
    """Gmail API 서비스 객체 생성"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        
        if not creds:
            print("❌ 유효한 토큰이 없으며 자동 갱신도 실패했습니다.")
            return None
            
    return build('gmail', 'v1', credentials=creds)

def extract_emails(text):
    """텍스트에서 이메일 주소 추출"""
    if not text:
        return []
    return re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)

def create_auto_reply_content(row):
    """DataFrame 행 기반 자동 답장 본문 생성"""
    rn = row.get('RN', '')
    app_num = row.get('신청\n번호', '')
    
    has_app_num = not pd.isna(app_num) and str(app_num).strip()
    
    # 유형 관련 값 가져오기
    social_val = row.get('사회계층\n유형', '')
    youth_val = row.get('청년생애', '')
    joint_val = row.get('공동명의', '')
    scrap_val = row.get('내연폐차', '')
    app_type_val = row.get('신청유형', '')
    
    # 추가 정보 가져오기 (DB에서 조회한 값)
    missing_docs = row.get('missing_docs')
    requirements = row.get('requirements')
    other_detail = row.get('other_detail')

    # 문서 명칭 매핑 테이블
    DOC_MAPPING = {
        '가족': '가족관계증명서',
        '지납세': '지방세 납세 증명서',
        '지세과': '지방세 세목별 과세증명서(청년생애)'
    }
    
    types = []
    
    # 신청번호가 있을 때만 유형 정보 수집 (엑셀에 있는 데이터라고 가정)
    if has_app_num:
        # 0. 신청유형 체크
        if not pd.isna(app_type_val):
            val_str = str(app_type_val).strip()
            if val_str == '개인사업자':
                types.append('개사')
            elif val_str == '단체':
                types.append('법인')
        
        # 1~4. 각종 유형 체크
        if not pd.isna(social_val) and str(social_val).strip():
            types.append(str(social_val).strip())
        if not pd.isna(youth_val) and str(youth_val).strip().upper() == 'Y':
            types.append('청년생애')
        if not pd.isna(joint_val) and str(joint_val).strip():
            types.append('공동명의')
        if not pd.isna(scrap_val) and str(scrap_val).strip().upper() == 'Y':
            types.append('내연폐차')
        
    final_type_str = " / ".join(types)
    
    # --- [추가 정보 처리 로직] ---
    additional_lines = []
    
    # 1. 누락 서류 (missing_docs: JSON List)
    if missing_docs:
        try:
            docs_list = json.loads(missing_docs) if isinstance(missing_docs, str) else missing_docs
            if isinstance(docs_list, list) and docs_list:
                # [수정됨] 매핑 적용: 매핑 테이블에 있으면 변환된 값 사용, 없으면 원래 값 사용
                mapped_docs = [DOC_MAPPING.get(doc, doc) for doc in docs_list]
                additional_lines.append(f"- 누락 서류: {', '.join(mapped_docs)}")
        except Exception:
            pass

    # 2. 보완 사항 (requirements: JSON List)
    if requirements:
        try:
            req_list = json.loads(requirements) if isinstance(requirements, str) else requirements
            if isinstance(req_list, list) and req_list:
                additional_lines.append(f"- 요건 불충족: {', '.join(req_list)}")
        except Exception:
            pass

    # 3. 기타 상세 (other_detail: Text)
    if other_detail and not pd.isna(other_detail) and str(other_detail).strip():
        additional_lines.append(f"- 확인 필요: {str(other_detail).strip()}")

    # ----------------------------

    # 본문 구성 시작
    lines = [
        "안녕하세요.",
        "",
        f"- RN: {rn}"
    ]
    
    # 신청번호가 있을 때만 '신청번호'와 '특이사항' 추가
    if has_app_num:
        lines.append(f"- 신청번호: {app_num}")
        if final_type_str:
            lines.append(f"- 특이사항: {final_type_str}")
        
    # 추가 정보(보완사항 등)가 있다면 본문에 삽입
    if additional_lines:
        lines.append("")
        lines.append("[추가 확인 필요]")
        lines.extend(additional_lines)
    
    lines.append("")

    # [수정됨] 마무리 인사 멘트 분기
    if has_app_num:
        lines.append("위 정보로 접수되었습니다.")
    else:
        lines.append("확인 부탁드립니다.")

    lines.append("감사합니다.")
    
    return "\n".join(lines)

def debug_reply_all_batch(df):
    """
    [DEBUG 모드] 실제 전송 없이 전송될 내용을 출력합니다.
    """
    service = get_gmail_service()
    if not service:
        print("Gmail 서비스 연결 실패 - 로컬 토큰을 확인해주세요.")
        return

    print(f"🚀 [DEBUG] 총 {len(df)}건의 메일 전송 시뮬레이션을 시작합니다.\n")
    
    for idx, row in df.iterrows():
        rn = row.get('RN', f'Unknown-{idx}')
        thread_id = row.get('recent_thread_id')
        
        print(f"--- [Case {idx+1}] RN: {rn} ---")
        
        if not thread_id:
            print(f"⚠️ [Skip] thread_id가 없습니다.")
            print("-" * 40)
            continue

        try:
            # 1. 원본 스레드 조회
            print(f"🔍 스레드 조회 중... (ID: {thread_id})")
            thread = service.users().threads().get(userId='me', id=thread_id).execute()
            messages = thread.get('messages', [])
            
            if not messages:
                print(f"⚠️ [Skip] 메시지가 없습니다.")
                print("-" * 40)
                continue
            
            # 스레드의 메일들을 역순(최신순)으로 확인하며 '내가 보낸 메일'이 아닌 것을 찾음
            target_msg = None
            
            # 내 프로필(이메일) 확인
            my_profile = service.users().getProfile(userId='me').execute()
            my_email = my_profile.get('emailAddress', '')
            
            for msg in reversed(messages):
                m_detail = service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata', metadataHeaders=['From']
                ).execute()
                
                headers_temp = m_detail.get('payload', {}).get('headers', [])
                from_val = next((h['value'] for h in headers_temp if h['name'].lower() == 'from'), '')
                
                if my_email not in from_val:
                    target_msg = msg
                    break
            
            if not target_msg:
                target_msg = messages[0] 

            # 선택된 메시지의 상세 정보(전체 헤더) 가져오기
            msg_detail = service.users().messages().get(userId='me', id=target_msg['id'], format='full').execute()
            headers = msg_detail['payload']['headers']
            
            # 2. 헤더 파싱
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(제목 없음)')
            from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
            cc_header = next((h['value'] for h in headers if h['name'].lower() == 'cc'), '')
            to_header = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
            
            # 3. 수신자 설정 시뮬레이션
            to_emails = extract_emails(from_header)
            cc_emails_raw = extract_emails(cc_header) + extract_emails(to_header)
            
            if 'my_email' not in locals():
                 my_profile = service.users().getProfile(userId='me').execute()
                 my_email = my_profile.get('emailAddress', '')

            exclude_emails = set(to_emails)
            if my_email:
                exclude_emails.add(my_email)
            
            cc_emails = list(set(cc_emails_raw) - exclude_emails)
            
            # 4. 본문 및 제목 생성
            reply_content = create_auto_reply_content(row)
            new_subject = subject if subject.strip().lower().startswith('re:') else f"Re: {subject}"
            
            # --- 디버그 출력 ---
            print(f"✅ [전송 예정 정보]")
            print(f"   - Thread ID: {thread_id}")
            print(f"   - 제목: {new_subject}")
            print(f"   - To (발신자): {to_emails}")
            print(f"   - Cc (참조+수신자): {cc_emails}")
            print(f"   - 본문 미리보기:\n{'-'*20}\n{reply_content}\n{'-'*20}")
            
            print(f"👉 (API 전송 호출은 건너뛰었습니다)")
            
        except Exception as e:
            print(f"❌ [Error] {e}")
        
        print("-" * 40 + "\n")

def send_reply_all_batch(df):
    """
    DataFrame을 순회하며 실제 '전체 답장'을 발송하고 DB 상태를 업데이트합니다.
    (API 과부하 방지 위한 재시도 로직 포함)
    """
    service = get_gmail_service()
    if not service:
        print("Gmail 서비스 연결 실패 - 로컬 토큰을 확인해주세요.")
        return

    # DB 연결
    try:
        conn = pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        return

    print(f"🚀 총 {len(df)}건의 메일 발송을 시작합니다.\n")
    
    success_count = 0
    fail_count = 0

    # 내 프로필 확인
    try:
        my_profile = service.users().getProfile(userId='me').execute()
        my_email = my_profile.get('emailAddress', '')
    except Exception as e:
        print(f"❌ 프로필 조회 실패: {e}")
        conn.close()
        return

    try:
        for idx, row in df.iterrows():
            rn = row.get('RN', f'Unknown-{idx}')
            thread_id = row.get('recent_thread_id')
            
            print(f"--- [진행중 {idx+1}/{len(df)}] RN: {rn} ---")
            
            if not thread_id or pd.isna(thread_id):
                print(f"⚠️ [Skip] thread_id가 없습니다.")
                fail_count += 1
                print("-" * 40)
                continue

            try:
                # 1. 원본 스레드 조회
                thread = service.users().threads().get(userId='me', id=thread_id).execute()
                messages = thread.get('messages', [])
                
                if not messages:
                    print(f"⚠️ [Skip] 메일 메시지를 찾을 수 없습니다.")
                    fail_count += 1
                    continue
                
                # 답장 대상 메시지 찾기 (역순 탐색)
                target_msg = None
                for msg in reversed(messages):
                    m_detail = service.users().messages().get(
                        userId='me', id=msg['id'], format='metadata', metadataHeaders=['From']
                    ).execute()
                    from_val = next((h['value'] for h in m_detail['payload']['headers'] if h['name'].lower() == 'from'), '')
                    if my_email not in from_val:
                        target_msg = msg
                        break
                
                if not target_msg:
                    target_msg = messages[0] 

                # 상세 정보 조회
                msg_detail = service.users().messages().get(userId='me', id=target_msg['id'], format='full').execute()
                headers = msg_detail['payload']['headers']
                
                # 2. 헤더 파싱
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(제목 없음)')
                from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                cc_header = next((h['value'] for h in headers if h['name'].lower() == 'cc'), '')
                to_header = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
                message_id_header = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), '')
                references_header = next((h['value'] for h in headers if h['name'].lower() == 'references'), '')
                
                # 3. 수신자 설정
                to_emails = extract_emails(from_header)
                cc_emails_raw = extract_emails(cc_header) + extract_emails(to_header)
                
                exclude_emails = set(to_emails)
                if my_email: exclude_emails.add(my_email)
                cc_emails = list(set(cc_emails_raw) - exclude_emails)
                
                # 4. 본문 및 메시지 구성
                reply_content = create_auto_reply_content(row)
                message = MIMEMultipart()
                message['to'] = ', '.join(to_emails)
                if cc_emails: message['cc'] = ', '.join(cc_emails)
                
                new_subject = subject if subject.strip().lower().startswith('re:') else f"Re: {subject}"
                message['subject'] = new_subject
                
                if message_id_header:
                    message['In-Reply-To'] = message_id_header
                    new_references = f"{references_header} {message_id_header}".strip()
                    message['References'] = new_references
                
                message.attach(MIMEText(reply_content, 'plain'))
                
                # 6. 실제 전송 (재시도 로직 추가)
                raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
                
                max_retries = 3     # 최대 재시도 횟수
                retry_wait = 10     # 대기 시간 (초)
                
                for attempt in range(max_retries):
                    try:
                        service.users().messages().send(
                            userId='me', body={'raw': raw_message, 'threadId': thread_id}
                        ).execute()
                        break # 성공 시 루프 탈출
                    except Exception as e:
                        print(f"⚠️ [발송 오류 - 시도 {attempt+1}/{max_retries}] {e}")
                        if attempt < max_retries - 1:
                            print(f"⏳ {retry_wait}초 대기 후 재시도합니다... (API 과부하/충돌 방지)")
                            time.sleep(retry_wait)
                        else:
                            print(f"❌ [최종 발송 실패] 재시도 횟수를 초과했습니다.")
                            raise e # 3회 실패 시 예외를 던져서 바깥의 catch 블록(fail_count 증가)으로 이동
                
                print(f"✅ [발송 성공] Thread ID: {thread_id}")
                success_count += 1
                
                try:
                    # 신청번호 유무 확인 (create_auto_reply_content와 동일한 로직)
                    app_num = row.get('신청\n번호', '')
                    has_app_num = not pd.isna(app_num) and str(app_num).strip()
                    
                    # status 값 결정
                    if has_app_num:
                        status_value = '이메일 전송'
                    else:
                        status_value = '요청메일 전송'
                    
                    with conn.cursor() as cursor:
                        # 1. subsidy_applications 테이블 업데이트
                        update_sql = """
                            UPDATE subsidy_applications 
                            SET status = %s, 
                                status_updated_at = NOW()
                            WHERE RN = %s
                        """
                        cursor.execute(update_sql, (status_value, rn))
                        
                        # 2. 신청번호가 없는 경우 additional_note.successed 업데이트
                        if not has_app_num:
                            update_note_sql = """
                                UPDATE additional_note 
                                SET successed = 1
                                WHERE RN = %s
                            """
                            cursor.execute(update_note_sql, (rn,))
                            print(f"✅ [DB 업데이트] {rn}: additional_note.successed -> 1")
                        
                    conn.commit()
                    print(f"✅ [DB 업데이트] {rn}: status -> '{status_value}'")
                except Exception as db_err:
                    print(f"⚠️ [DB 업데이트 실패] {rn}: {db_err}")
                    conn.rollback()
                # -------------------------------------------------------
                
                time.sleep(1) # 기본 대기
                
            except Exception as e:
                print(f"❌ [발송 실패] {e}")
                fail_count += 1
            
            print("-" * 40 + "\n")
            
    finally:
        if conn:
            conn.close()

    print(f"🎉 작업 종료: 성공 {success_count}건, 실패 {fail_count}건")

def main():
    print("📂 엑셀 파일을 로드하고 있습니다...")
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"❌ 파일이 존재하지 않습니다: {EXCEL_FILE_PATH}")
        return

    # 1. 엑셀 로드 및 전처리
    df = pd.read_excel(EXCEL_FILE_PATH, header=2)
    df = df[['제조수입사\n관리번호', '신청\n번호', "사회계층\n유형", "생애최초 차량\n구매자 여부", '공동명의\n성명', '내연기관\n폐차여부', '신청유형']]
    df = df[df['제조수입사\n관리번호'].notna()]
    df = df.rename(columns={
        '제조수입사\n관리번호': 'RN', 
        '생애최초 차량\n구매자 여부': '청년생애', 
        '공동명의\n성명': '공동명의', 
        '내연기관\n폐차여부': '내연폐차'
    })
    df['신청\n번호'] = pd.to_numeric(df['신청\n번호'], errors='coerce').astype('Int64')

    print(f"✅ 엑셀 로드 완료: {len(df)}행")

    # 2. DB 연결 및 데이터 조회
    print("🔌 DB에 연결하여 추가 정보를 조회합니다...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        
        # 엑셀 파일의 RN 목록 추출
        rn_list_excel = df['RN'].dropna().unique().tolist()
        if rn_list_excel:
            rn_str_list = [str(rn) for rn in rn_list_excel]
            rn_tuple_excel = ",".join([f"'{rn}'" for rn in rn_str_list])
        else:
            rn_tuple_excel = "''"
            
        sql = f"""
        SELECT 
            sa.RN, 
            sa.recent_thread_id,
            sa.status,
            CASE 
                WHEN an.successed = 0 OR an.successed IS NULL THEN an.missing_docs
                ELSE NULL
            END AS missing_docs,
            CASE 
                WHEN an.successed = 0 OR an.successed IS NULL THEN an.requirements
                ELSE NULL
            END AS requirements,
            CASE 
                WHEN an.successed = 0 OR an.successed IS NULL THEN an.other_detail
                ELSE NULL
            END AS other_detail
        FROM
            subsidy_applications sa
        LEFT JOIN
            additional_note an ON sa.RN = an.RN
        WHERE
            (sa.RN IN ({rn_tuple_excel}) OR an.RN IS NOT NULL)
        """
        
        df_db = pd.read_sql(sql, conn)
        conn.close()
        
    except Exception as e:
        print(f"❌ DB 조회 실패: {e}")
        return

    # 3. 데이터 병합
    df = pd.merge(df, df_db, on='RN', how='outer')

    # 4. 필터링 (이미 전송된 건 제외)
    # [수정됨] status가 '이메일 전송'인 행 제거
    df = df[~(df['status'] == '이메일 전송')]
    
    # 5. 실행
    print(f"\n🚀 처리 대상: 총 {len(df)}건")
    
    # 디버그 모드 실행 (필요 시 주석 해제)
    # debug_reply_all_batch(df)
    
    # 실제 발송 실행
    # (주의: 실제 메일이 발송됩니다)
    send_reply_all_batch(df)

if __name__ == "__main__":
    main()

