from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor


class FloatingToolbarWidget(QWidget):
    """pdf_view_widget 위에 떠다니는 이동 가능한 툴바."""
    stamp_menu_requested = pyqtSignal()
    fit_to_width_requested = pyqtSignal()
    fit_to_page_requested = pyqtSignal()
    rotate_90_requested = pyqtSignal()
    save_pdf_requested = pyqtSignal()
    crop_requested = pyqtSignal() # 자르기 신호 추가
    setting_requested = pyqtSignal()
    toggle_mail_overlay_requested = pyqtSignal()  # 메일 오버레이 토글 시그널 추가
    email_requested = pyqtSignal()  # 이메일 다이얼로그 시그널 추가
    
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "floating_toolbar.ui"
        uic.loadUi(str(ui_path), self)
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._add_shadow_effect()
        
        self.setObjectName("floatingToolbar")
        self._apply_styles()
        
        self._is_dragging = False
        self._drag_start_position = None
        
        if hasattr(self, 'pushButton_2'):
            self.pushButton_2.clicked.connect(self.toggle_mail_overlay_requested.emit)          
        if hasattr(self, 'pushButton_stamp'):
            try:
                self.pushButton_stamp.clicked.connect(self.stamp_menu_requested.emit)
            except Exception:
                pass
        
        if hasattr(self, 'pushButton_3'):
            self.pushButton_3.clicked.connect(self.fit_to_width_requested.emit)
        
        if hasattr(self, 'pushButton_4'):
            self.pushButton_4.clicked.connect(self.rotate_90_requested.emit)
        
        if hasattr(self, 'pushButton_5'):
            self.pushButton_5.clicked.connect(self.save_pdf_requested.emit)
        
        if hasattr(self, 'pushButton_6'):
            self.pushButton_6.clicked.connect(self.crop_requested.emit)
                
        if hasattr(self, 'drag_handle_label'):
            self.drag_handle_label.setCursor(Qt.CursorShape.SizeAllCursor)

        if hasattr(self, 'pushButton_4'):
            self.pushButton_4.clicked.connect(self.rotate_90_requested.emit)

        if hasattr(self, 'pushButton_setting'):
            self.pushButton_setting.clicked.connect(self.setting_requested.emit)

        if hasattr(self, 'pushButton_email'):
            self.pushButton_email.clicked.connect(self.email_requested.emit)

    def _add_shadow_effect(self):
        """툴바에 그림자 효과를 추가한다."""
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

    def mousePressEvent(self, event):
        # 'drag_handle_label' 위에서 마우스를 눌렀는지 확인
        if hasattr(self, 'drag_handle_label') and self.drag_handle_label.underMouse():
            if event.button() == Qt.MouseButton.LeftButton:
                self._is_dragging = True
                self._drag_start_position = event.globalPosition().toPoint() - self.pos()
                # 드래그 중 시각적 피드백
                self.drag_handle_label.setStyleSheet(
                    self.drag_handle_label.styleSheet() + 
                    "QLabel { color: rgba(255, 255, 255, 1.0); }"
                )
                event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            # 드래그 핸들 스타일을 원래대로 복원
            if hasattr(self, 'drag_handle_label'):
                self.drag_handle_label.setStyleSheet(
                    """
                    QLabel {
                        color: rgba(255, 255, 255, 0.6);
                        font-size: 14px;
                        font-weight: bold;
                        background: transparent;
                        border: none;
                        letter-spacing: -2px;
                    }
                    """
                )
            event.accept()

    def _apply_styles(self):
        """FloatingToolbar 전용 QSS 스타일을 적용한다."""
        self.setStyleSheet(
            """
            #floatingToolbar QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: #ffffff;
                font-size: 16px;
                font-weight: normal;
                padding: 0px;
                margin: 0px;
            }
            #floatingToolbar QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.2);
                margin-top: 1px;
                margin-bottom: -1px;
            }
            #floatingToolbar QPushButton:pressed {
                background: rgba(255, 255, 255, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.3);
                margin-top: 0px;
                margin-bottom: 0px;
            }
            #floatingToolbar QPushButton#pushButton_stamp {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FF6B9D, stop:1 #E91E63);
                border: 1px solid #AD1457;
            }
            #floatingToolbar QPushButton#pushButton_stamp:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FF8AB0, stop:1 #F06292);
                border: 1px solid #C2185B;
            }
            #floatingToolbar QPushButton#pushButton_setting {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #78909C, stop:1 #546E7A);
                border: 1px solid #37474F;
            }
            #floatingToolbar QPushButton#pushButton_setting:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #90A4AE, stop:1 #607D8B);
                border: 1px solid #455A64;
            }
            """
        )
