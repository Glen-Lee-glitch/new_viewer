import sys
import os
from PyQt6.QtWidgets import QDialog, QApplication, QFrame
from PyQt6.uic import loadUi

# Ensure we can import from core/widgets if needed in the future
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class SpecialNoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Load the UI file
        # Assumes ui folder is sibling to widgets folder
        ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "special_note_dialog.ui")
        loadUi(ui_path, self)
        
        # Connect Main Checkboxes to Visibility Logic
        # checkBox_2 : 서류미비 (Missing Documents)
        # checkBox   : 요건 (Requirements)
        # checkBox_3 : 기타 (Other)
        
        self.checkBox_2.toggled.connect(self.update_ui_state)
        self.checkBox.toggled.connect(self.update_ui_state)
        self.checkBox_3.toggled.connect(self.update_ui_state)
        
        # Initialize state (hide all sub-frames initially)
        self.update_ui_state()

        # Connect close button
        self.pushButton_2.clicked.connect(self.close)

    def update_ui_state(self):
        """Show/Hide sub-frames based on main checkbox state."""
        
        # Frame names defined in UI:
        # sub_frame_missing (for checkBox_2)
        # sub_frame_req     (for checkBox)
        # sub_frame_other   (for checkBox_3)
        
        # Simply set visibility based on checked state
        self.sub_frame_missing.setVisible(self.checkBox_2.isChecked())
        self.sub_frame_req.setVisible(self.checkBox.isChecked())
        self.sub_frame_other.setVisible(self.checkBox_3.isChecked())
        
        # Optional: Adjust dialog size to fit content dynamically if needed, 
        # but Layouts usually handle this.

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Apply a basic stylesheet for better visibility during test
    app.setStyleSheet("""
        QDialog { background-color: #f0f0f0; }
        QGroupBox { font-weight: bold; border: 1px solid gray; border-radius: 5px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
    """)
    
    dialog = SpecialNoteDialog()
    dialog.show()
    
    sys.exit(app.exec())

