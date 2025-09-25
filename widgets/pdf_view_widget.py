from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import (QObject, QRunnable, Qt, QThreadPool, pyqtSignal)
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene,
                                 QGraphicsView, QMessageBox, QWidget)

import pymupdf
from core.edit_mixin import ViewModeMixin
from core.pdf_render import PdfRender

from .floating_toolbar import FloatingToolbarWidget
from .zoomable_graphics_view import ZoomableGraphicsView


# --- 백그라운드 렌더링을 위한 Worker ---
class WorkerSignals(QObject):
    """
    Worker 스레드에서 발생할 수 있는 시그널 정의
    - finished: 작업 완료 시 (페이지 번호, 렌더링된 QPixmap)
    - error: 오류 발생 시 (페이지 번호, 에러 메시지)
    """
    finished = pyqtSignal(int, QPixmap)
    error = pyqtSignal(int, str)


class PdfRenderWorker(QRunnable):
    """단일 PDF 페이지를 렌더링하는 Worker 스레드"""

    def __init__(self, pdf_path: str, page_num: int, zoom_factor: float = 3.0):
        super().__init__()
        self.pdf_path = pdf_path
        self.page_num = page_num
        self.zoom_factor = zoom_factor
        self.signals = WorkerSignals()

    def run(self):
        """백그라운드 스레드에서 렌더링 실행"""
        try:
            doc = pymupdf.open(self.pdf_path)
            if self.page_num < 0 or self.page_num >= len(doc):
                raise IndexError("페이지 번호가 범위를 벗어났습니다.")

            page = doc.load_page(self.page_num)
            mat = pymupdf.Matrix(self.zoom_factor, self.zoom_factor)
            pix = page.get_pixmap(matrix=mat, alpha=False, annots=True)

            image_format = QImage.Format.Format_RGB888 if not pix.alpha else QImage.Format.Format_RGBA8888
            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format).copy()
            pixmap = QPixmap.fromImage(qimage)

            doc.close()
            self.signals.finished.emit(self.page_num, pixmap)

        except Exception as e:
            self.signals.error.emit(self.page_num, str(e))


class PdfViewWidget(QWidget, ViewModeMixin):
    """PDF 뷰어 위젯"""
    page_change_requested = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.renderer: PdfRender | None = None
        self.pdf_path: str | None = None
        self.scene = QGraphicsScene(self)
        self.current_page_item: QGraphicsPixmapItem | None = None
        
        # --- 비동기 처리 및 캐싱 설정 ---
        self.thread_pool = QThreadPool.globalInstance()
        self.page_cache = {}  # 페이지 캐시: {page_num: QPixmap}
        self.rendering_jobs = set()  # 현재 렌더링 중인 페이지 번호
        self.current_page = -1

        self.init_ui()

        # --- 툴바 추가 ---
        self.toolbar = FloatingToolbarWidget(self)
        self.toolbar.show()

        # --- 툴바 시그널 연결 ---
        self.toolbar.fit_to_width_requested.connect(self.set_fit_to_width)
        self.toolbar.fit_to_page_requested.connect(self.set_fit_to_page)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_view_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # Graphics View 설정
        if hasattr(self, 'pdf_graphics_view'):
            self.pdf_graphics_view.setScene(self.scene)
            self.setup_graphics_view()
    
    def setup_graphics_view(self):
        """Graphics View 초기 설정"""
        view = self.pdf_graphics_view
        view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform |
            QPainter.RenderHint.TextAntialiasing
        )
        view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    
    def resizeEvent(self, event):
        """뷰어 크기가 변경될 때 툴바 위치를 재조정한다."""
        super().resizeEvent(event)
        # 툴바를 상단 중앙에 배치 (가로 중앙, 세로 상단에서 10px)
        x = (self.width() - self.toolbar.width()) // 2
        y = 10
        self.toolbar.move(x, y)
    
    def keyPressEvent(self, event):
        """키보드 'Q', 'E'를 눌러 페이지를 변경한다."""
        if event.key() == Qt.Key.Key_Q:
            self.page_change_requested.emit(-1)
        elif event.key() == Qt.Key.Key_E:
            self.page_change_requested.emit(1)
        else:
            super().keyPressEvent(event)

    def set_renderer(self, renderer: PdfRender | None):
        """PDF 렌더러를 설정하고 캐시를 초기화한다."""
        self.renderer = renderer
        self.pdf_path = renderer.pdf_path if renderer else None

        # 기존 상태 초기화
        self.scene.clear()
        self.current_page_item = None
        self.page_cache.clear()
        self.rendering_jobs.clear()
        self.current_page = -1

    def show_page(self, page_num: int):
        """지정된 페이지를 뷰에 표시한다. 캐시를 확인하고, 없으면 백그라운드 렌더링을 시작한다."""
        if not self.renderer or not self.pdf_path or page_num < 0 or page_num >= self.renderer.get_page_count():
            return

        self.current_page = page_num

        if page_num in self.page_cache:
            # 캐시에 있으면 바로 표시
            pixmap = self.page_cache[page_num]
            self._display_pixmap(pixmap)
        else:
            # 캐시에 없으면 로딩 메시지 표시 후 렌더링 시작
            self._show_loading_message()
            self._start_render_job(page_num)

        # 인접 페이지 미리 렌더링
        self._pre_render_adjacent_pages(page_num)

    def _start_render_job(self, page_num: int):
        """지정된 페이지의 백그라운드 렌더링 작업을 시작한다."""
        if (not self.renderer or not self.pdf_path or
                page_num < 0 or page_num >= self.renderer.get_page_count()):
            return
        if page_num in self.page_cache or page_num in self.rendering_jobs:
            return

        self.rendering_jobs.add(page_num)
        worker = PdfRenderWorker(self.pdf_path, page_num, zoom_factor=3.0)
        worker.signals.finished.connect(self._on_page_rendered)
        worker.signals.error.connect(self._on_render_error)
        self.thread_pool.start(worker)

    def _on_page_rendered(self, page_num: int, pixmap: QPixmap):
        """페이지 렌더링이 완료되었을 때 호출된다."""
        self.page_cache[page_num] = pixmap
        if page_num in self.rendering_jobs:
            self.rendering_jobs.remove(page_num)

        if page_num == self.current_page:
            self._display_pixmap(pixmap)

    def _on_render_error(self, page_num: int, error_msg: str):
        """페이지 렌더링 중 오류 발생 시 호출된다."""
        if page_num in self.rendering_jobs:
            self.rendering_jobs.remove(page_num)

        if page_num == self.current_page:
            self.scene.clear()
            QMessageBox.warning(self, "렌더링 오류", f"페이지 {page_num + 1}을(를) 표시하는 중 오류 발생: {error_msg}")

    def _display_pixmap(self, pixmap: QPixmap):
        """주어진 QPixmap을 씬에 표시한다."""
        self.scene.clear()
        self.current_page_item = self.scene.addPixmap(pixmap)
        # TODO: 현재 뷰 모드(fit_to_page, fit_to_width)에 맞게 스케일 조정 필요
        self.set_fit_to_page()  # 기본값

    def _show_loading_message(self):
        """로딩 중 메시지를 표시한다."""
        self.scene.clear()
        self.current_page_item = None
        # 나중에 더 예쁜 스피너 등으로 교체 가능
        self.scene.addText(f"페이지 {self.current_page + 1} 로딩 중...")

    def _pre_render_adjacent_pages(self, page_num: int):
        """현재 페이지의 이전/다음 페이지를 미리 렌더링한다."""
        self._start_render_job(page_num + 1)
        self._start_render_job(page_num - 1)
