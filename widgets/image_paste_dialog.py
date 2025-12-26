from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage

class ImagePasteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이미지 붙여넣기")
        self.resize(400, 300)
        
        self.layout = QVBoxLayout(self)
        
        self.info_label = QLabel("이미지를 복사한 후 Ctrl+V를 눌러 붙여넣으세요.")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.info_label)
        
        self.image_preview = QLabel()
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet("border: 1px dashed #aaaaaa; background-color: #2b2b2b;")
        self.image_preview.setMinimumSize(300, 200)
        self.image_preview.setText("이미지 미리보기")
        self.layout.addWidget(self.image_preview)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)
        
        self.pasted_image = None

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V:
            self._paste_image()
        else:
            super().keyPressEvent(event)

    def _paste_image(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        
        if mime_data.hasImage():
            pixmap = clipboard.pixmap()
            if not pixmap.isNull():
                self.pasted_image = pixmap
                self.image_preview.setPixmap(pixmap.scaled(
                    self.image_preview.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                ))
                self.image_preview.setText("") # 텍스트 제거
        else:
            QMessageBox.warning(self, "알림", "클립보드에 이미지가 없습니다.")

    def accept(self):
        if self.pasted_image is None:
            QMessageBox.warning(self, "알림", "이미지를 붙여넣어 주세요.")
            return
        super().accept()
    
    def get_image(self):
        return self.pasted_image
