from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect, QPoint

class MailContentOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._content = ""
        self._position = QPoint(20, 60)
        
        # 투명 배경 설정
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        # 마우스 이벤트 투과 (중요!)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.hide()
    
    def set_content(self, content: str):
        """메일 content를 설정"""
        self._content = content
        self.update()  # 다시 그리기
    
    def show_overlay(self, parent_size):
        """오버레이를 전체 영역에 표시"""
        self.setGeometry(0, 0, parent_size.width(), parent_size.height())
        self.show()
        self.raise_()
    
    def paintEvent(self, event):
        """오버레이를 직접 그리기"""
        if not self._content:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 텍스트 높이를 동적으로 계산
        text_rect = QRect(self._position.x() + 15, self._position.y() + 15, 300, 0)  # 370 = 텍스트 너비
        text_rect = painter.boundingRect(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
            self._content
        )
        
        # 실제 텍스트 높이에 여백 추가
        overlay_height = text_rect.height() + 30  # 상하 여백 15px씩
        overlay_rect = QRect(self._position.x(), self._position.y(), 310, overlay_height)  # 400 = 박스 전체 너비
        
        # 배경 그리기 (흰색, 180 알파 = 약 70% 불투명, 참고 코드와 동일)
        painter.setBrush(QColor(255, 255, 255, 190))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(overlay_rect, 8, 8)
        
        # 테두리 그리기
        painter.setPen(QColor(38, 166, 154, 255))  # #26A69A
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(overlay_rect, 8, 8)
        
        # 텍스트 그리기
        painter.setPen(QColor(0, 0, 0, 200))
        painter.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))  # 10 → 9
        painter.drawText(
            QRect(self._position.x() + 15, self._position.y() + 15, 370, overlay_height - 30),
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
            self._content
        )