import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QGridLayout, QPushButton, QTableWidget, QGraphicsView,
    QFileDialog, QMessageBox, QSplitter, QListWidget, QListWidgetItem,
    QGraphicsScene, QGraphicsPixmapItem, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QEvent, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QIcon
from PyQt6 import uic
from core.pdf_render import PdfRender
from qt_material import apply_stylesheet
from .pdf_view_widget import PdfViewWidget
from .thumbnail_view_widget import ThumbnailViewWidget
from .stamp_overlay_widget import StampOverlayWidget

class ZoomableGraphicsView(QGraphicsView):
    """Ctrl + 마우스 휠로 확대/축소가 가능한 QGraphicsView"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag) # 마우스로 끌어서 이동

    def wheelEvent(self, event):
        """마우스 휠 이벤트를 재정의하여 확대/축소 기능 구현"""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            zoom_in_factor = 1.15
            zoom_out_factor = 1 / zoom_in_factor

            if event.angleDelta().y() > 0:
                zoom_factor = zoom_in_factor
            else:
                zoom_factor = zoom_out_factor
            
            self.scale(zoom_factor, zoom_factor)
        else:
            # Ctrl 키가 눌리지 않으면 기본 스크롤 동작을 수행
            super().wheelEvent(event)

class PdfLoadWidget(QWidget):
    """PDF 로드 영역 위젯"""
    pdf_selected = pyqtSignal(str)  # PDF 파일 경로를 전달하는 시그널
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_load_area.ui"
        uic.loadUi(str(ui_path), self)
        
        # UI 요소들이 제대로 로드되었는지 확인
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.setText("로컬에서 PDF 열기")
        if hasattr(self, 'center_import_btn'):
            self.center_import_btn.setText("메일에서 가져오기")
            
        # 테이블 위젯 설정
        if hasattr(self, 'complement_table_widget'):
            self.setup_table()
    
    def setup_table(self):
        """테이블 위젯 초기 설정"""
        table = self.complement_table_widget
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(['RN', '지역', '임시칼럼1', '임시칼럼2'])
        table.setAlternatingRowColors(True)
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        if hasattr(self, 'center_open_btn'):
            self.center_open_btn.clicked.connect(self.open_pdf_file)
        if hasattr(self, 'center_import_btn'):
            self.center_import_btn.clicked.connect(self.import_from_email)
    
    def open_pdf_file(self):
        """로컬에서 PDF 파일 열기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDF 파일 선택",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        
        if file_path:
            self.pdf_selected.emit(file_path)
    
    def import_from_email(self):
        """메일에서 PDF 가져오기 (향후 구현)"""
        QMessageBox.information(self, "알림", "메일 가져오기 기능은 향후 구현 예정입니다.")

class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.renderer = PdfRender()
        self._current_page = -1
        self.init_ui()
        # 오버레이 위젯 생성
        self.stamp_overlay = StampOverlayWidget(self)
        self.setup_connections()
    
    def init_ui(self):
        """메인 윈도우 UI 초기화"""
        self.setWindowTitle("PDF Viewer")
        self.setGeometry(100, 100, 1400, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 1. 위젯 인스턴스 생성
        self.thumbnail_widget = ThumbnailViewWidget()
        self.pdf_load_widget = PdfLoadWidget()
        self.pdf_view_widget = PdfViewWidget()

        # 2. 컨텐츠 영역을 관리할 QStackedWidget 생성
        self.main_content_stack = QStackedWidget()
        self.main_content_stack.addWidget(self.pdf_load_widget)
        self.main_content_stack.addWidget(self.pdf_view_widget)

        # 3. 메인 스플리터를 2분할로 구성
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
        # 툴바 스탬프 버튼 → 오버레이 표시
        if hasattr(self.pdf_view_widget, 'toolbar'):
            self.pdf_view_widget.toolbar.stamp_menu_requested.connect(self.show_stamp_overlay)
    
    def load_document(self, pdf_path: str):
        """PDF 문서를 로드하고 뷰를 전환한다."""
        try:
            self.renderer.close() # 이전 문서가 있다면 닫기
            self.renderer.load_pdf(pdf_path)
            self.setWindowTitle(f"PDF Viewer - {Path(pdf_path).name}")
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, "문서 로드 실패", str(e))
            self.renderer.close()
            self.setWindowTitle("PDF Viewer")
            return
        
        # 렌더러를 자식 위젯에 전달
        self.thumbnail_widget.set_renderer(self.renderer)
        self.pdf_view_widget.set_renderer(self.renderer)
        
        if self.renderer.get_page_count() > 0:
            self.go_to_page(0)

        # PDF 뷰어 화면으로 전환
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
        # 윈도우 리사이즈 시 오버레이도 동일 크기로 유지
        if hasattr(self, 'stamp_overlay') and self.stamp_overlay.isVisible():
            self.stamp_overlay.setGeometry(0, 0, self.width(), self.height())

    def closeEvent(self, event):
        """애플리케이션 종료 시 PDF 문서 자원을 해제한다."""
        self.renderer.close()
        event.accept()

def create_app():
    """애플리케이션 생성 함수"""
    app = QApplication(sys.argv)
    # qt_material 전역 테마 적용
    try:
        apply_stylesheet(app, theme='dark_teal.xml')
    except Exception:
        # 테마 적용 실패 시에도 앱은 동작하도록 무시
        pass
    window = MainWindow()
    return app, window
