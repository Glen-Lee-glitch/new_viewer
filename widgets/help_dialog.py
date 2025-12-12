from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog


class HelpDialog(QDialog):
    """도움말 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "help_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("도움말")
        self.setModal(False)
        
        # 리스트 위젯에 임시 아이템 추가
        self.listWidget.addItem("임시1")
        self.listWidget.addItem("임시2")
        self.listWidget.addItem("임시3")
        
        # Splitter 비율 설정 (col1:col2 = 2:8)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 8)
        
        # content_layout 비율 설정 (이미지:텍스트 = 7:3)
        self.content_layout.setStretch(0, 7)
        self.content_layout.setStretch(1, 3)
        
        # 리스트 아이템 선택 시그널 연결
        self.listWidget.currentItemChanged.connect(self._on_item_selected)
        
        # 초기 선택 시 내용 표시
        if self.listWidget.count() > 0:
            self.listWidget.setCurrentRow(0)
    
    def _on_item_selected(self, current, previous):
        """리스트 아이템이 선택되었을 때 호출되는 메서드"""
        if current is None:
            return
        
        # 임시 텍스트 업데이트
        self.text_label.setText("이건 임시 텍스트입니다.")

