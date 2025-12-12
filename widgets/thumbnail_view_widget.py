from pathlib import Path
from typing import Union

from PyQt6 import uic
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidgetItem, QWidget, QListWidget, QApplication, QMenu

from core.pdf_render import PdfRender
from core.edit_mixin import EditMixin

class ThumbnailViewWidget(QWidget):
    """썸네일 뷰어 위젯"""
    page_selected = pyqtSignal(int)  # 페이지 번호를 전달하는 시그널
    page_change_requested = pyqtSignal(int)
    page_order_changed = pyqtSignal(list) # 변경된 페이지 순서를 전달하는 새 시그널
    undo_requested = pyqtSignal()
    page_delete_requested = pyqtSignal(object, dict) # '보이는' 페이지 번호(단일 int 또는 리스트)와 삭제 정보로 삭제 요청
    page_replace_with_original_requested = pyqtSignal(object) # '보이는' 페이지 번호(단일 int 또는 리스트)로 원본 페이지 교체 요청
    
    def __init__(self):
        super().__init__()
        self.renderer: PdfRender | None = None
        self._page_rotations: dict[int, int] = {}  # 페이지별 회전 정보 저장
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

    def _prompt_delete_selected_page(self):
        """선택된 페이지의 삭제 여부를 묻는 확인 창을 띄운다."""
        selected_items = self.thumbnail_list_widget.selectedItems()
        if not selected_items:
            return

        # 선택된 모든 페이지의 row 번호를 수집 (1부터 시작하는 시각적 번호)
        visual_page_nums = [self.thumbnail_list_widget.row(item) + 1 for item in selected_items]
        # row 번호는 0부터 시작하므로 +1을 해서 시각적 번호로 변환
        
        # 정렬하여 일관성 유지
        visual_page_nums.sort()
        
        # 공통 삭제 확인 함수 사용
        from core.delete_utils import prompt_page_delete
        
        # 단일 페이지인 경우 int로, 여러 페이지인 경우 리스트로 전달
        if len(visual_page_nums) == 1:
            page_input = visual_page_nums[0]
        else:
            page_input = visual_page_nums
        
        delete_result = prompt_page_delete(self, page_input)
        if delete_result and delete_result.get("confirmed"):
            # 삭제 정보 가져오기 (나중에 활용 예정)
            print(f"삭제 사유: {delete_result['reason']}")
            if delete_result['custom_text']:
                print(f"기타 사유: {delete_result['custom_text']}")
            
            # MainWindow에 선택된 '보이는' 페이지의 삭제를 요청한다.
            # 단일 페이지인 경우 int, 여러 페이지인 경우 리스트를 전달
            # row 번호(0부터 시작)로 변환
            if len(visual_page_nums) == 1:
                pages_to_delete = visual_page_nums[0] - 1  # 다시 0부터 시작하는 인덱스로
            else:
                pages_to_delete = [num - 1 for num in visual_page_nums]  # 0부터 시작하는 인덱스 리스트
            
            self.page_delete_requested.emit(pages_to_delete, delete_result)

    def _show_context_menu(self, position):
        """컨텍스트 메뉴를 표시한다."""
        # 클릭된 위치의 아이템 가져오기
        item = self.thumbnail_list_widget.itemAt(position)
        if not item:
            return  # 빈 공간을 클릭한 경우 메뉴 표시 안 함
        
        # 클릭된 아이템을 선택 상태로 만들기
        self.thumbnail_list_widget.setCurrentItem(item)
        
        # 컨텍스트 메뉴 생성
        context_menu = QMenu(self)
        
        # 페이지 삭제 액션 추가
        delete_action = context_menu.addAction("페이지 삭제")
        delete_action.triggered.connect(self._prompt_delete_selected_page)
        
        # 원본 액션 추가 (기능 미구현)
        original_action = context_menu.addAction("원본")
        original_action.triggered.connect(self._on_original_requested)
        
        # 메뉴를 글로벌 좌표로 표시
        global_position = self.thumbnail_list_widget.mapToGlobal(position)
        context_menu.exec(global_position)
    
    def _on_original_requested(self):
        """원본 메뉴 항목이 선택되었을 때 호출되는 메서드"""
        selected_items = self.thumbnail_list_widget.selectedItems()
        if not selected_items:
            return
        
        # 선택된 모든 페이지의 row 번호를 수집 (0부터 시작하는 인덱스)
        visual_page_nums = [self.thumbnail_list_widget.row(item) for item in selected_items]
        
        # 정렬하여 일관성 유지
        visual_page_nums.sort()
        
        # 단일 페이지인 경우 int로, 여러 페이지인 경우 리스트로 전달
        if len(visual_page_nums) == 1:
            page_input = visual_page_nums[0]
        else:
            page_input = visual_page_nums
        
        # MainWindow에 원본 페이지 교체 요청
        self.page_replace_with_original_requested.emit(page_input)

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
        
        # --- 컨텍스트 메뉴 설정 ---
        list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(self._show_context_menu)
        
        # --- 모델의 데이터 변경 시그널 연결 ---
        list_widget.model().rowsMoved.connect(self._on_rows_moved)
    
    def setup_connections(self):
        """시그널-슬롯 연결"""
        if hasattr(self, 'thumbnail_list_widget'):
            self.thumbnail_list_widget.itemClicked.connect(self.on_thumbnail_clicked)
    
    def set_renderer(self, renderer: PdfRender | None, page_order: list[int] | None = None, rotations: dict | None = None):
        """PDF 렌더러를 설정하고 썸네일을 생성한다. page_order가 있으면 그 순서대로 생성한다."""
        self.renderer = renderer
        self.thumbnail_list_widget.clear()
        
        # 회전 정보 저장
        if rotations:
            self._page_rotations = rotations.copy()
        else:
            self._page_rotations.clear()

        if not self.renderer or self.renderer.get_page_count() == 0:
            return

        # page_order가 없으면 기본 순서(0, 1, 2...) 사용
        if page_order is None:
            page_order = list(range(self.renderer.get_page_count()))

        # page_order 순서대로 썸네일 생성
        for visual_index, actual_page_num in enumerate(page_order):
            try:
                # 회전 각도 가져오기
                user_rotation = self._page_rotations.get(actual_page_num, 0)
                
                # 실제 페이지 번호로 썸네일 이미지 생성
                icon = self.renderer.create_thumbnail(actual_page_num, max_width=120, user_rotation=user_rotation)
                
                # 텍스트는 '보이는 순서' (1부터 시작)
                item = QListWidgetItem(icon, f"{visual_index + 1}")
                
                # UserRole에는 '실제 페이지 번호' 저장
                item.setData(Qt.ItemDataRole.UserRole, actual_page_num)
                
                self.thumbnail_list_widget.addItem(item)
            except (IndexError, RuntimeError) as e:
                print(f"썸네일 생성 오류 (실제 페이지 {actual_page_num}): {e}")

    def update_page_rotation(self, page_num: int, rotation: int):
        """특정 페이지의 회전 상태를 업데이트한다."""
        if not self.renderer:
            return
        
        # 회전 정보 저장
        self._page_rotations[page_num] = rotation
            
        for i in range(self.thumbnail_list_widget.count()):
            item = self.thumbnail_list_widget.item(i)
            actual_page_num = item.data(Qt.ItemDataRole.UserRole)
            
            if actual_page_num == page_num:
                try:
                    icon = self.renderer.create_thumbnail(page_num, max_width=120, user_rotation=rotation)
                    item.setIcon(icon)
                except Exception as e:
                    print(f"썸네일 회전 업데이트 오류 (페이지 {page_num}): {e}")
                break

    def update_page_thumbnail(self, page_num: int):
        """특정 페이지의 썸네일을 업데이트한다. (자르기 등으로 페이지가 변경된 경우)"""
        if not self.renderer:
            return
        
        # 저장된 회전 정보 가져오기
        user_rotation = self._page_rotations.get(page_num, 0)
        
        for i in range(self.thumbnail_list_widget.count()):
            item = self.thumbnail_list_widget.item(i)
            actual_page_num = item.data(Qt.ItemDataRole.UserRole)
            
            if actual_page_num == page_num:
                try:
                    # PDF 데이터가 변경되었으므로 새로운 썸네일 생성
                    icon = self.renderer.create_thumbnail(page_num, max_width=120, user_rotation=user_rotation)
                    item.setIcon(icon)
                except Exception as e:
                    print(f"썸네일 업데이트 오류 (페이지 {page_num}): {e}")
                break

    def on_thumbnail_clicked(self, item):
        """썸네일 클릭 시 호출"""
        # Ctrl/Shift 키가 눌린 상태(다중 선택 모드)인지 확인
        modifiers = QApplication.keyboardModifiers()
        is_multi_select_mode = (
            modifiers & Qt.KeyboardModifier.ControlModifier or 
            modifiers & Qt.KeyboardModifier.ShiftModifier
        )
        
        # 다중 선택 모드가 아닐 때만 page_selected 시그널을 emit
        # 다중 선택 모드일 때는 Qt의 기본 선택 로직만 작동하도록 함
        if not is_multi_select_mode:
            # UserRole(실제 번호) 대신 리스트의 '보이는' 순서(row)를 전달
            row = self.thumbnail_list_widget.row(item)
            if row != -1:
                self.page_selected.emit(row)
    
    def _on_rows_moved(self):
        """드래그 앤 드롭으로 아이템 순서가 바뀌었을 때 호출"""
        new_order = []
        for i in range(self.thumbnail_list_widget.count()):
            item = self.thumbnail_list_widget.item(i)
            
            # 아이템의 순서가 바뀌었으므로, 현재 위치(i)에 맞춰 번호를 다시 1부터 매깁니다.
            item.setText(str(i + 1))
            
            actual_page_num = item.data(Qt.ItemDataRole.UserRole)
            new_order.append(actual_page_num)
        
        self.page_order_changed.emit(new_order)

    def get_selected_visual_pages(self) -> list[int]:
        """선택된 페이지의 시각적 번호(1부터 시작)를 반환한다.
        
        Returns:
            list[int]: 선택된 페이지의 시각적 번호 리스트 (1부터 시작, 정렬됨)
        """
        if not hasattr(self, 'thumbnail_list_widget'):
            return []
        
        selected_items = self.thumbnail_list_widget.selectedItems()
        if not selected_items:
            return []
        
        # 선택된 모든 페이지의 row 번호를 수집 (1부터 시작하는 시각적 번호)
        visual_page_nums = [self.thumbnail_list_widget.row(item) + 1 for item in selected_items]
        visual_page_nums.sort()
        
        return visual_page_nums

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
