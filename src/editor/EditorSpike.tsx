/**
 * Dev-only SDK spike — not wired in production UI (see TimelineEditor).
 * Set VITE_EDITOR_SPIKE=1 to import in a dev harness.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Timeline,
  TimelineState,
  TransportBar,
  useTimelinePlayer,
} from "@keplar-404/react-timeline-editor";
import "@keplar-404/react-timeline-editor/dist/react-timeline-editor.css";
import { api } from "../api/client";
import { theme } from "../theme/tokens";
import { editorJsonToTimeline, normalizeEditorJson } from "./projectAdapter";
import type { ClipAsset, EditorJson } from "./types";
import { DEFAULT_SUBTITLE_STYLE } from "./types";

interface Props {
  runDir: string;
}

export function EditorSpike({ runDir }: Props) {
  const timelineRef = useRef<TimelineState>(null!);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editorData, setEditorData] = useState<EditorJson | null>(null);
  const [clips, setClips] = useState<ClipAsset[]>([]);
  const [timelineRows, setTimelineRows] = useState<ReturnType<typeof editorJsonToTimeline>["editorData"]>([]);
  const [effects, setEffects] = useState<ReturnType<typeof editorJsonToTimeline>["effects"]>({});

  const player = useTimelinePlayer(timelineRef);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [raw, clipRes] = await Promise.all([api.loadEditor(runDir), api.listClips(runDir)]);
      const normalized = normalizeEditorJson(
        {
          ...raw,
          subtitle_style: raw.subtitle_style ?? DEFAULT_SUBTITLE_STYLE,
        },
        clipRes.clips
      );
      const mapped = editorJsonToTimeline(normalized, clipRes.clips);
      setEditorData(normalized);
      setClips(clipRes.clips);
      setTimelineRows(mapped.editorData);
      setEffects(mapped.effects);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [runDir]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <div style={{ padding: 16, color: theme.textSec }}>Loading spike…</div>;
  if (error) return <div style={{ padding: 16, color: theme.accentRed }}>{error}</div>;
  if (!editorData) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 12, gap: 8 }}>
      <div style={{ fontSize: 12, color: theme.textSec }}>
        Spike: {editorData.title} — {clips.length} clips via /api/local-file
      </div>
      <TransportBar player={player} />
      <div style={{ flex: 1, minHeight: 180, border: `1px solid ${theme.border}` }}>
        <Timeline
          ref={timelineRef}
          editorData={timelineRows}
          effects={effects}
          scale={1}
          scaleWidth={120}
          rowHeight={44}
          onChange={setTimelineRows}
        />
      </div>
    </div>
  );
}
