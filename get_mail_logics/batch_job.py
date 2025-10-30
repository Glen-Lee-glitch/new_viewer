import pathlib
import os
import re
import json
import time
import io
import sys
from google import genai
from google.genai import types # types.Part 사용을 위해 추가
import PyPDF2
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# config.py에서 API_KEY 임포트 (config.py 파일이 같은 디렉토리에 있다고 가정)
from config import API_KEY 

client = genai.Client(api_key=API_KEY)

# main.py에서 가져온 parse_response 함수 (계약서 정보용)
def parse_response_contract(text):
    """AI 응답에서 JSON을 파싱하여 날짜, 차량구성, 고객명, RN번호, 휴대폰번호, 이메일, 페이지번호 정보 추출"""
    if text is None:
        return None, None, None, None, None, None, None
    
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            return (data.get('order_date'), data.get('vehicle_config'), 
                   data.get('customer_name'), data.get('rn'),
                   data.get('phone_number'), data.get('email'), data.get('page_number'))
    except:
        pass
    
    date = extract_date(text)
    return date, None, None, None, None, None, None

def extract_date(text):
    """텍스트에서 날짜를 YYYY-MM-DD 형식으로 추출"""
    if text is None:
        return None
    
    patterns = [
        r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일',
        r'(\d{4})/(\d{1,2})/(\d{1,2})',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    return None

# 초본.py에서 가져온 parse_response 함수 (주민등록초본 정보용)
def parse_response_resident_cert(text):
    """AI 응답에서 JSON을 파싱하여 주민등록초본 정보 추출"""
    if text is None:
        return None
    
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            
            if data.get('name'):
                data['name'] = data['name'].replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            
            if data.get('address_1'):
                address = data['address_1']
                if '강원도' in address:
                    address = address.replace('강원도', '강원특별자치도')
                if '전라북도' in address:
                    address = address.replace('전라북도', '전북특별자치도')
                data['address_1'] = address
            
            if data.get('address_2'):
                address = data['address_2']
                if '강원도' in address:
                    address = address.replace('강원도', '강원특별자치도')
                if '전라북도' in address:
                    address = address.replace('전라북도', '전북특별자치도')
                data['address_2'] = address
            
            if data.get('issue_date'):
                issue_date = data['issue_date']
                date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', issue_date)
                if date_match:
                    year = date_match.group(1)
                    month = date_match.group(2).zfill(2)
                    day = date_match.group(3).zfill(2)
                    data['issue_date'] = f"{year}-{month}-{day}"
            
            return data
    except:
        pass
    
    return None

def parse_response_dajanyeo(text):
    """AI 응답에서 JSON을 파싱하여 가족관계증명서 정보 추출"""
    if text is None:
        return None
    
    try:
        # JSON 부분만 추출 (```json``` 블록이 있을 수 있음)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            
            # child_count 필드 검증 (숫자인지 확인)
            if 'child_count' in data and data['child_count'] is not None:
                try:
                    data['child_count'] = int(data['child_count'])
                except (ValueError, TypeError):
                    data['child_count'] = None
            
            # child_birth_date 필드 검증 (리스트인지 확인)
            if 'child_birth_date' in data and data['child_birth_date'] is not None:
                if not isinstance(data['child_birth_date'], list):
                    data['child_birth_date'] = None
            
            # page_number 필드 검증 (숫자인지 확인)
            if 'page_number' in data and data['page_number'] is not None:
                try:
                    data['page_number'] = int(data['page_number'])
                except (ValueError, TypeError):
                    data['page_number'] = None
            
            return data
    except Exception as e:
        print(f"⚠️  JSON 파싱 오류: {e}")
        pass
    
    return None

def parse_response_cheongnyeon(text):
    """AI 응답에서 JSON을 파싱하여 청년생애 정보 추출"""
    if text is None:
        return None
    
    try:
        # JSON 부분만 추출 (```json``` 블록이 있을 수 있음)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            
            # local_name 필드 검증 (리스트인지 확인)
            if 'local_name' in data and data['local_name'] is not None:
                if not isinstance(data['local_name'], list):
                    data['local_name'] = None
            
            # range_date 필드 검증 (리스트인지 확인)
            if 'range_date' in data and data['range_date'] is not None:
                if not isinstance(data['range_date'], list):
                    data['range_date'] = None
            
            return data
    except Exception as e:
        print(f"⚠️  JSON 파싱 오류: {e}")
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

def process_single_rn(rn, filepath, category, supabase_manager):
    """
    하나의 RN에 대해 카테고리에 따라 필요한 모든 프롬프트를 병렬로 처리하고 Supabase에 저장
    """
    start_time = time.time()
    results = {}
    
    print(f"\n--- [{rn}] 파일 처리 시작 (카테고리: {category}) ---")
    
    # PDF 바이트 데이터 미리 읽기
    pdf_bytes = pathlib.Path(filepath).read_bytes()
    
    def call_api(prompt_text, result_key, parse_function):
        """API 호출 및 결과 파싱을 위한 공통 함수"""
        try:
            print(f"  🔄 [{rn}] {result_key} 프롬프트 처리 시작...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'),
                    prompt_text
                ]
            )
            # 계약서의 경우 parse_response_contract가 튜플을 반환하므로 딕셔너리로 변환
            if parse_function == parse_response_contract:
                order_date, vehicle_config, customer_name, extracted_rn, phone_number, email, page_number = parse_function(response.text)
                data = {
                    'order_date': order_date,
                    'vehicle_config': vehicle_config,
                    'customer_name': customer_name,
                    'rn': extracted_rn,
                    'phone_number': phone_number,
                    'email': email,
                    'page_number': page_number
                }
            else:
                data = parse_function(response.text)
                
            print(f"  ✅ [{rn}] {result_key} 프롬프트 완료")
            return (result_key, data)
        except Exception as e:
            print(f"  ❌ [{rn}] {result_key} 프롬프트 실패: {e}")
            return (result_key, None)

    # 실행할 API 작업 목록
    tasks = [
        (prompt_contract, 'contract_data', parse_response_contract),
        (prompt_resident_cert, 'resident_cert_data', parse_response_resident_cert)
    ]

    if '다자녀' in category:
        tasks.append((prompt_dajanyeo, 'dajanyeo_data', parse_response_dajanyeo))
    if '청년생애' in category:
        tasks.append((prompt_cheongnyeon, 'cheongnyeon_data', parse_response_cheongnyeon))

    # API 병렬 호출
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = [executor.submit(call_api, *task) for task in tasks]
        
        for future in as_completed(futures):
            result_key, data = future.result()
            results[result_key] = data
            
    elapsed_time = time.time() - start_time
    print(f"--- [{rn}] 파일 처리 완료 ({round(elapsed_time, 2)}s) ---")

    # Supabase에 결과 저장
    if supabase_manager:
        for result_key, data in results.items():
            if data:
                # 카테고리명을 test_category에 맞게 변환
                category_map = {
                    'contract_data': '구매계약서',
                    'resident_cert_data': '초본',
                    'dajanyeo_data': '다자녀',
                    'cheongnyeon_data': '청년생애'
                }
                test_category = category_map.get(result_key, '기타')

                try:
                    success = supabase_manager.insert_test_result(
                        rn=rn,
                        test_category=test_category,
                        test_success=True,
                        test_model='gemini-2.5-flash',
                        memo=f'병렬처리 완료 ({round(elapsed_time, 2)}s)',
                        process_seconds=elapsed_time,
                        result_data=data
                    )
                    if success:
                        print(f"  ✅ [{rn}] {test_category} 데이터 Supabase 저장 완료")
                    else:
                        print(f"  ❌ [{rn}] {test_category} 데이터 Supabase 저장 실패")
                except Exception as e:
                    print(f"  ❌ [{rn}] {test_category} Supabase 저장 중 오류: {e}")

    return results

