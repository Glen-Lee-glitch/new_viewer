from PyQt6.QtWidgets import QDialog, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6 import uic
from pathlib import Path
from core.sql_manager import fetch_after_apply_counts, get_worker_names

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI 파일 로드
        ui_path = Path(__file__).parent.parent / "ui" / "login_dialog.ui"
        uic.loadUi(str(ui_path), self)
        
        # 다이얼로그 설정
        self.setWindowTitle("로그인")
        self.setModal(True)
        
        # 윈도우 작업표시줄에 아이콘이 나타나도록 설정 (부모 윈도우가 숨겨져 있을 때 필요)
        # WindowStaysOnTopHint: 다른 프로그램 실행 시 뒤로 숨는 문제 방지
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        
        # 검증 통과 플래그 (accept()가 호출되어도 검증을 통과한 경우에만 실제로 닫힘)
        self._validation_passed = False
        
        # UI 파일에서 자동 연결된 시그널을 끊고 우리가 원하는 동작만 연결
        # UI 파일의 buttonBox.accepted -> accept() 연결을 끊음
        try:
            self.buttonBox.accepted.disconnect()
        except TypeError:
            # 연결이 없을 경우 무시
            pass
        
        try:
            self.buttonBox.rejected.disconnect()
        except TypeError:
            # 연결이 없을 경우 무시
            pass
        
        # 버튼 연결 (검증 로직 포함)
        self.buttonBox.accepted.connect(self._validate_and_accept)
        self.buttonBox.rejected.connect(self.reject)
        
        # 리마인더 라벨 업데이트
        self._update_reminder_labels()
        
        # 입력 필드 포커스
        self.lineEdit_worker.setFocus()
    
    def accept(self):
        """다이얼로그를 승인한다. 검증을 통과한 경우에만 실제로 닫힌다."""
        if self._validation_passed:
            super().accept()
        # 검증을 통과하지 않았으면 아무것도 하지 않음 (다이얼로그 유지)
    
    def _validate_and_accept(self):
        """작업자 이름을 검증하고 유효하면 다이얼로그를 승인한다."""
        worker_name = self.lineEdit_worker.text().strip()
        
        # 빈 입력 체크
        if not worker_name:
            QMessageBox.warning(self, "입력 오류", "작업자 이름을 입력해주세요.")
            self.lineEdit_worker.setFocus()
            self._validation_passed = False
            return
        
        # 유효한 작업자 목록 가져오기
        valid_workers = get_worker_names()
        
        # 작업자 이름 유효성 검사
        if worker_name not in valid_workers:
            error_msg = f"'{worker_name}'은(는) 등록되지 않은 작업자입니다.\n\n등록된 작업자 목록:\n"
            error_msg += "\n".join(f"• {worker}" for worker in valid_workers)
            QMessageBox.warning(self, "등록되지 않은 작업자", error_msg)
            self.lineEdit_worker.setFocus()
            self._validation_passed = False
            return
        
        # 검증 통과 - 이제 accept()를 호출해도 실제로 닫힘
        self._validation_passed = True
        self.accept()
    
    def closeEvent(self, event: QCloseEvent):
        """X 버튼으로 다이얼로그를 닫을 때 reject()를 명시적으로 호출한다."""
        # X 버튼으로 닫을 때는 reject()를 호출하여 Rejected 상태로 만듦
        # reject()를 호출하면 다이얼로그가 닫히고 exec()가 Rejected를 반환함
        self.reject()
        event.accept()
    
    def _update_reminder_labels(self):
        """리마인더 라벨을 업데이트한다."""
        try:
            today_count, tomorrow_count = fetch_after_apply_counts()
            self.today_apply.setText(f"{today_count}건")
            self.tomorrow_label.setText(f"{tomorrow_count}건")
        except Exception:
            # 오류 발생 시 기본값 설정
            self.today_apply.setText("0건")
            self.tomorrow_label.setText("0건")
    
    def get_worker_name(self) -> str:
        """입력된 작업자 이름을 반환한다."""
        return self.lineEdit_worker.text().strip()