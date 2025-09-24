import pymupdf
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt

class PdfRender:
    def __init__(self):
        self.doc = None
        self.page_count = 0

    def load_pdf(self, pdf_path: str):
        return

    def render_page(self, page_num: int, zoom_factor: float = 2.0):
        # zoom_factor로 해상도 조절 (2.0 = 200% 화질)
        # 페이지를 QPixmap으로 변환
        # 안티앨리어싱 적용
        return

    def create_thumbnail(self, page_num: int, max_width: int = 90):
        # 작은 크기로 렌더링 (화질 유지)
        # 비율 유지하며 리사이징
        # QIcon으로 변환
        return