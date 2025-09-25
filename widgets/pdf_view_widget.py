from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene,
                                QGraphicsView, QMessageBox, QWidget)

from core.pdf_render import PdfRender
from .floating_toolbar import FloatingToolbarWidget


class PdfViewWidget(QWidget):
    """PDF 뷰어 위젯"""
    page_change_requested = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.renderer: PdfRender | None = None
        self.scene = QGraphicsScene(self)
        self.current_page_item: QGraphicsPixmapItem | None = None
        self.init_ui()
        
        # --- 툴바 추가 ---
        self.toolbar = FloatingToolbarWidget(self)
        self.toolbar.show()

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
        """PDF 렌더러를 설정한다."""
        self.renderer = renderer
        self.scene.clear()
        self.current_page_item = None

    def show_page(self, page_num: int):
        """지정된 페이지를 뷰에 렌더링한다."""
        if not self.renderer:
            return

        try:
            pixmap = self.renderer.render_page(page_num, zoom_factor=2.0)
            if self.current_page_item:
                self.current_page_item.setPixmap(pixmap)
            else:
                self.current_page_item = self.scene.addPixmap(pixmap)
            
            self.pdf_graphics_view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        except (IndexError, RuntimeError) as e:
            QMessageBox.warning(self, "오류", f"페이지 {page_num + 1}을(를) 표시할 수 없습니다: {e}")
