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
  clipMediaUrl,
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
import { api, getApiBaseUrl } from "../api/client";

interface Props {
  runDir: string;
  editorData: EditorJson;
  editClips: ClipAsset[];
  stockClips: ClipAsset[];
  onEditorDataChange: (data: EditorJson) => void;
  onSave: () => void;
  onExport: () => void;
  onBack: () => void;
  saving: boolean;
  rerendering: boolean;
  logs: string[];
}

export function TimelineEditor({
  runDir,
  editorData,
  editClips,
  stockClips,
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
  const audioRef = useRef<HTMLAudioElement>(null);
  const timelineWrapRef = useRef<HTMLDivElement>(null);
  const loadedVideoUrlRef = useRef("");
  const pendingSeekRef = useRef<number | null>(null);
  const [timelineRows, setTimelineRows] = useState<TimelineRow[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [scaleWidth, setScaleWidth] = useState(80);
  const [previewError, setPreviewError] = useState("");
  const [stockMusic, setStockMusic] = useState<{ name: string; filename: string; path: string }[]>([]);
  const [showStockClips, setShowStockClips] = useState(false);
  const [debugLog, setDebugLog] = useState<string[]>([]);
  const [videoInfo, setVideoInfo] = useState({ time: 0, duration: 0, readyState: 0, seeking: false });

  const addDebugLog = (msg: string) => {
    setDebugLog((prev) => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 7)]);
  };

  const updateVideoInfo = () => {
    const el = videoRef.current;
    if (el) {
      setVideoInfo({
        time: el.currentTime,
        duration: el.duration || 0,
        readyState: el.readyState,
        seeking: el.seeking,
      });
    }
  };

  const { editorData: initialRows, effects, totalDuration } = useMemo(
    () => editorJsonToTimeline(editorData, editClips),
    [editorData, editClips]
  );

  useEffect(() => {
    setTimelineRows(initialRows);
  }, [initialRows]);

  useEffect(() => {
    loadedVideoUrlRef.current = "";
  }, [runDir]);

  useEffect(() => {
    const el = timelineWrapRef.current;
    if (!el || totalDuration <= 0) return;
    const updateScale = () => {
      const w = el.clientWidth || 600;
      setScaleWidth(Math.max(40, Math.min(120, w / totalDuration)));
    };
    updateScale();
    const ro = new ResizeObserver(updateScale);
    ro.observe(el);
    return () => ro.disconnect();
  }, [totalDuration]);

  const player = useTimelinePlayer(timelineRef, {
    seekStep: 2,
    loop: { enabled: false, start: 0, end: Math.max(0.1, totalDuration) },
  });

  const voiceoverUrl = useMemo(() => {
    const base = `${runDir}/voiceover.mp3`.replace(/\\/g, "/");
    return `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(base)}`;
  }, [runDir]);

  const syncVideoToTime = useCallback(
    (time: number) => {
      try {
        const row = timelineRows[0];
        if (!row || !videoRef.current) return;

        const clamped = Math.max(0, Math.min(time, totalDuration));
        if (time > totalDuration && player.isPlaying) {
          player.pause();
        }

        let action = row.actions.find((a) => clamped >= a.start && clamped < a.end);
        if (!action && row.actions.length > 0) {
          action = row.actions[row.actions.length - 1];
        }
        if (!action) return;

        const data = (action.data ?? {}) as Partial<SegmentActionData>;
        const url = data.mediaUrl;
        if (!url) {
          setPreviewError("Clip URL missing — check API connection.");
          return;
        }

        const el = videoRef.current;
        const offset = Math.max(0, clamped - action.start);
        if (loadedVideoUrlRef.current !== url) {
          loadedVideoUrlRef.current = url;
          el.src = url;
          el.load();
          setPreviewError("");
          pendingSeekRef.current = offset;
        } else {
          if (!el.seeking) {
            const threshold = player.isPlaying ? 0.8 : 0.05;
            if (el.readyState >= 1) {
              if (Math.abs(el.currentTime - offset) > threshold) {
                el.currentTime = offset;
              }
            } else {
              pendingSeekRef.current = offset;
            }
          }
        }

        if (el.readyState >= 2 && !el.seeking) {
          if (player.isPlaying && el.paused) {
            void el.play().catch(() => setPreviewError("Clip failed to load: " + el.src));
          }
          if (!player.isPlaying && !el.paused) {
            el.pause();
          }
        }

        const audio = audioRef.current;
        if (audio) {
          if (Math.abs(audio.currentTime - clamped) > 0.2) {
            audio.currentTime = clamped;
          }
          if (player.isPlaying && audio.paused) {
            void audio.play().catch(() => undefined);
          }
          if (!player.isPlaying && !audio.paused) {
            audio.pause();
          }
        }
      } catch (err: any) {
        console.error("Error in syncVideoToTime:", err);
        addDebugLog(`sync error: ${err.message}`);
      }
    },
    [timelineRows, player.isPlaying, player.pause, totalDuration]
  );

  useEffect(() => {
    if (timelineRows.length === 0) return;
    syncVideoToTime(player.currentTime || 0);
  }, [timelineRows, syncVideoToTime]);

  useEffect(() => {
    syncVideoToTime(player.currentTime);
  }, [player.currentTime, syncVideoToTime]);

  useEffect(() => {
    const t = player.currentTime;
    const scrollLeft = Math.max(0, t * scaleWidth - 120);
    const id = requestAnimationFrame(() => {
      timelineRef.current?.setScrollLeft(scrollLeft);
    });
    return () => cancelAnimationFrame(id);
  }, [player.currentTime, scaleWidth]);

  const handleTimelineChange = (rows: TimelineRow[]) => {
    try {
      const next = timelineToEditorJson(rows, editorData);
      onEditorDataChange(next);
    } catch (err: any) {
      console.error("Error in handleTimelineChange:", err);
      addDebugLog(`timeline change error: ${err.message}`);
    }
  };

  const updateSelectedSegment = (patch: Partial<EditorJson["segments"][0]>) => {
    const segs = [...editorData.segments];
    if (selectedIndex < 0 || selectedIndex >= segs.length) return;
    segs[selectedIndex] = { ...segs[selectedIndex], ...patch };
    const next = { ...editorData, segments: segs };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, editClips);
    setTimelineRows(rows);
  };

  const applyTransition = (transition: string) => {
    updateSelectedSegment({ transition });
  };

  const applyEffect = (effect: string) => {
    updateSelectedSegment({ effect });
  };

  const swapClip = (clipName: string) => {
    const nextSegments = editorData.segments.map((s, i) =>
      i === selectedIndex ? { ...s, clip_name: clipName } : s
    );
    const next = { ...editorData, segments: nextSegments };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, editClips);
    setTimelineRows(rows);
    loadedVideoUrlRef.current = "";
  };

  const appendClip = (clipName: string) => {
    const newSeg = {
      voiceover: "",
      video_query: "",
      duration_hint: 5.0,
      clip_name: clipName,
    };
    const next = { ...editorData, segments: [...editorData.segments, newSeg] };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, editClips);
    setTimelineRows(rows);
    setSelectedIndex(next.segments.length - 1);
    addDebugLog(`Appended clip ${clipName} to timeline`);
  };

  const deleteSegment = () => {
    if (editorData.segments.length <= 1) {
      alert("Cannot delete the only segment in the timeline.");
      return;
    }
    const nextSegments = editorData.segments.filter((_, i) => i !== selectedIndex);
    const next = { ...editorData, segments: nextSegments };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, editClips);
    setTimelineRows(rows);
    setSelectedIndex(Math.max(0, selectedIndex - 1));
    addDebugLog(`Deleted segment ${selectedIndex + 1}`);
  };

  const splitSegment = () => {
    const t = player.currentTime || 0;
    let accumulatedTime = 0;
    let targetIdx = -1;
    let offset = 0;

    for (let i = 0; i < editorData.segments.length; i++) {
      const segDur = editorData.segments[i].duration_hint || 5;
      if (t >= accumulatedTime && t < accumulatedTime + segDur) {
        targetIdx = i;
        offset = t - accumulatedTime;
        break;
      }
      accumulatedTime += segDur;
    }

    if (targetIdx === -1 && editorData.segments.length > 0) {
      targetIdx = editorData.segments.length - 1;
      const lastDur = editorData.segments[targetIdx].duration_hint || 5;
      offset = lastDur;
    }

    if (targetIdx === -1) return;

    const originalSeg = editorData.segments[targetIdx];
    const originalDur = originalSeg.duration_hint || 5;

    if (offset < 0.2 || originalDur - offset < 0.2) {
      alert("Cannot split so close to the boundary. Move the playhead to a different time.");
      return;
    }

    const firstDur = Math.round(offset * 10) / 10;
    const secondDur = Math.round((originalDur - offset) * 10) / 10;

    const seg1 = {
      ...originalSeg,
      duration_hint: firstDur,
    };
    const seg2 = {
      ...originalSeg,
      duration_hint: secondDur,
      transition: undefined,
      effect: undefined,
    };

    const nextSegments = [
      ...editorData.segments.slice(0, targetIdx),
      seg1,
      seg2,
      ...editorData.segments.slice(targetIdx + 1),
    ];

    const next = { ...editorData, segments: nextSegments };
    onEditorDataChange(next);
    const { editorData: rows } = editorJsonToTimeline(next, editClips);
    setTimelineRows(rows);
    setSelectedIndex(targetIdx + 1);
    addDebugLog(`Split segment ${targetIdx + 1} at ${t.toFixed(2)}s`);
  };

  useEffect(() => {
    api.getStockAssets().then((res) => setStockMusic(res.music)).catch(() => undefined);
  }, []);

  const updateSubtitleStyle = (key: keyof typeof DEFAULT_SUBTITLE_STYLE, value: unknown) => {
    const style = { ...(editorData.subtitle_style || DEFAULT_SUBTITLE_STYLE), [key]: value };
    onEditorDataChange({ ...editorData, subtitle_style: style });
  };

  const selectedSeg = editorData.segments[selectedIndex];

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
            <h3 style={styles.panelTitle}>Edit clips</h3>
            <div style={styles.clipList}>
              {editClips.map((c) => (
                <div
                  key={c.name}
                  style={{
                    ...styles.clipItemRow,
                    ...(selectedSeg?.clip_name === c.name ? styles.clipItemRowActive : {}),
                  }}
                >
                  <span style={styles.clipItemName}>{c.name}</span>
                  <div style={styles.clipItemActions}>
                    <button
                      type="button"
                      style={styles.clipActionBtn}
                      title="Use this clip for the selected segment"
                      onClick={() => swapClip(c.name)}
                    >
                      Swap
                    </button>
                    <button
                      type="button"
                      style={styles.clipActionBtnAdd}
                      title="Add this clip as a new segment at the end"
                      onClick={() => appendClip(c.name)}
                    >
                      + Add
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {stockClips.length > 0 && (
            <section style={styles.panel}>
              <button
                type="button"
                style={styles.stockToggle}
                onClick={() => setShowStockClips((v) => !v)}
              >
                {showStockClips ? "▼" : "▶"} Replace from stock ({stockClips.length})
              </button>
              {showStockClips && (
                <div style={styles.clipList}>
                  {stockClips.map((c) => (
                    <div
                      key={c.name}
                      style={{
                        ...styles.clipItemRow,
                        borderStyle: "dashed",
                      }}
                    >
                      <span style={styles.clipItemName}>{c.name}</span>
                      <div style={styles.clipItemActions}>
                        <button
                          type="button"
                          style={styles.clipActionBtn}
                          title="Use this stock clip for the selected segment"
                          onClick={() => swapClip(c.name)}
                        >
                          Swap
                        </button>
                        <button
                          type="button"
                          style={styles.clipActionBtnAdd}
                          title="Add this stock clip as a new segment at the end"
                          onClick={() => appendClip(c.name)}
                        >
                          + Add
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {selectedSeg && (
            <section style={styles.panel}>
              <h3 style={styles.panelTitle}>Segment {selectedIndex + 1}</h3>
              <div style={styles.segmentActionsRow}>
                <button
                  type="button"
                  style={styles.splitBtn}
                  onClick={splitSegment}
                  title="Split this segment at the current playhead position"
                >
                  ✂️ Split ({player.currentTime.toFixed(1)}s)
                </button>
                <button
                  type="button"
                  style={styles.deleteBtn}
                  onClick={deleteSegment}
                  title="Delete this segment"
                >
                  🗑️ Delete
                </button>
              </div>
              <label style={styles.label}>Voiceover</label>
              <textarea
                style={styles.textarea}
                rows={3}
                value={selectedSeg.voiceover}
                placeholder={editorData.voiceover_text ? "Segment narration" : "No script saved — add text manually"}
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
              crossOrigin="anonymous"
              onLoadedData={() => {
                addDebugLog("loadeddata");
                updateVideoInfo();
                setPreviewError("");
                const el = videoRef.current;
                if (el && pendingSeekRef.current !== null) {
                  addDebugLog(`Applying pending seek to ${pendingSeekRef.current.toFixed(3)}s`);
                  el.currentTime = pendingSeekRef.current;
                  pendingSeekRef.current = null;
                }
                if (el && player.isPlaying && el.paused) {
                  addDebugLog("loadeddata -> calling play()");
                  void el.play().catch((err) => addDebugLog(`play failed: ${err.message}`));
                }
              }}
              onPlay={() => { addDebugLog("play"); updateVideoInfo(); }}
              onPause={() => { addDebugLog("pause"); updateVideoInfo(); }}
              onSeeking={() => { addDebugLog(`seeking (current=${videoRef.current?.currentTime.toFixed(2)}s)`); updateVideoInfo(); }}
              onSeeked={() => { addDebugLog(`seeked (current=${videoRef.current?.currentTime.toFixed(2)}s)`); updateVideoInfo(); }}
              onWaiting={() => { addDebugLog("waiting"); updateVideoInfo(); }}
              onStalled={() => { addDebugLog("stalled"); updateVideoInfo(); }}
              onEnded={() => { addDebugLog("ended"); updateVideoInfo(); }}
              onTimeUpdate={() => updateVideoInfo()}
              onError={() => {
                const err = videoRef.current?.error;
                addDebugLog(`error code=${err?.code} msg=${err?.message}`);
                setPreviewError("Clip failed to load: " + (videoRef.current?.src || ""));
              }}
            />
            <div style={{
              position: "absolute",
              top: 8,
              left: 8,
              background: "rgba(5, 10, 16, 0.9)",
              border: "1px solid #BF00FF",
              color: "#BF00FF",
              padding: 10,
              borderRadius: 4,
              fontSize: 10,
              fontFamily: "monospace",
              pointerEvents: "none",
              zIndex: 100,
              textAlign: "left",
              lineHeight: "1.4",
              boxShadow: "0 0 10px rgba(191,0,255,0.25)"
            }}>
              <div style={{ fontWeight: "bold", borderBottom: "1px solid #333", marginBottom: 4, paddingBottom: 2 }}>DEBUG OVERLAY</div>
              <div>PLAYHEAD: {player.currentTime?.toFixed(3)}s</div>
              <div>VIDEO TIME: {videoInfo.time?.toFixed(3)}s / {videoInfo.duration?.toFixed(3)}s</div>
              <div>READY STATE: {videoInfo.readyState}</div>
              <div>SEEKING: {String(videoInfo.seeking)}</div>
              <div>PENDING SEEK: {pendingSeekRef.current !== null ? pendingSeekRef.current.toFixed(3) + "s" : "none"}</div>
              <div style={{ borderTop: "1px solid #333", marginTop: 4, paddingTop: 4, maxHeight: 100, overflow: "hidden" }}>
                {debugLog.map((log, i) => <div key={i} style={{ color: log.includes("error") ? "#FF1744" : "#00E676" }}>{log}</div>)}
              </div>
            </div>
            <audio ref={audioRef} src={voiceoverUrl} preload="auto" crossOrigin="anonymous" />
            {previewError && <div style={styles.previewError}>{previewError}</div>}
          </div>
          <TransportBar player={player} />
          <div ref={timelineWrapRef} style={styles.timelineWrap}>
            <Timeline
              ref={timelineRef}
              style={{ width: "100%", height: "100%" }}
              editorData={timelineRows}
              effects={effects}
              scale={1}
              scaleWidth={scaleWidth}
              scaleSplitCount={5}
              rowHeight={48}
              gridSnap
              dragLine
              autoScroll
              onChange={handleTimelineChange}
              onClickAction={(_e, { action }) => {
                const idx = (action?.data as SegmentActionData | undefined)?.segmentIndex;
                if (typeof idx === "number") setSelectedIndex(idx);
              }}
              onCursorDrag={(time) => syncVideoToTime(time)}
              getActionRender={(action) => {
                const data = (action?.data ?? {}) as Partial<SegmentActionData>;
                return (
                  <div style={styles.actionBlock}>
                    <span style={styles.actionTitle}>{data.clipName || "Segment"}</span>
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
  clipItemStock: {
    textAlign: "left",
    padding: "6px 8px",
    background: theme.bgSec,
    border: `1px dashed ${theme.border}`,
    color: theme.textHint,
    fontSize: 11,
    cursor: "pointer",
  },
  clipItemActive: { borderColor: theme.accentPri, color: theme.textPri },
  clipItemRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "4px 8px",
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    borderRadius: 4,
    gap: 8,
  },
  clipItemRowActive: {
    borderColor: theme.accentPri,
  },
  clipItemName: {
    fontSize: 11,
    color: theme.textPri,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    flex: 1,
  },
  clipItemActions: {
    display: "flex",
    gap: 4,
  },
  clipActionBtn: {
    padding: "2px 6px",
    background: theme.bgCard,
    border: `1px solid ${theme.border}`,
    color: theme.textSec,
    fontSize: 10,
    cursor: "pointer",
    borderRadius: 2,
  },
  clipActionBtnAdd: {
    padding: "2px 6px",
    background: "rgba(0, 230, 118, 0.1)",
    border: "1px solid rgba(0, 230, 118, 0.4)",
    color: "#00E676",
    fontSize: 10,
    cursor: "pointer",
    borderRadius: 2,
    fontWeight: "bold",
  },
  segmentActionsRow: {
    display: "flex",
    gap: 8,
    marginBottom: 10,
  },
  splitBtn: {
    flex: 1,
    padding: "6px 8px",
    background: "rgba(191, 0, 255, 0.1)",
    border: "1px solid rgba(191, 0, 255, 0.4)",
    color: "#BF00FF",
    fontSize: 11,
    cursor: "pointer",
    borderRadius: 3,
    fontWeight: 600,
    textAlign: "center",
  },
  deleteBtn: {
    padding: "6px 12px",
    background: "rgba(255, 23, 68, 0.1)",
    border: "1px solid rgba(255, 23, 68, 0.4)",
    color: "#FF1744",
    fontSize: 11,
    cursor: "pointer",
    borderRadius: 3,
    fontWeight: 600,
    textAlign: "center",
  },
  stockToggle: {
    width: "100%",
    textAlign: "left",
    padding: "6px 8px",
    background: "transparent",
    border: "none",
    color: theme.textSec,
    fontSize: 11,
    cursor: "pointer",
    marginBottom: 4,
  },
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
    position: "relative",
  },
  previewVideo: { maxWidth: "100%", maxHeight: "100%", objectFit: "contain" },
  previewError: {
    position: "absolute",
    bottom: 8,
    left: 8,
    right: 8,
    padding: "6px 10px",
    background: "rgba(180,0,0,0.85)",
    color: "#fff",
    fontSize: 11,
    textAlign: "center",
  },
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
