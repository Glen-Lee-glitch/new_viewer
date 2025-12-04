import pymupdf
from pathlib import Path
import os
import platform
from PIL import Image, ImageDraw, ImageFont
import pymysql
from contextlib import closing
from datetime import datetime
from core.sql_manager import calculate_delivery_date

DB_CONFIG = {
    'host': '192.168.0.114',
    'port': 3306,
    'user': 'my_pc_user',
    'password': '!Qdhdbrclf56',
    'db': 'greetlounge',
    'charset': 'utf8mb4'
}

# A4 규격 (포인트 단위)
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890

file_path = 'stamp_test.pdf'
page_num = 5


def _normalize_file_path(raw_path):
    """
    로컬 경로를 네트워크 경로로 변환합니다.
    pdf_load_widget.py의 _normalize_file_path 메서드를 참고했습니다.
    """
    if raw_path is None:
        return None

    if isinstance(raw_path, Path):
        path_str = str(raw_path)
    else:
        path_str = str(raw_path)

    path_str = path_str.strip()
    if path_str.startswith('"') and path_str.endswith('"') and len(path_str) >= 2:
        path_str = path_str[1:-1]
    elif path_str.startswith("'") and path_str.endswith("'") and len(path_str) >= 2:
        path_str = path_str[1:-1]
    
    path_str = path_str.strip()

    if path_str.upper().startswith('C:'):
        path_str = r'\\DESKTOP-KMJ' + path_str[2:]

    return path_str.strip()

def fetch_table_data():
    """
    데이터베이스에서 3개의 테이블을 JOIN하여 데이터를 가져옵니다.
    
    - test_ai_구매계약서의 ['modified_date', 'RN', 'page_number']
    - subsidy_applications의 ['RN', 'recent_thread_id', 'region']를 RN으로 매칭
    - emails의 ['thread_id', 'attached_file_path']를 recent_thread_id로 매칭
    - attached_file_path가 없는 row는 제외
    - 최종 10개만 반환
    
    Returns:
        list[dict]: 조인된 데이터 리스트 (최대 10개)
    """
    try:
        with closing(pymysql.connect(**DB_CONFIG)) as connection:
            query = """
                SELECT 
                    c.modified_date,
                    c.RN,
                    c.page_number,
                    sa.recent_thread_id,
                    sa.region,
                    e.attached_file_path
                FROM test_ai_구매계약서 c
                INNER JOIN subsidy_applications sa 
                    ON c.RN COLLATE utf8mb4_unicode_ci = sa.RN COLLATE utf8mb4_unicode_ci
                INNER JOIN emails e 
                    ON sa.recent_thread_id = e.thread_id
                WHERE e.attached_file_path IS NOT NULL 
                    AND e.attached_file_path != ''
                ORDER BY c.modified_date DESC
                LIMIT 10
            """
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                
                # attached_file_path를 네트워크 경로로 변환
                for row in result:
                    if 'attached_file_path' in row:
                        row['attached_file_path'] = _normalize_file_path(row['attached_file_path'])
                
                print(f"✅ {len(result)}개의 데이터를 가져왔습니다.")
                return result
    
    except Exception as e:
        print(f"❌ 데이터베이스 조회 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return []

def find_korean_font():
    """시스템에서 한글 폰트 파일 경로를 찾습니다."""
    system = platform.system()
    
    if system == "Windows":
        font_dirs = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        ]
        font_files = [
            "malgun.ttf",  # 맑은 고딕
            "malgunbd.ttf",  # 맑은 고딕 Bold
            "gulim.ttc",  # 굴림
        ]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for font_file in font_files:
                    font_path = os.path.join(font_dir, font_file)
                    if os.path.exists(font_path):
                        return font_path
    
    elif system == "Darwin":  # macOS
        font_dirs = [
            "/System/Library/Fonts/Supplemental",
            "/Library/Fonts",
        ]
        font_files = ["AppleGothic.ttf"]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for font_file in font_files:
                    font_path = os.path.join(font_dir, font_file)
                    if os.path.exists(font_path):
                        return font_path
    
    elif system == "Linux":
        font_dirs = [
            "/usr/share/fonts/truetype/nanum",
            "/usr/share/fonts/truetype/liberation",
        ]
        font_files = ["NanumGothic.ttf"]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for font_file in font_files:
                    font_path = os.path.join(font_dir, font_file)
                    if os.path.exists(font_path):
                        return font_path
    
    return None

