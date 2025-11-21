import pymupdf
from pathlib import Path
import os
import platform
from PIL import Image, ImageDraw, ImageFont

# A4 규격 (포인트 단위)
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890

file_path = 'stamp_test.pdf'
page_num = 10

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
    
    # 페이지 중앙 좌표 계산
    x = (page_width - img_width) / 2
    y = (page_height - img_height) / 2
    
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

if __name__ == "__main__":
    text = '출고예정일 11/28'
    font_size = 19
    
    try:
        insert_text_to_pdf(file_path, page_num - 1, text, font_size)  # page_num은 1-based이므로 -1
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()