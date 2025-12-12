from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout


class EmailViewDialog(QDialog):
    """이메일 내용 확인 다이얼로그"""
    
    def __init__(self, title: str = "", content: str = "", original_worker: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이메일 확인")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.setStyleSheet("background-color: #ffffff;")
        
        layout = QVBoxLayout(self)
        
        # 기존 작업자 표시 (있을 경우에만)
        if original_worker:
            worker_container = QHBoxLayout()
            worker_label = QLabel("기존 작업자:")
            worker_label.setStyleSheet("font-weight: bold; color: #d32f2f;") # 빨간색 강조
            worker_value = QLabel(original_worker)
            worker_value.setStyleSheet("font-weight: bold; color: #d32f2f; margin-left: 5px;")
            
            worker_container.addWidget(worker_label)
            worker_container.addWidget(worker_value)
            worker_container.addStretch()
            layout.addLayout(worker_container)
            
            # 구분선
            line = QLabel()
            line.setFixedHeight(1)
            line.setStyleSheet("background-color: #ddd; margin: 5px 0px;")
            layout.addWidget(line)
        
        # 제목 레이블
        title_label = QLabel("제목:")
        title_label.setStyleSheet("font-weight: bold; color: #000000;")
        layout.addWidget(title_label)
        
        title_text = QLabel(title)
        title_text.setWordWrap(True)
        title_text.setStyleSheet("padding: 5px; background-color: #f0f0f0; border: 1px solid #ccc; color: #000000;")
        layout.addWidget(title_text)
        
        # 내용 레이블
        content_label = QLabel("내용:")
        content_label.setStyleSheet("font-weight: bold; margin-top: 10px; color: #000000;")
        layout.addWidget(content_label)
        
        # 내용 텍스트 에디터 (읽기 전용)
        content_text = QTextEdit()
        content_text.setPlainText(content)
        content_text.setReadOnly(True)
        content_text.setStyleSheet("padding: 5px; border: 1px solid #ccc; background-color: #ffffff; color: #000000;")
        layout.addWidget(content_text)
        
        # 닫기 버튼
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

