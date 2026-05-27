---
name: React Editor SDK Replace
overview: Replace the monolithic Ghost Editor (`EditorTab.tsx`) with an embeddable open-source React timeline SDK, keep the existing `documentary_editor.json` + FFmpeg re-render contract, and wire transitions/effects into the backend so exports match the timeline.
todos:
  - id: spike-sdk
    content: "Phase 1: Add @keplar-404/react-timeline-editor, build EditorSpike with real run clips via /api/local-file in Electron"
    status: in_progress
  - id: adapter
    content: "Phase 2: Create src/editor/projectAdapter.ts — documentary_editor.json <-> timeline model"
    status: pending
  - id: replace-editor-tab
    content: "Phase 3: Replace EditorTab.tsx with TimelineEditor shell + save/export wiring"
    status: pending
  - id: ffmpeg-effects
    content: "Phase 4: Add core/video_effects.py and wire segment transition/effect in documentary_assembler.py"
    status: pending
  - id: pipeline-pause
    content: "Phase 5: Implement pipeline_mode=editor pause/resume after clips_for_edit"
    status: pending
  - id: test-editor
    content: "Phase 6: Manual test checklist + adapter/effects unit smoke tests"
    status: pending
isProject: false
---

# Replace Ghost Editor with React Timeline SDK

## Why not OpenShot

