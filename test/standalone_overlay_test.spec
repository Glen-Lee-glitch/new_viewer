# -*- mode: python ; coding: utf-8 -*-

# PyInstaller 사양 파일
# 이 파일을 사용하여 'pyinstaller standalone_overlay_test.spec' 명령으로 빌드할 수 있습니다.

block_cipher = None

a = Analysis(
    ['standalone_overlay_test.py'],
    pathex=['test'], # 스크립트가 있는 폴더 경로
    binaries=[],
    datas=[],
    hiddenimports=[
        # pandas가 내부적으로 사용하는 모듈들을 명시적으로 포함
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.timestamps',
        # PyQt6의 필수 모듈
        'PyQt6.sip',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        # pynput이 Windows에서 사용하는 백엔드 모듈
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
    ],
    hookspath=[],
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
    name='StandaloneOverlayTester', # 생성될 exe 파일 이름
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # True로 설정하면 실행 시 콘솔 창이 나타남 (디버깅용)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None # 아이콘 파일 경로 (예: 'app.ico')
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StandaloneOverlayTester', # 생성될 폴더 이름
)
