from PyQt6.QtWidgets import QMessageBox, QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtProperty, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath

# To prevent dialogs from being garbage collected immediately
_active_alerts = []
_active_toasts = []  # 토스트 알림 목록


class Toast(QWidget):
    """화면 중앙 상단에 표시되는 토스트 알림 위젯"""
    
    def __init__(self, title: str, message: str, parent=None, recent_received_date=None, sticky: bool = False):
        super().__init__(parent)
        self._opacity = 1.0
        self._duration = 7000  # 7초 후 자동으로 사라짐
        self._recent_received_date = recent_received_date  # recent_received_date 저장
        self._sticky = sticky  # sticky 모드 저장
        
        # 프레임리스, 항상 위에 표시
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        self._last_active_hwnd = None  # 외부 윈도우 핸들 저장 변수
        
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

        # --- 버튼 추가 시작 ---
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        confirm_button = QPushButton("확인")
        close_button = QPushButton("닫기")

        button_style = """
            QPushButton {
                background-color: #555;
                color: #fff;
                border: 1px solid #777;
                border-radius: 5px;
                padding: 5px 10px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #777;
            }
            QPushButton:pressed {
                background-color: #444;
            }
        """
        confirm_button.setStyleSheet(button_style)
        close_button.setStyleSheet(button_style)

        confirm_button.clicked.connect(self._on_confirm_button_clicked)
        # '닫기' 버튼 클릭 시 기존 활성 윈도우 포커스 유지
        close_button.clicked.connect(self._on_close_button_clicked)

        button_layout.addWidget(confirm_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        # --- 버튼 추가 끝 ---
        
        # 최소 크기 설정
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        
        # 페이드 아웃 애니메이션 설정
        self._fade_animation = QPropertyAnimation(self, b"opacity")
        self._fade_animation.setDuration(300)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self.close)
        
        # 자동 닫기 타이머 (sticky가 아닐 때만 설정)
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._start_fade_out)
    
    def enterEvent(self, event):
        """마우스가 알림창에 들어올 때 현재 활성 윈도우(예: 크롬)의 핸들을 저장"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            current_hwnd = user32.GetForegroundWindow()
            # 현재 활성 창이 내 자신(토스트)이 아니면 저장
            if current_hwnd != int(self.winId()):
                self._last_active_hwnd = current_hwnd
        except Exception:
            pass
        super().enterEvent(event)

    def paintEvent(self, event):
        """둥근 모서리와 배경을 그린다"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        
        # 배경색 설정
        if self._sticky:
            # Sticky 모드: 파란색 계열 (확인 요청)
            bg_color = QColor(0, 123, 255, 240)
        else:
            # 일반 모드: 빨간색 계열 (경고 알림)
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
        # sticky가 아닐 때만 자동 닫기 타이머 시작
        if not self._sticky:
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

    def _on_confirm_button_clicked(self):
        """확인 버튼 클릭 시 호출되며, 알림창을 닫고 메인 윈도우를 최상위로 포커스합니다."""
        self.close()
        
        try:
            # 모든 탑레벨 위젯 중 MainWindow 찾기
            from PyQt6.QtWidgets import QApplication
            main_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.__class__.__name__ == 'MainWindow':
                    main_window = widget
                    break
            
            if main_window:
                # 윈도우 상태 정규화 및 활성화
                if main_window.isMinimized():
                    main_window.showNormal()
                
                main_window.raise_()
                main_window.activateWindow()
                
                # Windows OS인 경우 Win32 API로 확실하게 최상위로
                import sys
                if sys.platform == 'win32':
                    import ctypes
                    user32 = ctypes.windll.user32
                    hwnd = int(main_window.winId())
                    # 다른 프로세스의 윈도우가 이미 포커스를 가지고 있을 때를 대비해 강제 포커스
                    user32.ShowWindow(hwnd, 5)  # SW_SHOW
                    user32.SetForegroundWindow(hwnd)
        except Exception as e:
            print(f"메인 윈도우 포커스 전환 중 오류: {e}")

    def _on_close_button_clicked(self):
        """닫기 버튼 클릭 시 호출되며, 알림창을 닫고 이전 외부 윈도우의 포커스를 복원합니다."""
        self.close()
        
        if self._last_active_hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # 저장된 핸들의 윈도우를 다시 활성화
                user32.SetForegroundWindow(self._last_active_hwnd)
            except Exception:
                pass


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


def show_toast(title: str, message: str, parent=None, recent_received_date=None, sticky: bool = False):
    """
    화면 중앙 상단에 토스트 알림을 표시한다.
    최대 3개까지만 표시하며, recent_received_date가 더 최근인 것부터 우선적으로 표시한다.
    
    Args:
        title: 알림 제목
        message: 알림 메시지
        parent: 부모 위젯 (사용하지 않지만 호환성을 위해 유지)
        recent_received_date: 최근 접수 시간 (datetime 객체, 정렬 기준으로 사용)
        sticky: 사용자가 닫기 전까지 사라지지 않는지 여부
    """
    global _active_toasts
    
    # 최대 3개 제한: 이미 3개가 있으면 가장 오래된 것 제거
    if len(_active_toasts) >= 3:
        # recent_received_date 기준으로 정렬 (None인 경우 가장 오래된 것으로 간주)
        visible_toasts = [t for t in _active_toasts if t.isVisible()]
        
        if len(visible_toasts) >= 3:
            # recent_received_date가 None이거나 가장 오래된 토스트 찾기
            oldest_toast = None
            oldest_date = None
            
            for t in visible_toasts:
                toast_date = t._recent_received_date
                if toast_date is None:
                    # None인 경우 가장 오래된 것으로 간주하고 제거
                    oldest_toast = t
                    break
                elif oldest_date is None or toast_date < oldest_date:
                    oldest_date = toast_date
                    oldest_toast = t
            
            # 가장 오래된 토스트 제거
            if oldest_toast:
                oldest_toast.close()
                if oldest_toast in _active_toasts:
                    _active_toasts.remove(oldest_toast)
    
    toast = Toast(title, message, parent, recent_received_date, sticky=sticky)
    
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
