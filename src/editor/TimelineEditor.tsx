import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Timeline,
  TimelineState,
  TransportBar,
  useTimelinePlayer,
} from "@keplar-404/react-timeline-editor";
import type { TimelineRow } from "@keplar-404/react-timeline-editor";
import "@keplar-404/react-timeline-editor/dist/react-timeline-editor.css";
import { theme } from "../theme/tokens";
import {
  editorJsonToTimeline,
  resolveClipForSegment,
  timelineToEditorJson,
} from "./projectAdapter";
import type {
  ClipAsset,
  EditorJson,
  SegmentActionData,
} from "./types";
import {
  DEFAULT_SUBTITLE_STYLE,
  EFFECT_PRESETS,
  TRANSITION_PRESETS,
} from "./types";
import { api } from "../api/client";

interface Props {
  editorData: EditorJson;
  clips: ClipAsset[];
  onEditorDataChange: (data: EditorJson) => void;
  onSave: () => void;
  onExport: () => void;
  onBack: () => void;
  saving: boolean;
  rerendering: boolean;
  logs: string[];
}

export function TimelineEditor({
  editorData,
  clips,
  onEditorDataChange,
  onSave,
  onExport,
  onBack,
  saving,
  rerendering,
  logs,
}: Props) {
  const timelineRef = useRef<TimelineState>(null!);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [timelineRows, setTimelineRows] = useState<TimelineRow[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [stockMusic, setStockMusic] = useState<{ name: string; filename: string; path: string }[]>([]);

  const { editorData: initialRows, effects, totalDuration } = useMemo(
    () => editorJsonToTimeline(editorData, clips),
    [editorData, clips]
  );

  useEffect(() => {
    setTimelineRows(initialRows);
  }, [initialRows]);

  const player = useTimelinePlayer(timelineRef);

  const syncVideoToTime = useCallback(
    (time: number) => {
      const row = timelineRows[0];
      if (!row || !videoRef.current) return;
      const action = row.actions.find((a) => time >= a.start && time < a.end);
      if (!action) return;
      const data = action.data as SegmentActionData;
      const url = data.mediaUrl;
      if (!url) return;
      const el = videoRef.current;
      const offset = Math.max(0, time - action.start);
      if (el.src !== url) {
        el.src = url;
        el.load();
      }
      if (Math.abs(el.currentTime - offset) > 0.15) {
        el.currentTime = offset;
      }
      if (player.isPlaying && el.paused) {
        void el.play().catch(() => undefined);
      }
      if (!player.isPlaying && !el.paused) {
        el.pause();
      }
    },
    [timelineRows, player.isPlaying]
  );

  useEffect(() => {
    syncVideoToTime(player.currentTime);
  }, [player.currentTime, syncVideoToTime]);

  const handleTimelineChange = (rows: TimelineRow[]) => {
    setTimelineRows(rows);
    const next = timelineToEditorJson(rows, editorData);
    onEditorDataChange(next);
  };

  const updateSelectedSegment = (patch: Partial<EditorJson["segments"][0]>) => {
    const segs = [...editorData.segments];
    if (selectedIndex < 0 || selectedIndex >= segs.length) return;
    segs[selectedIndex] = { ...segs[selectedIndex], ...patch };
    const next = { ...editorData, segments: segs };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, clips);
    setTimelineRows(rows);
  };

  const applyTransition = (transition: string) => {
    updateSelectedSegment({ transition });
    const row = timelineRows[0];
    if (!row) return;
    const action = row.actions[selectedIndex];
    if (action?.data) {
      (action.data as SegmentActionData).transition = transition;
    }
  };

  const applyEffect = (effect: string) => {
    updateSelectedSegment({ effect });
    const row = timelineRows[0];
    if (!row) return;
    const action = row.actions[selectedIndex];
    if (action?.data) {
      (action.data as SegmentActionData).effect = effect;
    }
  };

  const swapClip = (clipName: string) => {
    const nextSegments = editorData.segments.map((s, i) =>
      i === selectedIndex ? { ...s, clip_name: clipName } : s
    );
    const next = { ...editorData, segments: nextSegments };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, clips);
    setTimelineRows(rows);
  };

  useEffect(() => {
    api.getStockAssets().then((res) => setStockMusic(res.music)).catch(() => undefined);
  }, []);

  const updateSubtitleStyle = (key: keyof typeof DEFAULT_SUBTITLE_STYLE, value: unknown) => {
    const style = { ...(editorData.subtitle_style || DEFAULT_SUBTITLE_STYLE), [key]: value };
    onEditorDataChange({ ...editorData, subtitle_style: style });
  };

  const selectedSeg = editorData.segments[selectedIndex];
  const previewClip = selectedSeg
    ? resolveClipForSegment(selectedSeg, selectedIndex, clips)
    : clips[0];

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <button type="button" style={styles.backBtn} onClick={onBack}>
          ← Back
        </button>
        <input
          style={styles.titleInput}
          value={editorData.title}
          onChange={(e) => onEditorDataChange({ ...editorData, title: e.target.value })}
          aria-label="Project title"
        />
        <span style={styles.meta}>{editorData.aspect_ratio} · {editorData.segments.length} clips · {totalDuration.toFixed(1)}s</span>
        <div style={styles.headerActions}>
          <button type="button" style={styles.saveBtn} onClick={onSave} disabled={saving || rerendering}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button type="button" style={styles.exportBtn} onClick={onExport} disabled={saving || rerendering}>
            {rerendering ? "Exporting…" : "Export (FFmpeg)"}
          </button>
        </div>
      </header>

      <div style={styles.main}>
        <aside style={styles.sidebar}>
          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Clips</h3>
            <div style={styles.clipList}>
              {clips.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  style={{
                    ...styles.clipItem,
                    ...(selectedSeg?.clip_name === c.name ? styles.clipItemActive : {}),
                  }}
                  onClick={() => swapClip(c.name)}
                >
                  {c.name}
                </button>
              ))}
            </div>
          </section>

          {selectedSeg && (
            <section style={styles.panel}>
              <h3 style={styles.panelTitle}>Segment {selectedIndex + 1}</h3>
              <label style={styles.label}>Voiceover</label>
              <textarea
                style={styles.textarea}
                rows={3}
                value={selectedSeg.voiceover}
                onChange={(e) => updateSelectedSegment({ voiceover: e.target.value })}
              />
              <label style={styles.label}>Duration (s)</label>
              <input
                type="number"
                min={0.5}
                step={0.1}
                style={styles.input}
                value={selectedSeg.duration_hint}
                onChange={(e) => updateSelectedSegment({ duration_hint: parseFloat(e.target.value) || 5 })}
              />
              <label style={styles.label}>Transitions</label>
              <div style={styles.presetRow}>
                {TRANSITION_PRESETS.map((t) => (
                  <button
                    key={t}
                    type="button"
                    style={{
                      ...styles.presetBtn,
                      ...(selectedSeg.transition === t ? styles.presetBtnActive : {}),
                    }}
                    onClick={() => applyTransition(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <label style={styles.label}>Effects</label>
              <div style={styles.presetRow}>
                {EFFECT_PRESETS.map((eff) => (
                  <button
                    key={eff}
                    type="button"
                    style={{
                      ...styles.presetBtn,
                      ...(selectedSeg.effect === eff ? styles.presetBtnActive : {}),
                    }}
                    onClick={() => applyEffect(eff)}
                  >
                    {eff}
                  </button>
                ))}
              </div>
            </section>
          )}

          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Subtitles</h3>
            <label style={styles.label}>Font size</label>
            <input
              type="number"
              style={styles.input}
              value={editorData.subtitle_style?.font_size ?? DEFAULT_SUBTITLE_STYLE.font_size}
              onChange={(e) => updateSubtitleStyle("font_size", parseInt(e.target.value, 10) || 28)}
            />
            <label style={styles.label}>Color</label>
            <input
              type="color"
              style={styles.colorInput}
              value={editorData.subtitle_style?.color ?? DEFAULT_SUBTITLE_STYLE.color}
              onChange={(e) => updateSubtitleStyle("color", e.target.value)}
            />
            <div style={styles.toggleRow}>
              <button
                type="button"
                style={{
                  ...styles.presetBtn,
                  ...(editorData.subtitle_style?.bold ? styles.presetBtnActive : {}),
                }}
                onClick={() => updateSubtitleStyle("bold", !editorData.subtitle_style?.bold)}
              >
                Bold
              </button>
              <button
                type="button"
                style={{
                  ...styles.presetBtn,
                  ...(editorData.subtitle_style?.italic ? styles.presetBtnActive : {}),
                }}
                onClick={() => updateSubtitleStyle("italic", !editorData.subtitle_style?.italic)}
              >
                Italic
              </button>
            </div>
          </section>

          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Background music</h3>
            <select
              style={styles.input}
              value={editorData.bg_music ?? ""}
              onChange={(e) =>
                onEditorDataChange({
                  ...editorData,
                  bg_music: e.target.value || undefined,
                  bg_music_volume: editorData.bg_music_volume ?? 0.25,
                })
              }
            >
              <option value="">None</option>
              {stockMusic.map((m) => (
                <option key={m.filename} value={m.filename}>
                  {m.name}
                </option>
              ))}
            </select>
            <label style={styles.label}>Volume</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={editorData.bg_music_volume ?? 0.25}
              onChange={(e) =>
                onEditorDataChange({
                  ...editorData,
                  bg_music_volume: parseFloat(e.target.value),
                })
              }
            />
          </section>
        </aside>

        <div style={styles.center}>
          <div style={styles.previewWrap}>
            <video
              ref={videoRef}
              style={styles.previewVideo}
              muted
              playsInline
              poster={previewClip ? undefined : undefined}
            />
          </div>
          <TransportBar player={player} />
          <div style={styles.timelineWrap}>
            <Timeline
              ref={timelineRef}
              editorData={timelineRows}
              effects={effects}
              scale={1}
              scaleWidth={120}
              scaleSplitCount={5}
              rowHeight={48}
              gridSnap
              dragLine
              onChange={handleTimelineChange}
              onClickAction={(_e, { action }) => {
                const idx = (action.data as SegmentActionData)?.segmentIndex;
                if (typeof idx === "number") setSelectedIndex(idx);
              }}
              getActionRender={(action) => {
                const data = action.data as SegmentActionData;
                return (
                  <div style={styles.actionBlock}>
                    <span style={styles.actionTitle}>{data.clipName}</span>
                    {data.transition && <span style={styles.actionBadge}>⚡</span>}
                    {data.effect && <span style={styles.actionBadge}>✨</span>}
                  </div>
                );
              }}
            />
          </div>
        </div>
      </div>

      {logs.length > 0 && (
        <pre style={styles.logs}>{logs.join("\n")}</pre>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: { display: "flex", flexDirection: "column", height: "100%", background: theme.bgMain, color: theme.textPri },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 16px",
    borderBottom: `1px solid ${theme.border}`,
    background: theme.bgCard,
  },
  backBtn: {
    background: "transparent",
    border: `1px solid ${theme.border}`,
    color: theme.textSec,
    padding: "6px 12px",
    cursor: "pointer",
    fontSize: 12,
  },
  titleInput: {
    flex: 1,
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.textPri,
    padding: "6px 10px",
    fontSize: 14,
    fontWeight: 600,
  },
  meta: { fontSize: 11, color: theme.textHint, whiteSpace: "nowrap" },
  headerActions: { display: "flex", gap: 8, marginLeft: "auto" },
  saveBtn: {
    padding: "6px 14px",
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.textPri,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
  },
  exportBtn: {
    padding: "6px 14px",
    background: "rgba(0,230,118,0.15)",
    border: "1px solid #00E676",
    color: "#00E676",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 700,
  },
  main: { display: "flex", flex: 1, minHeight: 0 },
  sidebar: {
    width: 280,
    overflow: "auto",
    borderRight: `1px solid ${theme.border}`,
    background: theme.bgCard,
    padding: 8,
  },
  panel: { marginBottom: 16 },
  panelTitle: { fontSize: 11, fontWeight: 700, color: theme.textSec, margin: "0 0 8px", textTransform: "uppercase" },
  clipList: { display: "flex", flexDirection: "column", gap: 4 },
  clipItem: {
    textAlign: "left",
    padding: "6px 8px",
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.textSec,
    fontSize: 11,
    cursor: "pointer",
  },
  clipItemActive: { borderColor: theme.accentPri, color: theme.textPri },
  label: { display: "block", fontSize: 10, color: theme.textHint, marginBottom: 4, marginTop: 8 },
  textarea: {
    width: "100%",
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.textPri,
    fontSize: 11,
    padding: 6,
    resize: "vertical",
    boxSizing: "border-box",
  },
  input: {
    width: "100%",
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.textPri,
    fontSize: 11,
    padding: 6,
    boxSizing: "border-box",
  },
  colorInput: { width: "100%", height: 32, padding: 0, border: "none", cursor: "pointer" },
  presetRow: { display: "flex", flexWrap: "wrap", gap: 4 },
  presetBtn: {
    padding: "4px 8px",
    fontSize: 10,
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.textSec,
    cursor: "pointer",
  },
  presetBtnActive: { borderColor: theme.accentPri, color: theme.accentPri },
  toggleRow: { display: "flex", gap: 4, marginTop: 8 },
  center: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },
  previewWrap: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#000",
    minHeight: 200,
  },
  previewVideo: { maxWidth: "100%", maxHeight: "100%", objectFit: "contain" },
  timelineWrap: { height: 220, borderTop: `1px solid ${theme.border}`, overflow: "hidden" },
  actionBlock: {
    height: "100%",
    display: "flex",
    alignItems: "center",
    gap: 4,
    padding: "0 6px",
    background: "rgba(0,230,118,0.2)",
    border: "1px solid rgba(0,230,118,0.5)",
    borderRadius: 2,
    fontSize: 10,
    overflow: "hidden",
  },
  actionTitle: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  actionBadge: { fontSize: 9 },
  logs: {
    maxHeight: 80,
    overflow: "auto",
    margin: 0,
    padding: 8,
    fontSize: 10,
    background: theme.bgSec,
    borderTop: `1px solid ${theme.border}`,
    color: theme.textSec,
  },
};
