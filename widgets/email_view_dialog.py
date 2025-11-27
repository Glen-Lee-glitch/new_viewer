from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout


class EmailViewDialog(QDialog):
    """이메일 내용 확인 다이얼로그"""
    
    def __init__(self, title: str = "", content: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("이메일 확인")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout(self)
        
        # 제목 레이블
        title_label = QLabel("제목:")
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)
        
        title_text = QLabel(title)
        title_text.setWordWrap(True)
        title_text.setStyleSheet("padding: 5px; background-color: #f0f0f0; border: 1px solid #ccc;")
        layout.addWidget(title_text)
        
        # 내용 레이블
        content_label = QLabel("내용:")
        content_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(content_label)
        
        # 내용 텍스트 에디터 (읽기 전용)
        content_text = QTextEdit()
        content_text.setPlainText(content)
        content_text.setReadOnly(True)
        content_text.setStyleSheet("padding: 5px; border: 1px solid #ccc;")
        layout.addWidget(content_text)
        
        # 닫기 버튼
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

