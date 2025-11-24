import sys
import os
from PyQt6.QtWidgets import (
    QDialog, QApplication, QCheckBox, QLineEdit, QGridLayout, QLabel
)
from PyQt6.uic import loadUi

# Ensure we can import from core/widgets if needed in the future
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class SpecialNoteDialog(QDialog):
    # Define detailed items as class constants
    MISSING_DOCS_ITEMS = [
        '신청서1p', '신청서2p', '계약서1p', '계약서4p', 
        '초본', '등본', '가족', '지납세', '지세과', '기타'
    ]
    
    REQ_ITEMS = [
        '전입일', '중복', '거주지 다름', '기타'
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Load the UI file
        ui_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "special_note_dialog.ui")
        loadUi(ui_path, self)
        
        # Dynamic Widget Storage
        self.missing_checkboxes = {}  # {name: {'cb': QCheckBox, 'le': QLineEdit|None}}
        self.req_checkboxes = {}      # {name: {'cb': QCheckBox, 'le': QLineEdit|None}}
        
        # Initialize Dynamic UI
        self._init_dynamic_ui()

        # Connect Main Checkboxes to Visibility Logic
        self.checkBox_2.toggled.connect(self.update_ui_state)  # 서류미비
        self.checkBox.toggled.connect(self.update_ui_state)    # 요건
        self.checkBox_3.toggled.connect(self.update_ui_state)  # 기타
        
        # Initialize state (hide all sub-frames initially)
        self.update_ui_state()

        # Connect close button
        self.pushButton_2.clicked.connect(self.close)

    def _init_dynamic_ui(self):
        """Generate checkboxes dynamically for Missing Docs and Requirements."""
        # Setup Missing Documents Frame (checkBox_2)
        self._setup_checkbox_grid(
            self.gridLayout_missing, 
            "↳ 서류미비 상세:", 
            self.MISSING_DOCS_ITEMS, 
            self.missing_checkboxes
        )
        
        # Setup Requirements Frame (checkBox)
        self._setup_checkbox_grid(
            self.gridLayout_req, 
            "↳ 요건 상세:", 
            self.REQ_ITEMS, 
            self.req_checkboxes
        )

    def _setup_checkbox_grid(self, layout: QGridLayout, label_text: str, items: list, storage: dict):
        """Helper to populate a grid layout with checkboxes and optional 'Other' input."""
        
        # Add Label at (0, 0) spanning multiple columns
        label = QLabel(label_text)
        label.setStyleSheet("color: gray;")
        layout.addWidget(label, 0, 0, 1, 4) 

        row = 1
        col = 0
        max_col = 4 # Number of columns for checkboxes

        for item_text in items:
            cb = QCheckBox(item_text)
            storage[item_text] = {'cb': cb, 'le': None}
            
            # Place checkbox
            layout.addWidget(cb, row, col)
            
            # If item is "기타", add a LineEdit
            if item_text == "기타":
                le = QLineEdit()
                le.setPlaceholderText("직접 입력")
                le.setVisible(False) # Initially hidden
                storage[item_text]['le'] = le
                
                # Connect toggle signal to show/hide LineEdit
                cb.toggled.connect(lambda checked, line_edit=le: line_edit.setVisible(checked))
                
                # Place LineEdit next to "기타" checkbox or wrapped
                if col < max_col - 1:
                    col += 1
                    layout.addWidget(le, row, col, 1, 2) # Span 2 columns
                    col += 1 # Skip one more due to span
                else:
                    # New row for LineEdit if no space
                    row += 1
                    layout.addWidget(le, row, 0, 1, 4)
                    col = max_col # Force next loop to new row if there were more items
            
            col += 1
            if col >= max_col:
                col = 0
                row += 1

    def update_ui_state(self):
        """Show/Hide sub-frames based on main checkbox state."""
        self.sub_frame_missing.setVisible(self.checkBox_2.isChecked())
        self.sub_frame_req.setVisible(self.checkBox.isChecked())
        self.sub_frame_other.setVisible(self.checkBox_3.isChecked())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    app.setStyleSheet("""
        QDialog { background-color: #f0f0f0; }
        QGroupBox { font-weight: bold; border: 1px solid gray; border-radius: 5px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        QLineEdit { background-color: white; }
    """)
    
    dialog = SpecialNoteDialog()
    dialog.show()
    
    sys.exit(app.exec())
