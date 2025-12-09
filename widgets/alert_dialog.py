from PyQt6.QtWidgets import QMessageBox, QApplication
from PyQt6.QtCore import Qt

# To prevent dialogs from being garbage collected immediately
_active_alerts = []

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
