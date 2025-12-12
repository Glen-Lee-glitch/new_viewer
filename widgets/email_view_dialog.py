from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QMessageBox


class EmailViewDialog(QDialog):
    """이메일 내용 확인 다이얼로그"""
    
    def __init__(self, title: str = "", content: str = "", original_worker: str = None, rn: str = None, parent=None):
        super().__init__(parent)
        self.rn = rn
        self.setWindowTitle("이메일 확인")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        # self.setStyleSheet("background-color: #ffffff;")  <-- 제거: 테마 색상 따름
        
        layout = QVBoxLayout(self)
        
        # 기존 작업자 표시 (있을 경우에만)
        if original_worker:
            worker_container = QHBoxLayout()
            worker_label = QLabel("기존 작업자:")
            # 빨간색 강조는 유지하되 배경색 관련 설정 제거
            worker_label.setStyleSheet("font-weight: bold; color: #ff5252;") 
            worker_value = QLabel(original_worker)
            worker_value.setStyleSheet("font-weight: bold; color: #ff5252; margin-left: 5px;")
            
            worker_container.addWidget(worker_label)
            worker_container.addWidget(worker_value)
            worker_container.addStretch()
            layout.addLayout(worker_container)
            
            # 구분선
            line = QLabel()
            line.setFixedHeight(1)
            # 테마에 맞는 구분선 색상 (반투명 흰색/검은색 사용 권장하나, 간단히 회색 사용)
            line.setStyleSheet("background-color: #808080; margin: 5px 0px;")
            layout.addWidget(line)
        
        # 제목 레이블
        title_label = QLabel("제목:")
        title_label.setStyleSheet("font-weight: bold;") # 색상 제거
        layout.addWidget(title_label)
        
        title_text = QLabel(title)
        title_text.setWordWrap(True)
        # 배경색/글자색 강제 설정 제거하고 테두리와 패딩만 유지 (테두리 색상도 테마에 맡기거나 조절)
        title_text.setStyleSheet("padding: 5px; border: 1px solid #808080; border-radius: 4px;")
        layout.addWidget(title_text)
        
        # 내용 레이블
        content_label = QLabel("내용:")
        content_label.setStyleSheet("font-weight: bold; margin-top: 10px;") # 색상 제거
        layout.addWidget(content_label)
        
        # 내용 텍스트 에디터 (읽기 전용)
        content_text = QTextEdit()
        content_text.setPlainText(content)
        content_text.setReadOnly(True)
        # 배경색/글자색 제거
        content_text.setStyleSheet("padding: 5px; border: 1px solid #808080; border-radius: 4px;")
        layout.addWidget(content_text)
        
        # 버튼 영역
        button_layout = QHBoxLayout()
        
        # 처리완료 버튼 (RN이 있을 때만 표시)
        if self.rn:
            complete_button = QPushButton("처리완료")
            complete_button.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50; 
                    color: white; 
                    font-weight: bold;
                    padding: 5px 15px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
            """)
            complete_button.clicked.connect(self._on_complete_clicked)
            button_layout.addWidget(complete_button)
        
        button_layout.addStretch()
        
        # 닫기 버튼
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.reject) # 닫기는 reject로 처리
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _on_complete_clicked(self):
        """처리완료 버튼 클릭 시"""
        if not self.rn:
            return
            
        from core.sql_manager import update_subsidy_status
        
        # 참조 코드와 동일한 방식으로 QMessageBox 사용
        reply = QMessageBox.question(
            self, 
            "확인", 
            "이 건을 '중복메일확인' 상태로 변경하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No  # 기본 버튼 설정
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if update_subsidy_status(self.rn, "중복메일확인"):
                QMessageBox.information(self, "알림", "처리가 완료되었습니다.")
                self.accept() # 성공 시 accept로 닫음 (부모 창에서 감지 가능)
            else:
                QMessageBox.critical(self, "오류", "상태 변경에 실패했습니다.")

