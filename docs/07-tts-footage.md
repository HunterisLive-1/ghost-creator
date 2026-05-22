# TTS & Footage

## TTS Backends

Configured in Settings → Audio. Only three backends are supported:

| Backend | Cost | Quality | Setup |
|---------|------|---------|-------|
| **OmniVoice** (default) | Free (local server) | Best voice clone | External OmniVoice install + reference WAV |
| **Edge TTS** | Free | Good neural voices | None — works immediately |
| **ElevenLabs** | Paid | Premium cloud | API key + Voice ID in Settings |

**OmniVoice is not bundled** in Ghost Creator or `GhostCreatorAPI.exe`. Install OmniVoice separately (e.g. `D:\omnivoice\OmniVoice`), then in Settings set **OmniVoice Server Path** to that folder's `run.bat`. Ghost Creator only starts the server and calls its WebUI over HTTP.

Language support varies by backend; the pipeline validates compatibility before synthesis.

---

## Footage Sources

Documentary mode downloads **real stock/video clips**, not AI-generated images.

Priority (`modules/video_fetcher.py`):

1. **Pexels API** — fast direct HD downloads (requires `api_keys.pexels`)
2. **yt-dlp fallback** — YouTube B-roll; downloads first ~90 s per query via `--download-sections`

Each script segment includes a **video search query** (editable in Script Review). Clips are trimmed and synced to narration length during assembly.
