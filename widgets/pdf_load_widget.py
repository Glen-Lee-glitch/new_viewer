from pathlib import Path
import math
import pandas as pd
from datetime import datetime
import pytz

from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, QPoint, Qt, QSettings, QThreadPool
from PyQt6.QtGui import QColor, QBrush, QPainter
from PyQt6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QWidget,
    QTableWidgetItem,
    QMenu,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QInputDialog,
    QButtonGroup,
    QApplication,
    QStyle,
    QStyleOptionButton,
    QAbstractItemView,
)

from core.sql_manager import (
    fetch_recent_subsidy_applications, 
    fetch_application_data_by_rn, 
    fetch_give_works,
    fetch_today_subsidy_applications_by_worker,
    fetch_today_unfinished_subsidy_applications,
    get_email_by_thread_id,
    check_gemini_flags,
    update_give_works_worker,
    update_rns_worker_id,
    update_subsidy_status_if_new
)
from core.utility import get_converted_path
from core.workers import DbFetchWorker
from widgets.email_view_dialog import EmailViewDialog
from widgets.detail_form_dialog import DetailFormDialog
from widgets.alert_dialog import show_alert, show_toast
from widgets.subsidy_history_dialog import SubsidyHistoryDialog
from widgets.give_memo_dialog import GiveMemoDialog

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
    """버튼 모양을 그리는 델리게이트"""
    def __init__(self, parent=None, text="시작"):
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


