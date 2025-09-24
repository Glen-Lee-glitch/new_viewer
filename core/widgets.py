import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QGridLayout, QPushButton, QTableWidget, QGraphicsView,
    QFileDialog, QMessageBox, QSplitter, QListWidget, QListWidgetItem,
    QGraphicsScene, QGraphicsPixmapItem, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QIcon
from PyQt6 import uic
from .pdf_render import PdfRender

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

class FloatingToolbarWidget(QWidget):
    """pdf_view_widget 위에 떠다니는 이동 가능한 툴바."""
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "floating_toolbar.ui"
        uic.loadUi(str(ui_path), self)
        
        # 창 테두리 없애기 (parent 위젯에 자연스럽게 떠있도록)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        self._is_dragging = False
        self._drag_start_position = None

    def mousePressEvent(self, event):
        # 'drag_handle_frame' 위에서 마우스를 눌렀는지 확인
        if self.drag_handle_frame.underMouse():
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True
                self._drag_start_position = event.globalPosition().toPoint() - self.pos()
                self.setCursor(Qt.CursorShape.SizeAllCursor) # 커서를 '+' 모양으로 변경
                event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor) # 커서를 원래대로 복원
            event.accept()

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

class ThumbnailViewWidget(QWidget):
    """썸네일 뷰어 위젯"""
    page_selected = pyqtSignal(int)  # 페이지 번호를 전달하는 시그널
    page_change_requested = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.renderer: PdfRender | None = None
        self.init_ui()
        self.setup_connections()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "thumbnail_viewer.ui"
        uic.loadUi(str(ui_path), self)
        
        # 리스트 위젯 설정
        if hasattr(self, 'thumbnail_list_widget'):
            self.setup_list_widget()
    
    def keyPressEvent(self, event):
        """키보드 'Q', 'E'를 눌러 페이지를 변경한다."""
        if event.key() == Qt.Key.Key_Q:
            self.page_change_requested.emit(-1)
        elif event.key() == Qt.Key.Key_E:
            self.page_change_requested.emit(1)
        else:
            super().keyPressEvent(event)

    def setup_list_widget(self):
        """리스트 위젯 초기 설정"""
        list_widget = self.thumbnail_list_widget
        list_widget.setIconSize(list_widget.iconSize())  # UI에서 설정한 크기 유지
        list_widget.setSpacing(2)
        list_widget.setGridSize(list_widget.gridSize())  # UI에서 설정한 그리드 크기 유지
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        if hasattr(self, 'thumbnail_list_widget'):
            self.thumbnail_list_widget.itemClicked.connect(self.on_thumbnail_clicked)
    
    def set_renderer(self, renderer: PdfRender | None):
        """PDF 렌더러를 설정하고 썸네일을 생성한다."""
        self.renderer = renderer
        self.thumbnail_list_widget.clear()

        if not self.renderer or self.renderer.get_page_count() == 0:
            return

        for i in range(self.renderer.get_page_count()):
            try:
                icon = self.renderer.create_thumbnail(i, max_width=120)
                item = QListWidgetItem(icon, f"페이지 {i + 1}")
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.thumbnail_list_widget.addItem(item)
            except (IndexError, RuntimeError) as e:
                print(f"썸네일 생성 오류 (페이지 {i}): {e}")

    def on_thumbnail_clicked(self, item):
        """썸네일 클릭 시 호출"""
        page_number = item.data(Qt.ItemDataRole.UserRole)
        if page_number is not None:
            self.page_selected.emit(page_number)
    
    def set_current_page(self, page_num: int):
        """지정된 페이지 번호에 해당하는 썸네일을 선택 상태로 만든다."""
        if hasattr(self, 'thumbnail_list_widget'):
            item = self.thumbnail_list_widget.item(page_num)
            if item:
                self.thumbnail_list_widget.setCurrentItem(item)

    def clear_thumbnails(self):
        """썸네일 목록 초기화"""
        if hasattr(self, 'thumbnail_list_widget'):
            self.thumbnail_list_widget.clear()

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

    def closeEvent(self, event):
        """애플리케이션 종료 시 PDF 문서 자원을 해제한다."""
        self.renderer.close()
        event.accept()

def create_app():
    """애플리케이션 생성 함수"""
    app = QApplication(sys.argv)
    window = MainWindow()
    return app, window
