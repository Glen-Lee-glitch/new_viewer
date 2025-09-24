import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QGridLayout, QPushButton, QTableWidget, QGraphicsView,
    QFileDialog, QMessageBox, QSplitter, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QIcon
from PyQt6 import uic

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
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["파일명", "크기", "수정일"])
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
    
    def __init__(self):
        super().__init__()
        self.current_pdf_path = None
        self.init_ui()
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_view_widget.ui"
        uic.loadUi(str(ui_path), self)
        
        # Graphics View 설정
        if hasattr(self, 'pdf_graphics_view'):
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
    
    def load_pdf(self, pdf_path: str):
        """PDF 파일 로드"""
        self.current_pdf_path = pdf_path
        # 실제 PDF 로딩 로직은 향후 PyMuPDF를 사용해서 구현
        print(f"PDF 로드: {pdf_path}")
        
        # 임시로 메시지 표시
        QMessageBox.information(self, "PDF 로드", f"PDF 파일이 로드되었습니다:\n{Path(pdf_path).name}")

class ThumbnailViewWidget(QWidget):
    """썸네일 뷰어 위젯"""
    page_selected = pyqtSignal(int)  # 페이지 번호를 전달하는 시그널
    
    def __init__(self):
        super().__init__()
        self.current_pdf_path = None
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "thumbnail_viewer.ui"
        uic.loadUi(str(ui_path), self)
        
        # 리스트 위젯 설정
        if hasattr(self, 'thumbnail_list_widget'):
            self.setup_list_widget()
    
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
    
    def load_pdf_thumbnails(self, pdf_path: str):
        """PDF 파일의 썸네일들을 로드"""
        self.current_pdf_path = pdf_path
        
        # 기존 썸네일 제거
        if hasattr(self, 'thumbnail_list_widget'):
            self.thumbnail_list_widget.clear()
            
            # 임시로 더미 썸네일 추가 (실제로는 PyMuPDF로 생성)
            for i in range(5):  # 5페이지 가정
                item = QListWidgetItem(f"페이지 {i+1}")
                item.setData(Qt.ItemDataRole.UserRole, i)  # 페이지 번호 저장
                self.thumbnail_list_widget.addItem(item)
    
    def on_thumbnail_clicked(self, item):
        """썸네일 클릭 시 호출"""
        page_number = item.data(Qt.ItemDataRole.UserRole)
        if page_number is not None:
            self.page_selected.emit(page_number)
    
    def clear_thumbnails(self):
        """썸네일 목록 초기화"""
        if hasattr(self, 'thumbnail_list_widget'):
            self.thumbnail_list_widget.clear()

class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """메인 윈도우 UI 초기화"""
        self.setWindowTitle("PDF Viewer")
        self.setGeometry(100, 100, 1400, 800)
        
        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 스플리터로 3분할
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. 썸네일 뷰어 (왼쪽)
        self.thumbnail_widget = ThumbnailViewWidget()
        main_splitter.addWidget(self.thumbnail_widget)
        
        # 2. PDF 로드 영역 (중앙)
        self.pdf_load_widget = PdfLoadWidget()
        main_splitter.addWidget(self.pdf_load_widget)
        
        # 3. PDF 뷰어 영역 (오른쪽)
        self.pdf_view_widget = PdfViewWidget()
        main_splitter.addWidget(self.pdf_view_widget)
        
        # 스플리터 비율 설정 (1:2:4 정도 - 썸네일:로더:뷰어)
        main_splitter.setSizes([200, 400, 800])
        
        # 메인 레이아웃
        layout = QHBoxLayout()
        layout.addWidget(main_splitter)
        central_widget.setLayout(layout)
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        # PDF 파일 선택 시 뷰어와 썸네일 모두에 전달
        self.pdf_load_widget.pdf_selected.connect(self.pdf_view_widget.load_pdf)
        self.pdf_load_widget.pdf_selected.connect(self.thumbnail_widget.load_pdf_thumbnails)
        
        # 썸네일 클릭 시 PDF 뷰어의 해당 페이지로 이동
        self.thumbnail_widget.page_selected.connect(self.on_page_selected)
    
    def on_page_selected(self, page_number: int):
        """썸네일에서 페이지 선택 시 호출"""
        print(f"페이지 {page_number + 1} 선택됨")
        # 향후 PDF 뷰어에서 해당 페이지로 이동하는 기능 구현
        # self.pdf_view_widget.go_to_page(page_number)

def create_app():
    """애플리케이션 생성 함수"""
    app = QApplication(sys.argv)
    window = MainWindow()
    return app, window
