from pathlib import Path

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QKeySequence

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = Path(__file__).parent.parent / "ui" / "settings.ui"
        uic.loadUi(str(ui_path), self)
        
        self.settings = QSettings("GyeonggooLee", "NewViewer")
        
        self._load_settings()
        
        self.accepted.connect(self._save_settings)

    def _load_settings(self):
        """저장된 단축키 설정을 불러와 UI에 적용합니다."""
        # TODO: settings.ui의 위젯 이름들이 명확해지면 키 값도 그에 맞게 수정해야 합니다.
        shortcut_toggle_todo = self.settings.value("shortcuts/toggle_todo", "`")
        stamp_overlay_shortcut = self.settings.value("shortcuts/toggle_stamp_overlay", "T")
        mail_overlay_shortcut = self.settings.value("shortcuts/toggle_mail_overlay", "M")
        crop_shortcut = self.settings.value("shortcuts/crop", "Y")
        view_ai_results_shortcut = self.settings.value("shortcuts/view_ai_results", "A")

        self.keySequenceEdit_to_do.setKeySequence(QKeySequence.fromString(shortcut_toggle_todo, QKeySequence.SequenceFormat.PortableText))
        self.keySequenceEdit_toggleStampOverlay.setKeySequence(QKeySequence.fromString(stamp_overlay_shortcut, QKeySequence.SequenceFormat.PortableText))
        self.keySequenceEdit_toggleMailOverlay.setKeySequence(QKeySequence.fromString(mail_overlay_shortcut, QKeySequence.SequenceFormat.PortableText))
        self.keySequenceEdit_crop.setKeySequence(QKeySequence.fromString(crop_shortcut, QKeySequence.SequenceFormat.PortableText))
        self.keySequenceEdit_insert_5.setKeySequence(QKeySequence.fromString(view_ai_results_shortcut, QKeySequence.SequenceFormat.PortableText))

        # 나머지 단축키 설정 로드 (임시)
        self.keySequenceEdit_insert_2.setKeySequence(QKeySequence(self.settings.value("shortcuts/unused_1", "")))
        #self.keySequenceEdit_insert_3.setKeySequence(QKeySequence(self.settings.value("shortcuts/unused_2", "")))
        self.keySequenceEdit_insert_4.setKeySequence(QKeySequence(self.settings.value("shortcuts/unused_3", "")))
        self.keySequenceEdit_insert_6.setKeySequence(QKeySequence(self.settings.value("shortcuts/unused_5", "")))
        self.keySequenceEdit_insert_7.setKeySequence(QKeySequence(self.settings.value("shortcuts/unused_6", "")))
        self.keySequenceEdit_insert_8.setKeySequence(QKeySequence(self.settings.value("shortcuts/unused_7", "")))


    def _save_settings(self):
        """UI에 설정된 단축키를 저장합니다."""
        self.settings.setValue("shortcuts/toggle_todo", self.keySequenceEdit_to_do.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
        self.settings.setValue("shortcuts/toggle_stamp_overlay", self.keySequenceEdit_toggleStampOverlay.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
        self.settings.setValue("shortcuts/toggle_mail_overlay", self.keySequenceEdit_toggleMailOverlay.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
        self.settings.setValue("shortcuts/crop", self.keySequenceEdit_crop.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
        self.settings.setValue("shortcuts/view_ai_results", self.keySequenceEdit_insert_5.keySequence().toString(QKeySequence.SequenceFormat.PortableText))


        # 나머지 설정들도 동일하게 저장 (임시)
        self.settings.setValue("shortcuts/unused_1", self.keySequenceEdit_insert_2.keySequence().toString())
        # self.settings.setValue("shortcuts/unused_2", self.keySequenceEdit_insert_3.keySequence().toString())
        self.settings.setValue("shortcuts/unused_3", self.keySequenceEdit_insert_4.keySequence().toString())
        self.settings.setValue("shortcuts/unused_5", self.keySequenceEdit_insert_6.keySequence().toString())
        self.settings.setValue("shortcuts/unused_6", self.keySequenceEdit_insert_7.keySequence().toString())
        self.settings.setValue("shortcuts/unused_7", self.keySequenceEdit_insert_8.keySequence().toString())

    def get_shortcuts(self):
        """외부에서 단축키를 가져갈 수 있도록 사전을 반환합니다."""
        # 이 메서드는 나중에 QAction에 단축키를 적용할 때 필요합니다.
        shortcuts = {
            "insert_tool_1": self.keySequenceEdit_insert.keySequence()
            # ...
        }
        return shortcuts
