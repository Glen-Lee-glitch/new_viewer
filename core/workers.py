from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from PyQt6.QtGui import QPixmap

from pdf_render import PdfRender
from pdf_saved import compress_pdf_with_multiple_stages


class WorkerSignals(QObject):
    """
    Worker 스레드에서 발생할 수 있는 시그널 정의
    - finished: 렌더링 완료 시 (페이지 번호, 렌더링된 QPixmap)
    - error: 렌더링 오류 시 (페이지 번호, 에러 메시지)
    - save_finished: 저장 완료 시 (경로, 성공 여부)
    - save_error: 저장 오류 시 (에러 메시지)
    """
    finished = pyqtSignal(int, QPixmap)
    error = pyqtSignal(int, str)
    save_finished = pyqtSignal(str, bool)
    save_error = pyqtSignal(str)

class PdfRenderWorker(QRunnable):
    """단일 PDF 페이지를 렌더링하는 Worker 스레드"""

    def __init__(self, pdf_bytes: bytes, page_num: int, zoom_factor: float = 2.0, user_rotation: int = 0):
        super().__init__()
        self.pdf_bytes = pdf_bytes
        self.page_num = page_num
        self.zoom_factor = zoom_factor
        self.user_rotation = user_rotation
        self.signals = WorkerSignals()

    @staticmethod
    def _is_a4_size(width_cm: float, height_cm: float, tolerance: float = 2.0) -> bool:
        """페이지가 A4 크기 범위 내인지 확인한다."""
        a4_width, a4_height = 21.0, 29.7
        vertical_match = (abs(width_cm - a4_width) <= tolerance and
                         abs(height_cm - a4_height) <= tolerance)
        horizontal_match = (abs(width_cm - a4_height) <= tolerance and
                           abs(height_cm - a4_width) <= tolerance)
        return vertical_match or horizontal_match

    def run(self):
        """백그라운드 스레드에서 렌더링 실행. 핵심 로직은 PdfRender 클래스에 위임."""
        try:
            # PdfRender의 스레드 안전 메서드를 호출 (A4 변환된 바이트 데이터 사용)
            pixmap = PdfRender.render_page_thread_safe(
                self.pdf_bytes, self.page_num, self.zoom_factor, self.user_rotation
            )
            self.signals.finished.emit(self.page_num, pixmap)

        except Exception as e:
            self.signals.error.emit(self.page_num, str(e))

class PdfSaveWorker(QRunnable):
    """QThreadPool에서 PDF 압축 및 저장을 실행하기 위한 Worker"""

    def __init__(self, input_bytes: bytes, output_path: str,
                 rotations: dict | None = None,
                 stamp_data: dict[int, list[dict]] | None = None,
                 page_order: list[int] | None = None):
        super().__init__()
        self.signals = WorkerSignals()
        self.input_bytes = input_bytes
        self.output_path = output_path
        self.rotations = rotations if rotations is not None else {}
        self.stamp_data = stamp_data if stamp_data is not None else {}
        self.page_order = page_order

    def run(self):
        """백그라운드 스레드에서 PDF 저장 및 압축 실행."""
        try:
            success = compress_pdf_with_multiple_stages(
                input_bytes=self.input_bytes,
                output_path=self.output_path,
                target_size_mb=3,
                rotations=self.rotations,
                stamp_data=self.stamp_data,
                page_order=self.page_order
            )
            self.signals.save_finished.emit(self.output_path, success)
        except Exception as e:
            self.signals.save_error.emit(str(e))
