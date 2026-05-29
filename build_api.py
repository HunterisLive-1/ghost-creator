import os
import sys
import subprocess
from pathlib import Path

# Spec file contents containing all dependencies, exclusions, and assets configuration
SPEC_CONTENT = """# -*- mode: python ; coding: utf-8 -*-
# GhostCreatorAPI.spec — PyInstaller spec for Ghost Creator AI API sidecar
# Generated for Python 3.10 / PyInstaller 6.x

import sys
import os
from pathlib import Path

block_cipher = None
ROOT = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, 'api', 'server.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'docs'), 'docs'),
        (os.path.join(ROOT, 'api', 'templates'), os.path.join('api', 'templates')),
    ],
    hiddenimports=[
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
        'pydantic',
        'pydantic.v1',
        'pydantic_core',
        'markdown',
        'google.auth',
        'google.oauth2',
        'google.oauth2.credentials',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'googleapiclient',
        'googleapiclient.discovery',
        'edge_tts',
        'elevenlabs',
        'backends',
        'backends.base',
        'backends.tts',
        'backends.tts.omnivoice_tts',
        'backends.tts.elevenlabs',
        'backends.tts.edge_tts',
        'backends.image',
        'backends.image.gemini_imagen',
        'httpx',
        'aiohttp',
        'aiofiles',
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
        'core',
        'core.config_manager',
        'core.ffmpeg_bootstrap',
        'core.pipeline_runner',
        'core.stock_manager',
        'modules',
        'modules.researcher',
        'modules.uploader',
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
        'torch',
        'torchaudio',
        'torchvision',
        'tensorboard',
        'tensorflow',
        'sklearn',
        'scipy',
        'pandas',
        'numpy',
        'pytrends',
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
    exclude_binaries=True,
    name='GhostCreatorAPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
"""

def main():
    root = Path(__file__).resolve().parent
    spec_path = root / "GhostCreatorAPI.spec"
    
    if not spec_path.exists():
        print("[Build System] GhostCreatorAPI.spec missing. Recreating file automatically...")
        spec_path.write_text(SPEC_CONTENT.strip(), encoding="utf-8")
        print("[Build System] GhostCreatorAPI.spec restored successfully!")
        
    print("[Build System] Running PyInstaller build ...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--distpath", str(root / "dist-api"),
        "--workpath", str(root / "build-api"),
        str(spec_path)
    ]
    try:
        subprocess.check_call(cmd, cwd=str(root))
        print("[Build System] API Build succeeded!")
    except subprocess.CalledProcessError as e:
        print(f"[Build System] PyInstaller failed with exit code: {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
