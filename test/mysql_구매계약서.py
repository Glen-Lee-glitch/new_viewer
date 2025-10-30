from google import genai
from google.genai import types
import pathlib
import os
import re
import json
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import PyPDF2
from PyPDF2 import PdfReader, PdfWriter
import pymysql
from datetime import datetime

# 상위 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import API_KEY, SUB_API_KEY

client = genai.Client(api_key=API_KEY)
client_free = genai.Client(api_key=SUB_API_KEY)

# MySQL 연결 설정
DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}

def parse_response(text):
    """AI 응답에서 JSON을 파싱하여 날짜, 차량구성, 고객명, RN번호, 휴대폰번호, 이메일, 페이지번호 정보 추출"""
    if text is None:
        return None, None, None, None, None, None, None
    
    try:
        # JSON 부분만 추출 (```json``` 블록이 있을 수 있음)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            return (data.get('order_date'), data.get('vehicle_config'), 
                   data.get('customer_name'), data.get('rn'),
                   data.get('phone_number'), data.get('email'), data.get('page_number'))
    except:
        pass
    
    # JSON 파싱 실패시 기존 방식으로 날짜만 추출
    date = extract_date(text)
    return date, None, None, None, None, None, None

def extract_date(text):
    """텍스트에서 날짜를 YYYY-MM-DD 형식으로 추출"""
    if text is None:
        return None
    
    # 다양한 날짜 패턴 매칭
    patterns = [
        r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',  # 2025년 10월 6일
        r'(\d{4})/(\d{1,2})/(\d{1,2})',  # 2025/10/06
        r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2025-10-06
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    return None

def is_valid_pdf(filepath):
    """PDF 파일이 유효한지 검사 (페이지가 있는지 확인)"""
    try:
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            return len(pdf_reader.pages) > 0
    except Exception:
        return False

def delete_pages_from_pdf(pdf_path, page_number):
    """PDF에서 특정 페이지를 삭제하고 원본 파일을 덮어씁니다"""
    try:
        if page_number is None:
            return False
        
        # PDF 읽기
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        # page_number는 0-indexed가 아닌 1-indexed (예: 3)
        page_to_delete = int(page_number) - 1
        
        # 삭제할 페이지만 제외하고 복사
        for i, page in enumerate(reader.pages):
            if i != page_to_delete:
                writer.add_page(page)
        
        # 원본 파일에 덮어쓰기
        with open(pdf_path, 'wb') as output_file:
            writer.write(output_file)
        
        return True
    except Exception as e:
        print(f"❌ PDF 페이지 삭제 실패: {e}")
        return False

def save_to_mysql(rn, data):
    """결과를 MySQL 테이블에 저장"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # 데이터 매핑
        ai_계약일자 = data.get('order_date')
        ai_이름 = data.get('customer_name')
        전화번호 = data.get('phone_number')
        이메일 = data.get('email')
        차종 = data.get('vehicle_config')
        modified_date = datetime.now()
        
        # INSERT 또는 UPDATE (UPSERT)
        sql = """
        INSERT INTO test_ai_구매계약서 (RN, modified_date, ai_계약일자, ai_이름, 전화번호, 이메일, 차종)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            modified_date = VALUES(modified_date),
            ai_계약일자 = VALUES(ai_계약일자),
            ai_이름 = VALUES(ai_이름),
            전화번호 = VALUES(전화번호),
            이메일 = VALUES(이메일),
            차종 = VALUES(차종)
        """
        
        cursor.execute(sql, (rn, modified_date, ai_계약일자, ai_이름, 전화번호, 이메일, 차종))
        connection.commit()
        cursor.close()
        connection.close()
        return True
    except Exception as e:
        print(f"❌ MySQL 저장 실패 ({rn}): {e}")
        return False

RN_LIST = ['RN126116642']

print(f"🚀 총 {len(RN_LIST)}개의 RN 처리 시작")

folder_pat = r'\\DESKTOP-KMJ\Users\HP\Desktop\greet_db\files\new'

# RN_LIST에 포함된 RN번호가 파일명에 들어간 파일만 골라 RN_LIST 개수와 일치하게 FILES_PATH 리스트에 저장
FILES_PATH = []
if os.path.isdir(folder_pat):
    files = os.listdir(folder_pat)
    for rn in RN_LIST:
        matched_file = next((f for f in files if rn in f), None)
        if matched_file:
            FILES_PATH.append(os.path.join(folder_pat, matched_file))
        else:
            FILES_PATH.append(None)  # RN이 포함된 파일이 없으면 None으로 표기
else:
    FILES_PATH = [None] * len(RN_LIST)

prompt = """자동차 구매 계약 서류에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요:

1. '온라인 주문 완료일' 날짜 (YYYY-MM-DD 형식)
2. '차량구성' 또는 '차량 구성내역' 섹션에서 첫 번째 행의 구성내역
3. '고객정보' 섹션에서 '고객 이름' - 영문 혹은 한글로 적힌 이름
4. '예약 번호'에 적힌 'RN123456789' 형식의 번호
5. '고객정보' 섹션에서 휴대폰 번호와 이메일 주소
6. 마지막으로 이 정보가 담긴 페이지 번호를 page_number 필드에 저장

답변 형식:
{
  "order_date": "2025-10-06",
  "vehicle_config": "Model Y 후륜구동",
  "customer_name": "John Doe",
  "rn": "RN123456789",
  "phone_number": "010-1234-5678",
  "email": "john.doe@naver.com",
  "page_number": 3
}

온라인 주문 완료일 예시:
- 2025/10/06 → 2025-10-06

판단해야하는 서류는 "자동차 구매 계약"과 "차량 구성"이라는 글자가 포함되어 있습니다.

차량구성은 정확히 첫 번째 행에 적힌 내용만 추출해주세요.

이메일 주소 및 휴대폰 번호 추출 시 주의사항:
- 대부분의 이메일이 다음 도메인을 사용합니다: naver.com, gmail.com, hanmail.net, nate.com, daum.net
- 이메일 주소는 정확히 @ 기호 앞뒤로 구성되어야 합니다
- 이메일 형식이 명확하지 않으면 null로 설정해주세요
- 휴대폰 번호는 010-XXXX-XXXX 형식으로 추출해주세요

"""

results = {}
skipped_rns = []  # 파일이 없는 RN 추적

def _process_single_pdf_with_free_api(rn, filepath, prompt_text):
    """무료 API로 단일 PDF 처리 (유료 API 실패 시 사용)"""
    start_time = time.time()
    max_retries = 3
    for attempt_index in range(max_retries):
        try:
            if attempt_index > 0:
                print(f"  ⏳ 무료 API 재시도 {attempt_index}회차... 10초 대기 중")
                time.sleep(10)
            else:
                time.sleep(6)
                
            response = client_free.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                        data=pathlib.Path(filepath).read_bytes(),
                        mime_type='application/pdf',
                    ),
                    prompt_text
                ]
            )
            order_date, vehicle_config, customer_name, extracted_rn, phone_number, email, page_number = parse_response(response.text)
            elapsed_time = time.time() - start_time
            print(f"  ✅ 무료 API로 처리 성공!")
            return rn, {
                'order_date': order_date,
                'vehicle_config': vehicle_config,
                'customer_name': customer_name,
                'rn': extracted_rn,
                'phone_number': phone_number,
                'email': email,
                'page_number': page_number,
                'process_seconds': round(elapsed_time, 2)
            }
        except Exception as e:
            if attempt_index < max_retries - 1:
                print(f"  ⚠️  무료 API 오류: {e}")
                time.sleep(15 * (2 ** attempt_index))
            else:
                elapsed_time = time.time() - start_time
                print(f"  ❌ 무료 API로도 처리 실패: {e}")
                return rn, {
                    'order_date': None,
                    'vehicle_config': None,
                    'customer_name': None,
                    'rn': None,
                    'phone_number': None,
                    'email': None,
                    'page_number': None,
                    'process_seconds': round(elapsed_time, 2)
                }

def _process_single_pdf(rn, filepath, prompt_text, max_retries=5, initial_backoff_sec=2.0):
    """단일 PDF 처리 (개선된 버전)"""
    start_time = time.time()
    backoff = initial_backoff_sec
    for attempt_index in range(max_retries):
        try:
            if attempt_index > 0:
                time.sleep(5)
                
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                        data=pathlib.Path(filepath).read_bytes(),
                        mime_type='application/pdf',
                    ),
                    prompt_text
                ]
            )
            order_date, vehicle_config, customer_name, extracted_rn, phone_number, email, page_number = parse_response(response.text)
            elapsed_time = time.time() - start_time
            return rn, {
                'order_date': order_date,
                'vehicle_config': vehicle_config,
                'customer_name': customer_name,
                'rn': extracted_rn,
                'phone_number': phone_number,
                'email': email,
                'page_number': page_number,
                'process_seconds': round(elapsed_time, 2)
            }
        except Exception as e:
            if attempt_index < max_retries - 1:
                sleep_sec = backoff * (1.0 + 0.25 * (os.urandom(1)[0] / 255.0))
                time.sleep(sleep_sec)
                backoff *= 2.0
            else:
                elapsed_time = time.time() - start_time
                print(f"파일 처리 중 오류 발생(최종 실패): {filepath}, 오류: {e}")
                return rn, {
                    'order_date': None,
                    'vehicle_config': None,
                    'customer_name': None,
                    'rn': None,
                    'phone_number': None,
                    'email': None,
                    'page_number': None,
                    'process_seconds': round(elapsed_time, 2)
                }

# 유료 API를 사용하여 3개씩 순차 배치, 배치 내 동시 2개 처리
print("🚀 Gemini API를 사용하여 처리 중...")

# PDF 파일이 없는 RN들은 건너뛰기
for i, filepath in enumerate(FILES_PATH):
    rn = RN_LIST[i]
    if filepath is None:
        print(f"⚠️  {rn}: PDF 파일을 찾을 수 없음 - 처리 건너뜀")
        skipped_rns.append(rn)

# PDF 파일이 있는 RN들을 3개씩 묶어서 처리 (유효한 PDF만)
valid_files = []
for i in range(len(RN_LIST)):
    if FILES_PATH[i] is not None:
        if is_valid_pdf(FILES_PATH[i]):
            valid_files.append((RN_LIST[i], FILES_PATH[i]))
        else:
            print(f"⚠️  {RN_LIST[i]}: PDF 파일이 손상되었거나 빈 파일입니다.")
            results[RN_LIST[i]] = {
                'order_date': None,
                'vehicle_config': None,
                'customer_name': None,
                'rn': None,
                'phone_number': None,
                'email': None,
                'page_number': None,
                'process_seconds': 0
            }

batch_size = 3
for i in range(0, len(valid_files), batch_size):
    batch_files = valid_files[i:i + batch_size]
    print(f"📦 Batch {i//batch_size + 1}: {len(batch_files)}개 파일 처리 중...")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        for rn, filepath in batch_files:
            future = executor.submit(_process_single_pdf, rn, filepath, prompt)
            futures.append(future)
            time.sleep(0.5)
        
        for future in as_completed(futures):
            rn_key, rn_result = future.result()
            results[rn_key] = rn_result
    
    print(f"✅ Batch {i//batch_size + 1} 완료")
    
    if i + batch_size < len(valid_files):
        time.sleep(10)

# 유료 API로 실패한 파일들을 무료 API로 재처리
failed_files = [(rn, filepath) for rn, filepath in valid_files 
                if results.get(rn) and all(v is None for v in results[rn].values()) and is_valid_pdf(filepath)]

if failed_files:
    print("\n" + "="*60)
    print(f"⚠️  유료 API로 실패한 {len(failed_files)}개 파일을 무료 API로 재처리합니다.")
    print("="*60)
    
    for idx, (rn, filepath) in enumerate(failed_files, 1):
        print(f"\n🔄 [{idx}/{len(failed_files)}] {rn} 무료 API로 재처리 중...")
        rn_key, rn_result = _process_single_pdf_with_free_api(rn, filepath, prompt)
        results[rn_key] = rn_result

print("\n" + "="*60)
print("Gemini API 추출 완료!")
print("="*60)

# 결과를 MySQL에 저장
print("\n💾 MySQL에 저장 중...")
saved_count = 0
failed_count = 0

for rn, data in results.items():
    if save_to_mysql(rn, data):
        saved_count += 1
    else:
        failed_count += 1

print(f"\n✅ 저장 완료: {saved_count}개 성공, {failed_count}개 실패")

# 페이지 삭제 로직
print("\n" + "="*60)
print("PDF 페이지 삭제 시작...")
print("="*60)

deleted_count = 0
for rn, data in results.items():
    if data and isinstance(data, dict) and data.get('page_number'):
        # PDF 파일 경로 찾기
        pdf_path = None
        for i, filepath in enumerate(FILES_PATH):
            if RN_LIST[i] == rn and filepath is not None:
                pdf_path = filepath
                break
        
        if pdf_path and os.path.exists(pdf_path):
            page_number = data.get('page_number')
            if delete_pages_from_pdf(pdf_path, page_number):
                print(f"✅ {rn}: 페이지 삭제 완료 - {page_number}")
                deleted_count += 1
            else:
                print(f"⚠️  {rn}: 페이지 삭제 실패")
        else:
            print(f"⚠️  {rn}: PDF 파일을 찾을 수 없음")

print(f"\n✅ 페이지 삭제 완료: {deleted_count}개 파일")
print("\n" + "="*60)

