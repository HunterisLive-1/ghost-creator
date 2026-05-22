# Troubleshooting

## GUI stuck on "Initializing Neural Interface…"

```powershell
venv\Scripts\activate.bat
pip install -r requirements.txt
npm install
python -m api.server
# Visit http://127.0.0.1:8766/health — should return {"ok": true, ...}
npm run electron:dev
```

Ensure nothing else is using port **8766**.

## FFmpeg not found

```powershell
winget install ffmpeg
ffmpeg -version
```

Or for dev only:

```powershell
powershell -ExecutionPolicy Bypass -File ensure_ffmpeg.ps1
```

## OmniVoice / voice step fails

- Confirm OmniVoice server is running
- Check **Settings → OmniVoice server path** points to the correct `.bat`
- Verify `my_voice_reference.wav` exists, or switch to **Edge TTS** for a quick test

## Footage download slow or failing

- Add a **Pexels API key** in Settings (free)
- yt-dlp fallback requires internet; some queries may fail if no matching YouTube clip exists
- Retry with **RETRY STEP** on the Documentary tab

## YouTube upload fails

- Use real **Google Chrome** (not Edge Chromium-only builds for Playwright)
- Run `python setup_chrome_profile.py` and complete sign-in once
- Check the correct Chrome profile is selected in Settings
- Ensure upload is enabled: Settings → YouTube upload

## `config.json` missing

```powershell
venv\Scripts\activate.bat
python -c "from core.config_manager import config; config.save()"
```

Or re-run `setup.bat`.

## Gemini / script errors

- Verify `api_keys.gemini` in Settings
- Check API quota at [aistudio.google.com](https://aistudio.google.com)
- For local scripts, ensure Ollama is running and reachable at the URL in Settings

## `No module named 'X'`

```powershell
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Documentation not loading

- Ensure the API is running: `python -m api.server`
- Open `http://127.0.0.1:8766/guide` in your browser
- API reference (Swagger) is at `http://127.0.0.1:8766/docs`