def process_single_rn_with_timing(rn, filepath, category, supabase_manager):
    """
    하나의 RN 처리 + 시간 측정을 포함한 래퍼 함수
    """
    start_time = time.time()
    result = process_single_rn(rn, filepath, category, supabase_manager)
    end_time = time.time()
    individual_time = end_time - start_time
    return result, individual_time

def process_multiple_rns(rn_info_list, download_folder, supabase_manager):
    """
    여러 RN에 대해 병렬 처리 (RN별로 내부에서 필요한 문서들 병렬 처리)
    """
    total_start_time = time.time()
    print(f"\n🚀 {len(rn_info_list)}개 RN 병렬 처리 시작...")
    
    # 각 RN에 대한 파일 경로 및 카테고리 정보 찾기
    rn_process_info = []
    for rn_info in rn_info_list:
        rn = rn_info['rn']
        category = rn_info['category']
        filepath = download_folder / rn_info['filename']
        
        if filepath.exists() and is_valid_pdf(filepath):
            rn_process_info.append({'rn': rn, 'filepath': filepath, 'category': category})
        else:
            print(f"⚠️  {rn}: PDF 파일을 찾을 수 없거나 손상됨 ({filepath})")
    
    if not rn_process_info:
        print("❌ 처리할 유효한 파일이 없습니다.")
        return {}, 0, 0
    
    print(f"📄 {len(rn_process_info)}개 유효한 파일 발견")
    
    # 여러 RN을 병렬로 처리
    all_results = {}
    individual_times = {}  # 각 RN별 처리 시간 저장
    
    with ThreadPoolExecutor(max_workers=3) as executor:  # 최대 3개 RN 동시 처리
        futures = []
        
        for info in rn_process_info:
            future = executor.submit(
                process_single_rn_with_timing, 
                info['rn'], 
                info['filepath'], 
                info['category'],
                supabase_manager
            )
            futures.append((info['rn'], future))
        
        # 결과 수집
        for rn, future in futures:
            try:
                result, individual_time = future.result()
                all_results[rn] = result
                individual_times[rn] = individual_time
            except Exception as e:
                print(f"❌ [{rn}] 처리 중 오류: {e}")
                all_results[rn] = {}
                individual_times[rn] = 0
    
    total_end_time = time.time()
    total_time = total_end_time - total_start_time
    
    return all_results, total_time, individual_times

