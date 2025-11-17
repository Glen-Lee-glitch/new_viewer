from typing import Union
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QLineEdit, QButtonGroup, QFrame
)


class PageDeleteDialog(QDialog):
    """페이지 삭제 확인 및 사유 선택 다이얼로그"""
    
    def __init__(self, page_number: Union[int, list[int]], parent=None):
        super().__init__(parent)
        # 단일 페이지 번호 또는 페이지 번호 리스트를 받을 수 있음
        if isinstance(page_number, int):
            self._page_numbers = [page_number]
            self._is_multiple = False
        else:
            self._page_numbers = sorted(page_number)  # 정렬된 복사본 저장
            self._is_multiple = len(page_number) > 1
        self._selected_reason = ""
        self._custom_text = ""
        self._setup_ui()
        
    def _setup_ui(self):
        """UI 구성"""
        self.setWindowTitle("페이지 삭제 확인")
        self.setModal(True)
        self.resize(400, 250)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # 확인 메시지 생성
        if self._is_multiple:
            # 여러 페이지인 경우: "N개의 페이지(2, 3, 5)를 정말로 삭제하시겠습니까?"
            page_count = len(self._page_numbers)
            page_list_str = ", ".join(str(p) for p in self._page_numbers)
            message_text = (
                f"{page_count}개의 페이지({page_list_str})를 정말로 삭제하시겠습니까?\n\n"
                "이 작업은 되돌릴 수 없습니다."
            )
        else:
            # 단일 페이지인 경우
            message_text = (
                f"{self._page_numbers[0]} 페이지를 정말로 삭제하시겠습니까?\n\n"
                "이 작업은 되돌릴 수 없습니다."
            )
        
        message_label = QLabel(message_text)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(message_label)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(line)
        
        # 삭제 사유 선택 섹션
        reason_label = QLabel("삭제 사유를 선택해주세요:")
        reason_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(reason_label)
        
        # 라디오 버튼 그룹
        self._button_group = QButtonGroup(self)
        
        # 삭제 사유 옵션들
        self._radio_additional = QRadioButton("추가 서류")
        self._radio_unnecessary = QRadioButton("필요 없음") 
        self._radio_other = QRadioButton("기타")
        
        # 기본 선택
        self._radio_unnecessary.setChecked(True)
        
        # 버튼 그룹에 추가
        self._button_group.addButton(self._radio_additional, 0)
        self._button_group.addButton(self._radio_unnecessary, 1)
        self._button_group.addButton(self._radio_other, 2)
        
        # 라디오 버튼들을 레이아웃에 추가
        main_layout.addWidget(self._radio_additional)
        main_layout.addWidget(self._radio_unnecessary)
        main_layout.addWidget(self._radio_other)
        
        # 기타 사유 입력 필드
        self._custom_input = QLineEdit()
        self._custom_input.setPlaceholderText("기타 사유를 입력해주세요...")
        self._custom_input.setEnabled(False)  # 초기에는 비활성화
        main_layout.addWidget(self._custom_input)
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self._cancel_button = QPushButton("취소")
        self._delete_button = QPushButton("삭제")
        self._delete_button.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; font-weight: bold; }")
        
        button_layout.addWidget(self._cancel_button)
        button_layout.addWidget(self._delete_button)
        
        main_layout.addLayout(button_layout)
        
        # 이벤트 연결
        self._setup_connections()
        
    def _setup_connections(self):
        """이벤트 연결"""
        # 라디오 버튼 상태 변경 시 텍스트 입력 필드 활성화/비활성화
        self._radio_other.toggled.connect(self._on_other_toggled)
        
        # 버튼 클릭 이벤트
        self._cancel_button.clicked.connect(self.reject)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        
    def _on_other_toggled(self, checked: bool):
        """'기타' 라디오 버튼 상태 변경 시 호출"""
        self._custom_input.setEnabled(checked)
        if checked:
            self._custom_input.setFocus()
        else:
            self._custom_input.clear()
    
    def _on_delete_clicked(self):
        """삭제 버튼 클릭 시 호출"""
        # 선택된 사유 저장
        if self._radio_additional.isChecked():
            self._selected_reason = "추가 서류(지방세, 환수동의서 등 -> 지급신청 시 사용)"
        elif self._radio_unnecessary.isChecked():
            self._selected_reason = "필요 없음(중복 서류 및 전혀 필요 없는 서류)"
        elif self._radio_other.isChecked():
            self._selected_reason = "기타(기타 사유를 입력해주세요)"
            self._custom_text = self._custom_input.text().strip()
            
            # 기타 선택 시 텍스트 입력 확인
            if not self._custom_text:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "입력 오류", "기타 사유를 입력해주세요.")
                self._custom_input.setFocus()
                return
        
        self.accept()
    
    def get_delete_info(self):
        """삭제 정보 반환"""
        return {
            "reason": self._selected_reason,
            "custom_text": self._custom_text if self._selected_reason == "기타" else ""
        }
