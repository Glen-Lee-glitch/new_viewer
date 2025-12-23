import sys
import os
from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import (
    QDialog, QTableWidgetItem, QCheckBox, QHBoxLayout, QWidget, 
    QMessageBox, QApplication, QHeaderView, QDateTimeEdit
)
from PyQt6.QtCore import Qt, QDateTime, QDate, QTime
import json
from datetime import datetime

# 프로젝트 루트 경로 추가 (core 모듈 임포트용)
sys.path.append(str(Path(__file__).parent.parent))

class RegionManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "region_manager.ui"
        uic.loadUi(str(ui_path), self)
        
        self.setWindowTitle("지자체 설정 관리")
        
        # 테이블 헤더 설정 (tab_1: 원본대조필)
        self.tableWidget_sealed.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_sealed.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tableWidget_sealed.setColumnWidth(1, 150)
        
        # 버튼 연결 (tab_1)
        self.btn_refresh.clicked.connect(self.load_data)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_close.clicked.connect(self.close)
        
        # 검색 기능 연결 (tab_1)
        self.lineEdit_search.textChanged.connect(self.filter_table)
        
        # 테이블 헤더 설정 (tab_3: 지원_서류)
        self.tableWidget_documents.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_documents.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_documents.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        # 검색 기능 연결 (tab_3)
        self.lineEdit_search_docs.textChanged.connect(self.filter_table_documents)
        
        # tab_3 더블 클릭 이벤트 연결
        self.tableWidget_documents.itemDoubleClicked.connect(self._on_document_item_double_clicked)

        # --- tab_after_open (추후 오픈) 설정 ---
        # 테이블 헤더 설정
        self.tableWidget_after_open.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tableWidget_after_open.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        # 버튼 연결
        self.btn_refresh_after.clicked.connect(self.load_after_open_data)
        self.btn_save_after.clicked.connect(self.save_after_open_data)
        
        # 검색 기능 연결
        self.lineEdit_search_after.textChanged.connect(self.filter_table_after_open)
        
        # 데이터 저장소
        self.original_data = {} # {region: is_apply_sealed}
        self.checkbox_map = {} # {region: QCheckBox}
        self.document_data = {} # {region_id: notification_apply dict}
        self.original_after_data = {} # {region: after_date_str}
        
        # 데이터 로드
        self.load_data()
        self.load_tab3_data()
        self.load_after_open_data()
        
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

    def filter_table_documents(self):
        """검색어에 따라 tab_3의 서류 테이블을 필터링합니다."""
        search_text = self.lineEdit_search_docs.text().strip()
        
        if not search_text:
            # 검색어가 없으면 모든 행 표시
            for row in range(self.tableWidget_documents.rowCount()):
                self.tableWidget_documents.setRowHidden(row, False)
            return
        
        # 검색어의 초성 추출
        search_chosung = self._extract_chosung(search_text)
        search_lower = search_text.lower()
        
        # 각 행에 대해 필터링
        for row in range(self.tableWidget_documents.rowCount()):
            region_item = self.tableWidget_documents.item(row, 0)
            if not region_item:
                self.tableWidget_documents.setRowHidden(row, True)
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
            
            self.tableWidget_documents.setRowHidden(row, not matches)

    def _format_document_summary(self, items):
        """서류 목록을 요약 텍스트로 변환 (예: "초본 외 2건")"""
        if not items or len(items) == 0:
            return "(없음)"
        if len(items) == 1:
            return items[0]
        return f"{items[0]} 외 {len(items)-1}건"

    def load_tab3_data(self):
        """tab_3의 서류 데이터를 로드합니다."""
        try:
            from core.sql_manager import DB_CONFIG
            import psycopg2
            from contextlib import closing
            
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    query = """
                        SELECT rm.region_id, rm.region, g.notification_apply 
                        FROM region_metadata rm 
                        LEFT JOIN "공고문" g ON rm.region_id = g.region_id 
                        ORDER BY rm.region
                    """
                    cursor.execute(query)
                    rows = cursor.fetchall()
            
            if not rows:
                self.tableWidget_documents.setRowCount(0)
                return
            
            self.tableWidget_documents.setRowCount(len(rows))
            self.document_data = {}
            
            for row_idx, (region_id, region, notification_apply) in enumerate(rows):
                # region_id를 UserRole로 저장
                region_item = QTableWidgetItem(region)
                region_item.setData(Qt.ItemDataRole.UserRole, region_id)
                region_item.setFlags(region_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_documents.setItem(row_idx, 0, region_item)
                
                # notification_apply 파싱
                if notification_apply:
                    if isinstance(notification_apply, str):
                        data = json.loads(notification_apply)
                    else:
                        data = notification_apply
                else:
                    data = {"general_documents": [], "additional_documents": []}
                
                # 데이터 저장
                self.document_data[region_id] = data
                
                # 일반서류 요약
                general_items = data.get("general_documents", [])
                general_summary = self._format_document_summary(general_items)
                general_item = QTableWidgetItem(general_summary)
                general_item.setFlags(general_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_documents.setItem(row_idx, 1, general_item)
                
                # 추가서류 요약
                additional_items = data.get("additional_documents", [])
                additional_summary = self._format_document_summary(additional_items)
                additional_item = QTableWidgetItem(additional_summary)
                additional_item.setFlags(additional_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_documents.setItem(row_idx, 2, additional_item)
            
            # 로드 후 현재 검색어에 맞춰 필터링 적용
            self.filter_table_documents()
                
        except Exception as e:
            QMessageBox.critical(self, "오류", f"서류 데이터를 로드하는 중 오류가 발생했습니다: {str(e)}")
            import traceback
            traceback.print_exc()

    def _on_document_item_double_clicked(self, item):
        """서류 항목 더블 클릭 시 수정 다이얼로그를 엽니다."""
        row = item.row()
        region_item = self.tableWidget_documents.item(row, 0)
        if not region_item:
            return
        
        region_id = region_item.data(Qt.ItemDataRole.UserRole)
        region_name = region_item.text()
        
        # 현재 데이터 가져오기
        current_data = self.document_data.get(region_id, {"general_documents": [], "additional_documents": []})
        
        # 수정 다이얼로그 열기
        from widgets.document_edit_dialog import DocumentEditDialog
        dialog = DocumentEditDialog(region_name, current_data, self)
        
        if dialog.exec():
            # 수정된 데이터 저장
            updated_data = dialog.get_data()
            self._save_document_data(region_id, updated_data)
            # 테이블 새로고침
            self.load_tab3_data()

    def _save_document_data(self, region_id, data):
        """서류 데이터를 DB에 저장합니다 (UPSERT)."""
        try:
            from core.sql_manager import DB_CONFIG
            import psycopg2
            from contextlib import closing
            import json
            
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    # UPSERT: 존재하면 UPDATE, 없으면 INSERT
                    cursor.execute("""
                        INSERT INTO "공고문" (region_id, notification_apply)
                        VALUES (%s, %s::jsonb)
                        ON CONFLICT (region_id) 
                        DO UPDATE SET notification_apply = EXCLUDED.notification_apply
                    """, (region_id, json.dumps(data, ensure_ascii=False)))
                conn.commit()
                
            QMessageBox.information(self, "완료", "서류 정보가 저장되었습니다.")
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다: {str(e)}")
            import traceback
            traceback.print_exc()

    def load_after_open_data(self):
        """region_metadata에서 after_date 정보를 로드합니다."""
        try:
            from core.sql_manager import DB_CONFIG
            import psycopg2
            from contextlib import closing
            
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT region, after_date FROM region_metadata ORDER BY region")
                    rows = cursor.fetchall()
            
            self.tableWidget_after_open.setRowCount(len(rows))
            self.original_after_data = {}
            self.after_date_widgets = {} # 위젯 참조 초기화
            
            for row_idx, (region, after_date) in enumerate(rows):
                # 1. 지역 (Read-only)
                region_item = QTableWidgetItem(region)
                region_item.setFlags(region_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.tableWidget_after_open.setItem(row_idx, 0, region_item)
                
                # 2. 오픈 예정일 (CheckBox + QDateTimeEdit)
                container = QWidget()
                layout = QHBoxLayout(container)
                layout.setContentsMargins(5, 0, 5, 0)
                layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                
                chk_enable = QCheckBox()
                dt_edit = QDateTimeEdit()
                dt_edit.setDisplayFormat("yyyy-MM-dd HH")
                dt_edit.setCalendarPopup(True)
                
                if after_date:
                    chk_enable.setChecked(True)
                    dt_edit.setEnabled(True)
                    # datetime 객체를 QDateTime으로 변환
                    if isinstance(after_date, datetime):
                        qdt = QDateTime(
                            after_date.year, after_date.month, after_date.day,
                            after_date.hour, 0, 0 # 분, 초는 0으로 초기화
                        )
                        dt_edit.setDateTime(qdt)
                    else:
                        # 폴백: 현재 날짜의 오전 9시
                        qdt = QDateTime.currentDateTime()
                        qdt.setTime(QTime(9, 0, 0))
                        dt_edit.setDateTime(qdt)
                else:
                    chk_enable.setChecked(False)
                    dt_edit.setEnabled(False)
                    # 날짜가 없을 경우 기본값을 내일 오전 9시로 설정
                    qdt = QDateTime.currentDateTime().addDays(1)
                    qdt.setTime(QTime(9, 0, 0))
                    dt_edit.setDateTime(qdt)
                
                # 체크박스 상태 변경 시 DateTimeEdit 활성/비활성 토글
                chk_enable.stateChanged.connect(lambda state, de=dt_edit: de.setEnabled(state == Qt.CheckState.Checked.value))
                
                layout.addWidget(chk_enable)
                layout.addWidget(dt_edit)
                
                self.tableWidget_after_open.setCellWidget(row_idx, 1, container)
                
                # 데이터 저장 (위젯 참조 및 원본 데이터)
                self.after_date_widgets[region] = (chk_enable, dt_edit)
                self.original_after_data[region] = after_date # datetime object or None
            
            self.filter_table_after_open()
                
        except Exception as e:
            QMessageBox.critical(self, "오류", f"오픈 예정일 데이터를 로드하는 중 오류가 발생했습니다: {str(e)}")
            import traceback
            traceback.print_exc()

    def filter_table_after_open(self):
        """검색어에 따라 추후 오픈 탭 테이블을 필터링합니다."""
        search_text = self.lineEdit_search_after.text().strip()
        
        if not search_text:
            for row in range(self.tableWidget_after_open.rowCount()):
                self.tableWidget_after_open.setRowHidden(row, False)
            return
        
        search_chosung = self._extract_chosung(search_text)
        search_lower = search_text.lower()
        
        for row in range(self.tableWidget_after_open.rowCount()):
            region_item = self.tableWidget_after_open.item(row, 0)
            if not region_item:
                self.tableWidget_after_open.setRowHidden(row, True)
                continue
            
            region = region_item.text()
            region_chosung = self._extract_chosung(region)
            region_lower = region.lower()
            
            matches = (
                search_lower in region_lower or
                search_chosung in region_chosung or
                region_lower.startswith(search_lower) or
                region_chosung.startswith(search_chosung)
            )
            
            self.tableWidget_after_open.setRowHidden(row, not matches)

    def save_after_open_data(self):
        """오픈 예정일 변경사항을 저장합니다."""
        changed_data = []
        today = datetime.now().date()
        
        for region, (chk, dt_edit) in self.after_date_widgets.items():
            original_val = self.original_after_data.get(region)
            
            new_val = None
            if chk.isChecked():
                # QDateTime -> python datetime
                qdt = dt_edit.dateTime()
                new_val = datetime(
                    qdt.date().year(), qdt.date().month(), qdt.date().day(),
                    qdt.time().hour(), 0, 0 # 분, 초는 무조건 0으로 저장
                )
            
            # 값 비교 (None vs None, datetime vs datetime)
            is_changed = False
            if original_val is None and new_val is not None:
                is_changed = True
            elif original_val is not None and new_val is None:
                is_changed = True
            elif original_val is not None and new_val is not None:
                # 초 단위까지만 비교 (microseconds 무시)
                if original_val.replace(microsecond=0) != new_val.replace(microsecond=0):
                    is_changed = True
            
            if is_changed:
                # 검증 로직: 금일 포함 이전 날짜는 설정 불가 (내일 이후만 가능)
                if new_val is not None and new_val.date() <= today:
                    QMessageBox.warning(
                        self, 
                        "검증 오류", 
                        f"[{region}] 오픈 예정일은 내일 이후 날짜로만 설정 가능합니다.\n"
                        f"(오늘 날짜: {today.strftime('%Y-%m-%d')})"
                    )
                    return # 저장 중단
                
                changed_data.append((new_val, region))
        
        if not changed_data:
            QMessageBox.information(self, "알림", "변경된 내용이 없습니다.")
            return
            
        try:
            from core.sql_manager import DB_CONFIG
            import psycopg2
            from contextlib import closing
            
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    for val, region in changed_data:
                        cursor.execute(
                            "UPDATE region_metadata SET after_date = %s WHERE region = %s",
                            (val, region)
                        )
                conn.commit()
                
            QMessageBox.information(self, "완료", f"{len(changed_data)}건의 변경사항이 저장되었습니다.")
            self.load_after_open_data() # 새로고침
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = RegionManagerDialog()
    dialog.show()
    sys.exit(app.exec())
