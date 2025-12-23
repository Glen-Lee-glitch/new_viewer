import math
import pandas as pd
import psycopg2
from contextlib import closing

from PyQt6.QtWidgets import (
    QDialog, QTableWidget, QTableWidgetItem, 
    QVBoxLayout, QWidget, QHeaderView, QPushButton, QMessageBox, 
    QAbstractItemView, QStyleOptionViewItem, QStyleOptionButton, 
    QStyle, QStyledItemDelegate, QHBoxLayout, QLabel, QApplication,
    QCheckBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QPainter
from pathlib import Path

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

class SubsidyHistoryDialog(QDialog):
    # 시그널 정의
    work_started = pyqtSignal(list, dict)  # 작업 시작 시그널 (파일 경로 리스트, 메타데이터)
    ai_review_requested = pyqtSignal(str) # AI 검토 요청 시그널 (RN)

    def __init__(self, parent=None, worker_id=None):
        super().__init__(parent)
        self.worker_id = worker_id
        self.setWindowTitle("지원금 신청 전체 목록")
        self.resize(1000, 650)
        
        self.current_page = 0  # 현재 페이지 (0부터 시작)
        self.page_size = 100   # 페이지 당 행 수
        
        # 메인 레이아웃 설정
        layout = QVBoxLayout(self)
        
        # 컨트롤 영역
        control_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("데이터 새로고침")
        self.refresh_btn.clicked.connect(self.populate_table)
        
        # 필터 그룹
        self.filter_group = QButtonGroup(self)
        
        self.radio_all = QRadioButton("전체")
        self.radio_my = QRadioButton("내 작업건")
        self.radio_unfinished = QRadioButton("미작업건")
        
        self.filter_group.addButton(self.radio_all, 0)
        self.filter_group.addButton(self.radio_my, 1)
        self.filter_group.addButton(self.radio_unfinished, 2)
        
        self.radio_all.setChecked(True)
        # 필터 변경 시 페이지 리셋 및 갱신 (arguments 무시를 위해 lambda 사용)
        self.filter_group.buttonClicked.connect(lambda: self._on_filter_changed())

        # '추후 신청' 필터 체크박스 추가
        self.filter_checkbox = QCheckBox("'추후 신청'만 보기")
        self.filter_checkbox.stateChanged.connect(lambda: self._on_filter_changed())
        
        self.status_label = QLabel("준비")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.radio_all)
        control_layout.addWidget(self.radio_my)
        control_layout.addWidget(self.radio_unfinished)
        control_layout.addWidget(self.filter_checkbox)
        control_layout.addStretch()
        control_layout.addWidget(self.status_label)
        layout.addLayout(control_layout)
        
        # 테이블 위젯 설정
        self.table_widget = QTableWidget()
        self.setup_table()
        layout.addWidget(self.table_widget)
        
        # 페이지네이션 컨트롤 영역
        pagination_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("◀ 이전")
        self.prev_btn.setFixedWidth(100)
        self.prev_btn.clicked.connect(self.go_prev_page)
        
        self.page_label = QLabel("1 페이지")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setFixedWidth(120)
        self.page_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.next_btn = QPushButton("다음 ▶")
        self.next_btn.setFixedWidth(100)
        self.next_btn.clicked.connect(self.go_next_page)
        
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        
        layout.addLayout(pagination_layout)
        
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
            self._start_work_by_row(row)

    def _start_work_by_row(self, row):
        """특정 행의 작업을 시작한다."""
        table = self.table_widget
        rn_item = table.item(row, 1)  # RN은 1번 컬럼

        # AI 결과가 있는 경우 -> AI 결과 요청 시그널 emit
        ai_item = table.item(row, 4)
        if ai_item and ai_item.text() == 'O':
            if rn_item:
                self.ai_review_requested.emit(rn_item.text())

        # 파일 경로는 SQL의 original_filepath에서 가져옴
        row_data = rn_item.data(Qt.ItemDataRole.UserRole)
        if not row_data or not isinstance(row_data, dict):
            QMessageBox.warning(self, "파일 없음", "데이터를 불러올 수 없습니다.")
            return

        worker = row_data.get('worker')
        finished_file_path = row_data.get('finished_file_path')
        original_file_path = row_data.get('original_filepath')

        file_path = ""
        # 작업자가 할당된 경우, finished_file_path 우선 사용
        if worker and finished_file_path:
            file_path = finished_file_path
        # 그 외의 경우 original_filepath 사용
        else:
            if original_file_path:
                file_path = original_file_path

        if not file_path:
            QMessageBox.warning(self, "파일 없음", "연결된 파일 경로가 없습니다.")
            return

        # 정규화된 파일 경로
        resolved_path = Path(file_path)
        if not resolved_path.exists():
            QMessageBox.warning(
                self,
                "파일 없음",
                f"경로를 찾을 수 없습니다.\n{resolved_path}"
            )
            return

        # 메타데이터 구성 (PdfLoadWidget과 동일한 구조)
        metadata = row_data.copy()
        
        # 다이얼로그를 먼저 숨겨서 사용자에게 즉각적인 피드백 제공
        self.hide()
        
        # 원본 파일 경로를 그대로 전달 (pdf_render.py에서 분할 파일 ex. RN123_1.pdf, RN123_2.pdf 등 감지 처리)
        self.work_started.emit([str(resolved_path)], metadata)
        
        # 다이얼로그 닫기
        self.accept()

    def _on_filter_changed(self):
        """필터 상태 변경 시 페이지를 0으로 초기화하고 테이블을 새로고침합니다."""
        self.current_page = 0
        self.populate_table()

    def fetch_data(self):
        """데이터베이스에서 페이징 처리하여 데이터를 조회합니다. (PostgreSQL 버전)"""
        try:
            with closing(psycopg2.connect(**DB_CONFIG)) as connection:
                # 기본 쿼리 가져오기
                base_query = _build_subsidy_query_base()
                
                # 기본 조건 설정 (WHERE 절 시작)
                where_clause = 'WHERE r.last_received_date >= %s '
                params = ['2025-01-01 00:00:00']
                
                # 라디오 버튼 필터 적용
                if self.radio_my.isChecked():
                    if self.worker_id:
                        where_clause += "AND r.worker_id = %s "
                        params.append(self.worker_id)
                    else:
                        # worker_id가 없으면 결과가 나오지 않도록 처리 (혹은 전체 보기?)
                        # 여기서는 worker_id IS NOT NULL AND worker_id = -1 같은 불가능한 조건을 추가하거나
                        # 단순히 빈 결과를 반환하도록 할 수 있음.
                        # 편의상 worker_id가 없으면 아무것도 안 보이게 함
                        where_clause += "AND 1=0 " 
                elif self.radio_unfinished.isChecked():
                    where_clause += "AND r.worker_id IS NULL "
                
                # '추후 신청' 필터 체크박스 적용
                if self.filter_checkbox.isChecked():
                    where_clause += "AND r.status = '추후 신청' "
                
                # 페이지네이션을 위한 OFFSET 계산
                offset = self.current_page * self.page_size
                
                # LIMIT과 OFFSET을 사용하여 쿼리 완성 (PostgreSQL 형식)
                query = base_query + where_clause + (
                    'ORDER BY r.last_received_date DESC '
                    f'LIMIT {self.page_size} OFFSET {offset}'
                )
                
                df = pd.read_sql(query, connection, params=tuple(params))
                
                return df
                
        except Exception as e:
            QMessageBox.critical(self, "에러", f"데이터 조회 중 오류 발생:\n{e}")
            return pd.DataFrame()

    def go_prev_page(self):
        """이전 페이지로 이동"""
        if self.current_page > 0:
            self.current_page -= 1
            self.populate_table()

    def go_next_page(self):
        """다음 페이지로 이동"""
        self.current_page += 1
        self.populate_table()

    def populate_table(self):
        """테이블에 데이터를 채웁니다."""
        table = self.table_widget
        
        # UI 업데이트
        self.page_label.setText(f"{self.current_page + 1} 페이지")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.status_label.setText("데이터 로딩 중...")
        QApplication.processEvents()
        
        df = self.fetch_data()
        
        if df.empty:
            if self.current_page > 0:
                self.status_label.setText("데이터 없음 (마지막 페이지)")
            else:
                self.status_label.setText("데이터 없음")
            table.setRowCount(0)
            self.next_btn.setEnabled(False)
            return

        # 가져온 데이터가 페이지 크기보다 작으면 마지막 페이지임
        if len(df) < self.page_size:
            self.next_btn.setEnabled(False)
        else:
            self.next_btn.setEnabled(True)

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
                'finished_file_path': row.get('finished_file_path', ''),  # 추가됨
                'original_filepath': row.get('original_filepath', ''),    # 추가됨
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
            table.setItem(row_index, 0, QTableWidgetItem(row_data['region']))
            
            rn_item = QTableWidgetItem(row_data['rn'])
            rn_item.setData(Qt.ItemDataRole.UserRole, row_data)
            table.setItem(row_index, 1, rn_item)
            
            table.setItem(row_index, 2, QTableWidgetItem(row_data['worker']))
            table.setItem(row_index, 3, QTableWidgetItem(row_data['result']))
            table.setItem(row_index, 4, QTableWidgetItem(ai_status))
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

