import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                             QMessageBox, QSplitter, QStackedWidget, QWidget, QFileDialog, QStatusBar,
                             QPushButton, QLabel)
from qt_material import apply_stylesheet

from core.pdf_render import PdfRender
from widgets.floating_toolbar import PdfSaveWorker
from widgets.pdf_load_widget import PdfLoadWidget
from widgets.pdf_view_widget import PdfViewWidget
from widgets.thumbnail_view_widget import ThumbnailViewWidget
from widgets.info_panel_widget import InfoPanelWidget


class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Viewer")
        self.setGeometry(100, 100, 1200, 800)

        self.renderer: PdfRender | None = None
        self.current_page = -1
        self.thread_pool = QThreadPool()
        
        # --- 위젯 인스턴스 생성 ---
        self.thumbnail_viewer = ThumbnailViewWidget()
        self.pdf_view_widget = PdfViewWidget()
        self.pdf_load_widget = PdfLoadWidget()
        self.info_panel = InfoPanelWidget()

        # --- 메인 레이아웃 설정 ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.pdf_load_widget)
        self.main_splitter.addWidget(self.pdf_view_widget)
        
        self.main_splitter.setSizes([600, 600])

        main_layout.addWidget(self.thumbnail_viewer, 1)
        main_layout.addWidget(self.main_splitter, 4)
        main_layout.addWidget(self.info_panel, 1)
        
        # --- 초기 위젯 상태 설정 ---
        self.pdf_view_widget.hide()
        self.thumbnail_viewer.hide()
        self.info_panel.hide()

        # --- 메뉴바 및 액션 설정 ---
        self._setup_menus()

        # --- 상태바 및 페이지 네비게이션 UI 설정 ---
        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)
        
        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        
        self.pushButton_prev = QPushButton("이전")
        self.pushButton_next = QPushButton("다음")
        self.label_page_nav = QLabel("N/A")
        
        nav_layout.addWidget(self.pushButton_prev)
        nav_layout.addWidget(self.label_page_nav)
        nav_layout.addWidget(self.pushButton_next)
        
        self.statusBar.addPermanentWidget(nav_widget)

        # --- 시그널 연결 ---
        self._setup_connections()

    def _setup_menus(self):
        """메뉴바를 설정합니다."""
        pass # 메뉴바 설정 로직 추가

    def _setup_connections(self):
        """애플리케이션의 모든 시그널-슬롯 연결을 설정한다."""
        self.pdf_load_widget.pdf_selected.connect(self.load_document)
        self.thumbnail_viewer.page_selected.connect(self.go_to_page)
        self.thumbnail_viewer.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_change_requested.connect(self.change_page)
        self.pdf_view_widget.page_aspect_ratio_changed.connect(self.set_splitter_sizes)
        
        # 툴바의 저장 요청 시그널 연결
        self.pdf_view_widget.toolbar.save_pdf_requested.connect(self._request_save_pdf)
        
        # 정보 패널 업데이트 연결
        self.pdf_view_widget.pdf_loaded.connect(self.info_panel.update_file_info)
        self.pdf_view_widget.page_info_updated.connect(self.info_panel.update_page_info)

        # 페이지 네비게이션 버튼 클릭 시그널 연결
        self.pushButton_prev.clicked.connect(lambda: self.change_page(-1))
        self.pushButton_next.clicked.connect(lambda: self.change_page(1))
        
        # PdfViewWidget의 내부 페이지 변경 요청 -> 실제 페이지 변경 로직 실행
        self.pdf_view_widget.page_change_requested.connect(self.change_page)

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
    
    def _update_page_navigation(self, current_page: int, total_pages: int):
        """페이지 네비게이션 상태(라벨, 버튼 활성화)를 업데이트한다."""
        if total_pages > 0:
            self.label_page_nav.setText(f"{current_page + 1} / {total_pages}")
        else:
            self.label_page_nav.setText("N/A")

        self.pushButton_prev.setEnabled(total_pages > 0 and current_page > 0)
        self.pushButton_next.setEnabled(total_pages > 0 and current_page < total_pages - 1)

    def _request_save_pdf(self):
        """PDF 저장 요청을 처리하고 파일 대화상자를 연다."""
        if not self.pdf_view_widget.get_current_pdf_path():
            self.statusBar.showMessage("저장할 PDF 파일이 열려있지 않습니다.", 5000)
            return
        
        self._start_save_process(self.pdf_view_widget.get_current_pdf_path())

    def _start_save_process(self, input_path: str):
        """실제 PDF 저장 프로세스를 시작한다."""
        # 파일 저장 경로 얻기
        default_filename = Path(input_path).stem + "_edited.pdf"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF 저장",
            default_filename,
            "PDF Files (*.pdf)"
        )

        if not save_path:
            self.statusBar.showMessage("저장이 취소되었습니다.", 3000)
            return

        self.statusBar.showMessage(f"'{Path(save_path).name}' 파일 저장 중...", 0)
        
        # 페이지별 회전 정보 가져오기
        rotations = self.pdf_view_widget.get_page_rotations()

        # 백그라운드에서 압축 및 저장 실행
        worker = PdfSaveWorker(input_path, save_path, rotations)
        worker.signals.finished.connect(self._on_save_finished)
        worker.signals.error.connect(lambda msg: self.statusBar.showMessage(f"저장 오류: {msg}", 5000))
        self.thread_pool.start(worker)

    def _on_save_finished(self, path, success):
        self.statusBar.clearMessage()
        """저장 완료 시 호출될 슬롯"""
        if success:
            message = f"성공적으로 '{Path(path).name}'에 압축 저장되었습니다."
        else:
            message = f"'{Path(path).name}'에 원본 파일을 저장했습니다 (압축 실패)."
        
        self.statusBar.showMessage(message, 8000)
        QMessageBox.information(self, "저장 완료", message)

    def _on_save_error(self, error_msg: str):
        """저장 중 오류 발생 시 호출될 슬롯"""
        self.statusBar.showMessage(f"오류 발생: {error_msg}", 8000)
        QMessageBox.critical(self, "저장 오류", f"PDF 저장 중 오류가 발생했습니다:\n{error_msg}")

    def load_document(self, pdf_path: str):
        """PDF 문서를 로드하고 뷰를 전환한다."""
        # 기존 문서가 열려있으면 자원을 해제한다.
        if self.renderer:
            self.renderer.close()

        try:
            self.renderer = PdfRender()
            self.renderer.load_pdf(pdf_path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 문서를 여는 데 실패했습니다: {e}")
            self.renderer = None
            return

        self.setWindowTitle(f"PDF Viewer - {Path(pdf_path).name}")
        
        self.thumbnail_viewer.set_renderer(self.renderer)
        self.pdf_view_widget.set_renderer(self.renderer)

        if self.renderer.get_page_count() > 0:
            self.go_to_page(0)

        self.pdf_load_widget.hide()
        self.pdf_view_widget.show()
        self.thumbnail_viewer.show()
        self.info_panel.show()
        
    def _on_pdf_closed(self):
        """PDF 파일이 닫혔을 때의 UI 상태를 처리한다."""
        self.setWindowTitle("PDF Viewer")
        self.renderer = None
        self.current_page = -1

        self.pdf_load_widget.show()
        self.thumbnail_viewer.clear()
        self.pdf_view_widget.hide()
        self.info_panel.clear_info()
        self.thumbnail_viewer.hide()
        self.info_panel.hide()
        self._update_page_navigation(0, 0)

    def go_to_page(self, page_num: int):
        """지정된 페이지 번호로 뷰를 이동시킨다."""
        if self.renderer and 0 <= page_num < self.renderer.get_page_count():
            self.current_page = page_num
            self.pdf_view_widget.show_page(page_num)
            self.thumbnail_viewer.set_current_page(page_num)
            self._update_page_navigation(self.current_page, self.renderer.get_page_count())
    
    def change_page(self, delta: int):
        """현재 페이지에서 delta만큼 페이지를 이동시킨다."""
        if self.renderer and self.current_page != -1:
            new_page = self.current_page + delta
            self.go_to_page(new_page)

    def closeEvent(self, event):
        """애플리케이션 종료 시 PDF 문서 자원을 해제한다."""
        if self.renderer:
            self.renderer.close()
        event.accept()

def create_app():
    """QApplication을 생성하고 메인 윈도우를 반환한다."""
    app = QApplication(sys.argv)
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception:
        pass
    window = MainWindow()
    return app, window
