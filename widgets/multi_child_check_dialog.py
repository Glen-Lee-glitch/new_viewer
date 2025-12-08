from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget, QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QPainter, QPalette
from datetime import datetime

# 하이라이트를 위한 커스텀 데이터 역할 정의
HighlightRole = Qt.ItemDataRole.UserRole + 1

class HighlightDelegate(QStyledItemDelegate):
    """특정 데이터 역할에 따라 배경색을 변경하는 델리게이트"""
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        highlight_color = index.data(HighlightRole)
        text_color = index.data(Qt.ItemDataRole.ForegroundRole)

        painter.save()
        
        if highlight_color:
            # 배경색을 직접 그리기 (qt_material 테마를 덮어쓰기 위함)
            painter.fillRect(option.rect, highlight_color)
            
            # 텍스트 색상 설정 (ItemDataRole.ForegroundRole에 설정된 색상 사용)
            if text_color:
                painter.setPen(text_color)

            # 기본 델리게이트가 배경을 다시 그리지 않도록 NoBrush 설정
            option.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)
            
        # 선택 상태일 때 기본 델리게이트의 선택 하이라이트가 적용되도록 super().paint 호출
        # 하지만 배경은 우리가 이미 그렸으므로, 기본 배경은 무시됨
        super().paint(painter, option, index)
        
        painter.restore()

class MultiChildCheckDialog(QDialog):
    def __init__(self, child_birth_dates: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자녀 생년월일 확인")
        self.setModal(True)
        self.resize(300, 400)
        
        self.child_birth_dates = child_birth_dates # 생년월일 데이터 저장
        
        layout = QVBoxLayout(self)
        
        # 안내 라벨
        label = QLabel("자녀 생년월일 목록 (만 19세 이상 포함됨)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        # 생년월일 목록 표시 및 하이라이트
        self.list_widget = QListWidget()
        self.list_widget.setItemDelegate(HighlightDelegate(self.list_widget)) # Delegate 적용
        
        today = datetime.now().date()

        for date_str in self.child_birth_dates:
            item = QListWidgetItem(date_str)
            try:
                # 문자열 형식에 따라 파싱
                if len(date_str) > 10: # YYYY-MM-DD HH:MM:SS 등
                    date_str = date_str.split()[0]

                birth_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                age = today.year - birth_date.year
                is_over_18 = False

                if age > 19:
                    is_over_18 = True
                elif age == 19:
                    if (today.month, today.day) >= (birth_date.month, birth_date.day):
                        is_over_18 = True

                if is_over_18:
                    # HighlightDelegate를 통해 배경색 적용
                    item.setData(HighlightRole, QColor(220, 53, 69, 180)) # 빨간색 계열
                    item.setData(Qt.ItemDataRole.ForegroundRole, QColor(255, 255, 255)) # 흰색 글씨
            except (ValueError, TypeError):
                pass
            self.list_widget.addItem(item)
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
