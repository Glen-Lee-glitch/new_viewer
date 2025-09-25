from pathlib import Path
import os
import shutil

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QRunnable, QThreadPool
from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor

from core.pdf_saved import compress_pdf_with_multiple_stages

class WorkerSignals(QObject):
    """
    백그라운드 작업 스레드의 시그널을 정의합니다.
    (진행률, 완료, 오류 등)
    """
    finished = pyqtSignal(str, bool)  # 저장 경로, 성공 여부
    error = pyqtSignal(str)


class PdfSaveWorker(QRunnable):
    """
    QThreadPool에서 PDF 압축 및 저장을 실행하기 위한 Worker
    """
    def __init__(self, input_path: str, output_path: str):
        super().__init__()
        self.signals = WorkerSignals()
        self.input_path = input_path
        self.output_path = output_path

    def run(self):
        try:
            # 원본 파일을 output_path로 복사 (shutil.move 대신)
            temp_input_path = self.output_path + ".tmp"
            shutil.copy2(self.input_path, temp_input_path)
            
            success = compress_pdf_with_multiple_stages(
                input_path=temp_input_path,
                output_path=self.output_path,
                target_size_mb=3
            )
            self.signals.finished.emit(self.output_path, success)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            if os.path.exists(temp_input_path):
                os.remove(temp_input_path)


class FloatingToolbarWidget(QWidget):
    """pdf_view_widget 위에 떠다니는 이동 가능한 툴바."""
    stamp_menu_requested = pyqtSignal()
    fit_to_width_requested = pyqtSignal()
    fit_to_page_requested = pyqtSignal()
    rotate_90_requested = pyqtSignal()
    save_pdf_requested = pyqtSignal()
    rotate_90_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "floating_toolbar.ui"
        uic.loadUi(str(ui_path), self)
        
        # 창 테두리 없애기 (parent 위젯에 자연스럽게 떠있도록)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # 배경 투명화
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 그림자 효과 추가
        self._add_shadow_effect()
        
        # 스타일 스코프 고정
        self.setObjectName("floatingToolbar")
        self._apply_styles()
        
        self._is_dragging = False
        self._drag_start_position = None

        self.thread_pool = QThreadPool()
        
        # 스탬프 버튼 클릭 시 오버레이 표시 요청
        if hasattr(self, 'pushButton_stamp'):
            try:
                self.pushButton_stamp.clicked.connect(self.stamp_menu_requested.emit)
            except Exception:
                pass
        
        # 보기 모드 버튼 연결
        if hasattr(self, 'pushButton_3'):
            self.pushButton_3.clicked.connect(self.fit_to_width_requested.emit)
        
        # 회전 버튼 연결 (pushButton_4를 90도 회전 기능으로 사용)
        if hasattr(self, 'pushButton_4'):
            self.pushButton_4.clicked.connect(self.rotate_90_requested.emit)
        
        if hasattr(self, 'pushButton_5'):
            self.pushButton_5.clicked.connect(self.save_pdf_requested.emit)
                
        # 드래그 핸들에 마우스 호버 효과 적용
        if hasattr(self, 'drag_handle_label'):
            self.drag_handle_label.setCursor(Qt.CursorShape.SizeAllCursor)

        # 회전 버튼 연결 (pushButton_4를 90도 회전 기능으로 사용)
        if hasattr(self, 'pushButton_4'):
            self.pushButton_4.clicked.connect(self.rotate_90_requested.emit)

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
