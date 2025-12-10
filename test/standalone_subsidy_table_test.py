import sys
from pathlib import Path

# 프로젝트 루트 경로를 sys.path에 추가하여 모듈 import가 가능하도록 설정
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

import math
import pandas as pd
import pymysql
from datetime import datetime
from contextlib import closing

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
    QVBoxLayout, QWidget, QHeaderView, QPushButton, QMessageBox, 
    QAbstractItemView, QStyleOptionViewItem, QStyleOptionButton, 
    QStyle, QStyledItemDelegate, QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QPainter

from core.sql_manager import DB_CONFIG, _build_subsidy_query_base

# 하이라이트를 위한 커스텀 데이터 역할 정의
HighlightRole = Qt.ItemDataRole.UserRole + 1

class HighlightDelegate(QStyledItemDelegate):
    """특정 데이터 역할에 따라 배경색을 변경하는 델리게이트"""
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        highlight_color = index.data(HighlightRole)
        
        if highlight_color:
            painter.save()
            painter.fillRect(option.rect, QBrush(QColor(highlight_color)))
            painter.restore()
            super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

class ButtonDelegate(QStyledItemDelegate):
    """버튼 모양을 그리는 델리게이트 (최적화용)"""
    def __init__(self, parent=None, text="보기"):
        super().__init__(parent)
        self.text = text

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        super().paint(painter, option, index)
        
        button_opt = QStyleOptionButton()
        margin = 4
        button_opt.rect = option.rect.adjusted(margin, margin, -margin, -margin)
        button_opt.text = self.text
        button_opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
        
        QApplication.style().drawControl(QStyle.ControlElement.CE_PushButton, button_opt, painter)

