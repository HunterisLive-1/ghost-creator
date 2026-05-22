# CLI & Building Releases

## CLI Reference

Headless entry point: `main.py`

```powershell
# Auto-topic documentary
python main.py

# Fixed topic
python main.py --topic "Future of AI in India"

# Force YouTube upload after generation
python main.py --topic "Space exploration" --upload

# Upload existing MP4 only
python main.py --from-video
python main.py --from-video --video-file "output\my_run\documentary.mp4"

# Show version
python main.py --version
```

**Notes**

- CLI runs **disable script review** automatically (no modal)
- Upload uses metadata from the run folder or `output/last_metadata.json`
- Respects `pipeline.upload_enabled` unless `--upload` flag is passed

---

## Building a Release

For developers packaging a Windows installer:

```powershell
# 1. Build Python API sidecar
build-api.bat
# Output: dist-api\GhostCreatorAPI.exe

# 2. Build Electron app + NSIS bundle
build-electron.bat
# Output: release\ (electron-builder)

# 3. Optional: Inno Setup installer
# Open installer_v4.iss in Inno Setup Compiler
# Bundles release\win-unpacked + GhostCreatorAPI.exe
```

### Why two build scripts?

| Script | What it builds | Output |
|--------|----------------|--------|
| **`build-api.bat`** | Python backend only (PyInstaller) | `dist-api\GhostCreatorAPI.exe` |
| **`build-electron.bat`** | Full app — calls `build-api.bat`, then compiles React + packages with electron-builder | `release\` folder |

They are separate because Python and Node/Electron use different toolchains. `build-electron.bat` automatically runs `build-api.bat` first so you usually only need the second script for a full release.

**FFmpeg on installed builds:** not bundled in the installer (keeps size small). On first run, FFmpeg is downloaded to:

`%LOCALAPPDATA%\GhostCreatorAI\ffmpeg`

See `core/ffmpeg_bootstrap.py`.
