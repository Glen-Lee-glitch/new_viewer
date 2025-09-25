import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar)
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from widgets.floating_toolbar import PdfSaveWorker
from .pdf_load_widget import PdfLoadWidget
from .pdf_view_widget import PdfViewWidget
from .thumbnail_view_widget import ThumbnailViewWidget


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.renderer = PdfRender()
        self._current_page = -1
        self.init_ui()
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

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.thumbnail_widget)
        self.main_splitter.addWidget(self.main_content_stack)
        
        # 초기 분할기 크기 설정 (세로 페이지 기준)
        self.set_splitter_sizes(is_landscape=False)
        
        layout = QHBoxLayout(central_widget)
        layout.addWidget(self.main_splitter)

        self.setStatusBar(QStatusBar(self))

    def setup_connections(self):
        """시그널-슬롯 연결"""
        self.pdf_load_widget.pdf_selected.connect(self.load_document)
        self.thumbnail_widget.page_selected.connect(self.go_to_page)
        self.thumbnail_widget.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_aspect_ratio_changed.connect(self.adjust_viewer_layout)
        
        # 툴바의 저장 요청 시그널 연결
        self.pdf_view_widget.toolbar.save_pdf_requested.connect(self._request_save_pdf)
    
    def adjust_viewer_layout(self, is_landscape: bool):
        """페이지 비율에 따라 뷰어 레이아웃을 조정한다."""
        self.set_splitter_sizes(is_landscape)

    def set_splitter_sizes(self, is_landscape: bool):
        """가로/세로 모드에 따라 QSplitter의 크기를 설정한다."""
        if is_landscape:
            # 가로 페이지: 뷰어 85%, 썸네일 15%
            self.main_splitter.setSizes([int(self.width() * 0.15), int(self.width() * 0.85)])
        else:
            # 세로 페이지: 뷰어 75%, 썸네일 25% (기존과 유사)
            self.main_splitter.setSizes([int(self.width() * 0.25), int(self.width() * 0.75)])
    
    def resizeEvent(self, event):
        """창 크기가 변경될 때 분할기 크기를 재조정한다."""
        super().resizeEvent(event)
        # 현재 페이지의 비율에 맞는 분할기 크기를 다시 적용
        if self.pdf_view_widget.current_page_item:
            pixmap = self.pdf_view_widget.current_page_item.pixmap()
            is_landscape = pixmap.width() > pixmap.height()
            self.set_splitter_sizes(is_landscape)
        else:
            # 문서가 로드되지 않았을 때는 기본값(세로) 적용
            self.set_splitter_sizes(is_landscape=False)

    def _request_save_pdf(self):
        """PDF 저장 요청을 처리한다."""
        current_path = self.pdf_view_widget.get_current_pdf_path()
        if not current_path:
            self.statusBar().showMessage("저장할 PDF 파일이 열려있지 않습니다.", 5000)
            return
        
        self._start_save_process(current_path)

    def _start_save_process(self, input_path: str):
        """파일 대화상자를 열고 저장 프로세스를 시작한다."""
        # 제안된 파일명 생성 (원본 파일명 + _compressed)
        original_path = Path(input_path)
        suggested_filename = f"{original_path.stem}_compressed.pdf"
        
        # 'test' 폴더 경로 설정
        test_dir = Path(__file__).parent.parent / "test"
        test_dir.mkdir(exist_ok=True) # 폴더가 없으면 생성
        
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "압축하여 다른 이름으로 저장",
            str(test_dir / suggested_filename),
            "PDF Files (*.pdf)"
        )

        if not save_path:
            self.statusBar().showMessage("저장이 취소되었습니다.", 3000)
            return

        self.statusBar().showMessage(f"'{Path(save_path).name}' 파일 저장 중...", 0)
        
        # 백그라운드에서 압축 및 저장 실행
        worker = PdfSaveWorker(input_path, save_path)
        worker.signals.finished.connect(self._on_save_finished)
        worker.signals.error.connect(self._on_save_error)
        self.pdf_view_widget.toolbar.thread_pool.start(worker)

    def _on_save_finished(self, output_path: str, success: bool):
        """저장 완료 시 호출될 슬롯"""
        if success:
            message = f"성공적으로 '{Path(output_path).name}'에 압축 저장되었습니다."
        else:
            message = f"'{Path(output_path).name}'에 원본 파일을 저장했습니다 (압축 실패)."
        
        self.statusBar().showMessage(message, 8000)
        QMessageBox.information(self, "저장 완료", message)

    def _on_save_error(self, error_msg: str):
        """저장 중 오류 발생 시 호출될 슬롯"""
        self.statusBar().showMessage(f"오류 발생: {error_msg}", 8000)
        QMessageBox.critical(self, "저장 오류", f"PDF 저장 중 오류가 발생했습니다:\n{error_msg}")

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
