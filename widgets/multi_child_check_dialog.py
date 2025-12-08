from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget
from PyQt6.QtCore import Qt
import json

class MultiChildCheckDialog(QDialog):
    def __init__(self, child_birth_dates: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자녀 생년월일 확인")
        self.setModal(True)
        self.resize(300, 400)
        
        layout = QVBoxLayout(self)
        
        # 안내 라벨
        label = QLabel("자녀 생년월일 목록 (만 19세 이상 포함됨)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        # 생년월일 목록 표시
        self.list_widget = QListWidget()
        self.list_widget.addItems(child_birth_dates)
        layout.addWidget(self.list_widget)
        
        # 버튼 영역
        button_layout = QHBoxLayout()
        
        self.btn_no_problem = QPushButton("문제없음")
        self.btn_not_multichild = QPushButton("다자녀 아님")
        
        # 현재는 둘 다 창 닫기 기능만 수행
        self.btn_no_problem.clicked.connect(self.accept)
        self.btn_not_multichild.clicked.connect(self.accept)
        
        button_layout.addWidget(self.btn_no_problem)
        button_layout.addWidget(self.btn_not_multichild)
        
        layout.addLayout(button_layout)
