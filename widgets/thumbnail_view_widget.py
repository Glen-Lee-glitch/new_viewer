from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidgetItem, QWidget, QListWidget, QMessageBox

from core.pdf_render import PdfRender
from core.edit_mixin import EditMixin

class ThumbnailViewWidget(QWidget):
    """썸네일 뷰어 위젯"""
    page_selected = pyqtSignal(int)  # 페이지 번호를 전달하는 시그널
    page_change_requested = pyqtSignal(int)
    page_order_changed = pyqtSignal(list) # 변경된 페이지 순서를 전달하는 새 시그널
    undo_requested = pyqtSignal()
    page_delete_requested = pyqtSignal(int) # '보이는' 페이지 번호로 삭제 요청
    
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
            if event.key() == Qt.Key.Key_Z and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.undo_requested.emit()
                return True
            elif event.key() == Qt.Key.Key_Delete:
                self._prompt_delete_selected_page()
                return True
            elif event.key() == Qt.Key.Key_Q:
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
        list_widget.setIconSize(list_widget.iconSize())
        list_widget.setSpacing(2)
        list_widget.setGridSize(list_widget.gridSize())
        
        # --- 드래그 앤 드롭 활성화 ---
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        list_widget.setMovement(QListWidget.Movement.Snap)
        
        # --- 모델의 데이터 변경 시그널 연결 ---
        list_widget.model().rowsMoved.connect(self._on_rows_moved)
    
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
                item = QListWidgetItem(icon, f"{i + 1}")
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.thumbnail_list_widget.addItem(item)
            except (IndexError, RuntimeError) as e:
                print(f"썸네일 생성 오류 (페이지 {i}): {e}")

    def on_thumbnail_clicked(self, item):
        """썸네일 클릭 시 호출"""
        # UserRole(실제 번호) 대신 리스트의 '보이는' 순서(row)를 전달
        row = self.thumbnail_list_widget.row(item)
        if row != -1:
            self.page_selected.emit(row)
    
    def _on_rows_moved(self):
        """드래그 앤 드롭으로 아이템 순서가 바뀌었을 때 호출"""
        new_order = []
        for i in range(self.thumbnail_list_widget.count()):
            item = self.thumbnail_list_widget.item(i)
            actual_page_num = item.data(Qt.ItemDataRole.UserRole)
            new_order.append(actual_page_num)
        
        self.page_order_changed.emit(new_order)

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

    def _prompt_delete_current_page(self):
        """현재 페이지를 삭제하는 메시지를 표시한다."""
        if self.current_page < 0:
            return
        
        reply = QMessageBox.question(
            self,
            '페이지 삭제 확인',
            f'현재 페이지 {self.current_page + 1}을(를) 삭제하시겠습니까?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.page_delete_requested.emit(self.current_page)
