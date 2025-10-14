from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from PyQt6.QtGui import QPixmap
import time
from pathlib import Path

from core.pdf_render import PdfRender
from core.pdf_saved import compress_pdf_with_multiple_stages


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


class BatchTestSignals(QObject):
    """PDF 일괄 테스트 Worker의 시그널 정의"""
    progress = pyqtSignal(str)
    error = pyqtSignal(str, str) # file_name, error_message
    finished = pyqtSignal()
    load_pdf = pyqtSignal(str) # UI에 PDF 로드를 요청하는 시그널
    # 도장 삽입 시나리오용 신호
    rotate_90_maybe = pyqtSignal()  # 10% 확률 회전은 슬롯에서 판단
    focus_page2_maybe = pyqtSignal()  # 50% 확률 2페이지 포커스는 슬롯에서 판단
    save_pdf = pyqtSignal(str)   # UI에 PDF 저장을 요청하는 시그널 (저장 경로 전달)

class PdfBatchTestWorker(QRunnable):
    """PDF 일괄 열기/저장 테스트를 수행하는 Worker"""
    def __init__(self):
        super().__init__()
        self.signals = BatchTestSignals()
        self.input_dir = r'C:\Users\HP\Desktop\files\테스트PDF'
        self.output_dir = r'C:\Users\HP\Desktop\files\결과'
        self._is_stopped = False

    def stop(self):
        """Worker를 중지시킨다."""
        self._is_stopped = True

    def run(self):
        input_path = Path(self.input_dir)
        output_path = Path(self.output_dir)

        if not input_path.is_dir():
            self.signals.error.emit("", f"입력 폴더를 찾을 수 없습니다: {self.input_dir}")
            return

        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.signals.error.emit("", f"출력 폴더를 생성하는 데 실패했습니다: {e}")
                return

        pdf_files = sorted(list(input_path.glob("*.pdf")))
        if not pdf_files:
            self.signals.error.emit("", f"테스트할 PDF 파일이 없습니다: {self.input_dir}")
            return
        
        # 파일 경로를 (원본, 저장될 경로) 튜플로 관리
        file_paths_to_process = [
            (str(p), str(output_path / f"{p.stem}_tested.pdf")) for p in pdf_files
        ]

        self.signals.progress.emit(f"총 {len(file_paths_to_process)}개의 PDF 파일 테스트 시작...")
        time.sleep(1)

        for input_file, output_file in file_paths_to_process:
            if self._is_stopped: return

            try:
                # 1. UI에 PDF 로드 요청
                self.signals.progress.emit(f"'{Path(input_file).name}' 로드 중...")
                self.signals.load_pdf.emit(input_file)
                
                # 2. 2초 대기
                time.sleep(2)
                if self._is_stopped: return

                # 3. 10% 확률 회전 요청 (실제 확률 판단은 슬롯에서 수행)
                self.signals.progress.emit("10% 확률로 첫 페이지 90도 회전 시도")
                self.signals.rotate_90_maybe.emit()
                time.sleep(2)
                if self._is_stopped: return

                # 4. 50% 확률로 2페이지 포커스 이동 (없으면 유지)
                self.signals.progress.emit("50% 확률로 2페이지 포커스 이동 시도")
                self.signals.focus_page2_maybe.emit()
                time.sleep(1)
                if self._is_stopped: return

                # 5. UI에 PDF 저장 요청 (저장 경로 전달)
                self.signals.progress.emit(f"'{Path(output_file).name}' 저장 요청...")
                self.signals.save_pdf.emit(output_file)
                
                # 6. 3초 대기
                time.sleep(3)

            except Exception as e:
                if not self._is_stopped:
                    self.signals.error.emit(Path(input_file).name, str(e))
                return # 오류 발생 시 즉시 중단
        
        if not self._is_stopped:
            self.signals.finished.emit()
