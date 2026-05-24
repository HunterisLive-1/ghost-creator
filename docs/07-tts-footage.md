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

Documentary **Step 4** downloads one clip per script segment. Choose the source in **Settings → FOOTAGE SOURCE**.

### Stock (default)

Real stock/video clips via [`modules/video_fetcher.py`](../modules/video_fetcher.py):

1. **Pexels API** — fast direct HD downloads (requires `api_keys.pexels` in Settings)
2. **yt-dlp fallback** — YouTube B-roll; downloads first ~90 s per query

Each segment includes a **video search query** (editable in Script Review). Clips are trimmed and synced to narration during assembly.

### Meta AI (browser automation)

Optional AI-generated B-roll using **Meta AI web UI** — no Meta video API key.

| Setting | Purpose |
|---------|---------|
| `documentary.footage_source` | `stock` or `meta_ai` |
| `meta_ai.chrome_profile_path` | Persistent Chrome login session |
| `meta_ai.fallback_to_stock` | Use Pexels/YouTube if one AI clip fails |
| `meta_ai.generation_timeout_ms` | Max wait per clip (default 10 min) |

**Setup (one time):**

1. Settings → **FOOTAGE SOURCE** → **Meta AI — browser automation**
2. Click **SETUP META PROFILE** (or run `python setup_meta_profile.py`)
3. Log in to Meta / Facebook in the Chrome window that opens
4. Close Chrome; profile path is saved automatically
5. Click **TEST META LOGIN** to verify

**CLI test (single clip):**

```bash
python -m modules.ai_video.meta_ai_browser "cinematic mountain sunset documentary"
```

Output: `output/meta_ai_test_clip.mp4` (or debug screenshots `output/meta_ai_debug_*.png` on failure).

**Expectations:**

- **Slow:** often 1–5+ minutes per clip (5 segments ≈ 5–25 min for footage step alone)
- **Visible browser recommended:** headless mode often fails login/captcha
- **Brittle:** Meta UI changes can break automation; update selectors in `modules/ai_video/meta_ai_browser.py`
- **Use at your own risk:** automating consumer web UIs may violate Meta terms of service

### Grok (browser automation)

Same shared Chrome profile as Meta AI — log in on the **Grok tab** during profile setup.

| Setting | Purpose |
|---------|---------|
| `documentary.footage_source` | `grok` |
| `meta_ai.chrome_profile_path` | Shared persistent Chrome session |
| `grok.base_url` | Default `https://grok.com/imagine` |
| `grok.fallback_to_stock` | Use Pexels/YouTube if one AI clip fails |

**CLI test (single clip):**

```bash
python -m modules.ai_video.grok_browser "cinematic mountain sunset documentary"
```

Output: `output/grok_test_clip.mp4` (or debug screenshots `output/grok_debug_*.png` on failure).

Requires Grok / X Premium for video generation on grok.com.

### Grok API (not used here)

The codebase also references `grok_image_model` for image API — documentary footage uses browser automation only, not the xAI API.
