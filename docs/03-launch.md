# Launching the App

Activate the virtual environment first:

```powershell
venv\Scripts\activate.bat
```

| Mode | Command | Notes |
|------|---------|-------|
| **GUI (recommended)** | `npm run electron:dev` | Starts Vite + Electron; Python API auto-spawns |
| **API only (debug)** | `python -m api.server` | Listens on `http://127.0.0.1:8766/health` |
| **CLI documentary** | `python main.py` | Unattended run; no script review modal |
| **CLI with topic** | `python main.py --topic "AI in India"` | Fixed subject |
| **CLI + force upload** | `python main.py --topic "..." --upload` | Upload even if disabled in config |
| **CLI upload only** | `python main.py --from-video --video-file output/run/film.mp4` | Skip generation |

Electron waits for `GET /health` before showing the main window. If the GUI hangs on "Initializing…", check that port **8766** is free and the venv Python is available.

---

## Documentation URLs (while app is running)

| URL | Purpose |
|-----|---------|
| `http://127.0.0.1:8766/guide` | This user guide (full project docs) |
| `http://127.0.0.1:8766/docs` | API Swagger reference (REST endpoints) |
| `http://127.0.0.1:8766/health` | API health check |

You can also open this guide from **Settings → OPEN DOCUMENTATION**.
