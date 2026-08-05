# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# List of plugin modules to import dynamically at runtime
plugins_hidden_imports = [
    'plugins.browser_plugin',
    'plugins.calculator_plugin',
    'plugins.code_helper_plugin',
    'plugins.file_manager_plugin',
    'plugins.memory_plugin',
    'plugins.scheduler_plugin',
    'plugins.system_control_plugin',
    'plugins.system_info_plugin',
    'plugins.system_monitor_plugin',
    'plugins.terminal_plugin',
    'plugins.time_plugin',
    'plugins.voice_plugin',
    'plugins.web_search_plugin'
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('.env.example', '.'),
        ('plugins', 'plugins'),
        ('skills', 'skills')
    ],
    hiddenimports=[
        'sounddevice',
        'numpy',
        'faster_whisper',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui'
    ] + plugins_hidden_imports,
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Nova',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
