from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QListWidgetItem


class ToDoWidget(QWidget):
    """'할 일 목록' 오버레이 위젯"""
    def __init__(self, parent=None):
        super().__init__(parent)

        # --- UI 파일 로드 ---
        ui_path = Path(__file__).parent.parent / "ui" / "to_do_widget.ui"
        uic.loadUi(ui_path, self)

        # --- 오버레이를 위한 윈도우 플래그 설정 ---
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |       # 프레임 없음
            Qt.WindowType.Tool |                      # 툴팁처럼 동작 (작업표시줄에 안나타남)
            Qt.WindowType.WindowStaysOnTopHint        # 항상 위에 표시
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # 배경 투명
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating) # 활성화 없이 표시

        # --- 스타일시트 강제 적용 ---
        # qt_material 테마의 스타일을 덮어쓰기 위해 코드에서 직접 스타일을 설정합니다.
        self.todoListWidget.setStyleSheet("""
            QListWidget::item {
                color: black;
            }
            QListWidget::item:selected {
                color: white; /* 선택 시에는 흰색 유지 */
            }

            /* 테마에 의해 숨겨진 체크박스를 다시 보이도록 스타일을 강제 적용합니다. */
            QListWidget::indicator {
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid #999;
                background-color: white;
                margin-right: 5px; /* 텍스트와 간격을 줍니다 */
            }

            /* 체크되었을 때의 스타일 */
            QListWidget::indicator:checked {
                background-color: #0078d7;
                border-color: #005a9e;
            }
            
            /* 마우스를 올렸을 때의 스타일 */
            QListWidget::indicator:hover {
                border: 1px solid #0078d7;
            }
        """)

        # --- 초기 할 일 목록 설정 ---
        self._setup_todo_items()

        # --- 시그널 연결 ---
        self.todoListWidget.itemChanged.connect(self._on_item_changed)

    def _setup_todo_items(self):
        """샘플 할 일 목록을 생성하고 체크박스를 설정한다."""
        todos = [
            "지원신청서 서명",
            "지원신청서 차종",
            "지원신청서 보조금 금액",
            "(공동명의 시)구매계약서 고객명 대표자명 일치",
            "(공동명의 시)구매계약서 대표자/공동명의자 서명 전부 존재"
        ]

        for item_text in todos:
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.todoListWidget.addItem(item)

    def _on_item_changed(self, item: QListWidgetItem):
        """리스트 아이템의 체크 상태가 변경될 때 호출된다."""
        font = item.font()
        if item.checkState() == Qt.CheckState.Checked:
            font.setStrikeOut(True)
        else:
            font.setStrikeOut(False)
        item.setFont(font)

    def toggle_overlay(self):
        """오버레이를 보이거나 숨긴다."""
        if self.isVisible():
            self.hide()
        else:
            if self.parent():
                # 부모 위젯의 중앙에 표시
                parent_rect = self.parent().geometry()
                self_rect = self.geometry()
                # 절대 좌표계 기준으로 부모의 중앙 위치 계산
                center_point = self.parent().mapToGlobal(parent_rect.center())
                new_x = center_point.x() - self_rect.width() // 2
                new_y = center_point.y() - self_rect.height() // 2
                self.move(new_x, new_y)
            self.show()
