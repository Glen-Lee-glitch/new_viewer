import sys
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication

class NotificationInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("공고문 관리")
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        self.label = QLabel("여기에 알림 정보가 표시됩니다.")
        layout.addWidget(self.label)
        
        self.setLayout(layout)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = NotificationInfoDialog()
    dialog.show()
    sys.exit(app.exec())
