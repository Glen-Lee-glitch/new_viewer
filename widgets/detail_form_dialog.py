from pathlib import Path
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog, QApplication
from PyQt6.QtCore import Qt, QEvent

from core.sql_manager import (fetch_gemini_contract_results, check_gemini_flags, fetch_gemini_chobon_results, 
                              fetch_subsidy_model, fetch_gemini_multichild_results, fetch_subsidy_region, 
                              calculate_delivery_date)

class DetailFormDialog(QDialog):
    """상세 정보 표시 다이얼로그 (form.ui 사용)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        ui_path = Path(__file__).parent.parent / "ui" / "form.ui"
        uic.loadUi(ui_path, self)
        
        # 스타일시트 적용: 모든 QLabel에 테두리 추가
        self.setStyleSheet("""
            QLabel {
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px;
                background-color: #1e1e1e;
                color: #ffffff;
            }
        """)
        
        # 버튼 연결
        if hasattr(self, 'buttonBox'):
            self.buttonBox.accepted.connect(self.accept)
            self.buttonBox.rejected.connect(self.reject)
            
        self._setup_label_interaction()
        self._setup_copy_on_click()

    def _setup_label_interaction(self):
        """라벨들이 텍스트 선택을 지원하도록 설정한다."""
        labels = [
            self.label_contract_date,
            self.label_name_1,
            self.label_hp,
            self.label_pn,
            self.label_email,
            self.label_birth_date,
            self.label_address_1,
            self.label_address_2,
            self.label_firstandyouth,
            self.label_gender,
            self.label_model,
            self.label_children,
            self.label_deliver_date
        ]
        
        for label in labels:
            if hasattr(self, label.objectName()):
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def _setup_copy_on_click(self):
        """라벨을 클릭했을 때 클립보드에 복사하는 기능 설정"""
        labels_to_make_clickable = [
            self.label_contract_date,
            self.label_name_1,
            self.label_hp,
            self.label_pn,
            self.label_email,
            self.label_birth_date,
            self.label_address_1,
            self.label_address_2,
            self.label_firstandyouth,
            self.label_gender,
            self.label_model,
            self.label_children,
            self.label_deliver_date
        ]
        
        for label in labels_to_make_clickable:
            if hasattr(self, label.objectName()):
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.installEventFilter(self)

    def eventFilter(self, obj, event):
        """이벤트 필터. 클릭 시 텍스트를 복사하는 로직을 처리한다."""
        clickable_labels = [
            self.label_contract_date,
            self.label_name_1,
            self.label_hp,
            self.label_pn,
            self.label_email,
            self.label_birth_date,
            self.label_address_1,
            self.label_address_2,
            self.label_firstandyouth,
            self.label_gender,
            self.label_model,
            self.label_children,
            self.label_deliver_date
        ]

        if obj in clickable_labels and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                text_to_copy = obj.text()
                # HTML 태그 제거 (필요한 경우)
                if obj.textFormat() == Qt.TextFormat.RichText:
                     # 간단한 제거 (복잡하면 QTextDocument 사용)
                     pass 
                
                if text_to_copy:
                    QApplication.clipboard().setText(text_to_copy)
                    # 복사 성공 시 배경색 변경 (연한 초록색, 텍스트 검정)
                    obj.setStyleSheet("""
                        QLabel {
                            border: 1px solid #555555;
                            border-radius: 3px;
                            padding: 4px;
                            background-color: #A5D6A7;
                            color: #000000;
                            font-weight: bold;
                        }
                    """)
                return True
        
        return super().eventFilter(obj, event)

    def load_data(self, rn: str):
        """제공된 RN으로 데이터를 조회하고 UI를 업데이트한다."""
        self.setWindowTitle(f"상세 정보: {rn}")

        # 1. 구매계약서 데이터 로드
        contract_data = fetch_gemini_contract_results(rn)
        
        # 계약일자
        self.label_contract_date.setText(str(contract_data.get('ai_계약일자', '')))
        
        # 이름 (초본 데이터 우선, 없으면 계약서 데이터)
        name = str(contract_data.get('ai_이름', ''))
        
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
                # 초본 이름이 있으면 우선 사용
                chobon_name = chobon_data.get('name')
                if chobon_name:
                    name = str(chobon_name)
                
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
                
                # 성별
                gender_val = chobon_data.get('gender')
                if gender_val is not None:
                    try:
                        # 0이면 여자, 1이면 남자
                        gender_int = int(gender_val)
                        if gender_int == 0:
                            self.label_gender.setText("여자")
                        elif gender_int == 1:
                            self.label_gender.setText("남자")
                        else:
                            self.label_gender.setText(str(gender_val))
                    except (ValueError, TypeError):
                        self.label_gender.setText(str(gender_val))
                else:
                    self.label_gender.setText("")
            else:
                 self._clear_chobon_fields()
        else:
            self._clear_chobon_fields()
            
        # 이름 설정 (최종 결정된 이름)
        self.label_name_1.setText(name)

        # 4. 청년생애 데이터 로드
        # 데이터가 있는 경우에만 'O' 표시
        if flags.get('청년생애', False):
             self.label_firstandyouth.setText("O")
        else:
             self.label_firstandyouth.setText("")
             
        # 5. 차종 데이터 로드
        model_name = fetch_subsidy_model(rn)
        
        # 모델명 매핑
        model_mapping = {
            'Model Y L': 'New Model Y Long Range',
            'Model Y R': 'New Model Y RWD',
            'Model 3 R': 'Model 3 RWD'
        }
        
        # 매핑된 이름이 있으면 사용, 없으면 원래 이름 사용
        display_model_name = model_mapping.get(model_name, model_name)
        self.label_model.setText(display_model_name)
        
        # 6. 출고예정일 계산 및 표시
        region = fetch_subsidy_region(rn)
        if region:
            delivery_date = calculate_delivery_date(region)
            self.label_deliver_date.setText(delivery_date)
        else:
            self.label_deliver_date.setText("")
        
        # 7. 다자녀 데이터 로드
        has_multichild = False
        if flags.get('다자녀', False):
            multichild_data = fetch_gemini_multichild_results(rn)
            child_birth_dates = multichild_data.get('child_birth_date', [])
            
            if child_birth_dates:
                count = len(child_birth_dates)
                self.label_children.setText(f"{count}자녀")
                has_multichild = True
            else:
                self.label_children.setText("")
        else:
            self.label_children.setText("")
            
        # 8. 하단 레이아웃 가시성 제어 (공동명의, 다자녀, 청년생애, 기타)
        # 일단 모두 숨김
        self._set_bottom_layout_visibility(
            show_joint=False, # 공동명의 (아직 로직 없음)
            show_multichild=has_multichild, 
            show_youth=flags.get('청년생애', False), 
            show_etc=False # 기타 (아직 로직 없음)
        )

    def _set_bottom_layout_visibility(self, show_joint, show_multichild, show_youth, show_etc):
        """하단 레이아웃 항목들의 가시성을 제어한다."""
        # 공동명의
        self.label_12.setVisible(show_joint)
        self.label_name_2.setVisible(show_joint)
        self.label_birth_date_2.setVisible(show_joint)
        
        # 다자녀
        self.label_13.setVisible(show_multichild)
        self.label_children.setVisible(show_multichild)
        
        # 청년생애
        self.label_14.setVisible(show_youth)
        self.label_firstandyouth.setVisible(show_youth)
        
        # 기타
        self.label_15.setVisible(show_etc)
        self.label_etc.setVisible(show_etc)

    def _clear_chobon_fields(self):
        """초본 관련 필드 초기화"""
        self.label_birth_date.setText("")
        self.label_address_1.setText("")
        self.label_address_2.setText("")
        self.label_gender.setText("")