def remove_processed_rns_from_excel(excel_path, processed_rns):
    """
    엑셀 파일에서 처리 완료된 RN들을 제거합니다.

    Args:
        excel_path (str): 엑셀 파일 경로
        processed_rns (list): 처리 완료된 RN 리스트
    """
    if not processed_rns:
        print("\nℹ️  엑셀에서 제거할 RN이 없습니다.")
        return

    try:
        print(f"\n🔄 '{excel_path}'에서 처리 완료된 {len(processed_rns)}개 RN 제거 중...")
        df = pd.read_excel(excel_path)
        
        # '제조수입사\n관리번호' 컬럼이 실제 파일에 있는 컬럼명과 일치해야 합니다.
        # mail_download.py를 참고하여 컬럼명을 정확히 기재합니다.
        rn_column_name = '제조수입사\n관리번호'
        
        initial_row_count = len(df)
        df = df[~df[rn_column_name].isin(processed_rns)]
        final_row_count = len(df)
        
        # 인덱스를 재설정하지 않고 저장하여 원본 형식 유지 시도
        df.to_excel(excel_path, index=False)
        
        print(f"✅ 엑셀 파일 업데이트 완료!")
        print(f"   - 이전 행 개수: {initial_row_count}")
        print(f"   - 제거된 행 개수: {initial_row_count - final_row_count}")
        print(f"   - 현재 행 개수: {final_row_count}")

    except FileNotFoundError:
        print(f"❌ 엑셀 파일을 찾을 수 없습니다: {excel_path}")
    except KeyError:
        print(f"❌ 엑셀 파일에서 '{rn_column_name}' 컬럼을 찾을 수 없습니다.")
    except Exception as e:
        print(f"❌ 엑셀 파일 처리 중 오류 발생: {e}")

# --- 프롬프트 정의 ---
prompt_contract = """자동차 구매 계약 서류에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요:

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

prompt_resident_cert = """주민등록초본에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요:

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

prompt_dajanyeo = """[가족관계증명서]에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요. [가족관계증명서] 서류가 보이지 않다면 모든 반환값을 null로 반환해주세요.:

확인 사항:
1. 모든 서류 중 "가족관계증명서"라는 글자가 상단에 표시된 서류가 있는지 확인하세요.
2. 가족관계증명서 상 ['구분']이 '자녀'인 것이 2개 이상인지 확인하세요.

추출 사항:
1. 가족관계증명서 상 ['구분']이 '자녀'의 개수를 추출해주세요.
2. 가족관계증명서 상 ['구분']이 '자녀'의 각 row중 ['출생연월일']에 대한 값을 추출해주세요. (출생연월일은 YYYY-MM-DD 형식으로 추출하세요. 예: 1999년 01월 01일 → "1999-01-01")
3. 가족관계증명서가 위치한 페이지 번호를 추출해주세요.

답변 형식 (JSON 형식을 정확히 지켜서 답변해주세요):
{
  "child_count": 2,
  "child_birth_date": ["1999-01-01", "2001-05-15"],
  "page_number": 1
}

중요:
- 가족관계증명서가 없다면 {"child_count": null, "child_birth_date": null, "page_number": null}을 반환해주세요.
- child_count와 page_number는 숫자만 반환해주세요.
- child_birth_date는 배열로 반환하고, 각 날짜는 "YYYY-MM-DD" 형식의 문자열로 반환해주세요.
- JSON 키는 반드시 큰따옴표로 감싸주세요.
"""

