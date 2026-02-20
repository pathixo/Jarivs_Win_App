# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Collect ctranslate2 binaries and data
ctranslate2_datas = collect_data_files('ctranslate2')
ctranslate2_bins = collect_dynamic_libs('ctranslate2')

# Collect faster_whisper data files
faster_whisper_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['Jarvis/main.py'],
    pathex=['d:/Coding/Projects/Antigravity'],
    binaries=ctranslate2_bins,
    datas=ctranslate2_datas + faster_whisper_datas + [
        ('Jarvis/config.py', 'Jarvis'),
    ],
    hiddenimports=[
        'faster_whisper',
        'ctranslate2',
        'huggingface_hub',
        'tokenizers',
        'pyaudio',
        'numpy',
        'scipy',
        'scipy.signal',
        'scipy.special',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.QtMultimedia',
        'PyQt6.sip',
        'edge_tts',
        'dotenv',
        'requests',
        'certifi',
        'charset_normalizer',
        'idna',
        'urllib3',
        'av',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchaudio',
        'torchvision',
        'tensorflow',
        'matplotlib',
        'pandas',
        'jupyter',
        'IPython',
    ],
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
    name='Jarvis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # Windowed mode (no console window)
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Jarvis',
)
