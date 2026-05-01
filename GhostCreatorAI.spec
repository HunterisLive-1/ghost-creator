# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('icon.ico', '.'), ('config.json', '.')]
binaries = []
hiddenimports = ['customtkinter', 'PIL._tkinter_finder', 'gui.app', 'gui.tabs.settings_tab', 'gui.tabs.documentary_tab', 'gui.tabs.history_tab', 'gui.tabs.direct_upload_tab', 'gui.components.video_preview', 'gui.components.script_review', 'gui.components.activation_window', 'gui.components.clip_editor', 'modules.researcher', 'modules.scripter', 'modules.voicer', 'modules.image_gen', 'modules.uploader', 'modules.thumbnail_maker', 'modules.video_fetcher', 'modules.documentary_assembler', 'modules.error_analyst', 'modules.tts_lang_support', 'modules.tts_number_normalize', 'core.pipeline_runner', 'core.config_manager', 'core.ffmpeg_bootstrap', 'core.clip_manager', 'core.vlc_helper', 'core.license', 'core.update_checker', 'config', 'backends.base', 'backends.tts.omnivoice_tts', 'backends.tts.edge_tts', 'backends.tts.elevenlabs', 'backends.image.gemini_imagen', 'edge_tts', 'elevenlabs', 'numpy', 'google.genai', 'google.genai.types', 'pydub', 'pydub.audio_segment', 'pydub.effects', 'feedparser', 'pytrends', 'pytrends.request', 'requests', 'requests.adapters', 'playwright', 'playwright.async_api', 'colorlog', 'dotenv', 'yt_dlp', 'vlc']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('edge_tts')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google.genai')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('yt_dlp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pydub')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gui\\app.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['google.genai.tests', 'pytest', 'tensorboard', 'torch.utils.tensorboard', 'urllib3.contrib.emscripten'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GhostCreatorAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
