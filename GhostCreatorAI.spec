# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('icon.ico', '.'), ('assets', 'assets'), ('config.json', '.'), ('ffmpeg', 'ffmpeg'), ('workflow_api.json', '.')]
binaries = []
hiddenimports = ['customtkinter', 'PIL._tkinter_finder', 'gui.app', 'gui.tabs.settings_tab', 'gui.tabs.pipeline_tab', 'modules.researcher', 'modules.scripter', 'modules.voicer', 'modules.image_gen', 'modules.image_prep', 'modules.video_builder', 'modules.img2video', 'modules.uploader', 'modules.thumbnail_maker', 'core.pipeline_runner', 'core.config_manager', 'core.license', 'config', 'backends.base', 'backends.tts.chatterbox', 'backends.tts.edge_tts', 'backends.tts.elevenlabs', 'backends.tts.google_tts', 'backends.tts.kokoro_tts', 'backends.tts.deepgram', 'backends.image.comfyui', 'backends.image.pollinations', 'backends.image.gemini_imagen', 'backends.image.fal_ai', 'backends.image.stable_horde', 'backends.image.replicate', 'backends.image.grok_image', 'edge_tts', 'elevenlabs', 'google.cloud.texttospeech', 'kokoro', 'soundfile', 'numpy', 'fal_client', 'replicate', 'google.genai', 'google.genai.types', 'pydub', 'pydub.audio_segment', 'pydub.effects', 'feedparser', 'pytrends', 'pytrends.request', 'requests', 'requests.adapters', 'playwright', 'playwright.async_api', 'colorlog', 'dotenv', 'tqdm', 'websocket']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('edge_tts')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('kokoro')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google.cloud.texttospeech')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google.genai')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fal_client')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('replicate')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('deepgram')
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
    excludes=[],
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
