import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QGridLayout, QPushButton, QTableWidget, QGraphicsView,
    QFileDialog, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter
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

class MainWindow(QMainWindow):
    """메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """메인 윈도우 UI 초기화"""
        self.setWindowTitle("PDF Viewer")
        self.setGeometry(100, 100, 1200, 800)
        
        # 중앙 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 스플리터로 좌우 분할
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # PDF 로드 영역 (왼쪽)
        self.pdf_load_widget = PdfLoadWidget()
        splitter.addWidget(self.pdf_load_widget)
        
        # PDF 뷰어 영역 (오른쪽)
        self.pdf_view_widget = PdfViewWidget()
        splitter.addWidget(self.pdf_view_widget)
        
        # 스플리터 비율 설정 (3:7 정도)
        splitter.setSizes([400, 800])
        
        # 메인 레이아웃
        layout = QHBoxLayout()
        layout.addWidget(splitter)
        central_widget.setLayout(layout)
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        self.pdf_load_widget.pdf_selected.connect(self.pdf_view_widget.load_pdf)

def create_app():
    """애플리케이션 생성 함수"""
    app = QApplication(sys.argv)
    window = MainWindow()
    return app, window