prompt_cheongnyeon = """[지방세 세목별 과세증명서]에서 다음 정보를 찾아서 JSON 형식으로 답변해주세요.

확인 사항:
1. 과세사실이 하나라도 있다면 모든 반환값을 null로 반환해주세요.
2. [지방세 세목별 과세증명서] 서류가 없다면 모든 반환값을 null로 반환해주세요.

추출 사항:
1. 모든 [지방세 세목별 과세증명서]를 검토해서 '내용' 부분에 있는 '지역명' 혹은 '전국 자치단체'에 해당하는 값을 추출해주세요.
2. 과세년도에 해당하는 '범위 연도' 형식을 추출해주세요.

주의 사항:
- [지방세 납세증명(신청)서] 서류와는 다른 서류입니다 이 점 주의해주세요.

답변 형식 (JSON 형식을 정확히 지켜서 답변해주세요):
{
  "local_name": ["경기도 파주시", "경기도 남양주시", "전국 자치단체"],
  "range_date": ["1993~2004", "2004 ~ 2008", "2009 ~ 2025"]
}

중요:
- 과세사실이 하나라도 있다면 {"local_name": null, "range_date": null}을 반환해주세요.
- local_name과 range_date는 문자열만 반환해주세요.
- JSON 키는 반드시 큰따옴표로 감싸주세요.
"""

