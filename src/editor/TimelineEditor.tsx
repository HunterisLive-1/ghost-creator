import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties } from "react";
import {
  Timeline,
  TimelineState,
  TransportBar,
  useTimelinePlayer,
} from "@keplar-404/react-timeline-editor";
import type { TimelineRow } from "@keplar-404/react-timeline-editor";
import "@keplar-404/react-timeline-editor/dist/react-timeline-editor.css";
import { api, getApiBaseUrl } from "../api/client";
import { theme } from "../theme/tokens";
import {
  clipMediaUrl,
  editorJsonToTimeline,
  ensureV2EditorJson,
  makeEditorId,
  timelineToEditorJson,
} from "./projectAdapter";
import type {
  ClipAsset,
  EditorAsset,
  EditorItemKind,
  EditorJson,
  EditorTimelineItem,
  EditorTrack,
  SegmentActionData,
} from "./types";
import {
  DEFAULT_OVERLAY_TRANSFORM,
  DEFAULT_SUBTITLE_STYLE,
  EFFECT_PRESETS,
  TRANSITION_PRESETS,
} from "./types";

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

type UploadKind = "video" | "audio" | "image";

const TRACK_LABELS: Record<string, string> = {
  video: "Video",
  overlay: "Overlay",
  audio: "Audio",
  music: "Music",
  subtitle: "Subtitle",
};

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
  const historyRef = useRef<EditorJson[]>([]);
  const redoRef = useRef<EditorJson[]>([]);

  const project = useMemo(
    () => ensureV2EditorJson(editorData, editClips, stockClips),
    [editorData, editClips, stockClips]
  );
  const [timelineRows, setTimelineRows] = useState<TimelineRow[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [scaleWidth, setScaleWidth] = useState(project.timeline_settings?.zoom ?? 80);
  const [previewError, setPreviewError] = useState("");
  const [stockMusic, setStockMusic] = useState<{ name: string; filename: string; path: string }[]>([]);
  const [debugOpen, setDebugOpen] = useState(false);
  const [uploading, setUploading] = useState<UploadKind | "">("");

  const { editorData: initialRows, effects, totalDuration } = useMemo(
    () => editorJsonToTimeline(project, editClips),
    [project, editClips]
  );

  useEffect(() => {
    setTimelineRows(initialRows);
  }, [initialRows]);

  useEffect(() => {
    api.getStockAssets().then((res) => setStockMusic(res.music)).catch(() => undefined);
  }, []);

  useEffect(() => {
    const el = timelineWrapRef.current;
    if (!el || totalDuration <= 0) return;
    const updateScale = () => {
      const zoom = project.timeline_settings?.zoom ?? 80;
      const fit = (el.clientWidth || 700) / Math.max(1, totalDuration);
      setScaleWidth(Math.max(36, Math.min(180, Math.max(fit, zoom))));
    };
    updateScale();
    const ro = new ResizeObserver(updateScale);
    ro.observe(el);
    return () => ro.disconnect();
  }, [project.timeline_settings?.zoom, totalDuration]);

  const player = useTimelinePlayer(timelineRef, {
    seekStep: 2,
    loop: { enabled: false, start: 0, end: Math.max(0.1, totalDuration) },
  });

  const assetsById = useMemo(() => new Map((project.assets ?? []).map((asset) => [asset.id, asset])), [project.assets]);
  const tracksById = useMemo(() => new Map((project.tracks ?? []).map((track) => [track.id, track])), [project.tracks]);

  const selectedItem = useMemo(
    () => (project.items ?? []).find((item) => item.id === selectedItemId) ?? null,
    [project.items, selectedItemId]
  );

  const voiceoverUrl = useMemo(() => {
    const base = `${runDir}/voiceover.mp3`.replace(/\\/g, "/");
    return `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(base)}`;
  }, [runDir]);

  const commitProject = useCallback(
    (next: EditorJson, pushHistory = true) => {
      if (pushHistory) {
        historyRef.current = [...historyRef.current.slice(-49), project];
        redoRef.current = [];
      }
      onEditorDataChange(next);
    },
    [onEditorDataChange, project]
  );

  const updateProjectItems = (updater: (items: EditorTimelineItem[]) => EditorTimelineItem[]) => {
    const next = { ...project, items: updater([...(project.items ?? [])]) };
    commitProject(timelineToEditorJson(editorJsonToTimeline(next, editClips).editorData, next));
  };

  const updateProjectTracks = (updater: (tracks: EditorTrack[]) => EditorTrack[]) => {
    commitProject({ ...project, tracks: updater([...(project.tracks ?? [])]) });
  };

  const undo = () => {
    const previous = historyRef.current.pop();
    if (!previous) return;
    redoRef.current = [...redoRef.current, project];
    onEditorDataChange(previous);
  };

  const redo = () => {
    const next = redoRef.current.pop();
    if (!next) return;
    historyRef.current = [...historyRef.current, project];
    onEditorDataChange(next);
  };

  const handleTimelineChange = (rows: TimelineRow[]) => {
    const next = timelineToEditorJson(rows, project);
    commitProject(next);
  };

  const addTrack = (type: EditorTrack["type"]) => {
    const count = (project.tracks ?? []).filter((track) => track.type === type).length + 1;
    const track: EditorTrack = {
      id: `${type}-${makeEditorId("track")}`,
      type,
      name: `${TRACK_LABELS[type]} ${count}`,
    };
    updateProjectTracks((tracks) => [...tracks, track]);
  };

  const toggleTrack = (trackId: string, key: "muted" | "locked") => {
    updateProjectTracks((tracks) => tracks.map((track) => (track.id === trackId ? { ...track, [key]: !track[key] } : track)));
  };

  const removeEmptyTrack = (trackId: string) => {
    if ((project.items ?? []).some((item) => item.trackId === trackId)) {
      alert("Track has timeline items. Delete or move them first.");
      return;
    }
    updateProjectTracks((tracks) => tracks.filter((track) => track.id !== trackId));
  };

  const firstTrackOfType = (type: EditorTrack["type"]) =>
    (project.tracks ?? []).find((track) => track.type === type)?.id ?? (project.tracks ?? [])[0]?.id ?? "video-main";

  const insertItem = (partial: Partial<EditorTimelineItem> & Pick<EditorTimelineItem, "kind">) => {
    const start = Math.max(0, player.currentTime || 0);
    const item: EditorTimelineItem = {
      id: makeEditorId(partial.kind),
      trackId: partial.trackId ?? firstTrackOfType(partial.kind === "video" ? "video" : partial.kind === "audio" ? "audio" : partial.kind === "music" ? "music" : "overlay"),
      start,
      end: start + 5,
      transform: partial.kind === "text" || partial.kind === "image" || partial.kind === "logo" ? DEFAULT_OVERLAY_TRANSFORM : undefined,
      ...partial,
    };
    updateProjectItems((items) => [...items, item]);
    setSelectedItemId(item.id);
  };

  const insertAsset = (asset: EditorAsset) => {
    const kind: EditorItemKind = asset.type === "audio" ? "audio" : asset.type === "image" ? "image" : "video";
    insertItem({ kind, assetId: asset.id, trackId: firstTrackOfType(kind === "video" ? "video" : kind === "audio" ? "audio" : "overlay") });
  };

  const addTextOverlay = () => {
    insertItem({
      kind: "text",
      text: "New Text",
      trackId: firstTrackOfType("overlay"),
      style: { ...DEFAULT_SUBTITLE_STYLE, font_size: 48 },
    });
  };

  const updateSelectedItem = (patch: Partial<EditorTimelineItem>) => {
    if (!selectedItem) return;
    updateProjectItems((items) => items.map((item) => (item.id === selectedItem.id ? { ...item, ...patch } : item)));
  };

  const splitSelectedOrAtPlayhead = () => {
    const t = player.currentTime || 0;
    const target = selectedItem ?? (project.items ?? []).find((item) => t > item.start + 0.1 && t < item.end - 0.1);
    if (!target || t <= target.start + 0.1 || t >= target.end - 0.1) return;
    const second: EditorTimelineItem = {
      ...target,
      id: makeEditorId(target.kind),
      start: t,
      sourceStart: (target.sourceStart ?? 0) + (t - target.start),
    };
    const first = { ...target, end: t, sourceEnd: (target.sourceStart ?? 0) + (t - target.start) };
    updateProjectItems((items) => items.flatMap((item) => (item.id === target.id ? [first, second] : [item])));
    setSelectedItemId(second.id);
  };

  const duplicateSelected = () => {
    if (!selectedItem) return;
    const copy: EditorTimelineItem = {
      ...selectedItem,
      id: makeEditorId(selectedItem.kind),
      start: selectedItem.end,
      end: selectedItem.end + (selectedItem.end - selectedItem.start),
    };
    updateProjectItems((items) => [...items, copy]);
    setSelectedItemId(copy.id);
  };

  const deleteSelected = () => {
    if (!selectedItem) return;
    updateProjectItems((items) => items.filter((item) => item.id !== selectedItem.id));
    setSelectedItemId(null);
  };

  const addKeyframe = () => {
    if (!selectedItem) return;
    const transform = selectedItem.transform ?? DEFAULT_OVERLAY_TRANSFORM;
    const keyframes = [...(selectedItem.keyframes ?? []), { time: player.currentTime || selectedItem.start, transform }].sort(
      (a, b) => a.time - b.time
    );
    updateSelectedItem({ keyframes });
  };

  const removeLastKeyframe = () => {
    if (!selectedItem?.keyframes?.length) return;
    updateSelectedItem({ keyframes: selectedItem.keyframes.slice(0, -1) });
  };

  const updateSubtitleStyle = (key: keyof typeof DEFAULT_SUBTITLE_STYLE, value: unknown) => {
    const style = { ...(project.subtitle_style || DEFAULT_SUBTITLE_STYLE), [key]: value };
    commitProject({ ...project, subtitle_style: style });
  };

  const addUploadedAsset = (kind: UploadKind, filename: string, path: string) => {
    const asset: EditorAsset = {
      id: `asset-${kind}-${filename.replace(/[^a-z0-9_-]/gi, "_")}`,
      type: kind === "image" ? "image" : kind === "audio" ? "audio" : "video",
      name: filename,
      path,
      category: "uploaded",
      role: "uploaded",
      size_mb: 0,
    };
    commitProject({ ...project, assets: [...(project.assets ?? []).filter((a) => a.id !== asset.id), asset] });
  };

  const handleUpload = async (kind: UploadKind, e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(kind);
    try {
      const res =
        kind === "image"
          ? await api.uploadImage(runDir, file)
          : kind === "audio"
            ? await api.uploadAudio(runDir, file)
            : await api.uploadClip(runDir, file);
      addUploadedAsset(kind, res.filename, res.path);
    } catch (err) {
      alert(`Upload failed: ${err}`);
    } finally {
      setUploading("");
      e.target.value = "";
    }
  };

  const activeVideoItem = useMemo(() => {
    const t = player.currentTime || 0;
    return (project.items ?? [])
      .filter((item) => item.kind === "video" && t >= item.start && t < item.end)
      .sort((a, b) => a.trackId.localeCompare(b.trackId))[0];
  }, [player.currentTime, project.items]);

  const overlayItems = useMemo(() => {
    const t = player.currentTime || 0;
    return (project.items ?? []).filter(
      (item) => ["text", "image", "logo", "subtitle"].includes(item.kind) && t >= item.start && t < item.end
    );
  }, [player.currentTime, project.items]);

  const syncVideoToTime = useCallback(
    (time: number) => {
      const item = (project.items ?? []).find((candidate) => candidate.kind === "video" && time >= candidate.start && time < candidate.end);
      const asset = item?.assetId ? assetsById.get(item.assetId) : undefined;
      const url = asset ? clipMediaUrl(asset.path) : "";
      const el = videoRef.current;
      if (!el || !url || !item) return;
      const offset = Math.max(0, (item.sourceStart ?? 0) + time - item.start);
      if (loadedVideoUrlRef.current !== url) {
        loadedVideoUrlRef.current = url;
        el.src = url;
        el.load();
        pendingSeekRef.current = offset;
        setPreviewError("");
      } else if (el.readyState >= 1 && Math.abs(el.currentTime - offset) > (player.isPlaying ? 0.8 : 0.05)) {
        el.currentTime = offset;
      }
      if (el.readyState >= 2) {
        if (player.isPlaying && el.paused) void el.play().catch(() => setPreviewError("Preview clip failed to play."));
        if (!player.isPlaying && !el.paused) el.pause();
      }
      const audio = audioRef.current;
      if (audio) {
        if (Math.abs(audio.currentTime - time) > 0.2) audio.currentTime = time;
        if (player.isPlaying && audio.paused) void audio.play().catch(() => undefined);
        if (!player.isPlaying && !audio.paused) audio.pause();
      }
    },
    [assetsById, player.isPlaying, project.items]
  );

  useEffect(() => {
    syncVideoToTime(player.currentTime || 0);
  }, [player.currentTime, syncVideoToTime]);

  useEffect(() => {
    const scrollLeft = Math.max(0, (player.currentTime || 0) * scaleWidth - 160);
    const id = requestAnimationFrame(() => timelineRef.current?.setScrollLeft(scrollLeft));
    return () => cancelAnimationFrame(id);
  }, [player.currentTime, scaleWidth]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName?.match(/INPUT|TEXTAREA|SELECT/)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        onSave();
      } else if (e.key === " ") {
        e.preventDefault();
        player.isPlaying ? player.pause() : player.play();
      } else if (e.key.toLowerCase() === "s") {
        splitSelectedOrAtPlayhead();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        deleteSelected();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const selectedAsset = selectedItem?.assetId ? assetsById.get(selectedItem.assetId) : undefined;

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <button type="button" style={styles.backBtn} onClick={onBack}>Back</button>
        <input
          style={styles.titleInput}
          value={project.title}
          onChange={(e) => commitProject({ ...project, title: e.target.value })}
          aria-label="Project title"
        />
        <span style={styles.meta}>{project.aspect_ratio} | {(project.tracks ?? []).length} tracks | {totalDuration.toFixed(1)}s</span>
        <div style={styles.headerActions}>
          <button type="button" style={styles.toolBtn} onClick={undo} disabled={!historyRef.current.length}>Undo</button>
          <button type="button" style={styles.toolBtn} onClick={redo} disabled={!redoRef.current.length}>Redo</button>
          <button type="button" style={styles.saveBtn} onClick={onSave} disabled={saving || rerendering}>{saving ? "Saving..." : "Save"}</button>
          <button type="button" style={styles.exportBtn} onClick={onExport} disabled={saving || rerendering}>{rerendering ? "Exporting..." : "Export"}</button>
        </div>
      </header>

      <div style={styles.toolbar}>
        <button type="button" style={styles.toolBtn} onClick={splitSelectedOrAtPlayhead}>Split</button>
        <button type="button" style={styles.toolBtn} onClick={duplicateSelected} disabled={!selectedItem}>Duplicate</button>
        <button type="button" style={styles.dangerBtn} onClick={deleteSelected} disabled={!selectedItem}>Delete</button>
        <button type="button" style={styles.toolBtn} onClick={addTextOverlay}>Text</button>
        {(["video", "overlay", "audio", "music", "subtitle"] as EditorTrack["type"][]).map((type) => (
          <button key={type} type="button" style={styles.toolBtn} onClick={() => addTrack(type)}>+ {TRACK_LABELS[type]}</button>
        ))}
        <label style={styles.uploadBtn}>Upload Video<input hidden type="file" accept="video/*" onChange={(e) => void handleUpload("video", e)} /></label>
        <label style={styles.uploadBtn}>Upload Audio<input hidden type="file" accept="audio/*" onChange={(e) => void handleUpload("audio", e)} /></label>
        <label style={styles.uploadBtn}>Upload Image<input hidden type="file" accept="image/*" onChange={(e) => void handleUpload("image", e)} /></label>
        {uploading && <span style={styles.meta}>Uploading {uploading}...</span>}
      </div>

      <div style={styles.main}>
        <aside style={styles.mediaBin}>
          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Media Bin</h3>
            <div style={styles.assetList}>
              {(project.assets ?? []).map((asset) => (
                <button key={asset.id} type="button" style={styles.assetRow} onClick={() => insertAsset(asset)} title={asset.path}>
                  <span style={styles.assetType}>{asset.type}</span>
                  <span style={styles.assetName}>{asset.name}</span>
                </button>
              ))}
            </div>
          </section>

          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Stock Music</h3>
            <select
              style={styles.input}
              value={project.bg_music ?? ""}
              onChange={(e) => commitProject({ ...project, bg_music: e.target.value || undefined, bg_music_volume: project.bg_music_volume ?? 0.25 })}
            >
              <option value="">None</option>
              {stockMusic.map((m) => <option key={m.filename} value={m.filename}>{m.name}</option>)}
            </select>
            <label style={styles.label}>Music Volume</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={project.bg_music_volume ?? 0.25}
              onChange={(e) => commitProject({ ...project, bg_music_volume: parseFloat(e.target.value) })}
            />
          </section>

          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Subtitles</h3>
            <label style={styles.label}>Font size</label>
            <input type="number" style={styles.input} value={project.subtitle_style?.font_size ?? DEFAULT_SUBTITLE_STYLE.font_size} onChange={(e) => updateSubtitleStyle("font_size", parseInt(e.target.value, 10) || 28)} />
            <label style={styles.label}>Color</label>
            <input type="color" style={styles.colorInput} value={project.subtitle_style?.color ?? DEFAULT_SUBTITLE_STYLE.color} onChange={(e) => updateSubtitleStyle("color", e.target.value)} />
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
                const el = videoRef.current;
                if (el && pendingSeekRef.current !== null) {
                  el.currentTime = pendingSeekRef.current;
                  pendingSeekRef.current = null;
                }
                if (el && player.isPlaying && el.paused) void el.play().catch(() => undefined);
              }}
              onError={() => setPreviewError("Clip failed to load: " + (videoRef.current?.src || ""))}
            />
            {!activeVideoItem && <div style={styles.emptyPreview}>No video item at playhead</div>}
            {overlayItems.map((item) => {
              const transform = item.transform ?? DEFAULT_OVERLAY_TRANSFORM;
              const asset = item.assetId ? assetsById.get(item.assetId) : undefined;
              const common: CSSProperties = {
                position: "absolute",
                left: `${transform.x * 100}%`,
                top: `${transform.y * 100}%`,
                opacity: transform.opacity,
                transform: `translate(-50%, -50%) scale(${transform.scale}) rotate(${transform.rotation}deg)`,
                pointerEvents: "none",
              };
              if (item.kind === "image" || item.kind === "logo") {
                return asset ? <img key={item.id} src={clipMediaUrl(asset.path)} style={{ ...common, maxWidth: "45%", maxHeight: "45%" }} /> : null;
              }
              return <div key={item.id} style={{ ...common, color: item.style?.color ?? "#fff", fontSize: item.style?.font_size ?? 48, fontWeight: 800, textShadow: "0 2px 8px #000" }}>{item.text}</div>;
            })}
            <audio ref={audioRef} src={voiceoverUrl} preload="auto" crossOrigin="anonymous" />
            {previewError && <div style={styles.previewError}>{previewError}</div>}
          </div>
          <TransportBar player={player} />
          <div ref={timelineWrapRef} style={styles.timelineWrap}>
            <div style={styles.trackLabels}>
              {(project.tracks ?? []).map((track) => (
                <div key={track.id} style={styles.trackLabel}>
                  <span style={styles.trackName}>{track.name}</span>
                  <button type="button" style={styles.iconBtn} onClick={() => toggleTrack(track.id, "muted")}>{track.muted ? "M" : "m"}</button>
                  <button type="button" style={styles.iconBtn} onClick={() => toggleTrack(track.id, "locked")}>{track.locked ? "L" : "l"}</button>
                  <button type="button" style={styles.iconBtn} onClick={() => removeEmptyTrack(track.id)}>x</button>
                </div>
              ))}
            </div>
            <div style={styles.timelineInner}>
              <Timeline
                ref={timelineRef}
                style={{ width: "100%", height: "100%" }}
                editorData={timelineRows}
                effects={effects}
                scale={1}
                scaleWidth={scaleWidth}
                scaleSplitCount={5}
                rowHeight={48}
                gridSnap={project.timeline_settings?.snap ?? true}
                dragLine
                autoScroll
                enableRowDrag
                enableCrossRowDrag
                onChange={handleTimelineChange}
                onClickAction={(_e, { action }) => {
                  const data = (action?.data ?? {}) as Partial<SegmentActionData>;
                  setSelectedItemId(data.itemId ?? action.id);
                }}
                onCursorDrag={(time) => syncVideoToTime(time)}
                getActionRender={(action) => {
                  const data = (action?.data ?? {}) as Partial<SegmentActionData>;
                  return (
                    <div style={{ ...styles.actionBlock, ...(selectedItemId === action.id ? styles.actionBlockActive : {}) }}>
                      <span style={styles.actionTitle}>{data.text || data.clipName || data.kind || "Item"}</span>
                      {data.transition && <span style={styles.actionBadge}>T</span>}
                      {data.effect && <span style={styles.actionBadge}>FX</span>}
                    </div>
                  );
                }}
              />
            </div>
          </div>
        </div>

        <aside style={styles.inspector}>
          <section style={styles.panel}>
            <h3 style={styles.panelTitle}>Inspector</h3>
            {!selectedItem && <p style={styles.hint}>Select an item on the timeline.</p>}
            {selectedItem && (
              <>
                <div style={styles.selectedTitle}>{selectedItem.kind} {selectedAsset ? `| ${selectedAsset.name}` : ""}</div>
                <label style={styles.label}>Track</label>
                <select style={styles.input} value={selectedItem.trackId} onChange={(e) => updateSelectedItem({ trackId: e.target.value })}>
                  {(project.tracks ?? []).map((track) => <option key={track.id} value={track.id}>{track.name}</option>)}
                </select>
                <div style={styles.grid2}>
                  <label style={styles.label}>Start<input type="number" step={0.1} style={styles.input} value={selectedItem.start} onChange={(e) => updateSelectedItem({ start: parseFloat(e.target.value) || 0 })} /></label>
                  <label style={styles.label}>End<input type="number" step={0.1} style={styles.input} value={selectedItem.end} onChange={(e) => updateSelectedItem({ end: parseFloat(e.target.value) || selectedItem.start + 1 })} /></label>
                </div>
                {selectedItem.kind === "video" && (
                  <>
                    <label style={styles.label}>Voiceover</label>
                    <textarea style={styles.textarea} rows={3} value={selectedItem.voiceover ?? ""} onChange={(e) => updateSelectedItem({ voiceover: e.target.value })} />
                    <label style={styles.label}>Transition</label>
                    <select style={styles.input} value={selectedItem.transition ?? ""} onChange={(e) => updateSelectedItem({ transition: e.target.value || undefined })}>
                      <option value="">None</option>
                      {TRANSITION_PRESETS.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <label style={styles.label}>Effect</label>
                    <select style={styles.input} value={selectedItem.effect ?? ""} onChange={(e) => updateSelectedItem({ effect: e.target.value || undefined })}>
                      <option value="">None</option>
                      {EFFECT_PRESETS.map((fx) => <option key={fx} value={fx}>{fx}</option>)}
                    </select>
                  </>
                )}
                {(selectedItem.kind === "text" || selectedItem.kind === "subtitle") && (
                  <>
                    <label style={styles.label}>Text</label>
                    <textarea style={styles.textarea} rows={3} value={selectedItem.text ?? ""} onChange={(e) => updateSelectedItem({ text: e.target.value })} />
                    <label style={styles.label}>Font size</label>
                    <input type="number" style={styles.input} value={selectedItem.style?.font_size ?? 48} onChange={(e) => updateSelectedItem({ style: { ...(selectedItem.style ?? {}), font_size: parseInt(e.target.value, 10) || 48 } })} />
                  </>
                )}
                {(selectedItem.kind === "audio" || selectedItem.kind === "music") && (
                  <label style={styles.label}>Volume<input type="range" min={0} max={2} step={0.05} value={selectedItem.volume ?? 1} onChange={(e) => updateSelectedItem({ volume: parseFloat(e.target.value) })} /></label>
                )}
                {(selectedItem.kind === "text" || selectedItem.kind === "image" || selectedItem.kind === "logo") && (
                  <>
                    <h3 style={styles.panelTitle}>Motion</h3>
                    {(["x", "y", "scale", "opacity", "rotation"] as const).map((key) => (
                      <label key={key} style={styles.label}>{key}
                        <input
                          type="number"
                          step={key === "rotation" ? 1 : 0.05}
                          style={styles.input}
                          value={(selectedItem.transform ?? DEFAULT_OVERLAY_TRANSFORM)[key]}
                          onChange={(e) => updateSelectedItem({ transform: { ...(selectedItem.transform ?? DEFAULT_OVERLAY_TRANSFORM), [key]: parseFloat(e.target.value) || 0 } })}
                        />
                      </label>
                    ))}
                    <div style={styles.row}>
                      <button type="button" style={styles.toolBtn} onClick={addKeyframe}>Add Keyframe</button>
                      <button type="button" style={styles.toolBtn} onClick={removeLastKeyframe}>Remove Keyframe</button>
                    </div>
                    <p style={styles.hint}>{selectedItem.keyframes?.length ?? 0} keyframes</p>
                  </>
                )}
              </>
            )}
          </section>
          <button type="button" style={styles.debugToggle} onClick={() => setDebugOpen((v) => !v)}>Logs</button>
          {debugOpen && logs.length > 0 && <pre style={styles.logs}>{logs.join("\n")}</pre>}
        </aside>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  root: { display: "flex", flexDirection: "column", height: "100%", background: theme.bgMain, color: theme.textPri, minWidth: 0 },
  header: { display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderBottom: `1px solid ${theme.border}`, background: theme.bgCard },
  backBtn: { background: "transparent", border: `1px solid ${theme.border}`, color: theme.textSec, padding: "6px 10px", cursor: "pointer", fontSize: 12 },
  titleInput: { flex: 1, background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri, padding: "6px 10px", fontSize: 14, fontWeight: 700 },
  meta: { fontSize: 11, color: theme.textHint, whiteSpace: "nowrap" },
  headerActions: { display: "flex", gap: 6, marginLeft: "auto" },
  toolbar: { display: "flex", alignItems: "center", gap: 6, padding: "7px 12px", borderBottom: `1px solid ${theme.border}`, background: theme.bgSec, overflowX: "auto" },
  toolBtn: { padding: "5px 8px", background: theme.bgCard, border: `1px solid ${theme.border}`, color: theme.textSec, cursor: "pointer", fontSize: 11 },
  dangerBtn: { padding: "5px 8px", background: "rgba(255,68,68,0.12)", border: "1px solid rgba(255,68,68,0.45)", color: theme.accentRed, cursor: "pointer", fontSize: 11 },
  saveBtn: { padding: "6px 12px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri, cursor: "pointer", fontSize: 12, fontWeight: 700 },
  exportBtn: { padding: "6px 12px", background: "rgba(0,204,102,0.15)", border: `1px solid ${theme.accentGrn}`, color: theme.accentGrn, cursor: "pointer", fontSize: 12, fontWeight: 800 },
  uploadBtn: { padding: "5px 8px", background: "rgba(191,0,255,0.11)", border: `1px solid ${theme.accentPri}`, color: theme.textPri, cursor: "pointer", fontSize: 11, whiteSpace: "nowrap" },
  main: { display: "flex", flex: 1, minHeight: 0 },
  mediaBin: { width: 250, overflow: "auto", borderRight: `1px solid ${theme.border}`, background: theme.bgCard, padding: 8 },
  inspector: { width: 280, overflow: "auto", borderLeft: `1px solid ${theme.border}`, background: theme.bgCard, padding: 8 },
  panel: { marginBottom: 14 },
  panelTitle: { fontSize: 11, fontWeight: 800, color: theme.textSec, margin: "0 0 8px", textTransform: "uppercase" },
  assetList: { display: "flex", flexDirection: "column", gap: 4 },
  assetRow: { display: "flex", gap: 6, alignItems: "center", textAlign: "left", padding: "6px 8px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textSec, cursor: "pointer", minWidth: 0 },
  assetType: { color: theme.accentPri, fontSize: 10, textTransform: "uppercase", width: 36 },
  assetName: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 11 },
  label: { display: "block", fontSize: 10, color: theme.textHint, marginBottom: 5, marginTop: 8 },
  input: { width: "100%", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri, fontSize: 11, padding: 6, boxSizing: "border-box" },
  textarea: { width: "100%", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri, fontSize: 11, padding: 6, resize: "vertical", boxSizing: "border-box" },
  colorInput: { width: "100%", height: 32, padding: 0, border: "none", cursor: "pointer" },
  center: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },
  previewWrap: { flex: 1, minHeight: 220, background: "#000", display: "flex", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden" },
  previewVideo: { maxWidth: "100%", maxHeight: "100%", objectFit: "contain" },
  emptyPreview: { position: "absolute", color: theme.textHint, fontSize: 12 },
  previewError: { position: "absolute", bottom: 8, left: 8, right: 8, padding: "6px 10px", background: "rgba(180,0,0,0.85)", color: "#fff", fontSize: 11, textAlign: "center" },
  timelineWrap: { height: 260, borderTop: `1px solid ${theme.border}`, display: "flex", minWidth: 0 },
  trackLabels: { width: 150, flexShrink: 0, borderRight: `1px solid ${theme.border}`, background: theme.bgCard, paddingTop: 24 },
  trackLabel: { height: 48, display: "flex", alignItems: "center", gap: 4, padding: "0 6px", borderBottom: `1px solid ${theme.border}` },
  trackName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 10, color: theme.textSec },
  iconBtn: { width: 18, height: 18, padding: 0, background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textHint, cursor: "pointer", fontSize: 10 },
  timelineInner: { flex: 1, minWidth: 0, overflow: "hidden" },
  actionBlock: { height: "100%", display: "flex", alignItems: "center", gap: 4, padding: "0 6px", background: "rgba(0,204,102,0.18)", border: "1px solid rgba(0,204,102,0.5)", borderRadius: 2, fontSize: 10, overflow: "hidden" },
  actionBlockActive: { borderColor: theme.accentPri, boxShadow: `0 0 0 1px ${theme.accentPri} inset` },
  actionTitle: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  actionBadge: { fontSize: 9, color: theme.accentWarn },
  selectedTitle: { color: theme.textPri, fontSize: 12, fontWeight: 700, marginBottom: 8 },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 },
  row: { display: "flex", gap: 6, marginTop: 8 },
  hint: { color: theme.textHint, fontSize: 11, lineHeight: 1.4 },
  debugToggle: { width: "100%", padding: "6px 8px", background: "transparent", border: `1px solid ${theme.border}`, color: theme.textSec, cursor: "pointer", fontSize: 11 },
  logs: { maxHeight: 120, overflow: "auto", margin: "8px 0 0", padding: 8, fontSize: 10, background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textSec },
};
