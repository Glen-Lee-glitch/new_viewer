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
    """AI 응답에서 JSON을 파싱하여 주민등록초본 정보 추출"""
    if text is None:
        return None
    
    try:
        # JSON 부분만 추출 (```json``` 블록이 있을 수 있음)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            
            # 성명(name) 필드 후처리: 공백, 개행문자, 탭 제거
            if data.get('name'):
                data['name'] = data['name'].replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            
            # 주소(address_1) 필드 후처리: 도 이름 변환
            if data.get('address_1'):
                address = data['address_1']
                # 강원도 -> 강원특별자치도
                if '강원도' in address:
                    address = address.replace('강원도', '강원특별자치도')
                # 전라북도 -> 전북특별자치도
                if '전라북도' in address:
                    address = address.replace('전라북도', '전북특별자치도')
                data['address_1'] = address
            
            # 주소(address_2) 필드 후처리: 도 이름 변환
            if data.get('address_2'):
                address = data['address_2']
                # 강원도 -> 강원특별자치도
                if '강원도' in address:
                    address = address.replace('강원도', '강원특별자치도')
                # 전라북도 -> 전북특별자치도
                if '전라북도' in address:
                    address = address.replace('전라북도', '전북특별자치도')
                data['address_2'] = address
            
            # 발급일(issue_date) 필드 후처리: '2025년 07월 03일' -> '2025-07-03'
            if data.get('issue_date'):
                issue_date = data['issue_date']
                # '년', '월', '일' 패턴으로 파싱
                date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', issue_date)
                if date_match:
                    year = date_match.group(1)
                    month = date_match.group(2).zfill(2)  # 월을 2자리로 맞춤
                    day = date_match.group(3).zfill(2)     # 일을 2자리로 맞춤
                    data['issue_date'] = f"{year}-{month}-{day}"
            
            return data
    except:
        pass
    
    return None

def is_valid_pdf(filepath):
    """PDF 파일이 유효한지 검사 (페이지가 있는지 확인)"""
    try:
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            return len(pdf_reader.pages) > 0
    except Exception:
        return False

def save_to_mysql(rn, data):
    """결과를 MySQL 테이블에 저장"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        if data is None:
            data = {}
        
        # 데이터 매핑
        address_1 = data.get('address_1')
        address_2 = data.get('address_2')
        at_date = data.get('at_date')
        birth_date = data.get('birth_date')
        name = data.get('name')
        issue_date = data.get('issue_date')
        page_number = json.dumps(data.get('page_number')) if data.get('page_number') else None
        modified_date = datetime.now()
        
        # INSERT 또는 UPDATE (UPSERT)
        sql = """
        INSERT INTO test_ai_초본 (RN, modified_date, address_1, address_2, at_date, birth_date, name, issue_date, page_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            modified_date = VALUES(modified_date),
            address_1 = VALUES(address_1),
            address_2 = VALUES(address_2),
            at_date = VALUES(at_date),
            birth_date = VALUES(birth_date),
            name = VALUES(name),
            issue_date = VALUES(issue_date),
            page_number = VALUES(page_number)
        """
        
        cursor.execute(sql, (rn, modified_date, address_1, address_2, at_date, birth_date, name, issue_date, page_number))
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

prompt = """주민등록초본에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요:

1. 모든 페이지에서 '마지막 번호'에 해당하는 ['주소', '발생일'] 정보를 추출해주세요. 발생일은 at_date 필드에 저장해주세요.
2. '주소'는 대부분 2줄로 되어 있는데 2줄을 각각 [address_1, address_2] 형식으로 추출해주세요. ',' 쉼표와 '.' 문자는 제거해주세요.
3. '발생일'은 YYYY-MM-DD 형식으로 추출해주세요.
4. '성명', '주민등록번호'를 추출한 후 앞 6자리의 숫자를 birth_date 필드에 저장해주세요. 950516-1234567 -> 1995-05-16
5. 아무 페이지 상단에 '2025년' 이라는 문자열을 찾아서 일자 전체를 찾아주세요. issue_date 필드에 저장해주세요.
6. 주민등록초본 데이터가 포함된 모든 페이지 번호를 page_number 필드에 리스트 형태로 저장해주세요.
7. 초본이 없다고 판단되면 모든 값을 None으로 반환해주세요.


답변 형식:
{
  address_1: "서울특별시 강남구 역삼동 123-45",
  address_2: "자이아파트 101동 101호"
  at_date: "2025-04-16",
  birth_date: "1999-10-06",
  name: "홍길동",
  issue_date: "2025-04-16",
  page_number: [3, 4, 5]
}

주소와 발생일은 모든 페이지 중에서 '번호'가 가장 높은 row에 대해서 추출해주세요. 마지막 페이지가 아닌 가장 큰 번호가 포함된 페이지에서 추출해주세요.
초본이 1페이지만 있으면 [3], 여러 페이지에 걸쳐있으면 [3, 4, 5, 6]처럼 모든 페이지 번호를 포함해주세요.

issue_date 추출 시 주의사항:
- 항상 '0000년 0월 00일' 처럼 쓰여져 있습니다.
- '0000-00-00' 으로 쓰여져 있지 않습니다.
- 항상 '2025년' 이라는 문자열을 찾아서 일자 전체를 찾아주세요.
- 대부분 페이지 상단에 존재합니다.
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
            extracted_data = parse_response(response.text)
            elapsed_time = time.time() - start_time
            print(f"  ✅ 무료 API로 처리 성공!")
            if extracted_data:
                extracted_data['process_seconds'] = round(elapsed_time, 2)
            return rn, extracted_data
        except Exception as e:
            if attempt_index < max_retries - 1:
                print(f"  ⚠️  무료 API 오류: {e}")
                time.sleep(15 * (2 ** attempt_index))
            else:
                elapsed_time = time.time() - start_time
                print(f"  ❌ 무료 API로도 처리 실패: {e}")
                return rn, {'process_seconds': round(elapsed_time, 2)} if extracted_data is None else None

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
            extracted_data = parse_response(response.text)
            elapsed_time = time.time() - start_time
            if extracted_data:
                extracted_data['process_seconds'] = round(elapsed_time, 2)
            return rn, extracted_data
        except Exception as e:
            if attempt_index < max_retries - 1:
                sleep_sec = backoff * (1.0 + 0.25 * (os.urandom(1)[0] / 255.0))
                time.sleep(sleep_sec)
                backoff *= 2.0
            else:
                elapsed_time = time.time() - start_time
                print(f"파일 처리 중 오류 발생(최종 실패): {filepath}, 오류: {e}")
                return rn, {'process_seconds': round(elapsed_time, 2)}

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
            results[RN_LIST[i]] = {'process_seconds': 0}

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
                if results.get(rn) is None and is_valid_pdf(filepath)]

if failed_files:
    print("\n" + "="*60)
    print(f"⚠️  유료 API로 실패한 {len(failed_files)}개 파일을 무료 API로 재처리합니다.")
    print("="*60)
    
    for idx, (rn, filepath) in enumerate(failed_files, 1):
        print(f"\n🔄 [{idx}/{len(failed_files)}] {rn} 무료 API로 재처리 중...")
        rn_key, rn_result = _process_single_pdf_with_free_api(rn, filepath, prompt)
        results[rn_key] = rn_result

print("\n" + "="*60)
print("주민등록초본 OCR 추출 완료!")
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
print("\n" + "="*60)