class PdfLoadWidget(QWidget):
    """PDF 로드 영역 위젯"""
    pdf_selected = pyqtSignal(list, dict)
    work_started = pyqtSignal(list, dict)
    rn_selected = pyqtSignal(str)
    ai_review_requested = pyqtSignal(str)
    data_refreshed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._pdf_view_widget = None
        self._is_context_menu_work = False
        self._filter_mode = 'all'
        self._worker_name = ''
        self._worker_id = None
        self._payment_request_load_enabled = True
        self._is_first_load = True
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """UI 파일을 로드하고 초기화"""
        ui_path = Path(__file__).parent.parent / "ui" / "pdf_load_area.ui"
        uic.loadUi(str(ui_path), self)
        
        if hasattr(self, 'center_open_btn'): self.center_open_btn.setText("로컬에서 PDF 열기")
        if hasattr(self, 'center_open_rn_btn'): self.center_open_rn_btn.setText("RN번호로 열기")
        if hasattr(self, 'center_refresh_btn'): self.center_refresh_btn.setText("데이터 새로고침")
        
        if hasattr(self, 'complement_table_widget'): self.setup_table()
        if hasattr(self, 'tableWidget'): self.setup_give_works_table()
        
        self._setup_filter_buttons()
    
    def setup_table(self):
        """지원 테이블 위젯 초기 설정"""
        table = self.complement_table_widget
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(['지역', 'RN', '작업자', '상태', 'AI', 'PDF열기'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(False)
        table.setItemDelegate(HighlightDelegate(table))
        table.setItemDelegateForColumn(4, ButtonDelegate(table, "보기"))
        table.setItemDelegateForColumn(5, ButtonDelegate(table, "시작"))

        self.populate_recent_subsidy_rows()
        table.customContextMenuRequested.connect(self.show_context_menu)
        table.cellClicked.connect(self._handle_cell_clicked)
        table.itemSelectionChanged.connect(lambda: self.rn_selected.emit(self.get_selected_rn() or ""))
    
    def setup_give_works_table(self):
        """지급 테이블 위젯 초기 설정"""
        table = self.tableWidget
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['RN', '작업자', '지역', '상태', 'PDF열기'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setItemDelegateForColumn(4, ButtonDelegate(table, "시작"))
        table.cellClicked.connect(self._handle_give_works_cell_clicked)
        self.populate_give_works_rows()

    def refresh_data(self, force_refresh_give_works: bool = False):
        """데이터 새로고침 (비동기)"""
        # 1. 지원 테이블
        fetch_func = None
        args = []
        if self._filter_mode == 'all': fetch_func = fetch_recent_subsidy_applications
        elif self._filter_mode == 'my':
            if not self._worker_id: self.complement_table_widget.setRowCount(0)
            else:
                fetch_func = fetch_today_subsidy_applications_by_worker
                args = [self._worker_id]
        elif self._filter_mode == 'unfinished': fetch_func = fetch_today_unfinished_subsidy_applications
        
        if fetch_func:
            worker = DbFetchWorker(fetch_func, *args)
            worker.signals.fetched.connect(self._on_subsidy_data_fetched)
            QThreadPool.globalInstance().start(worker)

        # 2. 지급 테이블
        if (force_refresh_give_works or self._payment_request_load_enabled) and hasattr(self, 'tableWidget'):
            p_worker = DbFetchWorker(fetch_give_works)
            p_worker.signals.fetched.connect(self._on_payment_data_fetched)
            QThreadPool.globalInstance().start(p_worker)

    def _on_subsidy_data_fetched(self, df):
        self.populate_recent_subsidy_rows(df)
        self.data_refreshed.emit()

    def _on_payment_data_fetched(self, df):
        self.populate_give_works_rows(df)

    def populate_recent_subsidy_rows(self, df=None):
        """지원 테이블 데이터 채우기 (최적화)"""
        table = self.complement_table_widget
        if df is None:
            try:
                if self._filter_mode == 'all': df = fetch_recent_subsidy_applications()
                elif self._filter_mode == 'my':
                    if not self._worker_id: return
                    df = fetch_today_subsidy_applications_by_worker(self._worker_id)
                elif self._filter_mode == 'unfinished': df = fetch_today_unfinished_subsidy_applications()
            except: return

        if df is None or df.empty:
            table.setRowCount(0)
            return

        table.setUpdatesEnabled(False)
        try:
            self._check_unassigned_subsidies(df)
            table.setRowCount(len(df))
            for i, (_, row) in enumerate(df.iterrows()):
                row_data = {
                    'rn': self._sanitize_text(row.get('RN', '')),
                    'region': self._sanitize_text(row.get('region', '')),
                    'worker': self._sanitize_text(row.get('worker', '')),
                    'name': self._sanitize_text(row.get('name', '')),
                    'special_note': self._sanitize_text(row.get('special_note', '')),
                    'recent_thread_id': self._sanitize_text(row.get('recent_thread_id', '')),
                    'file_rendered': row.get('file_rendered', 0),
                    'urgent': row.get('urgent', 0),
                    'mail_count': row.get('mail_count', 0),
                    'outlier': self._sanitize_text(row.get('outlier', '')),
                    'original_filepath': self._normalize_file_path(row.get('original_filepath')),
                    'finished_file_path': self._normalize_file_path(row.get('finished_file_path')),
                    'result': self._sanitize_text(row.get('result', '')),
                    'all_ai': row.get('all_ai', 0),
                    '차종': row.get('차종', ''),
                    'child_birth_date': row.get('child_birth_date', ''),
                    'issue_date': row.get('issue_date', '')
                }

                table.setItem(i, 0, QTableWidgetItem(row_data['region']))
                rn_item = QTableWidgetItem(row_data['rn'])
                rn_item.setData(Qt.ItemDataRole.UserRole, row_data)
                table.setItem(i, 1, rn_item)
                table.setItem(i, 2, QTableWidgetItem(row_data['worker']))
                table.setItem(i, 3, QTableWidgetItem(row_data['result']))
                table.setItem(i, 4, QTableWidgetItem('O' if row_data['all_ai'] == 1 else 'X'))
                table.setItem(i, 5, QTableWidgetItem(""))

                if row_data['urgent'] == 1:
                    color = QColor(220, 53, 69, 180)
                    for c in range(table.columnCount()):
                        it = table.item(i, c)
                        if it:
                            it.setData(HighlightRole, color)
                            it.setForeground(QColor("white"))
                elif row_data.get('mail_count', 0) >= 2:
                    rn_item.setData(HighlightRole, QColor(255, 249, 170, 180))
            self._apply_ai_filter()
        finally:
            table.setUpdatesEnabled(True)

    def populate_give_works_rows(self, df=None):
        """지급 테이블 데이터 채우기"""
        table = self.tableWidget
        if df is None:
            try: df = fetch_give_works()
            except: return
        if df is None or df.empty:
            table.setRowCount(0)
            return

        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(df))
            for i, (_, row) in enumerate(df.iterrows()):
                row_data = {
                    'rn': self._sanitize_text(row.get('RN', '')),
                    'worker': self._sanitize_text(row.get('worker', '')),
                    'region': self._sanitize_text(row.get('region', '')),
                    'status': self._sanitize_text(row.get('give_status', '')),
                    'memo': self._sanitize_text(row.get('memo', '')),
                    'give_file_path': self._sanitize_text(row.get('give_file_path', ''))
                }
                item = QTableWidgetItem(row_data['rn'])
                item.setData(Qt.ItemDataRole.UserRole, row_data)
                table.setItem(i, 0, item)
                table.setItem(i, 1, QTableWidgetItem(row_data['worker']))
                table.setItem(i, 2, QTableWidgetItem(row_data['region']))
                table.setItem(i, 3, QTableWidgetItem(row_data['status']))
                table.setItem(i, 4, QTableWidgetItem(""))
        finally:
            table.setUpdatesEnabled(True)

    def _handle_cell_clicked(self, row, column):
        if column == 5:
            self._is_context_menu_work = True
            self._start_work_by_row(row)
            self._is_context_menu_work = False
        elif column == 4:
            self._show_gemini_results(row)

    def _handle_give_works_cell_clicked(self, row, column):
        if column == 4:
            table = self.tableWidget
            rn = table.item(row, 0).text().strip()
            existing_worker = table.item(row, 1).text().strip()
            if not existing_worker and self._worker_name:
                if update_give_works_worker(rn, self._worker_name):
                    table.item(row, 1).setText(self._worker_name)
            
            search_dir = Path(get_converted_path(r"C:\Users\HP\Desktop\Tesla\24q4\지급\지급서류\merged"))
            pdf_files = list(search_dir.glob(f"*{rn}*.pdf"))
            if pdf_files:
                self.pdf_selected.emit([str(pdf_files[0])], {'is_give_works': True, 'rn': rn})
            else:
                QMessageBox.warning(self, "파일 없음", f"RN {rn}에 해당하는 PDF 파일을 찾을 수 없습니다.")

    def _start_work_by_row(self, row):
        table = self.complement_table_widget
        rn_item = table.item(row, 1)
        if not rn_item: return
        data = rn_item.data(Qt.ItemDataRole.UserRole)
        rn = data['rn']
        
        if table.item(row, 4).text() == 'O':
            self.ai_review_requested.emit(rn)

        if not data.get('worker'):
            if self._worker_id and update_rns_worker_id(rn, self._worker_id):
                table.item(row, 2).setText(self._worker_name)
                data['worker'] = self._worker_name

        update_subsidy_status_if_new(rn, '처리중')
        table.item(row, 3).setText('처리중')

        path = data.get('finished_file_path') if data.get('worker') and data.get('finished_file_path') else data.get('original_filepath')
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "파일 없음", f"파일을 찾을 수 없습니다: {path}")
            return

        metadata = self._extract_row_metadata(rn_item)
        metadata['is_context_menu_work'] = self._is_context_menu_work
        self.work_started.emit([str(path)], metadata)

    def _check_unassigned_subsidies(self, df):
        if df is None or df.empty: return
        kst = pytz.timezone('Asia/Seoul')
        if not hasattr(self, '_alert_tracker'): self._alert_tracker = {}
        for _, row in df.iterrows():
            rn = row.get('RN')
            worker = str(row.get('worker') or "").strip()
            if row.get('result') == '추후 신청': continue
            if not worker:
                recv_date = row.get('recent_received_date')
                if pd.notna(recv_date):
                    if isinstance(recv_date, str): recv_date = datetime.strptime(recv_date, "%Y-%m-%d %H:%M:%S")
                    if recv_date.tzinfo is None: recv_date = kst.localize(recv_date)
                    if (datetime.now(kst) - recv_date).total_seconds() >= 600:
                        if self._is_first_load: continue
                        if not QApplication.activeWindow() == self.window():
                            state = self._alert_tracker.get(rn, 0)
                            if state == 0 or state == 2:
                                show_toast("미배정 알림", f"10분 이상 미배정: {rn}", self, recv_date)
                                self._alert_tracker[rn] = 1
                            else: self._alert_tracker[rn] = 2
            elif rn in self._alert_tracker: del self._alert_tracker[rn]
        self._is_first_load = False

    def show_context_menu(self, pos):
        table = self.complement_table_widget
        item = table.itemAt(pos)
        if not item: return
        row = item.row()
        data = table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("비고")

        # '외부 작업중' 상태인 경우 'PDF 작업 완료' 액션 추가
        if data.get('result') == '외부 작업중':
            complete_act = menu.addAction("PDF 작업 완료")
            # 액션 실행 시 핸들러 연결
            complete_act.triggered.connect(lambda: self._complete_external_work(data['rn'], row))

        if int(data.get('mail_count', 0)) >= 2:
            menu.addSeparator()
            email_act = menu.addAction("이메일 확인하기")
            
            selected_action = menu.exec(table.viewport().mapToGlobal(pos))
            if selected_action == email_act:
                self._show_email_view(row)
        else:
            menu.exec(table.viewport().mapToGlobal(pos))

    def _show_email_view(self, row):
        data = self.complement_table_widget.item(row, 1).data(Qt.ItemDataRole.UserRole)
        email = get_email_by_thread_id(data.get('recent_thread_id'))
        if email:
            EmailViewDialog(title=email['title'], content=email['content'], parent=self).exec()

    def _show_gemini_results(self, row):
        rn = self.complement_table_widget.item(row, 1).text().strip()
        if check_gemini_flags(rn):
            dialog = DetailFormDialog(parent=self)
            dialog.load_data(rn)
            dialog.show()

    def _complete_external_work(self, rn, row):
        """외부에서 수동으로 작업한 PDF가 완료되었을 때 상태를 'pdf 전처리'로 변경한다."""
        # 1. 파일 존재 확인 로직
        from core.utility import get_converted_path
        kst = pytz.timezone('Asia/Seoul')
        today_date = datetime.now(kst).strftime('%Y-%m-%d')
        worker_folder = self._worker_name if self._worker_name else "미지정"
        
        # 공유 폴더 내 작업자/날짜 경로 구성
        base_dir = get_converted_path(r'\\DESKTOP-KEHQ34D\Users\com\Desktop\GreetLounge\25q4_test\finished_file')
        target_dir = Path(base_dir) / worker_folder / today_date
        
        file_exists = False
        if target_dir.exists():
            # 해당 경로에 RN이 포함된 PDF 파일이 있는지 glob으로 확인
            if list(target_dir.glob(f"*{rn}*.pdf")):
                file_exists = True
                
        if not file_exists:
            QMessageBox.warning(self, "경고", "저장 폴더에 파일이 없습니다!")
            return

        # 2. 파일이 존재하는 경우 기존 status 업데이트 로직 실행
        from core.sql_manager import update_subsidy_status
        
        # update_subsidy_status 내부에서 'pdf 전처리'로 업데이트 시 서류미비 상태 등을 체크함
        if update_subsidy_status(rn, 'pdf 전처리'):
            show_toast("작업 완료", f"RN: {rn} 상태가 'pdf 전처리'로 변경되었습니다.", self)
            # 테이블 UI 즉시 업데이트
            table = self.complement_table_widget
            table.item(row, 3).setText('pdf 전처리')
            # 내부 데이터 객체도 업데이트 (추후 컨텍스트 메뉴 다시 열 때 반영되도록)
            data = table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            if data:
                data['result'] = 'pdf 전처리'
                table.item(row, 1).setData(Qt.ItemDataRole.UserRole, data)
        else:
            QMessageBox.warning(self, "실패", "상태 업데이트에 실패했습니다. (서류미비 요청 등 특정 상태에서는 변경이 제한될 수 있습니다.)")

    def open_by_rn(self):
        rn, ok = QInputDialog.getText(self, "RN 검색", "RN 번호:")
        if ok and rn.strip():
            data = fetch_application_data_by_rn(rn.strip().upper())
            if data:
                if data.get('all_ai'): self.ai_review_requested.emit(data['RN'])
                path = data.get('finished_file_path') if data.get('worker') and data.get('finished_file_path') else data.get('original_filepath')
                path = get_converted_path(path)
                if path and Path(path).exists():
                    self.work_started.emit([path], self._extract_row_metadata_from_dict(data))
                else: QMessageBox.warning(self, "파일 없음", "파일을 찾을 수 없습니다.")

    def _setup_filter_buttons(self):
        self._filter_button_group = QButtonGroup(self)
        self._filter_button_group.addButton(self.radioButton_all_rows, 0)
        self._filter_button_group.addButton(self.radioButton_my_rows, 1)
        self._filter_button_group.addButton(self.radioButton_unfinished_rows, 2)
        self.radioButton_all_rows.setChecked(True)
        self._filter_button_group.buttonClicked.connect(self._on_filter_changed)

    def _on_filter_changed(self, button):
        idx = self._filter_button_group.id(button)
        self._filter_mode = ['all', 'my', 'unfinished'][idx]
        self.populate_recent_subsidy_rows()

    def _apply_ai_filter(self):
        if not hasattr(self, 'ai_checkbox'): return
        checked = self.ai_checkbox.isChecked()
        table = self.complement_table_widget
        for i in range(table.rowCount()):
            table.setRowHidden(i, checked and table.item(i, 4).text() != 'O')

    def setup_connections(self):
        if hasattr(self, 'center_open_btn'): self.center_open_btn.clicked.connect(self.open_pdf_file)
        if hasattr(self, 'center_refresh_btn'): self.center_refresh_btn.clicked.connect(lambda: self.refresh_data(True))
        if hasattr(self, 'center_open_rn_btn'): self.center_open_rn_btn.clicked.connect(self.open_by_rn)
        if hasattr(self, 'pushButton_more'): self.pushButton_more.clicked.connect(lambda: SubsidyHistoryDialog(self, self._worker_id).exec())
        if hasattr(self, 'ai_checkbox'): self.ai_checkbox.stateChanged.connect(self._apply_ai_filter)

    def open_pdf_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", "PDF/Images (*.pdf *.png *.jpg *.jpeg)")
        if paths: self.pdf_selected.emit(paths, {})

    @staticmethod
    def _sanitize_text(val):
        if val is None or (isinstance(val, float) and math.isnan(val)): return ""
        s = str(val).strip()
        return "" if s.lower() == "nan" else s

    @staticmethod
    def _normalize_file_path(path):
        return get_converted_path(path) if path else ""

    def _extract_row_metadata(self, item):
        d = item.data(Qt.ItemDataRole.UserRole)
        return d if isinstance(d, dict) else {}

    def _extract_row_metadata_from_dict(self, data):
        return {
            'rn': data.get('RN', ''),
            'name': data.get('name', ''),
            'region': data.get('region', ''),
            'worker': data.get('worker', ''),
            'finished_file_path': data.get('finished_file_path', ''),
            'special_note': data.get('special_note', ''),
            'recent_thread_id': data.get('recent_thread_id', ''),
            'mail_count': data.get('mail_count', 0),
            'urgent': data.get('urgent', 0),
            'original_filepath': data.get('original_filepath', '')
        }

    def get_selected_rn(self):
        table = self.complement_table_widget
        ranges = table.selectedRanges()
        row = ranges[0].topRow() if ranges else -1
        return table.item(row, 1).text().strip() if row != -1 else None

    def set_worker_name(self, name): self._worker_name = name or ''
    def set_worker_id(self, id): self._worker_id = id
    def set_payment_request_load_enabled(self, e): self._payment_request_load_enabled = e