[OpenShot](https://github.com/OpenShot/openshot-qt) is a **PyQt desktop app** (Python UI + `libopenshot` C++). It cannot be embedded inside Ghost Creator's Electron/React tab without a separate window. Building `libopenshot` into `GhostCreatorAPI.exe` on Windows is heavy and still would not give the OpenShot UI inside your app.

You chose **React SDK** — this matches Ghost Creator's stack (React 19 + Vite + Electron + FastAPI + native FFmpeg) and is the most reliable path to a working in-app editor.

## Recommended SDK (MIT, npm)

| Option | License | Fit |
|--------|---------|-----|
| **`@keplar-404/react-timeline-editor` + `@keplar-404/timeline-engine`** | MIT | Best default: timeline UI + playback engine, framework-friendly |
| `graphicstone/quik-clip` (`react-video-editor`) | Check repo license before ship | Canvas + timeline components; may vendor from GitHub if npm package is stale |
| `@twick/studio` | Sustainable Use License | Avoid for a commercial installer unless you accept SUL terms |

**Plan default:** spike **`@keplar-404/react-timeline-editor`** first; fall back to vendoring quik-clip `VideoTimeline` / `VideoCanvas` into `src/editor/` if the npm API is too limited.

**Export stays native FFmpeg** (existing [`api/services/history_rerender.py`](api/services/history_rerender.py) → [`modules/documentary_assembler.py`](modules/documentary_assembler.py)). Do **not** use FFmpeg.wasm for final export in Electron — the API sidecar already has FFmpeg and is faster.

## Target architecture

```mermaid
flowchart TB
    subgraph ui [Electron React]
        EditorTab[EditorTab shell]
        SDK[Timeline SDK components]
        Adapter[projectAdapter.ts]
        EditorTab --> SDK
        EditorTab --> Adapter
    end

    subgraph api [FastAPI]
        Load[/api/history/load-editor]
        Save[/api/history/save-editor]
        Clips[/api/history/list-clips]
        Rerender[/api/history/rerender]
        LocalFile[/api/local-file]
    end

    subgraph disk [Run folder]
        JSON[documentary_editor.json]
        ClipsDir[clips_for_edit/e_XX.mp4]
        VO[voiceover.mp3]
    end

    subgraph render [FFmpeg]
        Assembler[assemble_documentary]
    end

    Adapter --> Load
    Adapter --> Clips
    EditorTab --> Save
    EditorTab --> Rerender
    SDK --> LocalFile
    Save --> JSON
    Rerender --> Assembler
    Assembler --> JSON
    Assembler --> ClipsDir
    Assembler --> VO
```

## Data contract (keep backward compatible)

Preserve [`documentary_editor.json`](core/pipeline_runner.py) fields the pipeline already uses:

- **Required for render:** `segments[].voiceover`, `duration_hint`, `clip_name`, `aspect_ratio`, `title`
- **Editor extras:** `subtitle_style`, `bg_music`, `bg_music_volume`
- **New (wire to FFmpeg):** `segments[].transition`, `segments[].effect` — currently UI-only in [`EditorTab.tsx`](src/tabs/EditorTab.tsx); map SDK actions to these fields

Clip preview URLs: `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(clip.path)}` (already used pattern; served by [`api/routes/misc.py`](api/routes/misc.py)).

## Implementation phases

### Phase 1 — Spike (validate SDK in Electron)

- Add dependencies to [`package.json`](package.json): `@keplar-404/react-timeline-editor`, `@keplar-404/timeline-engine` (+ peer deps if required).
- Create [`src/editor/EditorSpike.tsx`](src/editor/EditorSpike.tsx): load one run's clips via `api.listClips`, play in timeline, seek/scrub.
- Verify in `npm run electron:dev` that Windows paths work through `/api/local-file`.

**Exit criteria:** 3+ clips from a real run display on timeline with smooth preview.

### Phase 2 — Adapter layer

New module [`src/editor/projectAdapter.ts`](src/editor/projectAdapter.ts):

- `editorJsonToTimeline(data, clips)` — map segments to video track items (start time = sum of prior `duration_hint`, duration = `duration_hint`, media URL from clip path).
- `timelineToEditorJson(timeline, base)` — write back `clip_name`, `duration_hint`, reorder segments, `transition`/`effect` per clip.
- Keep undo/redo in SDK or a thin wrapper (replace current manual stack in EditorTab).

### Phase 3 — Replace EditorTab

- Replace body of [`src/tabs/EditorTab.tsx`](src/tabs/EditorTab.tsx) (~1600 lines) with a slim shell:
  - Project picker (keep existing history list UX)
  - SDK timeline + preview panel
  - Toolbar: Save, Export (re-render), Back
  - Side panels: subtitle style, bg music (reuse existing API calls from current EditorTab)
- Remove dead UI-only features (fake multi-track mute, Filmora branding) unless SDK supports them.
- Keep [`src/App.tsx`](src/App.tsx) / [`src/tabs/HistoryTab.tsx`](src/tabs/HistoryTab.tsx) wiring unchanged (`onOpenEditor`, `editorRunDir`).

### Phase 4 — Backend: transitions/effects in FFmpeg

Extend [`modules/documentary_assembler.py`](modules/documentary_assembler.py) (segment trim/concat path):

| Editor preset | FFmpeg approach |
|---------------|-----------------|
| Cross Dissolve / Fade | `xfade` between consecutive segments |
| Fade to Black | `fade=t=out` on clip tail |
| B&W Film / Grayscale | `format=gray` or `hue=s=0` per segment |
| Cinematic Grain | `noise=alls=20:allf=t+u` (light) |

Add small helper [`core/video_effects.py`](core/video_effects.py) to build filter strings from `segment.transition` / `segment.effect` so assembler stays readable.

[`api/services/history_rerender.py`](api/services/history_rerender.py) — no schema change; already passes full segments to assembler.

### Phase 5 — Pipeline editor pause (fix dead setting)

Settings checkbox **"Pause for Ghost Editor"** (`pipeline_mode === "editor"`) is stored but **never read** by [`core/pipeline_runner.py`](core/pipeline_runner.py).

After Step 4.5 (`clips_for_edit` ready), if editor mode:

1. Set `waiting_for_editor` flag (mirror script-review pattern in [`api/routes/pipeline.py`](api/routes/pipeline.py)).
2. Stop before Step 5 assembly.
3. DocumentaryTab shows "Open Editor" + "Continue pipeline" button.
4. Resume endpoint runs assembly only.

This makes the editor part of the live pipeline, not only post-hoc via History.

### Phase 6 — Test plan (manual + automated smoke)

1. **Load test:** History run with `documentary_editor.json` + `clips_for_edit/` → timeline shows correct segment count and durations.
2. **Edit test:** Reorder 2 segments, change one `duration_hint`, swap clip → Save → verify JSON on disk.
3. **Effect test:** Apply transition on segment 2 → Export → verify output MP4 differs (visual check + file size/duration).
4. **Pipeline pause test:** Enable editor mode → run documentary → pipeline pauses → edit → continue → final MP4 generated.
5. **Regression:** Stock/Meta/Grok footage paths unaffected; History re-render still sets `can_rerender`.

Optional: add one pytest for `projectAdapter` round-trip and one for `video_effects` filter string generation.

## Files to create / change

| Action | Path |
|--------|------|
| Replace | [`src/tabs/EditorTab.tsx`](src/tabs/EditorTab.tsx) |
| Create | `src/editor/projectAdapter.ts`, `src/editor/types.ts`, `src/editor/TimelineEditor.tsx` |
| Create | `core/video_effects.py` |
| Extend | [`modules/documentary_assembler.py`](modules/documentary_assembler.py) |
| Extend | [`core/pipeline_runner.py`](core/pipeline_runner.py), [`api/routes/pipeline.py`](api/routes/pipeline.py), [`src/tabs/DocumentaryTab.tsx`](src/tabs/DocumentaryTab.tsx) |
| Update deps | [`package.json`](package.json) |
| Docs | [`docs/05-gui-upload-settings-history.md`](docs/05-gui-upload-settings-history.md) — editor section |

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| SDK preview ≠ FFmpeg output | Export always via backend assembler; document that preview is approximate |
| Segment split without new TTS | UI split updates `voiceover` text only (same as today); document limitation |
| SDK npm immature | Spike in Phase 1; fallback to vendored quik-clip components |
| Timeline duration vs voiceover length | Assembler keeps voiceover as master clock; adapter normalizes `duration_hint` weights (existing behavior in assembler) |

## Out of scope (this plan)

- OpenShot / Shotcut external launcher (you declined via SDK choice)
- Full multi-track NLE (unlimited tracks, VST, keyframes)
- Replacing FFmpeg with libopenshot
