from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidgetItem, QWidget

from core.pdf_render import PdfRender

class ThumbnailViewWidget(QWidget):
    """썸네일 뷰어 위젯"""
    page_selected = pyqtSignal(int)  # 페이지 번호를 전달하는 시그널
    page_change_requested = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.renderer: PdfRender | None = None
        self.init_ui()
        self.setup_connections()
        
        # thumbnail_list_widget에 이벤트 필터 설치
        if hasattr(self, 'thumbnail_list_widget'):
            self.thumbnail_list_widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """이벤트 필터. thumbnail_list_widget의 키 이벤트를 가로챈다."""
        if watched == self.thumbnail_list_widget and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Q:
                self.page_change_requested.emit(-1)
                return True  # 이벤트가 처리되었음을 알림
            elif event.key() == Qt.Key.Key_E:
                self.page_change_requested.emit(1)
                return True  # 이벤트가 처리되었음을 알림
        
        # 처리하지 않은 이벤트는 기본 로직으로 전달
        return super().eventFilter(watched, event)

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
