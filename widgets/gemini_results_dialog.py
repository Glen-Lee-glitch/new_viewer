from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt

from core.sql_manager import fetch_gemini_contract_results, check_gemini_flags, fetch_gemini_youth_results

class GeminiResultsDialog(QDialog):
    """Gemini AI 결과 표시 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        ui_path = Path(__file__).parent.parent / "ui" / "gemini_results_dialog.ui"
        uic.loadUi(ui_path, self)
        
        self.setModal(False)
        self._setup_label_interaction()
        
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setup_label_interaction(self):
        """라벨들이 텍스트 선택 및 복사를 지원하도록 설정한다."""
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.contract_date_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.phone_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.email_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.local_name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.range_date_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def load_data(self, rn: str):
        """제공된 RN으로 데이터를 조회하고 UI를 업데이트한다."""
        # 구매계약서 데이터 로드
        contract_data = fetch_gemini_contract_results(rn)
        self.name_label.setText(str(contract_data.get('ai_이름', '')))
        self.contract_date_label.setText(str(contract_data.get('ai_계약일자', '')))
        self.phone_label.setText(str(contract_data.get('전화번호', '')))
        self.email_label.setText(str(contract_data.get('이메일', '')))

        # gemini_results 테이블에서 플래그 확인
        flags = check_gemini_flags(rn)
        
        # 청년생애 데이터 로드 및 표시
        if flags.get('청년생애', False):
            youth_data = fetch_gemini_youth_results(rn)
            
            # JSON 배열을 보기 좋은 문자열로 변환
            local_names = youth_data.get('local_name', [])
            range_dates = youth_data.get('range_date', [])
            
            local_name_text = ', '.join(local_names) if local_names else '데이터 없음'
            range_date_text = ', '.join(range_dates) if range_dates else '데이터 없음'
            
            self.local_name_label.setText(local_name_text)
            self.range_date_label.setText(range_date_text)
            self.youth_groupBox.setVisible(True)
        else:
            self.youth_groupBox.setVisible(False)

        self.setWindowTitle(f"AI 검토 결과: {rn}")