if __name__ == "__main__":
    # 다운로드 폴더 경로
    download_folder = pathlib.Path(r'C:\Users\HP\Desktop\GyeonggooLee\controller\download')
    
    # test_results.json 기준으로 RN/카테고리/파일명 구성 (우선 사용), 없으면 폴더 스캔
    rn_info_list = []
    json_path = 'test_results.json'
    try:
        # tesla001 모드: threads_filtered JSON 기준으로 RN/카테고리 구성 + 폴더 경로 temp_download로 교체
        if len(sys.argv) > 1 and sys.argv[1] == 'tesla001':
            download_folder = pathlib.Path(r'C:\Users\HP\Desktop\GyeonggooLee\controller\temp_download')
            threads_json_path = os.path.join('테슬라1팀정보', 'threads_filtered_20251030_140141.json')
            if os.path.exists(threads_json_path):
                with open(threads_json_path, 'r', encoding='utf-8') as f:
                    threads = json.load(f)
                    for item in threads:
                        rn = item.get('rn')
                        category = item.get('priority')  # priority.py에서 채운 값 사용
                        if rn and category:
                            # 파일명은 RN만 사용 (카테고리 접미어 금지)
                            filename = f"{rn}.pdf"
                            rn_info_list.append({'rn': rn, 'category': category, 'filename': filename})
                if rn_info_list:
                    print(f"✅ threads_filtered JSON 기준 {len(rn_info_list)}건 로드 (tesla001)")
            else:
                print(f"⚠️  threads JSON을 찾을 수 없습니다: {threads_json_path}")

        # 기본 경로: test_results.json → 폴더 스캔
        if not rn_info_list and os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
                # mail_download.py에서 저장한 all_rn_info 포맷 가정: {RN, category, ...}
                for item in items:
                    rn = item.get('RN')
                    category = item.get('category')
                    if rn and category:
                        filename = f"{rn}_{category.replace('_', '_')}.pdf"
                        rn_info_list.append({'rn': rn, 'category': category, 'filename': filename})
            if rn_info_list:
                print(f"✅ test_results.json에서 {len(rn_info_list)}건 로드")
        
        if not rn_info_list:
            # 폴더 스캔 폴백
            for f in os.listdir(download_folder):
                if f.endswith('.pdf'):
                    parts = f.replace('.pdf', '').split('_')
                    if len(parts) >= 2:
                        rn = parts[0]
                        category = "_".join(parts[1:])
                        rn_info_list.append({'rn': rn, 'category': category, 'filename': f})
                    else:
                        print(f"⚠️  파일명 형식 오류 (무시): {f}")
    except Exception as e:
        print(f"⚠️  RN 로드 중 오류: {e}")
    
    if not rn_info_list:
        print("❌ 처리할 RN 정보가 없습니다 (test_results.json/폴더 모두 비어있음).")
        exit()

    # Supabase 매니저 초기화
    supabase_manager = None
    try:
        # Supabase 프로젝트 정보
        supabase_url = "https://qehjythxhuaxkuotowjq.supabase.co"
        supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFlaGp5dGh4aHVheGt1b3Rvd2pxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjA0ODYwMTYsImV4cCI6MjA3NjA2MjAxNn0.VbzUwkXInOUS4Afj11F0wu_mn244glyIXsDHmE7NDho"
        
        supabase_manager = SupabaseManager(url=supabase_url, key=supabase_key)
        if supabase_manager.test_connection():
            print("✅ Supabase 연결 성공!")
        else:
            print("❌ Supabase 연결 실패!")
            supabase_manager = None
    except Exception as e:
        print(f"❌ Supabase 초기화 실패: {e}")
        supabase_manager = None
    
    # Supabase 기준으로 이미 처리된 RN 제외 (요청/결과 모두 건너뜀)
    try:
        if supabase_manager:
            existing_rows = supabase_manager.get_test_results()
            existing_rns = set(row.get('RN') for row in existing_rows if row and row.get('RN'))
            original_count = len(rn_info_list)
            rn_info_list = [info for info in rn_info_list if info['rn'] not in existing_rns]
            filtered_count = len(rn_info_list)
            excluded = original_count - filtered_count
            if excluded > 0:
                print(f"⚠️  Supabase에 기존 기록이 있는 RN {excluded}건 제외 ({filtered_count}건 처리 예정)")
            if filtered_count == 0:
                print("모든 RN이 Supabase에 이미 존재하여 종료합니다.")
                exit()
    except Exception as e:
        print(f"⚠️  Supabase 기존 RN 필터링 중 오류: {e}")
    
    # 여러 RN 병렬 처리 시작
    print(f"\n🎯 {len(rn_info_list)}개 RN 병렬 처리 시작...")
    
    all_results, total_time, individual_times = process_multiple_rns(
        rn_info_list,
        download_folder,
        supabase_manager
    )

    # tesla001 모드에서 유효 파일이 없어 처리 결과가 비어있으면 조기 종료하여 요약 단계 오류 방지
    if len(sys.argv) > 1 and sys.argv[1] == 'tesla001':
        if not all_results:
            print("\n❌ tesla001: 처리할 유효한 파일이 없어 종료합니다.")
            exit()
    
    # 최종 결과 출력
    print("\n" + "="*60)
    print("🎯 최종 처리 결과 요약")
    print("="*60)
    
    success_count = 0
    for rn, result in all_results.items():
        # 각 결과에서 성공한 카테고리 확인
        contract_success = result.get('contract_data') is not None
        resident_success = result.get('resident_cert_data') is not None
        dajanyeo_success = result.get('dajanyeo_data') is not None
        cheongnyeon_success = result.get('cheongnyeon_data') is not None

        individual_time = individual_times.get(rn, 0)
        
        # 성공 여부 판단 (모든 필수 항목이 성공했는지)
        # 파일의 카테고리에 따라 필수 항목이 달라짐
        category = next((item['category'] for item in rn_info_list if item['rn'] == rn), "")
        
        is_fully_successful = contract_success and resident_success
        if '다자녀' in category:
            is_fully_successful = is_fully_successful and dajanyeo_success
        if '청년생애' in category:
            is_fully_successful = is_fully_successful and cheongnyeon_success
        
        if is_fully_successful:
            success_count += 1
            print(f"✅ {rn} ({category}): 모든 항목 처리 성공 ({individual_time:.1f}s)")
        else:
            status = []
            if contract_success: status.append("계약서")
            if resident_success: status.append("초본")
            if dajanyeo_success: status.append("다자녀")
            if cheongnyeon_success: status.append("청년생애")
            
            if not status:
                print(f"❌ {rn} ({category}): 모든 항목 처리 실패 ({individual_time:.1f}s)")
            else:
                print(f"⚠️  {rn} ({category}): 부분 성공 - {', '.join(status)} ({individual_time:.1f}s)")

    # 시간 통계 계산
    valid_times = [t for t in individual_times.values() if t > 0]
    avg_time = sum(valid_times) / len(valid_times) if valid_times else 0
    total_rn_count = len(rn_info_list)
    
    print(f"\n📊 전체 성공률: {success_count}/{total_rn_count} ({success_count/total_rn_count*100:.1f}%)")
    print(f"\n⏱️  시간 통계:")
    print(f"   - 총 처리 시간: {total_time:.1f}초")
    print(f"   - RN당 평균 처리 시간: {avg_time:.1f}초")
    if total_time > 0:
        print(f"   - 병렬 처리 효율: {sum(valid_times)/total_time:.1f}x (순차 대비)")
    
    if supabase_manager:
        print(f"\n💾 모든 결과가 Supabase에 저장되었습니다.")

    # 성공적으로 처리된 RN 목록을 엑셀에서 제거
    successful_rns = [rn for rn, result in all_results.items() if result] # 결과가 있는 모든 RN을 성공으로 간주
    excel_file_path = 'real.xlsx'
    remove_processed_rns_from_excel(excel_file_path, successful_rns)