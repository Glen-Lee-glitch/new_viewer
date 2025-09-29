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

        # --- 초기 할 일 목록 설정 ---
        self._setup_todo_items()

        # --- 시그널 연결 ---
        self.todoListWidget.itemChanged.connect(self._on_item_changed)

    def _setup_todo_items(self):
        """샘플 할 일 목록을 생성하고 체크박스를 설정한다."""
        todos = [
            "단축키(~)로 오버레이 표시/숨김 기능 구현",
            "PDF 페이지 회전 기능 테스트",
            "스탬프 기능 안정성 확인",
            "일괄 처리 기능 오류 리포트 검토",
            "UI/UX 개선사항 아이디어 회의"
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