def create_text_image(text: str, font_size: int = 19) -> bytes:
    """
    PIL을 사용하여 텍스트를 이미지로 변환하여 PNG 바이트를 반환합니다.
    """
    # 한글 폰트 찾기
    font_path = find_korean_font()
    
    try:
        if font_path:
            # 폰트 파일 로드 (폰트 크기를 포인트에서 픽셀로 변환, DPI 72 기준)
            font = ImageFont.truetype(font_path, int(font_size * 1.33))  # pt to px 변환
        else:
            # 기본 폰트 사용 (한글 지원 안 될 수 있음)
            font = ImageFont.load_default()
            print("⚠️ 한글 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
    except Exception as e:
        print(f"⚠️ 폰트 로드 실패: {e}, 기본 폰트 사용")
        font = ImageFont.load_default()
    
    # 텍스트 크기 계산
    # 임시 이미지로 텍스트 크기 측정
    temp_img = Image.new('RGB', (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # 여백 추가하여 이미지 생성
    padding = 10
    img_width = text_width + padding * 2
    img_height = text_height + padding * 2
    
    # 투명 배경 이미지 생성
    img = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # 텍스트 그리기 (검정색)
    draw.text((padding, padding), text, font=font, fill=(0, 0, 0, 255))
    
    # PNG 바이트로 변환
    import io
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()

def insert_text_to_pdf(pdf_path: str, page_num: int, text: str, font_size: int = 19):
    """
    PDF 파일의 특정 페이지에 텍스트를 중앙에 삽입하고 저장합니다.
    
    Args:
        pdf_path: PDF 파일 경로
        page_num: 페이지 번호 (0-based index)
        text: 삽입할 텍스트
        font_size: 폰트 크기 (pt)
    """
    pdf_file = Path(pdf_path)
    
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
    
    # PDF 열기
    doc = pymupdf.open(pdf_path)
    
    if page_num >= len(doc):
        doc.close()
        raise ValueError(f"페이지 번호가 범위를 벗어났습니다. 총 페이지 수: {len(doc)}")
    
    # 해당 페이지 가져오기
    page = doc[page_num]
    
    # 페이지 크기 가져오기
    page_rect = page.rect
    page_width = page_rect.width
    page_height = page_rect.height
    
    # 텍스트를 이미지로 변환
    text_image_bytes = create_text_image(text, font_size)
    
    # 이미지 크기 계산
    text_image = pymupdf.open(stream=text_image_bytes, filetype="png")
    img_page = text_image[0]
    img_rect = img_page.rect
    img_width = img_rect.width
    img_height = img_rect.height
    
    text_image.close()
    
    # 페이지 중앙 좌표 계산 후 살짝 아래로 이동
    x = (page_width - img_width) / 2
    y = (page_height - img_height) / 2 + 30  # 중앙에서 30pt 아래로 이동
    
    # 이미지를 PDF 페이지에 삽입
    image_rect = pymupdf.Rect(x, y, x + img_width, y + img_height)
    page.insert_image(image_rect, stream=text_image_bytes)
    
    # 임시 파일에 저장한 후 원본 파일로 교체
    temp_path = str(pdf_file.with_suffix('.tmp.pdf'))
    doc.save(temp_path, incremental=False, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    
    # 원본 파일을 임시 파일로 교체
    pdf_file.unlink()  # 원본 파일 삭제
    Path(temp_path).rename(pdf_path)  # 임시 파일을 원본 이름으로 변경
    
    print(f"✅ 텍스트 '{text}'가 페이지 {page_num + 1}에 삽입되었습니다.")
    print(f"   좌표: ({x:.2f}, {y:.2f})")
    print(f"   파일 저장 완료: {pdf_path}")

def process_batch_files():
    """
    데이터베이스에서 가져온 10개 데이터를 순회하며 각 PDF 파일에 텍스트를 삽입합니다.
    """
    font_size = 16
    
    # 데이터베이스에서 데이터 가져오기
    data_list = fetch_table_data()
    
    if not data_list:
        print("❌ 처리할 데이터가 없습니다.")
        return
    
    print(f"\n📋 총 {len(data_list)}개의 파일을 처리합니다.\n")
    
    success_count = 0
    error_count = 0
    
    for idx, data in enumerate(data_list, 1):
        pdf_path = data.get('attached_file_path')
        page_number = data.get('page_number')
        rn = data.get('RN')
        region = data.get('region')
        
        if not pdf_path:
            print(f"[{idx}/{len(data_list)}] ❌ RN {rn}: attached_file_path가 없습니다.")
            error_count += 1
            continue
        
        if page_number is None:
            print(f"[{idx}/{len(data_list)}] ❌ RN {rn}: page_number가 없습니다.")
            error_count += 1
            continue
        
        # 출고예정일 계산
        if not region:
            print(f"[{idx}/{len(data_list)}] ⚠️ RN {rn}: region이 없어 출고예정일을 계산할 수 없습니다.")
            error_count += 1
            continue
        
        delivery_date_str = calculate_delivery_date(region)
        if not delivery_date_str:
            print(f"[{idx}/{len(data_list)}] ⚠️ RN {rn}: 출고예정일 계산 실패 (region: {region})")
            error_count += 1
            continue
        
        # YYYY-MM-DD 형식을 MM/DD 형식으로 변환
        try:
            delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d')
            date_formatted = delivery_date.strftime('%m/%d')
            text = f'출고예정일 {date_formatted}'
        except Exception as e:
            print(f"[{idx}/{len(data_list)}] ⚠️ RN {rn}: 날짜 형식 변환 실패: {e}")
            error_count += 1
            continue
        
        print(f"[{idx}/{len(data_list)}] 처리 중: RN {rn}, 파일: {Path(pdf_path).name}, 페이지: {page_number}, 출고예정일: {text}")
        
        try:
            # PDF 파일 존재 확인
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                print(f"  ⚠️ 파일이 존재하지 않습니다: {pdf_path}")
                error_count += 1
                continue
            
            # 페이지 번호는 1-based이므로 0-based로 변환
            page_num_0based = int(page_number) - 1
            
            # 텍스트 삽입
            insert_text_to_pdf(pdf_path, page_num_0based, text, font_size)
            success_count += 1
            print(f"  ✅ 완료\n")
            
        except Exception as e:
            print(f"  ❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
            print()
    
    print(f"\n📊 처리 완료: 성공 {success_count}개, 실패 {error_count}개")


if __name__ == "__main__":
    try:
        process_batch_files()
    except Exception as e:
        print(f"❌ 전체 처리 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()