from pathlib import Path
import sys
import os

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget, QMenu


# PyInstaller로 빌드된 경우와 개발 환경 구분
def get_resource_path(relative_path):
    """리소스 파일의 절대 경로를 반환"""
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 경우
        # onedir 모드: _internal 폴더에 모든 파일이 있음
        if hasattr(sys, '_MEIPASS'):
            # onefile 모드 (임시 폴더)
            base_path = Path(sys._MEIPASS)
        else:
            # onedir 모드: 실행 파일과 같은 디렉토리의 _internal 폴더
            base_path = Path(sys.executable).parent / '_internal'
    else:
        # 개발 환경
        base_path = Path(__file__).parent.parent
    
    full_path = base_path / relative_path
    return full_path


class StampOverlayWidget(QWidget):
    """메인 윈도우 위에 나타나는 반투명 오버레이 위젯."""
    stamp_selected = pyqtSignal(dict)  # 변경: str -> dict
    
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "stamp_overlay.ui"
        uic.loadUi(str(ui_path), self)

        # 프레임 제거 + 투명 배경
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.hide()
        self._setup_stamp_button_5_menu()
        self._connect_signals()

    def _setup_stamp_button_5_menu(self):
        if hasattr(self, 'stamp_button_5'):
            menu = QMenu(self)
            check_action = QAction("체크", self)
            check_action.triggered.connect(lambda: self._on_stamp_button_clicked(
                {'path': str(get_resource_path('assets/체크.png')), 'width': 50}
            ))
            menu.addAction(check_action)
            
            circle_action = QAction("원", self)
            circle_action.triggered.connect(lambda: self._on_stamp_button_clicked(
                {'path': str(get_resource_path('assets/circle.png')), 'width': 50}
            ))
            menu.addAction(circle_action)
            
            self.stamp_button_5.setMenu(menu)

    def _connect_signals(self):
        if hasattr(self, 'stamp_button_1'):
            self.stamp_button_1.clicked.connect(lambda: self._on_stamp_button_clicked(
                {'path': str(get_resource_path('assets/도장1.png')), 'width': 90}
            ))
        if hasattr(self, 'stamp_button_2'):
            self.stamp_button_2.clicked.connect(lambda: self._on_stamp_button_clicked(
                {'path': str(get_resource_path('assets/원본대조필.png')), 'width': 320}
            ))
        if hasattr(self, 'stamp_button_3'):
            self.stamp_button_3.clicked.connect(lambda: self._on_stamp_button_clicked(
                {'path': str(get_resource_path('assets/명판.png')), 'width': 360}
            ))
        if hasattr(self, 'stamp_button_4'):
            self.stamp_button_4.clicked.connect(self._on_stamp_selected)

    def _on_stamp_button_clicked(self, stamp_info: dict):
        """도장 버튼 클릭 시, 선택된 도장 정보를 포함한 시그널을 발생시킨다."""
        self.stamp_selected.emit(stamp_info)
        try:
            self.releaseKeyboard()
        finally:
            self.hide()

    def _on_stamp_selected(self):
        print("성공")
        try:
            self.releaseKeyboard()
        finally:
            self.hide()

    def show_overlay(self, parent_size):
        self.setGeometry(0, 0, parent_size.width(), parent_size.height())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    def mousePressEvent(self, event):
        # content_frame 밖을 클릭하면 닫기
        if hasattr(self, 'content_frame'):
            local_in_frame = self.content_frame.mapFrom(self, event.pos())
            if not self.content_frame.rect().contains(local_in_frame):
                try:
                    self.releaseKeyboard()
                finally:
                    self.hide()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # 숫자/숫자패드 1~5 모두 처리
        key = event.key()

        if key == Qt.Key.Key_1:
            self._on_stamp_button_clicked({'path': str(get_resource_path('assets/도장1.png')), 'width': 90})
            return

        if key == Qt.Key.Key_2:
            # 여기에 2번 이미지 경로와 너비를 넣으세요.
            self._on_stamp_button_clicked({'path': str(get_resource_path('assets/원본대조필.png')), 'width': 320}) # 예시
            return

        if key == Qt.Key.Key_3:
            self._on_stamp_button_clicked({'path': str(get_resource_path('assets/명판.png')), 'width': 360})
            return

        if key == Qt.Key.Key_4:
            # 4번 도장은 현재 기능이 없으므로 기존 동작 유지
            self._on_stamp_selected()
            return

        if key == Qt.Key.Key_5:
            if hasattr(self, 'stamp_button_5'):
                self.stamp_button_5.showMenu()
            return

        super().keyPressEvent(event)
