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
        
        # 검색 기능 연결
        self.lineEdit_search.textChanged.connect(self.filter_table)
        
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
            
            # 로드 후 현재 검색어에 맞춰 필터링 적용
            self.filter_table()
                
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

    def _extract_chosung(self, text: str) -> str:
        """
        한글 문자열에서 초성을 추출합니다.
        
        Args:
            text: 초성을 추출할 한글 문자열
            
        Returns:
            초성 문자열 (예: "서울시" -> "ㅅㅇㅅ")
        """
        if not text:
            return ""
        
        chosung_list = []
        for char in text:
            if '가' <= char <= '힣':  # 한글 완성형
                # 유니코드 계산: (char_code - '가') // 588
                chosung_code = (ord(char) - ord('가')) // 588
                chosung = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 
                          'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'][chosung_code]
                chosung_list.append(chosung)
            elif 'ㄱ' <= char <= 'ㅎ':  # 이미 초성인 경우
                chosung_list.append(char)
            elif char.isalnum() or char.isspace():  # 영문, 숫자, 공백은 그대로
                chosung_list.append(char.lower())
        
        return ''.join(chosung_list)

    def filter_table(self):
        """검색어에 따라 테이블을 필터링합니다."""
        search_text = self.lineEdit_search.text().strip()
        
        if not search_text:
            # 검색어가 없으면 모든 행 표시
            for row in range(self.tableWidget_sealed.rowCount()):
                self.tableWidget_sealed.setRowHidden(row, False)
            return
        
        # 검색어의 초성 추출
        search_chosung = self._extract_chosung(search_text)
        search_lower = search_text.lower()
        
        # 각 행에 대해 필터링
        for row in range(self.tableWidget_sealed.rowCount()):
            region_item = self.tableWidget_sealed.item(row, 0)
            if not region_item:
                self.tableWidget_sealed.setRowHidden(row, True)
                continue
            
            region = region_item.text()
            region_chosung = self._extract_chosung(region)
            region_lower = region.lower()
            
            # 매칭 조건:
            # 1. 일반 텍스트 포함 검색
            # 2. 초성 검색
            # 3. 부분 일치 (간단하게 검색)
            matches = (
                search_lower in region_lower or
                search_chosung in region_chosung or
                region_lower.startswith(search_lower) or
                region_chosung.startswith(search_chosung)
            )
            
            self.tableWidget_sealed.setRowHidden(row, not matches)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = RegionManagerDialog()
    dialog.show()
    sys.exit(app.exec())
