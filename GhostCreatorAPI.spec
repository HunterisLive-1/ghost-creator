# -*- mode: python ; coding: utf-8 -*-
# GhostCreatorAPI.spec — PyInstaller spec for Ghost Creator AI API sidecar
# Generated for Python 3.10 / PyInstaller 6.x
# Build: pyinstaller GhostCreatorAPI.spec

import sys
import os
from pathlib import Path

block_cipher = None

# Project root (where this spec lives)
ROOT = os.path.abspath(SPECPATH)  # SPECPATH is already the spec's directory

a = Analysis(
    [os.path.join(ROOT, 'api', 'server.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'docs'), 'docs'),
        (os.path.join(ROOT, 'api', 'templates'), os.path.join('api', 'templates')),
    ],
    hiddenimports=[
        # FastAPI / Uvicorn
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn._types',
        'fastapi',
        'fastapi.middleware.cors',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        # Pydantic
        'pydantic',
        'pydantic.v1',
        'pydantic_core',
        # Markdown
        'markdown',
        # Google auth
        'google.auth',
        'google.oauth2',
        'google.oauth2.credentials',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'googleapiclient',
        'googleapiclient.discovery',
        # TTS backends
        'edge_tts',
        'elevenlabs',
        # HTTP
        'httpx',
        'aiohttp',
        'aiofiles',
        # API routes
        'api.server',
        'api.routes',
        'api.routes.config',
        'api.routes.docs',
        'api.routes.history',
        'api.routes.misc',
        'api.routes.pipeline',
        'api.routes.system',
        'api.routes.upload',
        'api.routes.workshop',
        # Core
        'core',
        'core.config_manager',
        'core.ffmpeg_bootstrap',
        'core.pipeline_runner',
        'core.stock_manager',
        # Modules
        'modules',
        'modules.researcher',
        'modules.uploader',
        # LangGraph / LangChain / Graph
        'langgraph',
        'langgraph.graph',
        'langgraph.checkpoint.sqlite',
        'langchain',
        'langchain_core',
        'langchain_community',
        'langchain_google_genai',
        'langchain_groq',
        'aiosqlite',
        'groq',
        'tavily',
        'sqlite3',
        'graph',
        'graph.state',
        'graph.pipeline',
        'graph.nodes',
        'graph.nodes.research_node',
        'graph.nodes.script_node',
        'graph.nodes.script_critic_node',
        'graph.nodes.human_review_node',
        'graph.nodes.image_node',
        'graph.nodes.voiceover_node',
        'graph.nodes.seo_node',
        'graph.nodes.editor_prep_node',
        'graph.nodes.assemble_node',
        'graph.nodes.upload_node',
        'graph.nodes.error_recovery_node',
        'pydantic.v1',
        # Misc
        'email.mime',
        'email.mime.text',
        'email.mime.multipart',
        'pkg_resources',
        'pkg_resources.extern',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy ML/Science libs — not needed at runtime
        'torch',
        'torchaudio',
        'torchvision',
        'tensorboard',
        'tensorflow',
        'sklearn',
        'scipy',
        # pandas causes dis.py crash on Python 3.10.0 — skip static analysis
        'pandas',
        'numpy',
        # pytrends uses pandas — skip
        'pytrends',
        # Not needed
        'numba',
        'omnivoice',
        'matplotlib',
        'IPython',
        'ipykernel',
        'notebook',
        'pytest',
        'docutils',
        'sphinx',
        'Cython',
        'tkinter',
        'wx',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'gi',
        'gtk',
        # num2words language modules cause dis crashes — exclude them; only keep what's needed
        'num2words',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir mode — binaries go in the COLLECT step
    name='GhostCreatorAPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX off to avoid false-positive AV alerts
    console=True,            # Keep console so errors are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'icon.ico') if os.path.exists(os.path.join(ROOT, 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GhostCreatorAPI',
)
