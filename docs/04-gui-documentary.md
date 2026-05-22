# GUI — Documentary Tab

The app opens directly to the main interface (no activation or license key).

Primary workflow for creating a new video.

## Mode

- **SHORT** — 30–60 s, vertical 9:16
- **LONG** — 3 min – 2 hr, forces 16:9 aspect ratio

## Subject

- Enter a topic manually, or enable **AUTO-SELECT** to let the pipeline pick a trending subject

## Duration slider

- Adjust target length; saved per mode (short vs long)

## Language

- Hindi, Hinglish, English, Marathi, Bengali, Gujarati, Tamil, Telugu, Odia

## Voice engine

- **OmniVoice** — local voice clone (default)
- **ElevenLabs** — cloud premium voice
- **Edge TTS** — free Microsoft neural voices (easiest setup)

## Footage

- **Clips:** Auto (based on duration) or fixed count (3–100)
- **Burn subtitles:** long-form only — hardcoded white bold subs at bottom

## Idea Workshop

- Collapsible Gemini chat to brainstorm documentary ideas
- **SEND** — chat with the consultant
- **CREATE NOW** — start pipeline from the last generated plan or topic field

## Controls

- **ROLL FILM** — start the pipeline
- **CUT** — stop after current step
- **RETRY STEP** — retry the failed step (appears on error)

## Progress

- Six hex steps: Research → Script → Voice → Footage → Assembly → Upload
- **Cinema Terminal** — live log with INFO / SUCCESS / ERROR / WARNING tags

## Script Review (modal)

When **Pause for script review** is enabled in Settings, the pipeline pauses after scripting:

- Edit title, full voiceover text, and per-segment footage search queries
- **Approve & Continue** — resume pipeline
- **Regenerate** — cancel and restart from script step
- **Cancel** — abort run

## AI Error Analyst

On pipeline error, click **EXPLAIN & FIX** to get a Gemini-powered explanation from the log.

## Output

- Finished MP4 path shown on success
- **OPEN OUTPUT FOLDER** — opens the run directory in Explorer
