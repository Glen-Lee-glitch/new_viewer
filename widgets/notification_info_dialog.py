import sys
import os

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 core 패키지를 찾을 수 있게 함
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

import psycopg2
from contextlib import closing
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QApplication,
    QSplitter,
    QWidget,
    QComboBox,
    QStackedWidget,
    QLineEdit,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QFormLayout,
    QPushButton,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QCompleter,
    QSizePolicy
)
from PyQt6.QtCore import Qt

from core.data_manage import DB_CONFIG

class DragAndDropLineEdit(QLineEdit):
    """드래그 앤 드롭을 지원하는 커스텀 QLineEdit"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setReadOnly(True)
        self.setPlaceholderText("파일을 이곳에 드래그하거나 선택 버튼을 누르세요...")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # 드롭된 데이터가 URL(파일 경로)을 포함하고 있는지 확인
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.pdf'):
                event.acceptProposedAction()
                self.setStyleSheet("background-color: #e1f0fe; border: 2px solid #0078d4;")
            else:
                event.ignore()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("background-color: #f8f8f8; color: #666;")

    def dropEvent(self, event):
        file_path = event.mimeData().urls()[0].toLocalFile()
        if file_path.lower().endswith('.pdf'):
            self.setText(file_path)
            self.setStyleSheet("background-color: #f8f8f8; color: #333; font-weight: bold;")
        self.setStyleSheet("background-color: #f8f8f8; color: #333;")

class RegionDataFormWidget(QWidget):
    """공고문을 보며 데이터를 입력하는 위젯 (기존 DataEntryDialog 대체)"""
    
    # 제조사 기본 지급 서류
    DEFAULT_MFG_DOCS = ['지급신청서', '자동차등록증', '세금계산서', '사업자등록증', '통장사본']

    def __init__(self, parent=None):
        super().__init__(parent)
        self.region = None
        self._init_ui()

    def set_region(self, region):
        """지역 설정 및 UI 초기화 상태 변경"""
        self.region = region
        # 개인사업자 페이지의 지역명 라디오 버튼 업데이트
        if hasattr(self, 'rb_loc_region'):
            self.rb_loc_region.setText(region)
            # 기본적으로 지역명 체크 (load_data에서 덮어씌워질 수 있음)
            self.rb_loc_region.setChecked(True)

        # 지급신청서류 기본값 세팅 (DB 저장 안 함)
        self._reset_payment_defaults()

    def _reset_payment_defaults(self):
        """지급신청서류를 주체별 기본값으로 리셋합니다."""
        if not hasattr(self, 'cust_payment_list') or not hasattr(self, 'mfg_payment_list'):
            return

        self.cust_payment_list.clear()
        self.mfg_payment_list.clear()

        # 무조건 제조사에 기본 5종 투입
        for doc in self.DEFAULT_MFG_DOCS:
            self.mfg_payment_list.addItem(doc)

    def load_data(self, data):
        """DB에서 불러온 데이터를 UI에 채웁니다."""
        if not data:
            return

        # 1. 지원신청서류 데이터 로드
        apply_data = data.get('notification_apply', {}).get('application_docs', {})
        if apply_data:
            # 구매 주체 및 하위 항목
            entity = apply_data.get('purchase_entity', {})
            entity_type = entity.get('type', '개인')
            self.entity_type_combo.setCurrentText(entity_type)
            
            selected_docs = entity.get('selected_docs', [])
            if entity_type == '개인':
                self.chk_resident_reg.setChecked("주민등록등본" in selected_docs)
                self.chk_resident_abstract.setChecked("주민등록초본" in selected_docs)
            elif entity_type == '개인사업자':
                self.chk_biz_person.setChecked("개인서류" in selected_docs)
                self.chk_biz_reg_cert.setChecked("사업자등록증명원" in selected_docs)
                # 사업장 소재지 로드
                biz_loc = entity.get('business_location')
                if biz_loc == "무관":
                    self.rb_loc_any.setChecked(True)
                else:
                    self.rb_loc_region.setChecked(True)
            elif entity_type == '법인':
                self.chk_corp_reg.setChecked("법인등기부등본" in selected_docs)
                self.chk_corp_biz_cert.setChecked("사업자등록증명원" in selected_docs)
            elif entity_type == '외국인':
                self.foreigner_input.setText(entity.get('foreigner_input', ''))

            # 추가 서류 리스트
            self.extra_docs_list.clear()
            for doc in apply_data.get('extra_docs', []):
                self.extra_docs_list.addItem(doc)

            # 서류 발급일
            self.doc_date_combo.setCurrentText(apply_data.get('document_date', '30'))

            # 우선순위 조건 로드
            priority_data = apply_data.get('priority_conditions', {})
            # 다자녀
            mc_data = priority_data.get('multi_child', {})
            self.chk_multi_child_reg_only.setChecked(mc_data.get('reg_only', False))
            self.combo_multi_child_age.setCurrentText(mc_data.get('age_limit', '만 18세 이하'))
            
            # 나머지 우선순위 항목
            p_defaults = {
                "first_time": "(출생~현재)지방세 세목별 미과세증명서",
                "low_income": "차상위 계층 증명서/기초생활 수급자 증명서",
                "disabled": "장애인증명서(장애인등록증 혹은 복지카드 등)",
                "merit": "국가유공자 확인 증명 서류",
                "scrappage": "(지급신청 시 필요) 자동차 말소 등록 사실증명서",
                "small_biz": "중소기업(소상공인)확인서"
            }
            for key, edit in self.priority_edits.items():
                val = priority_data.get(key, p_defaults.get(key, ""))
                edit.setText(val)

        # 2. 지급 서류 리스트 로드 (notification_payment 컬럼에서 별도로 로드)
        payment_root = data.get('notification_payment', {})
        p_docs = payment_root.get('payment_docs', {}) if payment_root else {}
        
        if p_docs:
            if isinstance(p_docs, dict):
                for doc in p_docs.get('customer', []):
                    existing = [self.cust_payment_list.item(i).text() for i in range(self.cust_payment_list.count())]
                    if doc not in existing:
                        self.cust_payment_list.addItem(doc)
                for doc in p_docs.get('manufacturer', []):
                    existing = [self.mfg_payment_list.item(i).text() for i in range(self.mfg_payment_list.count())]
                    if doc not in existing:
                        self.mfg_payment_list.addItem(doc)
            elif isinstance(p_docs, list):
                # 하위 호환성: 기존 리스트 데이터는 고객 서류로 간주
                for doc in p_docs:
                    existing = [self.cust_payment_list.item(i).text() for i in range(self.cust_payment_list.count())]
                    if doc not in existing:
                        self.cust_payment_list.addItem(doc)

        # 3. 공동명의 데이터 로드
        co_data = data.get('co_name', {})
        if co_data:
            basic_cond = co_data.get('basic_condition', "")
            found = False
            for rb in self.joint_radios:
                if rb.text() == basic_cond:
                    rb.setChecked(True)
                    found = True
                    break
            if not found and basic_cond:
                self.joint_custom_radio.setChecked(True)
                self.joint_custom_edit.setText(basic_cond)
            
            self.joint_share_edit.setText(co_data.get('share_ratio', ''))
            self.joint_rep_edit.setText(co_data.get('representative_setting', ''))

        # 3. 거주요건 데이터 로드
        res_val = data.get('residence_requirements')
        if res_val is not None:
            res_str = str(res_val)
            for i in range(self.residence_period_group.buttons().__len__()):
                btn = self.residence_period_group.buttons()[i]
                if btn.property("value") == res_str:
                    btn.setChecked(True)
                    break
        else:
            # NULL인 경우 '확인필요' 선택
            for btn in self.residence_period_group.buttons():
                if btn.property("value") == "":
                    btn.setChecked(True)
                    break

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0) # 내장 위젯이므로 여백 제거
        layout.setSpacing(15)

        # 1. 대분류 선택 섹션
        category_layout = QHBoxLayout()
        category_label = QLabel("대분류 선택:")
        category_label.setStyleSheet("font-weight: bold;")
        
        self.category_combo = QComboBox()
        self.category_combo.addItems(["선택해주세요", "지원신청서류", "공동명의 조건", "거주요건 조건", "우선순위 조건", "지급신청서류"])
        self.category_combo.setCurrentIndex(1) # '지원신청서류' 디폴트 선택
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        self.category_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #0078d4;
                border-radius: 4px;
                font-size: 14px;
            }
        """)
        
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combo, stretch=1)
        layout.addLayout(category_layout)

        # 2. 동적 입력 섹션 (Stacked Widget)
        self.stack = QStackedWidget()
        
        # 각 카테고리별 위젯 생성
        self.stack.addWidget(self._create_empty_page())            # index 0
        self.stack.addWidget(self._create_application_docs_page()) # index 1: 지원신청서류
        self.stack.addWidget(self._create_joint_owner_page())      # index 2: 공동명의
        self.stack.addWidget(self._create_residence_page())        # index 3: 거주요건
        self.stack.addWidget(self._create_priority_page())         # index 4: 우선순위
        self.stack.addWidget(self._create_payment_docs_page())     # index 5: 지급신청서류
        
        layout.addWidget(self.stack, stretch=1)

        # 초기 카테고리 설정 (지원신청서류)
        self.category_combo.setCurrentIndex(1)
        self.stack.setCurrentIndex(1)

        # 3. 하단 버튼
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("저장하기")
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                padding: 12px;
                font-weight: bold;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

    def _on_save_clicked(self):
        """데이터 수집 및 파일 복사, DB 저장을 수행합니다."""
        if not self.region:
            QMessageBox.warning(self, "경고", "지역이 선택되지 않았습니다.")
            return

        import shutil
        import json
        
        # 1. 파일 복사 로직 (지원신청서)
        source_file = self.app_form_path_edit.text().strip()
        has_app_form = False
        
        if source_file and os.path.exists(source_file):
            try:
                base_path = r"\\DESKTOP-KEHQ34D\Users\com\Desktop\GreetLounge\26q1\공고문"
                target_dir = os.path.join(base_path, self.region, "전처리된 서류")
                os.makedirs(target_dir, exist_ok=True)
                target_file = os.path.join(target_dir, "지원신청서.pdf")
                shutil.copy2(source_file, target_file)
                has_app_form = True
            except Exception as e:
                QMessageBox.critical(self, "파일 저장 오류", f"파일 복사 중 오류 발생: {e}")
                return

        # 2. UI 데이터 수집 (JSON 형식)
        # (1) 지원신청서류 데이터
        entity_type = self.entity_type_combo.currentText()
        selected_docs = []
        foreigner_input = ""
        biz_location = None
        
        if entity_type == '개인':
            if self.chk_resident_reg.isChecked(): selected_docs.append("주민등록등본")
            if self.chk_resident_abstract.isChecked(): selected_docs.append("주민등록초본")
        elif entity_type == '개인사업자':
            if self.chk_biz_person.isChecked(): selected_docs.append("개인서류")
            if self.chk_biz_reg_cert.isChecked(): selected_docs.append("사업자등록증명원")
            # 사업장 소재지 수집
            if hasattr(self, 'rb_loc_region') and self.rb_loc_region.isChecked():
                biz_location = self.region
            else:
                biz_location = "무관"
        elif entity_type == '법인':
            if self.chk_corp_reg.isChecked(): selected_docs.append("법인등기부등본")
            if self.chk_corp_biz_cert.isChecked(): selected_docs.append("사업자등록증명원")
        elif entity_type == '외국인':
            foreigner_input = self.foreigner_input.text().strip()
            
        extra_docs = [self.extra_docs_list.item(i).text() for i in range(self.extra_docs_list.count())]
        
        # 지급 서류 수집 및 기본값 제외 필터링
        all_cust_pay = [self.cust_payment_list.item(i).text() for i in range(self.cust_payment_list.count())]
        all_mfg_pay = [self.mfg_payment_list.item(i).text() for i in range(self.mfg_payment_list.count())]
        
        # 기본값 리스트에 없는 것만 골라냄
        payment_docs = {
            "customer": [d for d in all_cust_pay if d not in self.DEFAULT_MFG_DOCS],
            "manufacturer": [d for d in all_mfg_pay if d not in self.DEFAULT_MFG_DOCS]
        }
        
        doc_date = self.doc_date_combo.currentText()
        
        # (2) 공동명의 데이터 수집 (라디오 버튼)
        if self.joint_custom_radio.isChecked():
            selected_joint_condition = self.joint_custom_edit.text().strip()
        else:
            selected_joint_condition = self.joint_group.checkedButton().text()
        
        co_name_data = {
            "basic_condition": selected_joint_condition
        }
        
        # 값이 있는 경우에만 추가
        share_ratio = self.joint_share_edit.text().strip()
        if share_ratio:
            co_name_data["share_ratio"] = share_ratio
            
        rep_setting = self.joint_rep_edit.text().strip()
        if rep_setting:
            co_name_data["representative_setting"] = rep_setting

        # (3) 거주요건 데이터 수집 (integer 타입)
        selected_period_btn = self.residence_period_group.checkedButton()
        residence_period = selected_period_btn.property("value") if selected_period_btn else None
        
        # '확인필요'("")인 경우 None(NULL)으로 처리, 그 외에는 int 변환
        residence_val = int(residence_period) if residence_period else None

        # (4) 우선순위 데이터 수집 (기본값과 다를 때만 저장)
        priority_conditions = {}
        
        # 다자녀: 변경된 서브 항목만 기입
        mc_data = {}
        mc_reg_only = self.chk_multi_child_reg_only.isChecked()
        mc_age_limit = self.combo_multi_child_age.currentText()
        
        if mc_reg_only != False:
            mc_data["reg_only"] = mc_reg_only
        if mc_age_limit != "만 18세 이하":
            mc_data["age_limit"] = mc_age_limit
            
        if mc_data:
            priority_conditions["multi_child"] = mc_data
            
        # 나머지 6개 항목 기본값 정의
        p_defaults = {
            "first_time": "(출생~현재)지방세 세목별 미과세증명서",
            "low_income": "차상위 계층 증명서/기초생활 수급자 증명서",
            "disabled": "장애인증명서(장애인등록증 혹은 복지카드 등)",
            "merit": "국가유공자 확인 증명 서류",
            "scrappage": "(지급신청 시 필요) 자동차 말소 등록 사실증명서",
            "small_biz": "중소기업(소상공인)확인서"
        }
        
        for key, default_val in p_defaults.items():
            current_val = self.priority_edits[key].text().strip()
            # 입력값이 기본값과 다를 때만 딕셔너리에 추가
            # 만약 다시 기본값으로 수정했다면, 딕셔너리에 포함되지 않아 DB에서 해당 키가 제거됨
            if current_val != default_val:
                priority_conditions[key] = current_val

        # (5) 최종 저장용 데이터 분리
        # notification_apply 컬럼용 (지급 서류 제외)
        app_docs_data = {
            "application_docs": {
                "has_app_form": has_app_form,
                "purchase_entity": {
                    "type": entity_type,
                    "selected_docs": selected_docs,
                    "foreigner_input": foreigner_input
                },
                "extra_docs": extra_docs,
                "document_date": doc_date
            }
        }
        
        # 개인사업자 사업장 소재지 추가
        if biz_location:
            app_docs_data["application_docs"]["purchase_entity"]["business_location"] = biz_location

        # 우선순위 변경사항이 있다면 추가
        if priority_conditions:
            app_docs_data["application_docs"]["priority_conditions"] = priority_conditions

        # notification_payment 컬럼용 데이터
        payment_data = {
            "payment_docs": payment_docs
        }

        # 3. DB 업데이트
        try:
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    # (1) region_id 조회
                    cursor.execute("SELECT region_id FROM region_metadata WHERE region = %s", (self.region,))
                    result = cursor.fetchone()
                    if not result:
                        raise Exception(f"'{self.region}'에 해당하는 region_id를 찾을 수 없습니다.")
                    region_id = result[0]
                    
                    # (2) 공고문 테이블 업데이트
                    update_query = """
                        INSERT INTO 공고문 (region_id, notification_apply, notification_payment, co_name, residence_requirements, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (region_id) DO UPDATE 
                        SET notification_apply = COALESCE(공고문.notification_apply, '{}'::jsonb) || EXCLUDED.notification_apply,
                            notification_payment = EXCLUDED.notification_payment,
                            co_name = EXCLUDED.co_name,
                            residence_requirements = EXCLUDED.residence_requirements,
                            updated_at = NOW()
                    """
                    cursor.execute(update_query, (
                        region_id, 
                        json.dumps(app_docs_data),
                        json.dumps(payment_data),
                        json.dumps(co_name_data),
                        residence_val
                    ))
                    conn.commit()
                    
            QMessageBox.information(self, "성공", f"데이터와 파일이 성공적으로 저장되었습니다.\n지역: {self.region}")
            
        except Exception as e:
            QMessageBox.critical(self, "DB 저장 오류", f"데이터베이스 저장 중 오류가 발생했습니다:\n{str(e)}")

    def _create_payment_docs_page(self):
        """지급신청서류 입력 페이지 (고객/제조사 구분)"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)

        # 1. 고객 작성 서류 섹션
        self.cust_payment_list = QListWidget()
        cust_group = self._create_subject_doc_group(
            "고객 작성 서류", 
            self.cust_payment_list, 
            "고객용 서류 명칭 입력...",
            ["지급신청서", "보조금 지급신청서", "통장사본", "차량등록증"]
        )
        layout.addWidget(cust_group)

        # 2. 제조사 작성 서류 섹션
        self.mfg_payment_list = QListWidget()
        mfg_group = self._create_subject_doc_group(
            "제조사 작성 서류", 
            self.mfg_payment_list, 
            "제조사용 서류 명칭 입력...",
            ["지급신청서", "지방세 납세증명서", "사업자등록증명원"]
        )
        layout.addWidget(mfg_group)

        tip = QLabel("※ 각 항목을 더블클릭하여 삭제할 수 있습니다.")
        tip.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(tip)
        layout.addStretch()
        return page

    def _create_subject_doc_group(self, title, list_widget, placeholder, quick_items):
        """주체별 서류 그룹 박스 생성 헬퍼"""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        
        # 입력창 및 추가 버튼
        add_layout = QHBoxLayout()
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder)
        
        add_btn = QPushButton("추가")
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(lambda: self._add_to_list(input_field, list_widget))
        input_field.returnPressed.connect(lambda: self._add_to_list(input_field, list_widget))
        
        add_layout.addWidget(input_field)
        add_layout.addWidget(add_btn)
        
        # 빠른 추가 버튼
        quick_layout = QHBoxLayout()
        for name in quick_items:
            btn = QPushButton(name)
            btn.setStyleSheet("""
                QPushButton { font-size: 11px; color: #0078d4; background: transparent; 
                border: 1px solid #0078d4; border-radius: 10px; padding: 2px 10px; }
            """)
            btn.clicked.connect(lambda checked, n=name: self._add_to_list(None, list_widget, n))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        
        layout.addWidget(list_widget)
        layout.addLayout(add_layout)
        layout.addLayout(quick_layout)
        
        list_widget.itemDoubleClicked.connect(
            lambda item: list_widget.takeItem(list_widget.row(item))
        )
        return group

    def _add_to_list(self, input_field, list_widget, text=None):
        """리스트 위젯에 항목을 추가하는 공통 유틸리티"""
        if text is None and input_field:
            text = input_field.text().strip()
            if input_field: input_field.clear()
            
        if text:
            # 중복 체크
            existing = [list_widget.item(i).text() for i in range(list_widget.count())]
            if text not in existing:
                list_widget.addItem(text)

    def _create_empty_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        msg = QLabel("상단의 대분류를 선택하면\n입력 양식이 표시됩니다.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(msg)
        return page

    def _create_application_docs_page(self):
        """지원신청서류 입력 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(15)

        # 공통 서류 섹션 (파일 첨부 UI)
        common_group = QGroupBox("공통 서류 (기본 항목)")
        common_layout = QVBoxLayout(common_group)
        common_layout.setSpacing(10)
        
        # 1. 지원신청서 행 (커스텀 드래그 앤 드롭 위젯 사용)
        app_form_row = QHBoxLayout()
        app_form_label = QLabel("지원신청서")
        app_form_label.setFixedWidth(80)
        
        self.app_form_path_edit = DragAndDropLineEdit()
        self.app_form_path_edit.setStyleSheet("background-color: #f8f8f8; color: #666;")
        
        app_form_btn = QPushButton("파일 선택")
        app_form_btn.setFixedWidth(80)
        app_form_btn.clicked.connect(self._select_app_form_file)
        
        app_form_row.addWidget(app_form_label)
        app_form_row.addWidget(self.app_form_path_edit)
        app_form_row.addWidget(app_form_btn)
        
        common_layout.addLayout(app_form_row)
        
        # 2. 구매계약서 (텍스트로만 표시)
        contract_label = QLabel("구매계약서")
        contract_label.setStyleSheet("color: #777; padding-left: 5px;")
        common_layout.addWidget(contract_label)

        # 3. 구매 주체 선택 및 동적 항목 섹션
        entity_layout = QHBoxLayout()
        entity_label = QLabel("구매 주체")
        entity_label.setFixedWidth(80)
        self.entity_type_combo = QComboBox()
        self.entity_type_combo.addItems(['개인', '개인사업자', '법인', '외국인'])
        self.entity_type_combo.setStyleSheet("padding: 3px;")
        
        entity_layout.addWidget(entity_label)
        entity_layout.addWidget(self.entity_type_combo)
        common_layout.addLayout(entity_layout)

        # 주체별 하위 항목 (StackedWidget)
        self.entity_stack = QStackedWidget()
        
        # (1) 개인 페이지
        person_page = QWidget()
        person_layout = QHBoxLayout(person_page)
        person_layout.setContentsMargins(85, 0, 0, 0) # 라벨 너비만큼 왼쪽 여백
        self.chk_resident_reg = QCheckBox("주민등록등본")
        self.chk_resident_reg.setChecked(True)
        self.chk_resident_abstract = QCheckBox("주민등록초본")
        self.chk_resident_abstract.setChecked(True)
        person_layout.addWidget(self.chk_resident_reg)
        person_layout.addWidget(self.chk_resident_abstract)
        person_layout.addStretch()
        
        # (2) 개인사업자 페이지
        indiv_biz_page = QWidget()
        indiv_biz_layout = QHBoxLayout(indiv_biz_page)
        indiv_biz_layout.setContentsMargins(85, 0, 10, 0)
        
        # 1. 서류 체크박스 (왼쪽)
        self.chk_biz_person = QCheckBox("개인서류")
        self.chk_biz_person.setChecked(True)
        self.chk_biz_reg_cert = QCheckBox("사업자등록증명원")
        self.chk_biz_reg_cert.setChecked(True)
        
        indiv_biz_layout.addWidget(self.chk_biz_person)
        indiv_biz_layout.addWidget(self.chk_biz_reg_cert)
        
        indiv_biz_layout.addStretch() # 중간 여백
        
        # 2. 사업장 소재지 라디오 버튼 (오른쪽)
        loc_label = QLabel("사업장 소재지:")
        loc_label.setStyleSheet("color: #666; font-size: 11px;")
        
        self.biz_location_group = QButtonGroup(self)
        self.rb_loc_any = QRadioButton("무관")
        self.rb_loc_region = QRadioButton("지역명") # set_region에서 업데이트됨
        
        self.biz_location_group.addButton(self.rb_loc_any)
        self.biz_location_group.addButton(self.rb_loc_region)
        
        indiv_biz_layout.addWidget(loc_label)
        indiv_biz_layout.addWidget(self.rb_loc_any)
        indiv_biz_layout.addWidget(self.rb_loc_region)

        # (3) 법인 페이지
        corp_page = QWidget()
        corp_layout = QHBoxLayout(corp_page)
        corp_layout.setContentsMargins(85, 0, 0, 0)
        self.chk_corp_reg = QCheckBox("법인등기부등본")
        self.chk_corp_reg.setChecked(True)
        self.chk_corp_biz_cert = QCheckBox("사업자등록증명원")
        self.chk_corp_biz_cert.setChecked(True)
        corp_layout.addWidget(self.chk_corp_reg)
        corp_layout.addWidget(self.chk_corp_biz_cert)
        corp_layout.addStretch()

        # (4) 외국인 페이지
        foreigner_page = QWidget()
        foreigner_layout = QVBoxLayout(foreigner_page)
        foreigner_layout.setContentsMargins(85, 0, 0, 0)
        self.foreigner_input = QLineEdit()
        self.foreigner_input.setPlaceholderText("'외국인등록증' 혹은 '국내거소사실확인서' 입력")
        foreigner_layout.addWidget(self.foreigner_input)

        self.entity_stack.addWidget(person_page)     # index 0
        self.entity_stack.addWidget(indiv_biz_page)  # index 1
        self.entity_stack.addWidget(corp_page)       # index 2
        self.entity_stack.addWidget(foreigner_page)  # index 3

        # 콤보박스 변경 시 스택 변경 연결
        self.entity_type_combo.currentIndexChanged.connect(self.entity_stack.setCurrentIndex)
        
        common_layout.addWidget(self.entity_stack)

        # 4. 서류 발급일 기준
        doc_date_layout = QHBoxLayout()
        doc_date_label = QLabel("서류 발급일 기준:")
        doc_date_label.setFixedWidth(110)
        
        self.doc_date_combo = QComboBox()
        self.doc_date_combo.addItems(["15", "30", "60", "90", "X"])
        self.doc_date_combo.setFixedWidth(60)
        self.doc_date_combo.setCurrentIndex(1)  # "30"이 디폴트가 되도록 인덱스 1로 설정
        
        day_unit_label = QLabel("(일)")
        day_unit_label.setStyleSheet("color: #666;")
        
        doc_date_layout.addWidget(doc_date_label)
        doc_date_layout.addWidget(self.doc_date_combo)
        doc_date_layout.addWidget(day_unit_label)
        doc_date_layout.addStretch()
        
        common_layout.addLayout(doc_date_layout)

        layout.addWidget(common_group)

        # 지자체 추가 서류 섹션 (작업자가 추가 가능)
        extra_group = QGroupBox("지자체 추가 서류")
        extra_layout = QVBoxLayout(extra_group)
        
        self.extra_docs_list = QListWidget()
        self.extra_docs_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.extra_docs_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # 항목 추가 입력창 및 버튼
        add_input_layout = QHBoxLayout()
        self.doc_input_field = QLineEdit()
        self.doc_input_field.setPlaceholderText("추가 서류 명칭 입력...")
        
        # 자동완성 (Completer) 설정
        self.common_docs = ['지방세(납세)증명 신청서', '탄소중립포인트(에너지) 가입 확인서']
        completer = QCompleter(self.common_docs)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains) # 포함된 텍스트로 검색 가능
        self.doc_input_field.setCompleter(completer)
        
        self.doc_input_field.returnPressed.connect(self._add_extra_document) # 엔터키 지원
        
        add_btn = QPushButton("추가")
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(self._add_extra_document)
        add_btn.setStyleSheet("padding: 5px; background-color: #f0f0f0;")
        
        add_input_layout.addWidget(self.doc_input_field)
        add_input_layout.addWidget(add_btn)
        
        # 빠른 추가 버튼 (UX 개선)
        quick_add_layout = QHBoxLayout()
        quick_add_layout.setSpacing(8)
        quick_label = QLabel("빠른 추가:")
        quick_label.setStyleSheet("font-size: 11px; color: #666;")
        quick_add_layout.addWidget(quick_label)
        
        for doc_name in self.common_docs:
            q_btn = QPushButton(doc_name)
            q_btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px;
                    color: #0078d4;
                    background: transparent;
                    border: 1px solid #0078d4;
                    border-radius: 10px;
                    padding: 2px 10px;
                }
                QPushButton:hover {
                    background-color: #f0f7ff;
                }
            """)
            # 람다 캡처 문제 방지를 위해 doc_name=doc_name 사용
            q_btn.clicked.connect(lambda checked, name=doc_name: self._add_extra_document(name))
            quick_add_layout.addWidget(q_btn)
        quick_add_layout.addStretch()

        extra_layout.addWidget(self.extra_docs_list)
        extra_layout.addLayout(add_input_layout)
        extra_layout.addLayout(quick_add_layout) # 빠른 추가 레이아웃 추가
        
        # 도움말 팁
        tip_label = QLabel("※ 항목을 더블클릭하면 삭제할 수 있습니다.")
        tip_label.setStyleSheet("color: #999; font-size: 11px;")
        extra_layout.addWidget(tip_label)
        
        self.extra_docs_list.itemDoubleClicked.connect(lambda item: self.extra_docs_list.takeItem(self.extra_docs_list.row(item)))
        
        layout.addWidget(extra_group)
        layout.addStretch()
        return page

    def _select_app_form_file(self):
        """파일 탐색기를 열어 PDF 파일을 선택합니다."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "지원신청서 파일 선택",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if file_path:
            if file_path.lower().endswith('.pdf'):
                self.app_form_path_edit.setText(file_path)
                self.app_form_path_edit.setStyleSheet("background-color: #f8f8f8; color: #333; font-weight: bold;")
            else:
                QMessageBox.warning(self, "경고", "PDF 파일만 첨부할 수 있습니다.")

    def _add_extra_document(self, text=None):
        # 인자가 없거나(returnPressed) 불리언인 경우(clicked) 입력창의 텍스트를 사용
        if text is None or isinstance(text, bool):
            text = self.doc_input_field.text().strip()
        else:
            text = text.strip()
            
        if text:
            # 중복 체크
            existing_items = [self.extra_docs_list.item(i).text() for i in range(self.extra_docs_list.count())]
            if text not in existing_items:
                self.extra_docs_list.addItem(text)
                self.doc_input_field.clear()
            else:
                self.doc_input_field.setPlaceholderText("이미 존재하는 항목입니다!")

    def _create_joint_owner_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # 1. 공동명의 기본 조건 (라디오 버튼 그룹)
        cond_group = QGroupBox("공동명의 기본 조건")
        cond_layout = QVBoxLayout(cond_group)
        
        self.joint_group = QButtonGroup(self)
        self.joint_radios = []
        conditions = [
            "등본 상 세대 내 가족 (거주요건 둘 다 만족)",
            "등본 상 세대 내 가족 (대표자만 만족 가능)",
            "같은 지역 내 (가족 관계 무관 가능)",
            "타지역 (가족 관계 무관 가능)",
            "타지역 (가족 필수)",
            "주민등록상 동일 세대원 한정",
            "지자체 확인 필요"
        ]
        
        for i, text in enumerate(conditions):
            rb = QRadioButton(text)
            if i == 0: rb.setChecked(True)
            cond_layout.addWidget(rb)
            self.joint_group.addButton(rb)
            self.joint_radios.append(rb)
            
        # 직접 입력 라디오 버튼 및 입력창
        custom_layout = QHBoxLayout()
        self.joint_custom_radio = QRadioButton("직접 입력")
        self.joint_group.addButton(self.joint_custom_radio)
        self.joint_custom_edit = QLineEdit()
        self.joint_custom_edit.setPlaceholderText("조건을 직접 입력하세요...")
        self.joint_custom_edit.setEnabled(False) # 처음엔 비활성화
        
        # 라디오 버튼 상태에 따라 입력창 활성화 제어
        self.joint_custom_radio.toggled.connect(self.joint_custom_edit.setEnabled)
        
        custom_layout.addWidget(self.joint_custom_radio)
        custom_layout.addWidget(self.joint_custom_edit)
        cond_layout.addLayout(custom_layout)
        
        layout.addWidget(cond_group)

        # 2. 기타 조건 (지분율, 대표자 설정)
        other_group = QGroupBox("세부 조건 설정")
        other_layout = QFormLayout(other_group)
        other_layout.setSpacing(10)

        self.joint_share_edit = QLineEdit()
        self.joint_share_edit.setPlaceholderText("예: 대표자 지분 50% 이상")
        other_layout.addRow("지분율 조건:", self.joint_share_edit)

        self.joint_rep_edit = QLineEdit()
        self.joint_rep_edit.setPlaceholderText("예: 거주요건 충족자 우선")
        other_layout.addRow("대표자 설정 방식:", self.joint_rep_edit)
        
        layout.addWidget(other_group)
        layout.addStretch()

        return page

    def _create_residence_page(self):
        """거주요건 조건 입력 페이지"""
        page = QWidget()
        layout = QFormLayout(page)
        layout.setSpacing(15)

        # 1. 거주 기간 조건 (라디오 버튼)
        period_layout = QHBoxLayout()
        self.residence_period_group = QButtonGroup(self)
        
        periods = [("30", "30일"), ("60", "60일"), ("90", "90일"), ("", "확인필요")]
        for val, label in periods:
            rb = QRadioButton(label)
            if val == "90": rb.setChecked(True) # 기본값 90일
            rb.setProperty("value", val)
            self.residence_period_group.addButton(rb)
            period_layout.addWidget(rb)
        
        layout.addRow("거주 기간 조건:", period_layout)

        return page

    def _create_priority_page(self):
        """우선순위 조건 입력 페이지"""
        page = QWidget()
        layout = QFormLayout(page)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # 7가지 항목 정의
        self.priority_edits = {}
        items = [
            ("multi_child", "다자녀"),
            ("first_time", "생애최초"),
            ("low_income", "차상위/기초생활수급자"),
            ("disabled", "장애인"),
            ("scrappage", "노후 경유차 조기폐차"),
            ("merit", "국가유공자"),
            ("small_biz", "소상공인")
        ]

        for key, label in items:
            if key == "multi_child":
                # 다자녀 전용 UI: 체크박스 + 콤보박스
                h_layout = QHBoxLayout()
                
                self.chk_multi_child_reg_only = QCheckBox("등본만 가능")
                self.chk_multi_child_reg_only.setChecked(False)
                
                self.combo_multi_child_age = QComboBox()
                self.combo_multi_child_age.addItems(['만 18세 이하', '만 19세 이하', '알 수 없음'])
                self.combo_multi_child_age.setCurrentIndex(0) # '만 18세 이하' 디폴트
                
                h_layout.addWidget(self.chk_multi_child_reg_only)
                h_layout.addWidget(self.combo_multi_child_age)
                h_layout.addStretch()
                
                layout.addRow(f"{label}:", h_layout)
            else:
                edit = QLineEdit()
                if key == "first_time":
                    edit.setText("(출생~현재)지방세 세목별 미과세증명서")
                elif key == "low_income":
                    edit.setText("차상위 계층 증명서/기초생활 수급자 증명서")
                elif key == "disabled":
                    edit.setText("장애인증명서(장애인등록증 혹은 복지카드 등)")
                elif key == "merit":
                    edit.setText("국가유공자 확인 증명 서류")
                elif key == "scrappage":
                    edit.setText("(지급신청 시 필요) 자동차 말소 등록 사실증명서")
                elif key == "small_biz":
                    edit.setText("중소기업(소상공인)확인서")
                edit.setPlaceholderText(f"{label} 관련 세부 조건 또는 증빙 서류 입력")
                self.priority_edits[key] = edit
                layout.addRow(f"{label}:", edit)

        return page

    def _on_category_changed(self, index):
        self.stack.setCurrentIndex(index)

class NotificationInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("공고문 관리")
        self.resize(1100, 750)
        self.setMinimumSize(900, 600)
        # 최대화 및 최소화 버튼 활성화
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        
        self.data = {}
        self._load_data_from_db()
        
        self._init_ui()
        self._setup_styles()
        self._load_regions()

    def _load_data_from_db(self):
        """실제 DB에서 공고문 데이터를 불러옵니다."""
        try:
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    # file_paths가 NULL이 아니고 배열 길이가 0보다 큰 데이터 조회
                    query = """
                        SELECT region, file_paths 
                        FROM ev_info 
                        WHERE file_paths IS NOT NULL 
                          AND array_length(file_paths, 1) > 0
                        ORDER BY region ASC
                    """
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    
                    self.data = {row[0]: row[1] for row in rows}
        except Exception as e:
            print(f"DB 데이터 로드 실패: {e}")
            self.data = {}

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 상단 타이틀
        self.title_label = QLabel("지역별 공고문 관리")
        self.title_label.setObjectName("titleLabel")
        main_layout.addWidget(self.title_label)

        # 스플리터 생성
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        
        # 1. 왼쪽: 지역 리스트 영역
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0) # 우측 여백
        
        region_label = QLabel("지역 선택")
        region_label.setObjectName("subHeader")
        
        self.region_list = QListWidget()
        self.region_list.setObjectName("regionList")
        self.region_list.itemClicked.connect(self._on_region_selected)
        
        left_layout.addWidget(region_label)
        left_layout.addWidget(self.region_list)
        
        # 2. 오른쪽: 상세 정보 및 입력 영역
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0) # 좌측 여백
        right_layout.setSpacing(10)
        
        # 2-1. 헤더 (지역명 + 파일 열기)
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 10)
        
        self.region_name_label = QLabel("지역을 선택해주세요")
        self.region_name_label.setObjectName("regionHeader")
        
        # 파일 선택 컨트롤
        file_control_layout = QHBoxLayout()
        file_control_layout.setSpacing(10)
        
        self.file_combo = QComboBox()
        self.file_combo.setPlaceholderText("참조할 공고문 파일을 선택하세요")
        self.file_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.file_combo.setStyleSheet("padding: 5px;")
        
        self.open_file_btn = QPushButton("파일 열기")
        self.open_file_btn.setFixedWidth(80)
        self.open_file_btn.setStyleSheet("padding: 5px;")
        self.open_file_btn.clicked.connect(self._on_open_file_clicked)
        
        file_control_layout.addWidget(self.file_combo)
        file_control_layout.addWidget(self.open_file_btn)
        
        header_layout.addWidget(self.region_name_label)
        header_layout.addLayout(file_control_layout)
        
        right_layout.addWidget(header_widget)
        
        # 2-2. 입력 폼 (내장된 RegionDataFormWidget)
        self.form_widget = RegionDataFormWidget()
        
        # 초기엔 비활성화 상태 (지역 선택 전)
        self.form_widget.setEnabled(False)
        
        right_layout.addWidget(self.form_widget)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        
        # 화면 비율 1:2
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)

    def _setup_styles(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            #titleLabel {
                font-size: 24px;
                font-weight: bold;
                color: #1a1a1a;
                margin-bottom: 5px;
            }
            #subHeader {
                font-size: 14px;
                font-weight: bold;
                color: #666666;
                padding-bottom: 5px;
            }
            #regionHeader {
                font-size: 20px;
                font-weight: bold;
                color: #0078d4;
                border-bottom: 2px solid #0078d4;
                padding-bottom: 8px;
            }
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #fcfcfc;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 15px;
                border-bottom: 1px solid #f0f0f0;
                color: #333333;
            }
            QListWidget::item:hover {
                background-color: #f0f7ff;
            }
            QListWidget::item:selected {
                background-color: #e1f0fe;
                color: #0078d4;
                font-weight: bold;
                border-left: 3px solid #0078d4;
            }
            QSplitter::handle {
                background-color: #e0e0e0;
                width: 1px;
            }
        """)

    def _load_regions(self):
        # file_paths가 있고 그 길이가 0보다 큰 지역만 리스트에 추가합니다.
        regions = sorted(self.data.keys())
        for region in regions:
            files = self.data.get(region, [])
            if files:  # 파일 리스트가 비어있지 않은 경우에만 추가
                item = QListWidgetItem(region)
                self.region_list.addItem(item)
        
        # 만약 표시할 지역이 하나도 없다면 안내 메시지 표시 가능
        if self.region_list.count() == 0:
            item = QListWidgetItem("공고문이 있는 지역이 없습니다.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.region_list.addItem(item)

    def _on_region_selected(self, item):
        region = item.text()
        
        # 1. 헤더 업데이트
        self.region_name_label.setText(f"{region}")
        
        # 2. 파일 콤보박스 업데이트
        self.file_combo.clear()
        files = self.data.get(region, [])
        if files:
            self.file_combo.addItems(files)
            self.file_combo.setEnabled(True)
            self.open_file_btn.setEnabled(True)
        else:
            self.file_combo.addItem("표시할 파일이 없습니다")
            self.file_combo.setEnabled(False)
            self.open_file_btn.setEnabled(False)
            
        # 3. 폼 위젯 활성화 및 지역 설정
        self.form_widget.setEnabled(True)
        self.form_widget.set_region(region)

        # 4. 기존 DB 데이터 로드
        try:
            with closing(psycopg2.connect(**DB_CONFIG)) as conn:
                with conn.cursor() as cursor:
                    query = """
                        SELECT notification_apply, co_name, residence_requirements, notification_payment
                        FROM 공고문 g
                        JOIN region_metadata r ON g.region_id = r.region_id
                        WHERE r.region = %s
                    """
                    cursor.execute(query, (region,))
                    row = cursor.fetchone()
                    if row:
                        existing_data = {
                            'notification_apply': row[0],
                            'co_name': row[1],
                            'residence_requirements': row[2],
                            'notification_payment': row[3]
                        }
                        self.form_widget.load_data(existing_data)
                    else:
                        # 데이터가 없는 경우 폼을 기본 상태로 초기화 (필요시)
                        pass
        except Exception as e:
            print(f"기존 데이터 로드 실패: {e}")

    def _on_open_file_clicked(self):
        file_path = self.file_combo.currentText()
        if file_path and os.path.exists(file_path):
            try:
                os.startfile(file_path)
            except Exception as e:
                QMessageBox.warning(self, "오류", f"파일을 열 수 없습니다:\n{e}")
        else:
            QMessageBox.warning(self, "경고", "유효한 파일 경로가 아닙니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # 부드러운 외관을 위해 Fusion 스타일 적용
    dialog = NotificationInfoDialog()
    dialog.show()
    sys.exit(app.exec())
