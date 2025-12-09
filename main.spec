# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 파일
main.py를 기반으로 실행 파일 생성
"""

import os
from pathlib import Path

block_cipher = None

# 프로젝트 루트 경로
# SPECPATH는 PyInstaller가 자동으로 설정하는 변수 (spec 파일이 있는 디렉토리)
try:
    project_root = Path(SPECPATH)
except NameError:
    # SPECPATH가 없는 경우 현재 파일의 디렉토리 사용
    project_root = Path(__file__).parent if '__file__' in globals() else Path.cwd()

# UI 파일들 수집
ui_files = []
ui_dir = project_root / 'ui'
if ui_dir.exists():
    for ui_file in ui_dir.glob('*.ui'):
        ui_files.append((str(ui_file), 'ui'))

# assets 파일들 수집
assets_files = []
assets_dir = project_root / 'assets'
if assets_dir.exists():
    for asset_file in assets_dir.glob('*'):
        if asset_file.is_file():
            assets_files.append((str(asset_file), 'assets'))

# 데이터 파일들
data_files = [
    (str(project_root / 'core' / 'region_data.json'), 'core'),
]

# 모든 데이터 파일 추가
datas = ui_files + assets_files + data_files

# 숨겨진 import들
hiddenimports = [
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.uic',
    'qt_material',
    'pymupdf',
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'pandas',
    'openpyxl',
    'xlrd',
    'mysql',
    'mysql.connector',
    'google',
    'google.oauth2',
    'google.oauth2.credentials',
    'google_auth_oauthlib',
    'googleapiclient',
    'googleapiclient.discovery',
    'google.genai',
    'google.generativeai',
    'httpx',
    'requests',
    'pytz',
    'filelock',
    'reportlab',
    'PyPDF2',
    'pypdf',
    'pynput',
    'core',
    'core.pdf_render',
    'core.pdf_saved',
    'core.sql_manager',
    'core.workers',
    'core.utility',
    'core.ui_helpers',
    'core.delete_utils',
    'core.edit_mixin',
    'core.etc_tools',
    'core.insert_utils',
    'core.mail_utils',
    'widgets',
    'widgets.main_window',
    'widgets.pdf_load_widget',
    'widgets.pdf_view_widget',
    'widgets.thumbnail_view_widget',
    'widgets.info_panel_widget',
    'widgets.todo_widget',
    'widgets.settings_dialog',
    'widgets.login_dialog',
    'widgets.special_note_dialog',
    'widgets.worker_progress_dialog',
    'widgets.alarm_widget',
    'widgets.detail_form_dialog',
    'widgets.config_dialog',
    'widgets.necessary_widget',
    'widgets.multi_child_check_dialog',
    'widgets.crop_dialog',
    'widgets.custom_item',
    'widgets.email_view_dialog',
    'widgets.ev_helper_dialog',
    'widgets.floating_toolbar',
    'widgets.gemini_results_dialog',
    'widgets.helper_overlay',
    'widgets.mail_content_overlay',
    'widgets.mail_dialog',
    'widgets.page_delete_dialog',
    'widgets.reverse_line_edit',
    'widgets.stamp_overlay_widget',
    'widgets.unqualified_document_dialog',
    'widgets.zoomable_graphics_view',
    'get_mail_logics',
    'get_mail_logics.thread',
    'get_mail_logics.db_mail',
    'get_mail_logics.pdf_annotation_guard',
    'get_mail_logics.pdf_process',
    'get_mail_logics.pdf_rotation',
    'get_mail_logics.reply_mail',
    'get_mail_logics.gemini_utils',
    'get_mail_logics.config',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 디버깅을 위해 콘솔 창 표시
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 아이콘 파일이 있다면 경로 지정
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)

