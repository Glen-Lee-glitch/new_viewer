from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QGraphicsScene


class CropDialog(QDialog):
    """PDF 페이지 자르기 다이얼로그"""
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "crop_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        self.scene = QGraphicsScene(self)
        self.page_preview_view.setScene(self.scene)
        
        # 버튼 텍스트 설정
        ok_button = self.buttonBox.button(self.buttonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("자르기 적용")
        
        cancel_button = self.buttonBox.button(self.buttonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("취소")

    def set_page_pixmap(self, pixmap: QPixmap):
        """미리보기 Grahpics View에 현재 페이지의 QPixmap을 설정한다."""
        self.scene.clear()
        self.scene.addPixmap(pixmap)
        # 뷰에 맞게 pixmap 크기를 조정하고 중앙에 표시
        self.page_preview_view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
