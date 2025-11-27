from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt

from core.sql_manager import fetch_gemini_contract_results, check_gemini_flags, fetch_gemini_chobon_results

class DetailFormDialog(QDialog):
    """상세 정보 표시 다이얼로그 (form.ui 사용)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        ui_path = Path(__file__).parent.parent / "ui" / "form.ui"
        uic.loadUi(ui_path, self)
        
        # 버튼 연결
        if hasattr(self, 'buttonBox'):
            self.buttonBox.accepted.connect(self.accept)
            self.buttonBox.rejected.connect(self.reject)

    def load_data(self, rn: str):
        """제공된 RN으로 데이터를 조회하고 UI를 업데이트한다."""
        self.setWindowTitle(f"상세 정보: {rn}")

        # 1. 구매계약서 데이터 로드
        contract_data = fetch_gemini_contract_results(rn)
        
        # 계약일자
        self.label_contract_date.setText(str(contract_data.get('ai_계약일자', '')))
        # 이름
        self.label_name_1.setText(str(contract_data.get('ai_이름', '')))
        # 전화번호 (휴대폰, 전화 동일하게 설정)
        phone = str(contract_data.get('전화번호', ''))
        self.label_hp.setText(phone)
        self.label_pn.setText(phone)
        # 이메일
        self.label_email.setText(str(contract_data.get('이메일', '')))

        # 2. 플래그 확인
        flags = check_gemini_flags(rn)

        # 3. 초본 데이터 로드
        if flags.get('초본', False):
            chobon_data = fetch_gemini_chobon_results(rn)
            if chobon_data:
                # 생년월일
                birth_date = chobon_data.get('birth_date')
                if birth_date:
                    if not isinstance(birth_date, str):
                         birth_date_str = birth_date.strftime('%Y-%m-%d')
                    else:
                        birth_date_str = birth_date
                else:
                    birth_date_str = ''
                self.label_birth_date.setText(birth_date_str)
                
                # 주소
                self.label_address_1.setText(str(chobon_data.get('address_1', '')))
                self.label_address_2.setText(str(chobon_data.get('address_2', '')))
            else:
                 self._clear_chobon_fields()
        else:
            self._clear_chobon_fields()

        # 4. 청년생애 데이터 로드
        # 데이터가 있는 경우에만 'O' 표시
        if flags.get('청년생애', False):
             self.label_firstandyouth.setText("O")
        else:
             self.label_firstandyouth.setText("")

    def _clear_chobon_fields(self):
        """초본 관련 필드 초기화"""
        self.label_birth_date.setText("")
        self.label_address_1.setText("")
        self.label_address_2.setText("")

