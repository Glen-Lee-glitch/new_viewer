from PyQt6.QtWidgets import QMessageBox, QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath

# To prevent dialogs from being garbage collected immediately
_active_alerts = []
_active_toasts = []  # 토스트 알림 목록


class Toast(QWidget):
    """화면 중앙 상단에 표시되는 토스트 알림 위젯"""
    
    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self._opacity = 1.0
        self._duration = 4000  # 4초 후 자동으로 사라짐
        
        # 프레임리스, 항상 위에 표시
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 레이아웃 설정
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(5)
        
        # 제목 라벨
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 13px;
                color: #fff;
            }
        """)
        layout.addWidget(title_label)
        
        # 메시지 라벨
        message_label = QLabel(message)
        message_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #e0e0e0;
            }
        """)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)
        
        # 최소 크기 설정
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        
        # 페이드 아웃 애니메이션 설정
        self._fade_animation = QPropertyAnimation(self, b"opacity")
        self._fade_animation.setDuration(300)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self.close)
        
        # 자동 닫기 타이머
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._start_fade_out)
    
    def paintEvent(self, event):
        """둥근 모서리와 배경을 그린다"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        
        # 배경색 (빨간색 계열 - 경고 알림)
        bg_color = QColor(220, 53, 69, 240)
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # 둥근 사각형 그리기
        rect = self.rect()
        path = QPainterPath()
        # QRect를 QRectF로 변환
        path.addRoundedRect(QRectF(rect), 8, 8)
        painter.drawPath(path)
    
    def showEvent(self, event):
        """표시될 때 위치를 설정하고 타이머를 시작한다"""
        super().showEvent(event)
        self._position_toast()
        self._close_timer.start(self._duration)
    
    def _position_toast(self):
        """화면 중앙 상단에 토스트를 배치한다 (여러 개일 경우 쌓임)"""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        
        geometry = screen.availableGeometry()
        margin = 20  # 화면 가장자리 여백
        spacing = 10  # 토스트 간 간격
        
        # 현재 활성 토스트 개수 계산 (자기 자신 제외)
        active_count = len([t for t in _active_toasts if t.isVisible() and t != self])
        
        # 중앙 상단 기준 위치 계산
        x = geometry.left() + (geometry.width() - self.width()) // 2
        y = geometry.top() + margin + (active_count * (self.height() + spacing))
        
        self.move(x, y)
    
    def _start_fade_out(self):
        """페이드 아웃 애니메이션을 시작한다"""
        self._fade_animation.start()
    
    @pyqtProperty(float)
    def opacity(self):
        return self._opacity
    
    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.update()


def show_alert(title: str, message: str, parent=None):
    """
    Shows a topmost, non-modal alert box.
    """
    global _active_alerts
    
    # parent를 None으로 설정하여 독립적인 윈도우로 만듦 (비모달 동작 보장)
    alert_box = QMessageBox(None)
    alert_box.setWindowTitle(title)
    alert_box.setText(message)
    alert_box.setIcon(QMessageBox.Icon.Warning)
    alert_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    
    # 명시적으로 비모달 설정
    alert_box.setWindowModality(Qt.WindowModality.NonModal)
    
    # Make the dialog stay on top
    alert_box.setWindowFlags(alert_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    
    # When the dialog is closed, remove it from the list
    alert_box.finished.connect(lambda: _active_alerts.remove(alert_box))
    
    # Add to the list to keep it alive
    _active_alerts.append(alert_box)
    
    # Flash the taskbar icon if a window is available
    if QApplication.activeWindow():
        QApplication.alert(QApplication.activeWindow())

    # Show non-modally
    alert_box.show()


def show_toast(title: str, message: str, parent=None):
    """
    화면 중앙 상단에 토스트 알림을 표시한다.
    
    Args:
        title: 알림 제목
        message: 알림 메시지
        parent: 부모 위젯 (사용하지 않지만 호환성을 위해 유지)
    """
    global _active_toasts
    
    toast = Toast(title, message, parent)
    
    # 닫힐 때 목록에서 제거
    def on_closed():
        if toast in _active_toasts:
            _active_toasts.remove(toast)
            # 남은 토스트들의 위치 재조정
            for remaining_toast in _active_toasts:
                if remaining_toast.isVisible():
                    remaining_toast._position_toast()
    
    toast.destroyed.connect(on_closed)
    
    _active_toasts.append(toast)
    toast.show()
