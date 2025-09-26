import pymupdf
import traceback # 상세한 오류 추적을 위해 추가
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

    def load_pdf(self, pdf_path: str) -> None:
        """PDF를 로드하고, 모든 페이지를 A4 규격으로 변환하여 메모리에 저장한다."""
        source_doc = None
        new_doc = None
        current_page_num = -1
        TARGET_DPI = 200 # 목표 해상도 (품질과 속도의 균형점)
        try:
            print(f"원본 파일 여는 중: {pdf_path}")
            source_doc = pymupdf.open(pdf_path)
            new_doc = pymupdf.open()
            print("새 인메모리 PDF 문서 생성 완료.")

            for page in source_doc:
                current_page_num = page.number
                print(f"--- 페이지 {current_page_num + 1} 변환 시작 ---")
                
                # 1. 렌더링 전, 페이지의 최종 시각적 크기(bound)를 먼저 계산
                bounds = page.bound()
                is_landscape = bounds.width > bounds.height
                
                # 2. 최종 캔버스가 될 A4 용지 크기 결정
                if is_landscape:
                    a4_rect = pymupdf.paper_rect("a4-l")
                else:
                    a4_rect = pymupdf.paper_rect("a4")
                
                # 3. A4 캔버스에 목표 DPI를 적용했을 때의 픽셀 크기 계산
                target_pixel_width = a4_rect.width / 72 * TARGET_DPI
                target_pixel_height = a4_rect.height / 72 * TARGET_DPI

                # 4. 원본 페이지를 목표 픽셀 크기에 맞추기 위한 최적의 줌(zoom) 비율 계산
                zoom_x = target_pixel_width / bounds.width if bounds.width > 0 else 0
                zoom_y = target_pixel_height / bounds.height if bounds.height > 0 else 0
                zoom = min(zoom_x, zoom_y)

                # 5. 계산된 줌 비율로 '딱 필요한 만큼만' 렌더링
                matrix = pymupdf.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False, annots=True)
                print(f"  - 최적 해상도로 렌더링 완료 (크기: {pix.width}x{pix.height})")
                
                # 6. 새 A4 페이지 생성 및 이미지 삽입
                new_page = new_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                
                margin = 0.98
                page_rect = new_page.rect
                margin_x = page_rect.width * (1 - margin) / 2
                margin_y = page_rect.height * (1 - margin) / 2
                target_rect = page_rect + (margin_x, margin_y, -margin_x, -margin_y)

                new_page.insert_image(target_rect, pixmap=pix)
                print(f"--- 페이지 {current_page_num + 1} 변환 성공 ---\n")

            # 변환된 문서를 바이트로 저장
            print("모든 페이지 변환 완료. PDF 바이트 스트림 생성 중...")
            self.pdf_bytes = new_doc.tobytes(garbage=4, deflate=True) # 안정성을 위해 저장 시 압축
            
            if not self.pdf_bytes:
                raise ValueError("PDF 바이트 스트림 생성에 실패하여 데이터가 비어있습니다.")
            
            print(f"PDF 바이트 스트림 생성 성공 (크기: {len(self.pdf_bytes)} bytes). 최종 문서 로드 중...")

            # 바이트 스트림으로부터 최종 문서 로드
            self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            self.pdf_path = pdf_path
            self.page_count = len(self.doc)
            print("최종 문서 로드 성공!")

        except Exception as exc:
            print("\n" + "="*20 + " PDF 처리 중 심각한 오류 발생 " + "="*20)
            print(f"오류 발생 지점: 페이지 {current_page_num + 1}")
            print(f"예외 유형: {type(exc).__name__}")
            print(f"예외 메시지: {exc}")
            print("\n--- 상세 Traceback 정보 ---")
            traceback.print_exc() # 전체 오류 스택 출력
            print("="*65 + "\n")
            raise ValueError(f"PDF 로드 및 A4 변환 실패: {exc}")
        finally:
            if source_doc:
                source_doc.close()
            if new_doc:
                new_doc.close()

        if self.doc is None or len(self.doc) == 0:
            raise ValueError("빈 문서이거나 변환 후 페이지가 없습니다.")

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