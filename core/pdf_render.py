import pymupdf  # PyMuPDF
from PyQt6.QtGui import QPixmap, QImage, QIcon, QTransform
from PyQt6.QtCore import Qt, QBuffer, QIODevice


class PdfRender:
    """PyMuPDF 기반 PDF 렌더러.

    - render_page: 고화질(oversampling)로 페이지를 QPixmap으로 렌더링
    - create_thumbnail: 선명한 썸네일(QIcon) 생성
    """

    def __init__(self):
        self.doc = None
        self.page_count = 0
        self.pdf_path: str | None = None

    def load_pdf(self, pdf_path: str) -> None:
        """PDF 문서를 로드한다.

        Args:
            pdf_path: PDF 파일 경로
        Raises:
            FileNotFoundError: 파일이 존재하지 않을 때
            ValueError: 문서 로드 실패 시
        """
        try:
            self.doc = pymupdf.open(pdf_path)
            self.pdf_path = pdf_path
        except Exception as exc:  # 파일 경로/형식 문제 포함
            raise ValueError(f"PDF 로드 실패: {exc}")

        if self.doc is None or len(self.doc) == 0:
            raise ValueError("빈 문서이거나 로드할 수 없습니다.")

        self.page_count = len(self.doc)

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
    def render_page_thread_safe(pdf_path: str, page_num: int, zoom_factor: float = 2.0, user_rotation: int = 0) -> QPixmap:
        """
        모든 페이지를 A4 세로(Portrait) 기준으로 정규화하여 렌더링한다.
        - 페이지의 원본 크기/회전값과 관계없이 일관된 A4 세로 레이아웃으로 보이도록 처리한다.
        - 고화질을 위해 zoom_factor를 내부적으로 사용하여 A4보다 크게 렌더링 후 QTransform으로 회전한다.
        """
        doc = None
        try:
            doc = pymupdf.open(pdf_path)
            if page_num < 0 or page_num >= len(doc):
                raise IndexError(f"잘못된 페이지 번호: {page_num}")

            page = doc.load_page(page_num)

            # 1. 목표 A4 크기 정의 (고화질 렌더링을 위해 zoom_factor 적용)
            a4_rect = pymupdf.paper_rect("a4")
            target_rect = pymupdf.Rect(0, 0, a4_rect.width * zoom_factor, a4_rect.height * zoom_factor)

            # 2. 페이지의 시각적 크기를 나타내는 사각형 계산
            r = page.rect
            if page.rotation in [90, 270]:
                source_rect = pymupdf.Rect(0, 0, r.height, r.width)
            else:
                source_rect = pymupdf.Rect(0, 0, r.width, r.height)
            
            # 3. 시각적 크기를 목표 A4 크기에 맞추는 변환 매트릭스 계산 (최신 PyMuPDF 방식)
            if source_rect.is_empty: # 너비나 높이가 0인 경우 방지
                fit_matrix = pymupdf.Matrix(1, 1)
            else:
                sx = target_rect.width / source_rect.width
                sy = target_rect.height / source_rect.height
                scale = min(sx, sy)
                fit_matrix = pymupdf.Matrix(scale, scale)

            # 4. 페이지의 원본 회전을 적용하는 매트릭스 생성
            rotation_matrix = pymupdf.Matrix(page.rotation)
            
            # 5. 두 매트릭스를 결합 (회전 후 맞춤)
            final_matrix = rotation_matrix * fit_matrix

            pix = page.get_pixmap(matrix=final_matrix, alpha=False, annots=True)

            image_format = QImage.Format.Format_RGB888 if not pix.alpha else QImage.Format.Format_RGBA8888
            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format).copy()
            
            pixmap = QPixmap.fromImage(qimage)

            # 6. 사용자 인터페이스 회전 적용
            if user_rotation != 0:
                transform = QTransform().rotate(user_rotation)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            
            return pixmap
            
        finally:
            if doc:
                doc.close()