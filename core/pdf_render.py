import pymupdf
import traceback
import io
import os
from PIL import Image
from PyQt6.QtGui import QPixmap, QImage, QIcon, QTransform
from PyQt6.QtCore import Qt, QBuffer, QIODevice
from pathlib import Path

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

    def load_preprocessed_pdf(self, path: str) -> None:
        """전처리된 PDF 파일을 빠르게 로드한다."""
        if not Path(path).exists():
            raise FileNotFoundError(f"전처리된 파일을 찾을 수 없습니다: {path}")
        
        try:
            print(f"🚀 전처리된 파일 고속 로딩 시작: {Path(path).name}")
            with open(path, 'rb') as f:
                self.pdf_bytes = f.read()
            
            self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            self.pdf_path = path
            self.page_count = len(self.doc)
            print(f"✅ 고속 로딩 완료. 총 {self.page_count} 페이지.")
        
        except Exception as exc:
            traceback.print_exc()
            raise ValueError(f"전처리된 문서 로딩 중 오류 발생: {exc}")

    def load_pdf(self, path: str) -> None:
        """단일 PDF 파일을 A4 규격으로 변환하여 메모리에 저장한다."""
        if not path:
            raise ValueError("입력 파일 경로가 없습니다.")

        if not Path(path).exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
        
        source_doc = None
        new_doc = None
        
        try:
            print(f"🔄 A4 변환 시작: {Path(path).name}")
            
            # 원본 PDF 열기
            source_doc = pymupdf.open(path)
            if source_doc.page_count == 0:
                raise ValueError("처리할 수 있는 유효한 페이지가 없습니다.")
            
            print(f"원본 문서 로드 완료. 총 {source_doc.page_count} 페이지.")

            # A4 규격으로 변환
            print("A4 규격으로 변환 중...")
            new_doc = pymupdf.open()
            TARGET_DPI = 200

            for page in source_doc:
                bounds = page.bound()
                is_landscape = bounds.width > bounds.height
                
                if is_landscape: 
                    a4_rect = pymupdf.paper_rect("a4-l")
                else: 
                    a4_rect = pymupdf.paper_rect("a4")
                
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
            
            print(f"✅ A4 변환 완료 (크기: {len(self.pdf_bytes)} bytes).")
            
            self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            self.pdf_path = path
            self.page_count = len(self.doc)

        except Exception as exc:
            traceback.print_exc()
            raise ValueError(f"문서 처리 중 오류 발생: {exc}")
        finally:
            if source_doc: source_doc.close()
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

    def set_pdf_bytes(self, pdf_bytes: bytes):
        """
        PDF 문서의 바이트 데이터를 외부에서 설정한다. (되돌리기 기능용)
        """
        self.pdf_bytes = pdf_bytes
        # 새 데이터로 교체되었으므로, doc 객체도 다시 로드해야 함
        self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")

    def create_thumbnail(self, page_num: int, max_width: int = 90, user_rotation: int = 0) -> QIcon:
        """선명한 썸네일(QIcon)을 생성한다.

        전략:
        - oversampling(대략 목표 폭의 2배)로 먼저 크게 렌더링
        - Qt의 SmoothTransformation으로 다운스케일 → 선명도 유지

        Args:
            page_num: 0-based 페이지 인덱스
            max_width: 썸네일 최대 너비(px)
            user_rotation: 사용자 지정 회전 각도 (0, 90, 180, 270)
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

        # 사용자 회전 적용
        if user_rotation != 0:
            transform = QTransform().rotate(user_rotation)
            qpix = qpix.transformed(transform, Qt.TransformationMode.SmoothTransformation)

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
        self.apply_crop_to_pages([page_num], crop_rect_normalized)

    def apply_crop_to_pages(self, page_nums: list[int], crop_rect_normalized: tuple) -> None:
        """
        여러 페이지에 동일한 자르기를 적용하고 A4 세로 규격으로 확대한다.
        
        Args:
            page_nums: 0-based 페이지 인덱스 리스트
            crop_rect_normalized: (x, y, width, height) 정규화된 자르기 영역 (0.0~1.0)
        """
        if not self.pdf_bytes:
            raise RuntimeError("PDF가 로드되지 않았습니다.")
        
        if not page_nums:
            return
        
        # 페이지 번호 검증
        for page_num in page_nums:
            if page_num < 0 or page_num >= self.page_count:
                raise IndexError(f"잘못된 페이지 번호: {page_num}")
        
        x, y, width, height = crop_rect_normalized
        
        # 정규화된 값 검증
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 
                0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            raise ValueError("자르기 영역이 유효하지 않습니다.")
        
        page_nums_set = set(page_nums)  # 빠른 조회를 위해 set 사용
        
        try:
            # 현재 PDF 바이트에서 새 문서 생성
            with pymupdf.open(stream=self.pdf_bytes, filetype="pdf") as source_doc:
                new_doc = pymupdf.open()
                
                # 모든 페이지를 복사하되, 지정된 페이지들만 자르기 적용
                for i, page in enumerate(source_doc):
                    if i in page_nums_set:
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
                        # 다른 페이지들은 A4 규격으로 변환하여 복사
                        page = source_doc.load_page(i)
                        
                        # 페이지 방향에 맞춰 A4 크기 결정
                        bounds = page.bound()
                        is_landscape = bounds.width > bounds.height
                        if is_landscape: a4_rect = pymupdf.paper_rect("a4-l")
                        else: a4_rect = pymupdf.paper_rect("a4")
                        
                        new_page = new_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                        new_page.show_pdf_page(new_page.rect, source_doc, i)
                
                # 새로운 PDF 바이트 생성
                self.pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
                
                # 문서 객체 갱신
                if self.doc:
                    self.doc.close()
                self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
                
                if len(page_nums) == 1:
                    print(f"페이지 {page_nums[0] + 1}에 자르기 적용 완료")
                else:
                    print(f"{len(page_nums)}개 페이지에 자르기 적용 완료: {[p+1 for p in sorted(page_nums)]}")
                
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

    def delete_pages(self, page_nums_to_delete: list[int]):
        """지정된 페이지들을 PDF에서 삭제하고 내부 데이터를 갱신한다."""
        if not self.pdf_bytes:
            raise RuntimeError("PDF가 로드되지 않았습니다.")
        
        # 중복 제거 및 정렬
        pages_to_delete = sorted(list(set(page_nums_to_delete)), reverse=True)
        
        try:
            with pymupdf.open(stream=self.pdf_bytes, filetype="pdf") as source_doc:
                # 유효한 페이지 번호인지 확인
                for page_num in pages_to_delete:
                    if not (0 <= page_num < source_doc.page_count):
                         raise IndexError(f"잘못된 페이지 번호: {page_num}")
                
                # 지정된 페이지들을 삭제
                source_doc.delete_pages(pages_to_delete)
                
                # 페이지가 하나도 남지 않았는지 확인
                if source_doc.page_count == 0:
                    self.pdf_bytes = b"" # 빈 바이트로 설정
                else:
                    # 변경된 내용으로 새로운 바이트 데이터 생성
                    self.pdf_bytes = source_doc.tobytes(garbage=4, deflate=True)

            # 새 데이터로 내부 문서 객체와 페이지 수 갱신
            if self.doc:
                self.doc.close()
            
            if self.pdf_bytes:
                self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
                self.page_count = self.doc.page_count
            else:
                self.doc = None
                self.page_count = 0
            
            print(f"페이지 삭제 완료: {[p + 1 for p in sorted(page_nums_to_delete)]}. 현재 페이지 수: {self.page_count}")

        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"페이지 삭제 중 오류 발생: {e}")

    def append_file(self, file_path: str) -> None:
        """파일(PDF/이미지)을 현재 문서의 끝에 추가한다 (A4 변환 적용)."""
        if not self.pdf_bytes:
            # 현재 문서가 없으면 그냥 로드
            self.load_pdf([file_path])
            return

        try:
            # 1. 추가할 파일을 임시 문서로 오픈
            append_doc = pymupdf.open()
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext == '.pdf':
                with pymupdf.open(file_path) as f:
                    append_doc.insert_pdf(f)
            elif ext in ['.png', '.jpg', '.jpeg']:
                with Image.open(file_path).convert("RGB") as img:
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format="PDF")
                    img_bytes.seek(0)
                    with pymupdf.open("pdf", img_bytes.read()) as img_doc:
                        append_doc.insert_pdf(img_doc)
            else:
                 raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")
            
            # 2. 현재 문서를 수정 가능한 상태로 오픈
            current_doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            
            # 3. 추가할 문서의 페이지를 A4로 변환하여 현재 문서 끝에 추가
            TARGET_DPI = 200
            for page in append_doc:
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
                
                new_page = current_doc.new_page(width=a4_rect.width, height=a4_rect.height)
                
                margin = 0.98
                page_rect = new_page.rect
                margin_x = page_rect.width * (1 - margin) / 2
                margin_y = page_rect.height * (1 - margin) / 2
                target_rect = page_rect + (margin_x, margin_y, -margin_x, -margin_y)

                new_page.insert_image(target_rect, pixmap=pix)

            # 4. 변경사항 저장 및 상태 업데이트
            self.pdf_bytes = current_doc.tobytes(garbage=4, deflate=True)
            
            if self.doc:
                self.doc.close()
            self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            self.page_count = len(self.doc)
            
            append_doc.close()
            current_doc.close()
            
            print(f"파일 추가 완료: {file_path}. 총 페이지 수: {self.page_count}")

        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"파일 추가 중 오류 발생: {e}")

    def replace_page(self, page_num: int, source_pdf_bytes: bytes, source_page_num: int) -> None:
        """지정된 페이지를 원본 PDF 파일의 같은 페이지 번호로 교체한다.
        
        Args:
            page_num: 교체할 현재 PDF의 페이지 번호 (0부터 시작)
            source_pdf_bytes: 원본 PDF 파일의 바이트 데이터
            source_page_num: 원본 PDF에서 가져올 페이지 번호 (0부터 시작)
        """
        if not self.pdf_bytes:
            raise RuntimeError("PDF가 로드되지 않았습니다.")
        
        try:
            # 원본 PDF 문서 열기
            with pymupdf.open(stream=source_pdf_bytes, filetype="pdf") as source_doc:
                # 원본 페이지 번호 유효성 확인
                if not (0 <= source_page_num < source_doc.page_count):
                    raise IndexError(f"원본 PDF에 페이지 번호 {source_page_num}가 없습니다. (총 {source_doc.page_count} 페이지)")
                
                # 현재 문서 열기
                with pymupdf.open(stream=self.pdf_bytes, filetype="pdf") as current_doc:
                    # 현재 페이지 번호 유효성 확인
                    if not (0 <= page_num < current_doc.page_count):
                        raise IndexError(f"현재 PDF에 페이지 번호 {page_num}가 없습니다. (총 {current_doc.page_count} 페이지)")
                    
                    # 원본 페이지를 A4로 변환하여 가져오기
                    source_page = source_doc.load_page(source_page_num)
                    bounds = source_page.bound()
                    is_landscape = bounds.width > bounds.height
                    
                    TARGET_DPI = 200
                    if is_landscape:
                        a4_rect = pymupdf.paper_rect("a4-l")
                    else:
                        a4_rect = pymupdf.paper_rect("a4")
                    
                    target_pixel_width = a4_rect.width / 72 * TARGET_DPI
                    target_pixel_height = a4_rect.height / 72 * TARGET_DPI
                    
                    zoom_x = target_pixel_width / bounds.width if bounds.width > 0 else 0
                    zoom_y = target_pixel_height / bounds.height if bounds.height > 0 else 0
                    zoom = min(zoom_x, zoom_y)
                    
                    matrix = pymupdf.Matrix(zoom, zoom)
                    pix = source_page.get_pixmap(matrix=matrix, alpha=False, annots=True)
                    
                    # 기존 페이지 삭제
                    current_doc.delete_pages([page_num])
                    
                    # 새 페이지 생성 및 이미지 삽입
                    new_page = current_doc.new_page(page_num, width=a4_rect.width, height=a4_rect.height)
                    
                    margin = 0.98
                    page_rect = new_page.rect
                    margin_x = page_rect.width * (1 - margin) / 2
                    margin_y = page_rect.height * (1 - margin) / 2
                    target_rect = page_rect + (margin_x, margin_y, -margin_x, -margin_y)
                    
                    new_page.insert_image(target_rect, pixmap=pix)
                    
                    # 변경사항 저장
                    self.pdf_bytes = current_doc.tobytes(garbage=4, deflate=True)
            
            # 내부 문서 객체 갱신
            if self.doc:
                self.doc.close()
            
            self.doc = pymupdf.open(stream=self.pdf_bytes, filetype="pdf")
            self.page_count = self.doc.page_count
            
            print(f"페이지 교체 완료: 페이지 {page_num + 1}을 원본 페이지 {source_page_num + 1}로 교체했습니다.")
        
        except Exception as e:
            traceback.print_exc()
            raise ValueError(f"페이지 교체 중 오류 발생: {e}")