class StandaloneSubsidyTable(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("지원금 신청 목록 테스트 (100 rows)")
        self.resize(1000, 600)
        
        # 메인 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 컨트롤 영역
        control_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("데이터 새로고침")
        self.refresh_btn.clicked.connect(self.populate_table)
        self.status_label = QLabel("준비")
        
        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # 테이블 위젯 설정
        self.table_widget = QTableWidget()
        self.setup_table()
        layout.addWidget(self.table_widget)
        
        # 초기 데이터 로드
        self.populate_table()

    def setup_table(self):
        """테이블 초기 설정"""
        table = self.table_widget
        # 컬럼: 지역, RN, 작업자, 결과, AI, 보기
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(['지역', 'RN', '작업자', '결과', 'AI', '보기'])

        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # 델리게이트 설정
        table.setItemDelegate(HighlightDelegate(table))
        table.setItemDelegateForColumn(5, ButtonDelegate(table, "시작"))
        
        # 클릭 이벤트 연결
        table.cellClicked.connect(self._handle_cell_clicked)

    def _handle_cell_clicked(self, row, column):
        """테이블 셀 클릭 핸들러"""
        if column == 5: # 버튼 컬럼
            rn_item = self.table_widget.item(row, 1)
            rn = rn_item.text() if rn_item else "Unknown"
            QMessageBox.information(self, "작업 시작", f"RN: {rn}\n작업을 시작합니다.")

    def fetch_data_limit_100(self):
        """데이터베이스에서 최대 100개의 데이터를 조회합니다."""
        try:
            with closing(pymysql.connect(**DB_CONFIG)) as connection:
                # 기본 쿼리 가져오기
                base_query = _build_subsidy_query_base()
                
                # LIMIT 100으로 설정하여 쿼리 완성
                query = base_query + (
                    "WHERE sa.recent_received_date >= %s "
                    "ORDER BY sa.recent_received_date DESC "
                    "LIMIT 100"
                )
                params = ('2025-01-01 00:00',) # 날짜 조건은 넉넉하게 설정
                
                df = pd.read_sql(query, connection, params=params)
                
                # 이상치 계산 로직 (sql_manager에서 사용하는 로직과 유사하게 처리 필요하지만, 
                # 여기서는 테스트 목적이므로 간단히 처리하거나 필요한 경우 sql_manager의 로직을 복사해와야 함.
                # 편의상 outlier 컬럼이 쿼리 결과에 포함되어 있다고 가정하고(쿼리에 계산 로직 있음),
                # 파이썬 레벨의 추가 계산 로직은 생략하거나 간단히 구현)
                
                return df
                
        except Exception as e:
            QMessageBox.critical(self, "에러", f"데이터 조회 중 오류 발생:\n{e}")
            return pd.DataFrame()

    def populate_table(self):
        """테이블에 데이터를 채웁니다."""
        table = self.table_widget
        self.status_label.setText("데이터 로딩 중...")
        QApplication.processEvents()
        
        df = self.fetch_data_limit_100()
        
        if df.empty:
            table.setRowCount(0)
            self.status_label.setText("데이터 없음")
            return

        table.setRowCount(len(df))
        
        for row_index, (_, row) in enumerate(df.iterrows()):
            # 데이터 정제
            row_data = {
                'rn': self._sanitize_text(row.get('RN', '')),
                'region': self._sanitize_text(row.get('region', '')),
                'worker': self._sanitize_text(row.get('worker', '')),
                'result': self._sanitize_text(row.get('result', '')),
                'urgent': row.get('urgent', 0),
                'mail_count': row.get('mail_count', 0),
                # AI 관련 플래그들
                '구매계약서': row.get('구매계약서', 0),
                '초본': row.get('초본', 0),
                '공동명의': row.get('공동명의', 0),
                'is_법인': row.get('is_법인', 0),
            }

            # AI 상태 계산
            ai_status = 'X'
            구매계약서 = row_data['구매계약서'] == 1
            초본 = row_data['초본'] == 1
            공동명의 = row_data['공동명의'] == 1
            is_법인 = row_data['is_법인'] == 1

            if 구매계약서 and (초본 or 공동명의 or is_법인):
                ai_status = 'O'

            # 아이템 생성 및 설정
            # 0: 지역
            table.setItem(row_index, 0, QTableWidgetItem(row_data['region']))
            
            # 1: RN (데이터 저장)
            rn_item = QTableWidgetItem(row_data['rn'])
            rn_item.setData(Qt.ItemDataRole.UserRole, row_data)
            table.setItem(row_index, 1, rn_item)
            
            # 2: 작업자
            table.setItem(row_index, 2, QTableWidgetItem(row_data['worker']))
            
            # 3: 결과
            table.setItem(row_index, 3, QTableWidgetItem(row_data['result']))
            
            # 4: AI
            table.setItem(row_index, 4, QTableWidgetItem(ai_status))
            
            # 5: 버튼 (빈 텍스트, 델리게이트가 처리)
            table.setItem(row_index, 5, QTableWidgetItem(""))

            # 하이라이트 처리
            self._apply_highlight(table, row_index, row_data)

        self.status_label.setText(f"로딩 완료 ({len(df)}건)")

    def _apply_highlight(self, table, row_index, row_data):
        """행 하이라이트 적용"""
        if row_data['urgent'] == 1:
            highlight_color = QColor(220, 53, 69, 180)  # 빨간색
            text_color = QColor("white")
            
            for col in range(table.columnCount()):
                item = table.item(row_index, col)
                if item:
                    item.setData(HighlightRole, highlight_color)
                    item.setForeground(text_color)
                    
        elif row_data.get('mail_count', 0) >= 2:
            mail_highlight_color = QColor(255, 249, 170, 180)  # 연한 노란색
            mail_text_color = QColor("black")
            
            rn_item = table.item(row_index, 1)
            if rn_item:
                rn_item.setData(HighlightRole, mail_highlight_color)
                rn_item.setForeground(mail_text_color)

    @staticmethod
    def _sanitize_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            if math.isnan(value):
                return ""
            return str(int(value)) if value.is_integer() else str(value)
        value_str = str(value).strip()
        return "" if value_str.lower() == "nan" else value_str

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StandaloneSubsidyTable()
    window.show()
    sys.exit(app.exec())

