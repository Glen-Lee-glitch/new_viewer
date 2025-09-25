import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget)
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from .pdf_load_widget import PdfLoadWidget
from .pdf_view_widget import PdfViewWidget
from .stamp_overlay_widget import StampOverlayWidget
from .thumbnail_view_widget import ThumbnailViewWidget


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.renderer = PdfRender()
        self._current_page = -1
        self.init_ui()
        self.stamp_overlay = StampOverlayWidget(self)
        self.setup_connections()
    
    def init_ui(self):
        """메인 윈도우 UI 초기화"""
        self.setWindowTitle("PDF Viewer")
        self.setGeometry(100, 100, 1400, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        self.thumbnail_widget = ThumbnailViewWidget()
        self.pdf_load_widget = PdfLoadWidget()
        self.pdf_view_widget = PdfViewWidget()

        self.main_content_stack = QStackedWidget()
        self.main_content_stack.addWidget(self.pdf_load_widget)
        self.main_content_stack.addWidget(self.pdf_view_widget)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.thumbnail_widget)
        main_splitter.addWidget(self.main_content_stack)
        main_splitter.setSizes([200, 1200])
        
        layout = QHBoxLayout(central_widget)
        layout.addWidget(main_splitter)

    def setup_connections(self):
        """시그널-슬롯 연결"""
        self.pdf_load_widget.pdf_selected.connect(self.load_document)
        self.thumbnail_widget.page_selected.connect(self.go_to_page)
        self.thumbnail_widget.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_change_requested.connect(self.change_page)
        if hasattr(self.pdf_view_widget, 'toolbar'):
            self.pdf_view_widget.toolbar.stamp_menu_requested.connect(self.show_stamp_overlay)
    
    def load_document(self, pdf_path: str):
        """PDF 문서를 로드하고 뷰를 전환한다."""
        try:
            self.renderer.close()
            self.renderer.load_pdf(pdf_path)
            self.setWindowTitle(f"PDF Viewer - {Path(pdf_path).name}")
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, "문서 로드 실패", str(e))
            self.renderer.close()
            self.setWindowTitle("PDF Viewer")
            return
        
        self.thumbnail_widget.set_renderer(self.renderer)
        self.pdf_view_widget.set_renderer(self.renderer)
        
        if self.renderer.get_page_count() > 0:
            self.go_to_page(0)

        self.main_content_stack.setCurrentWidget(self.pdf_view_widget)

    def go_to_page(self, page_num: int):
        """지정된 페이지로 이동한다."""
        if self.renderer and 0 <= page_num < self.renderer.get_page_count():
            self._current_page = page_num
            self.pdf_view_widget.show_page(page_num)
            self.thumbnail_widget.set_current_page(page_num)
    
    def change_page(self, delta: int):
        """현재 페이지에서 delta만큼 페이지를 이동한다."""
        if self._current_page != -1:
            new_page = self._current_page + delta
            self.go_to_page(new_page)

    def show_stamp_overlay(self):
        """스탬프 오버레이를 메인 윈도우 크기에 맞춰 표시한다."""
        self.stamp_overlay.show_overlay(self.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'stamp_overlay') and self.stamp_overlay.isVisible():
            self.stamp_overlay.setGeometry(0, 0, self.width(), self.height())

    def closeEvent(self, event):
        """애플리케이션 종료 시 PDF 문서 자원을 해제한다."""
        self.renderer.close()
        event.accept()

def create_app():
    """애플리케이션 생성 함수"""
    app = QApplication(sys.argv)
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception:
        pass
    window = MainWindow()
    return app, window
