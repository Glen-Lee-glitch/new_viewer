import sys
import os
import pandas as pd
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QPushButton, QHeaderView, QMessageBox, QDateEdit, QWidget, QLabel, QApplication
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor

# Ensure we can import from core/widgets if needed in the future
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sql_manager import fetch_scheduled_regions, update_scheduled_region

class ScheduledRegionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("예정 지자체 관리")
        self.resize(600, 700)
        
        # Main Layout
        layout = QVBoxLayout(self)
        
        # Title Label
        title_label = QLabel("예정 지자체 출고 예정일 관리")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["지역", "출고예정일", "최근 업데이트"])
        
        # Header Settings
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 180)
        
        layout.addWidget(self.table)
        
        # Buttons Layout
        btn_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.load_data)
        btn_layout.addWidget(self.refresh_btn)
        
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("저장")
        self.save_btn.clicked.connect(self.save_changes)
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px 15px;")
        btn_layout.addWidget(self.save_btn)
        
        self.close_btn = QPushButton("닫기")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
        # Data storage
        self.original_data = {} # {region: plan_open_date_str}
        self.modified_data = {} # {region: plan_open_date_str}
        
        # Load Data
        self.load_data()
        
    def load_data(self):
        """DB에서 데이터를 불러와 테이블에 표시합니다."""
        df = fetch_scheduled_regions()
        
        if df.empty:
            QMessageBox.information(self, "알림", "데이터가 없습니다.")
            return
            
        self.table.setRowCount(len(df))
        self.original_data = {}
        self.modified_data = {}
        self.date_edits = {} # {row: QDateEdit}
        
        for row_idx, row in df.iterrows():
            region = row['region']
            plan_date = row['plan_open_date']
            updated_at = row['updated_datetime']
            
            # 1. Region (Read-only)
            region_item = QTableWidgetItem(region)
            region_item.setFlags(region_item.flags() ^ Qt.ItemFlag.ItemIsEditable) # Make read-only
            self.table.setItem(row_idx, 0, region_item)
            
            # 2. Plan Open Date (DateEdit Widget)
            date_edit = QDateEdit()
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setCalendarPopup(True)
            
            # Set date if exists, otherwise set to empty/null representation (unchecked or custom)
            # QDateEdit doesn't support "null" natively well without a checkbox or special handling.
            # Using QDateEdit with a "clear" button approach or special date to represent null is tricky.
            # Instead, let's use a widget that holds a DateEdit and a "Clear" button, or just use text edit for simplicity?
            # Let's stick to QDateEdit. If null, we can set a special date or use a checkbox "설정".
            # Better approach for Nullable Date: Use a QWidget container with CheckBox + DateEdit
            
            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(2, 0, 2, 0)
            h_layout.setSpacing(5)
            
            # Checkbox to enable/disable date (represents Null vs Not Null)
            chk = pd.notna(plan_date)
            
            # Date Edit
            date_widget = QDateEdit()
            date_widget.setDisplayFormat("yyyy-MM-dd")
            date_widget.setCalendarPopup(True)
            
            if chk:
                if isinstance(plan_date, str):
                    qdate = QDate.fromString(plan_date, "yyyy-MM-dd")
                elif isinstance(plan_date, (datetime, pd.Timestamp)):
                    qdate = QDate(plan_date.year, plan_date.month, plan_date.day)
                else:
                    qdate = QDate.currentDate()
                date_widget.setDate(qdate)
                date_str = qdate.toString("yyyy-MM-dd")
            else:
                date_widget.setDate(QDate.currentDate())
                date_widget.setEnabled(False) # Initially disabled if null
                date_str = None
                
            # Store original data
            self.original_data[region] = date_str
            
            # Checkbox logic
            checkbox = QPushButton("사용")
            checkbox.setCheckable(True)
            checkbox.setChecked(chk)
            checkbox.setFixedWidth(40)
            if chk:
                checkbox.setText("설정")
                checkbox.setStyleSheet("color: green;")
            else:
                checkbox.setText("없음")
                checkbox.setStyleSheet("color: gray;")
                
            checkbox.toggled.connect(lambda checked, de=date_widget, btn=checkbox: self.on_date_toggled(checked, de, btn))
            
            # Connect date change to track modifications
            # We need to capture row_idx or region for the callback
            # Using partial or lambda with captured variables
            
            h_layout.addWidget(checkbox)
            h_layout.addWidget(date_widget)
            
            self.table.setCellWidget(row_idx, 1, container)
            
            # Store references to widgets to retrieve values later
            self.date_edits[row_idx] = {
                'region': region,
                'checkbox': checkbox,
                'date_edit': date_widget
            }
            
            # 3. Updated At (Read-only)
            updated_str = ""
            if pd.notna(updated_at):
                updated_str = str(updated_at)
            
            updated_item = QTableWidgetItem(updated_str)
            updated_item.setFlags(updated_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            updated_item.setForeground(QColor("gray"))
            self.table.setItem(row_idx, 2, updated_item)

    def on_date_toggled(self, checked, date_edit, btn):
        date_edit.setEnabled(checked)
        if checked:
            btn.setText("설정")
            btn.setStyleSheet("color: green;")
        else:
            btn.setText("없음")
            btn.setStyleSheet("color: gray;")

    def save_changes(self):
        """변경된 내용을 DB에 저장합니다."""
        changed_count = 0
        error_count = 0
        
        for row_idx, widgets in self.date_edits.items():
            region = widgets['region']
            checkbox = widgets['checkbox']
            date_edit = widgets['date_edit']
            
            current_val = None
            if checkbox.isChecked():
                current_val = date_edit.date().toString("yyyy-MM-dd")
            
            original_val = self.original_data.get(region)
            
            # Check if changed
            if current_val != original_val:
                # Update DB
                success = update_scheduled_region(region, current_val)
                if success:
                    changed_count += 1
                else:
                    error_count += 1
                    print(f"Failed to update {region}")
        
        if changed_count > 0:
            QMessageBox.information(self, "완료", f"{changed_count}건이 저장되었습니다." + (f"\n({error_count}건 실패)" if error_count > 0 else ""))
            self.load_data() # Reload to refresh UI and original_data
        elif error_count > 0:
            QMessageBox.warning(self, "오류", f"저장 중 오류가 발생했습니다. ({error_count}건 실패)")
        else:
            QMessageBox.information(self, "알림", "변경된 내용이 없습니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = ScheduledRegionDialog()
    dialog.show()
    sys.exit(app.exec())
