from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal

class InfoPanelWidget(QWidget):
    """PDF 파일 및 페이지 정보를 표시하는 위젯"""
    text_stamp_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "info_panel.ui"
        uic.loadUi(str(ui_path), self)

        if hasattr(self, 'pushButton_insert_text'):
            self.pushButton_insert_text.clicked.connect(self._on_insert_text_clicked)

    def clear_info(self):
        """모든 정보 라벨을 'N/A'로 초기화한다."""
        self.label_file_path.setText("N/A")
        self.label_file_size.setText("N/A")
        self.label_total_pages_val.setText("N/A")
        self.label_current_page.setText("N/A")
        self.label_page_dims.setText("N/A")
        self.label_page_rotation.setText("N/A")

    def update_file_info(self, file_path: str, file_size_mb: float, total_pages: int):
        """파일 관련 정보를 업데이트한다."""
        self.label_file_path.setText(file_path)
        self.label_file_size.setText(f"{file_size_mb:.2f} MB")
        self.label_total_pages_val.setText(str(total_pages))

    def update_page_info(self, page_num: int, width: float, height: float, rotation: int):
        """현재 페이지 관련 정보를 업데이트한다."""
        self.label_current_page.setText(str(page_num + 1))  # 0-based to 1-based
        self.label_page_dims.setText(f"{width:.2f} x {height:.2f} (pt)")
        self.label_page_rotation.setText(f"{rotation}°")

    def _on_insert_text_clicked(self):
        if hasattr(self, 'text_edit') and hasattr(self, 'font_spinBox'):
            text = self.text_edit.text()
            font_size = self.font_spinBox.value() # 스핀박스에서 폰트 크기 가져오기
            if text:
                self.text_stamp_requested.emit(text, font_size) # 텍스트와 폰트 크기 함께 전달
                self.text_edit.clear() # 입력창 비우기
            else:
                # (선택사항) 사용자에게 텍스트를 입력하라는 메시지를 보여줄 수 있습니다.
                print("입력된 텍스트가 없습니다.")
