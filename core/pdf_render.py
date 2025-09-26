import pymupdf
import traceback
import io
import os
from PIL import Image
from PyQt6.QtGui import QPixmap, QImage, QIcon, QTransform
from PyQt6.QtCore import Qt, QBuffer, QIODevice

A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890

# 거대 이미지 판별을 위한 픽셀 수 임계값 (5천만 픽셀)
# 8k UHD (3840x2160)가 약 830만 픽셀인 것을 감안한 넉넉한 값
LARGE_IMAGE_PIXELS_THRESHOLD = 50_000_000


class PdfRender:
    """PyMuPDF 기반 PDF 렌더러.
    - load_pdf: PDF를 로드하며 A4 규격으로 사전 변환
    - render_page: 변환된 페이지를 QPixmap으로 렌더링
    - create_thumbnail: 선명한 썸네일(QIcon) 생성
    """

    def __init__(self):
        self.doc = None
        self.page_count = 0
        self.pdf_path: str | None = None
        self.pdf_bytes: bytes | None = None

    def load_pdf(self, paths: list) -> None:
        """여러 PDF 및 이미지 파일을 병합하고, 모든 페이지를 A4 규격으로 변환하여 메모리에 저장한다."""
        if not paths:
            raise ValueError("입력 파일 경로가 없습니다.")

        merged_doc = None
        new_doc = None
        source_doc_for_a4 = None
        
        try:
            # --- 1단계: 모든 입력 파일을 하나의 PDF로 병합 ---
            merged_doc = pymupdf.open()
            print("입력 파일 병합 시작...")
            for path in paths:
                ext = os.path.splitext(path)[1].lower()
                
                if ext == '.pdf':
                    try:
                        with pymupdf.open(path) as temp_doc:
                            merged_doc.insert_pdf(temp_doc)
                        print(f"  - PDF 병합 성공: {path}")
                    except Exception as e:
                        print(f"  - PDF 병합 실패, 재시도...: {path} ({e})")
                        try: # 정리하여 재시도
                            with pymupdf.open(path) as temp_doc:
                                buffer = temp_doc.write(garbage=4, clean=True)
                            with pymupdf.open("pdf", buffer) as cleaned_doc:
                                merged_doc.insert_pdf(cleaned_doc)
                            print(f"  - PDF 병합 재시도 성공: {path}")
                        except Exception as e2:
                            print(f"  - PDF 병합 최종 실패: {path} ({e2})")

                elif ext in ['.png', '.jpg', '.jpeg']:
                    try:
                        with Image.open(path).convert("RGB") as img:
                            img_bytes = io.BytesIO()
                            img.save(img_bytes, format="PDF")
                            img_bytes.seek(0)
                            with pymupdf.open("pdf", img_bytes.read()) as img_doc:
                                merged_doc.insert_pdf(img_doc)
                            print(f"  - 이미지 -> PDF 변환 및 병합 성공: {path}")
                    except Exception as e:
                        print(f"  - 이미지 병합 실패: {path} ({e})")

            if merged_doc.page_count == 0:
                raise ValueError("병합할 수 있는 유효한 페이지가 없습니다.")
            
            print(f"모든 파일 병합 완료. 총 {merged_doc.page_count} 페이지.")

            # --- 2단계: 병합된 PDF를 A4 규격으로 변환 ---
            print("\nA4 규격으로 변환 시작...")
            new_doc = pymupdf.open()
            source_doc_for_a4 = merged_doc # A4 변환의 소스는 병합된 문서
            TARGET_DPI = 200

            for page in source_doc_for_a4:
                # (기존의 최적화된 A4 변환 로직과 동일)
                bounds = page.bound()
                is_landscape = bounds.width > bounds.height
                
                if is_landscape: a4_rect = pymupdf.paper_rect("a4-l")
                else: a4_rect = pymupdf.paper_rect("a4")
                
                target_pixel_width = a4_rect.width / 72 * TARGET_DPI
                target_pixel_height = a4_rect.height / 72 * TARGET_DPI

                zoom_x = target_pixel_width / bounds.width if bounds.width > 0 else 0
                zoom_y = target_pixel_height / bounds.height if bounds.height > 0 else 0
                zoom = min(zoom_x, zoom_y)

                matrix = pymupdf.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False, annots=True)
                
                new_page = new_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                
                margin = 0.98
                page_rect = new_page.rect
                margin_x = page_rect.width * (1 - margin) / 2
                margin_y = page_rect.height * (1 - margin) / 2
                target_rect = page_rect + (margin_x, margin_y, -margin_x, -margin_y)

                new_page.insert_image(target_rect, pixmap=pix)

            print("A4 규격 변환 완료. 최종 바이트 스트림 생성 중...")
            self.pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
            
            if not self.pdf_bytes:
                raise ValueError("최종 PDF 바이트 스트림 생성에 실패했습니다.")
            
            print(f"최종 문서 생성 성공 (크기: {len(self.pdf_bytes)} bytes).")
            
            self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            self.pdf_path = paths[0] # 첫 번째 파일을 대표 경로로 사용
            self.page_count = len(self.doc)

        except Exception as exc:
            traceback.print_exc()
            raise ValueError(f"문서 처리 중 오류 발생: {exc}")
        finally:
            if merged_doc: merged_doc.close()
            if new_doc: new_doc.close()

    def get_pdf_bytes(self) -> bytes | None:
        """변환된 PDF의 바이트 데이터를 반환한다."""
        return self.pdf_bytes
        
    def _ensure_loaded(self) -> None:
        if self.doc is None:
            raise RuntimeError("PDF가 로드되지 않았습니다. load_pdf()를 먼저 호출하세요.")

    def render_page(self, page_num: int, zoom_factor: float = 2.0) -> QPixmap:
        """페이지를 고화질로 렌더링하여 QPixmap을 반환한다.

        고화질 유지 전략:
        - PyMuPDF의 Matrix zoom(>=2.0)을 사용해 oversampling 렌더링
        - Qt에서 추가 스케일 없이 그대로 사용해 선명도 유지

        Args:
            page_num: 0-based 페이지 인덱스
            zoom_factor: 배율(기본 2.0; 2.0~3.0 권장)
        Returns:
            QPixmap: 렌더링 결과
        """
        self._ensure_loaded()
        if page_num < 0 or page_num >= self.page_count:
            raise IndexError(f"잘못된 페이지 번호: {page_num}")

        page = self.doc.load_page(page_num)
        # alpha=False로 불필요한 알파 채널 방지(성능/메모리), 주석 해제 시 투명 포함 가능
        mat = pymupdf.Matrix(zoom_factor, zoom_factor)
        pix = page.get_pixmap(matrix=mat, alpha=False, annots=True)

        # PyMuPDF pixmap -> QImage -> QPixmap
        image_format = QImage.Format.Format_RGB888 if not pix.alpha else QImage.Format.Format_RGBA8888
        qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format)
        # QImage가 원본 버퍼에 의존하지 않도록 강제 복사
        qimage = qimage.copy()
        return QPixmap.fromImage(qimage)

    def create_thumbnail(self, page_num: int, max_width: int = 90) -> QIcon:
        """선명한 썸네일(QIcon)을 생성한다.

        전략:
        - oversampling(대략 목표 폭의 2배)로 먼저 크게 렌더링
        - Qt의 SmoothTransformation으로 다운스케일 → 선명도 유지

        Args:
            page_num: 0-based 페이지 인덱스
            max_width: 썸네일 최대 너비(px)
        Returns:
            QIcon: 아이콘으로 반환(리스트/트리 뷰에 바로 사용 가능)
        """
        self._ensure_loaded()
        if page_num < 0 or page_num >= self.page_count:
            raise IndexError(f"잘못된 페이지 번호: {page_num}")

        page = self.doc.load_page(page_num)

        # 페이지 원본 크기(포인트 단위)를 이용해 목표 폭의 2배 정도로 렌더링 비율 계산
        rect = page.rect
        if rect.width == 0:
            zoom = 2.0
        else:
            target_render_width = max(max_width * 2, max_width)  # 최소 2배 oversampling
            zoom = max(1.0, target_render_width / rect.width)

        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False, annots=True)

        image_format = QImage.Format.Format_RGB888 if not pix.alpha else QImage.Format.Format_RGBA8888
        qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format).copy()
        qpix = QPixmap.fromImage(qimage)

        if qpix.width() > max_width:
            qpix = qpix.scaled(
                max_width,
                int(qpix.height() * (max_width / qpix.width())),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        return QIcon(qpix)

    def close(self) -> None:
        """문서를 닫고 자원 해제."""
        if self.doc is not None:
            try:
                self.doc.close()
            finally:
                self.doc = None
                self.page_count = 0

    def get_page_count(self) -> int:
        """페이지 수 반환."""
        return self.page_count

    def apply_crop_to_page(self, page_num: int, crop_rect_normalized: tuple) -> None:
        """
        특정 페이지에 자르기를 적용하고 A4 세로 규격으로 확대한다.
        
        Args:
            page_num: 0-based 페이지 인덱스
            crop_rect_normalized: (x, y, width, height) 정규화된 자르기 영역 (0.0~1.0)
        """
        if not self.pdf_bytes:
            raise RuntimeError("PDF가 로드되지 않았습니다.")
        
        if page_num < 0 or page_num >= self.page_count:
            raise IndexError(f"잘못된 페이지 번호: {page_num}")
        
        x, y, width, height = crop_rect_normalized
        
        # 정규화된 값 검증
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 
                0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            raise ValueError("자르기 영역이 유효하지 않습니다.")
        
        try:
            # 현재 PDF 바이트에서 새 문서 생성
            with pymupdf.open(stream=self.pdf_bytes, filetype="pdf") as source_doc:
                new_doc = pymupdf.open()
                
                # 모든 페이지를 복사하되, 지정된 페이지만 자르기 적용
                for i, page in enumerate(source_doc):
                    if i == page_num:
                        # 자르기 적용할 페이지
                        page_rect = page.rect
                        
                        # 정규화된 좌표를 실제 페이지 좌표로 변환
                        crop_x = page_rect.x0 + x * page_rect.width
                        crop_y = page_rect.y0 + y * page_rect.height  
                        crop_width = width * page_rect.width
                        crop_height = height * page_rect.height
                        
                        crop_rect = pymupdf.Rect(
                            crop_x, crop_y, 
                            crop_x + crop_width, crop_y + crop_height
                        )
                        
                        # 자르기 영역을 고해상도로 렌더링 (TARGET_DPI 사용)
                        TARGET_DPI = 200
                        zoom_factor = TARGET_DPI / 72.0
                        matrix = pymupdf.Matrix(zoom_factor, zoom_factor)
                        
                        # 자르기 영역만 렌더링
                        pix = page.get_pixmap(matrix=matrix, clip=crop_rect, alpha=False, annots=True)
                        
                        # A4 세로 페이지 생성
                        a4_rect = pymupdf.paper_rect("a4")
                        new_page = new_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                        
                        # A4 페이지에 자른 이미지를 확대하여 삽입 (2% 여백)
                        margin = 0.98
                        target_rect = new_page.rect
                        margin_x = target_rect.width * (1 - margin) / 2
                        margin_y = target_rect.height * (1 - margin) / 2
                        insert_rect = target_rect + (margin_x, margin_y, -margin_x, -margin_y)
                        
                        new_page.insert_image(insert_rect, pixmap=pix)
                        
                    else:
                        # 다른 페이지들은 그대로 복사
                        new_doc.insert_pdf(source_doc, from_page=i, to_page=i)
                
                # 새로운 PDF 바이트 생성
                self.pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
                
                # 문서 객체 갱신
                if self.doc:
                    self.doc.close()
                self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
                
                print(f"페이지 {page_num + 1}에 자르기 적용 완료")
                
        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"자르기 적용 중 오류 발생: {e}")

    @staticmethod
    def render_page_thread_safe(pdf_bytes: bytes, page_num: int, zoom_factor: float = 2.0, user_rotation: int = 0) -> QPixmap:
        """
        A4로 사전 변환된 PDF 바이트 스트림으로부터 페이지를 렌더링한다.
        - 이제 이 메서드는 항상 A4 비율의 페이지를 다루게 된다.
        """
        doc = None
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            if page_num < 0 or page_num >= len(doc):
                raise IndexError(f"잘못된 페이지 번호: {page_num}")

            page = doc.load_page(page_num)

            # 고화질 렌더링 매트릭스 생성
            zoom_matrix = pymupdf.Matrix(zoom_factor, zoom_factor)
            pix = page.get_pixmap(matrix=zoom_matrix, alpha=False, annots=True)

            image_format = QImage.Format.Format_RGB888 if not pix.alpha else QImage.Format.Format_RGBA8888
            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format).copy()
            
            pixmap = QPixmap.fromImage(qimage)

            # 사용자 인터페이스에서 요청한 추가 회전을 적용한다.
            if user_rotation != 0:
                transform = QTransform().rotate(user_rotation)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            
            return pixmap
            
        finally:
            if doc:
                doc.close()