import pymupdf
from pathlib import Path
import os
import platform
from PyQt6.QtGui import QPixmap, QPainter, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QBuffer, QIODevice

# A4 규격 (포인트 단위)
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890

file_path = 'stamp_test.pdf'
page_num = 10

def create_text_image(text: str, font_size: int = 19) -> bytes:
    """
    텍스트를 이미지로 변환하여 PNG 바이트를 반환합니다.
    한글 폰트를 제대로 지원하기 위해 PyQt6를 사용합니다.
    """
    # 한글 폰트 설정 (Windows: 맑은 고딕)
    system = platform.system()
    if system == "Windows":
        font_family = "Malgun Gothic"
    elif system == "Darwin":  # macOS
        font_family = "AppleGothic"
    else:  # Linux
        font_family = "NanumGothic"
    
    font = QFont(font_family, font_size, QFont.Weight.Normal)
    
    # 텍스트 크기 계산
    fm = QFontMetrics(font)
    text_width = fm.horizontalAdvance(text)
    text_height = fm.height()
    
    # 여백 추가하여 Pixmap 생성
    padding = 10
    pixmap = QPixmap(text_width + padding * 2, text_height + padding * 2)
    pixmap.fill(Qt.GlobalColor.transparent)  # 투명 배경
    
    # QPainter로 텍스트 그리기
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(font)
    painter.setPen(Qt.GlobalColor.black)  # 검정색
    
    # 텍스트 그리기 (여백 고려)
    painter.drawText(padding, padding + fm.ascent(), text)
    painter.end()
    
    # QPixmap을 PNG 바이트로 변환
    byte_array = QBuffer()
    byte_array.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(byte_array, "PNG")
    return bytes(byte_array.data())

def insert_text_to_pdf(pdf_path: str, page_num: int, text: str, font_size: int = 19):
    """
    PDF 파일의 특정 페이지에 텍스트를 중앙에 삽입하고 저장합니다.
    한글 지원을 위해 텍스트를 이미지로 변환하여 삽입합니다.
    
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
    
    # 이미지 크기 계산 (포인트 단위로 변환)
    # 폰트 크기를 기준으로 대략적인 이미지 크기 계산
    text_image = pymupdf.open(stream=text_image_bytes, filetype="png")
    img_page = text_image[0]
    img_rect = img_page.rect
    img_width = img_rect.width
    img_height = img_rect.height
    
    # 페이지 중앙 좌표 계산
    x = (page_width - img_width) / 2
    y = (page_height - img_height) / 2
    
    # 이미지를 PDF 페이지에 삽입
    image_rect = pymupdf.Rect(x, y, x + img_width, y + img_height)
    page.insert_image(image_rect, stream=text_image_bytes)
    
    text_image.close()
    
    # 같은 파일명으로 저장
    doc.save(pdf_path, incremental=False, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    doc.close()
    
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