# Configuration Reference

Settings are stored in **`config.json`**.

| Environment | Config location |
|-------------|-----------------|
| Development (`python` / `npm run electron:dev`) | Project root `config.json` |
| Installed app | `%LOCALAPPDATA%\GhostCreatorAI\config.json` |

Secrets can also be set in **`.env.local`** (synced on Save).

## Key settings

| Key | Default | Description |
|-----|---------|-------------|
| `api_keys.gemini` | `""` | Gemini API key (required) |
| `api_keys.pexels` | `""` | Pexels API key (optional footage) |
| `api_keys.elevenlabs` | `""` | ElevenLabs key |
| `tts.backend` | `omnivoice` | `omnivoice` \| `edge_tts` \| `elevenlabs` |
| `tts.reference_audio` | `my_voice_reference.wav` | OmniVoice clone reference |
| `tts.omnivoice_server_path` | `""` | Path to OmniVoice start script |
| `script_provider` | `gemini` | `gemini` \| `ollama` |
| `gemini_model` | `gemini-2.0-flash` | Script generation model |
| `script_review_enabled` | `true` | Pause for script review in GUI |
| `pipeline.language` | `hi` | Narration language code |
| `pipeline.output_folder` | `output` | Finished videos directory |
| `pipeline.upload_enabled` | `true` | Auto-upload after assembly |
| `pipeline.upload_mode` | `unlisted` | `unlisted` \| `public` \| `draft` |
| `documentary.length_mode` | `short` | `short` \| `long` |
| `documentary.short_duration` | `60` | Short mode seconds |
| `documentary.long_duration` | `600` | Long mode seconds |
| `documentary.burn_subtitles` | `false` | Long-form hard subs |
| `documentary.logo_enabled` | `false` | Watermark on export |
| `aspect_ratio` | `9:16` | Overridden to `16:9` for long mode |
