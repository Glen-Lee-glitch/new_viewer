from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, 
    QVBoxLayout, 
    QHBoxLayout,
    QGroupBox, 
    QRadioButton,
    QPushButton,
    QDialogButtonBox
)


class UnqualifiedDocumentDialog(QDialog):
    """서류미비 항목 선택 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("서류미비 항목 선택")
        self.setModal(True)
        
        # 20% 투명도 설정 (80% 불투명도)
        self.setWindowOpacity(0.8)
        
        self._init_ui()
        
    def _init_ui(self):
        """UI 초기화"""
        main_layout = QVBoxLayout(self)
        
        # 그룹박스 1
        group1 = QGroupBox("그룹 1")
        group1_layout = QVBoxLayout()
        self.radio1_1 = QRadioButton("임시1")
        self.radio1_2 = QRadioButton("임시2")
        group1_layout.addWidget(self.radio1_1)
        group1_layout.addWidget(self.radio1_2)
        group1.setLayout(group1_layout)
        
        # 그룹박스 2
        group2 = QGroupBox("그룹 2")
        group2_layout = QVBoxLayout()
        self.radio2_1 = QRadioButton("임시3")
        self.radio2_2 = QRadioButton("임시4")
        group2_layout.addWidget(self.radio2_1)
        group2_layout.addWidget(self.radio2_2)
        group2.setLayout(group2_layout)
        
        # 그룹박스 3
        group3 = QGroupBox("그룹 3")
        group3_layout = QVBoxLayout()
        self.radio3_1 = QRadioButton("임시5")
        self.radio3_2 = QRadioButton("임시6")
        group3_layout.addWidget(self.radio3_1)
        group3_layout.addWidget(self.radio3_2)
        group3.setLayout(group3_layout)
        
        # 그룹박스들을 메인 레이아웃에 추가
        main_layout.addWidget(group1)
        main_layout.addWidget(group2)
        main_layout.addWidget(group3)
        
        # 버튼 박스 (OK, Cancel)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        self.setLayout(main_layout)
        
        # 최소 크기 설정
        self.setMinimumWidth(300)
    
    def get_selected_items(self) -> list[str]:
        """선택된 라디오버튼 항목들을 반환한다."""
        selected = []
        
        if self.radio1_1.isChecked():
            selected.append("임시1")
        elif self.radio1_2.isChecked():
            selected.append("임시2")
            
        if self.radio2_1.isChecked():
            selected.append("임시3")
        elif self.radio2_2.isChecked():
            selected.append("임시4")
            
        if self.radio3_1.isChecked():
            selected.append("임시5")
        elif self.radio3_2.isChecked():
            selected.append("임시6")
        
        return selected

