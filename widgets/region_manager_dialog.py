import sys
import os
from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import (
    QDialog, QTableWidgetItem, QCheckBox, QHBoxLayout, QWidget, 
    QMessageBox, QApplication, QHeaderView
)
from PyQt6.QtCore import Qt

# 프로젝트 루트 경로 추가 (core 모듈 임포트용)
sys.path.append(str(Path(__file__).parent.parent))

class RegionManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "region_manager.ui"
        uic.loadUi(str(ui_path), self)
        
        self.setWindowTitle("지자체 설정 관리")
        
        # 테이블 헤더 설정
        self.tableWidget_sealed.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_sealed.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tableWidget_sealed.setColumnWidth(1, 150)
        
        # 버튼 연결
        self.btn_refresh.clicked.connect(self.load_data)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_close.clicked.connect(self.close)
        
        # 데이터 저장소
        self.original_data = {} # {region: is_apply_sealed}
        self.checkbox_map = {} # {region: QCheckBox}
        
        # 데이터 로드
        self.load_data()
        
    def load_data(self):
        """MCP를 통해 region_metadata 테이블에서 데이터를 로드합니다."""
        try:
            # MCP PostgreSQL 조회 사용
            # 실제 실행 시에는 MCP 서버를 통해 쿼리가 수행됨
            from core.sql_manager import DB_CONFIG
            import psycopg2
            from contextlib import closing
            
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT region, is_apply_sealed FROM region_metadata ORDER BY region")
                    rows = cursor.fetchall()
            
            if not rows:
                QMessageBox.information(self, "알림", "데이터가 없습니다.")
                return
                
            self.tableWidget_sealed.setRowCount(len(rows))
            self.original_data = {}
            self.checkbox_map = {}
            
            for row_idx, (region, is_apply_sealed) in enumerate(rows):
                # 1. 지역 (Read-only)
                region_item = QTableWidgetItem(region)
                region_item.setFlags(region_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_sealed.setItem(row_idx, 0, region_item)
                
                # 2. 원본대조필 적용 (Checkbox)
                container = QWidget()
                layout = QHBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                checkbox = QCheckBox()
                checkbox.setChecked(bool(is_apply_sealed))
                layout.addWidget(checkbox)
                
                self.tableWidget_sealed.setCellWidget(row_idx, 1, container)
                
                # 데이터 저장
                self.original_data[region] = bool(is_apply_sealed)
                self.checkbox_map[region] = checkbox
                
        except Exception as e:
            QMessageBox.critical(self, "오류", f"데이터를 로드하는 중 오류가 발생했습니다: {str(e)}")
            import traceback
            traceback.print_exc()

    def save_changes(self):
        """변경된 내용을 DB에 저장합니다."""
        changed_regions = []
        for region, original_val in self.original_data.items():
            checkbox = self.checkbox_map.get(region)
            if checkbox and checkbox.isChecked() != original_val:
                changed_regions.append((region, checkbox.isChecked()))
        
        if not changed_regions:
            QMessageBox.information(self, "알림", "변경된 내용이 없습니다.")
            return
            
        try:
            from core.sql_manager import DB_CONFIG
            import psycopg2
            from contextlib import closing
            
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    for region, new_val in changed_regions:
                        cursor.execute(
                            "UPDATE region_metadata SET is_apply_sealed = %s WHERE region = %s",
                            (new_val, region)
                        )
                conn.commit()
                
            QMessageBox.information(self, "완료", f"{len(changed_regions)}건의 변경사항이 저장되었습니다.")
            self.load_data() # 새로고침
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = RegionManagerDialog()
    dialog.show()
    sys.exit(app.exec())
