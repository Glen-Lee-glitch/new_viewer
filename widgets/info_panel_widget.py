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
        self.label_current_page.setText("N/A")
        self.label_page_dims.setText("N/A")
        self.label_page_rotation.setText("N/A")
        self.lineEdit_name.clear()
        self.lineEdit_region.clear()
        self.lineEdit_special.clear()
        if hasattr(self, 'lineEdit_rn_num'):
            self.lineEdit_rn_num.clear()  # RN 필드도 초기화

    def update_file_info(self, file_path: str, file_size_mb: float, total_pages: int):
        """파일 관련 정보를 업데이트한다. (UI에서 파일 정보 그룹박스가 제거되어 비활성화됨)"""
        pass

    def update_total_pages(self, total_pages: int):
        """총 페이지 수 정보만 업데이트한다. (UI에서 파일 정보 그룹박스가 제거되어 비활성화됨)"""
        pass

    def update_page_info(self, page_num: int, width: float, height: float, rotation: int):
        """현재 페이지 관련 정보를 업데이트한다."""
        self.label_current_page.setText(str(page_num + 1))  # 0-based to 1-based
        self.label_page_dims.setText(f"{width:.2f} x {height:.2f} (pt)")
        self.label_page_rotation.setText(f"{rotation}°")

    def update_basic_info(self, name: str, region: str, special_note: str, rn: str = ""):
        """기본 정보를 업데이트한다."""
        self.lineEdit_name.setText(name)
        self.lineEdit_region.setText(region)
        self.lineEdit_special.setText(special_note)
        if hasattr(self, 'lineEdit_rn_num'):
            self.lineEdit_rn_num.setText(rn)

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
