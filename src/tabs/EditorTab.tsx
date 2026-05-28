import { useCallback, useEffect, useState } from "react";
import { api, getApiBaseUrl } from "../api/client";
import { theme } from "../theme/tokens";
import { TimelineEditor } from "../editor/TimelineEditor";
import { normalizeEditorJson } from "../editor/projectAdapter";
import type { ClipAsset, EditorJson } from "../editor/types";
import { DEFAULT_SUBTITLE_STYLE } from "../editor/types";

interface Props {
  runDir: string | null;
  onClearRunDir: () => void;
}

interface RecentRun {
  run_dir: string;
  title: string;
  timestamp: string;
  topic: string;
  video_path: string;
  duration: string;
}

export function EditorTab({ runDir, onClearRunDir }: Props) {
  const [activeRunDir, setActiveRunDir] = useState<string | null>(runDir);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [editorData, setEditorData] = useState<EditorJson | null>(null);
  const [editClips, setEditClips] = useState<ClipAsset[]>([]);
  const [stockClips, setStockClips] = useState<ClipAsset[]>([]);
  const [saving, setSaving] = useState(false);
  const [rerendering, setRerendering] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  const loadRecentRuns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getHistory();
      setRecentRuns(
        res.entries
          .filter((e) => e.can_rerender)
          .map((e) => ({
            run_dir: e.run_dir,
            title: e.title,
            timestamp: e.timestamp,
            topic: e.topic,
            video_path: e.video_path,
            duration: e.duration,
          }))
      );
    } catch (err) {
      console.error("Failed to load runs", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRunEditor = useCallback(
    async (dir: string) => {
      setLoading(true);
      try {
        const [raw, clipRes] = await Promise.all([api.loadEditor(dir), api.listClips(dir)]);
        const edit = clipRes.edit_clips?.length ? clipRes.edit_clips : clipRes.clips;
        const stock = clipRes.stock_clips ?? [];
        const normalized = normalizeEditorJson(
          {
            ...raw,
            subtitle_style: raw.subtitle_style ?? DEFAULT_SUBTITLE_STYLE,
          },
          edit
        );
        setEditorData(normalized);
        setEditClips(edit);
        setStockClips(stock);
        setActiveRunDir(dir);
        setLogs([]);
      } catch (err) {
        alert(`Failed to load project: ${err}`);
        setActiveRunDir(null);
        onClearRunDir();
      } finally {
        setLoading(false);
      }
    },
    [onClearRunDir]
  );

  useEffect(() => {
    if (runDir) {
      void loadRunEditor(runDir);
    } else {
      void loadRecentRuns();
    }
  }, [runDir, loadRunEditor, loadRecentRuns]);

  const pollRerender = async (jobId: string, offset = 0) => {
    const res = await fetch(`${getApiBaseUrl()}/api/history/job/${jobId}?offset=${offset}`);
    const data = await res.json();
    if (data.logs?.length) {
      setLogs((prev) => [...prev, ...data.logs.map((l: { message: string }) => l.message)]);
    }
    if (data.done) {
      setRerendering(false);
      alert("Final video compiled successfully!");
    } else {
      setTimeout(() => pollRerender(jobId, offset + (data.logs?.length || 0)), 600);
    }
  };

  const handleSave = async () => {
    if (!activeRunDir || !editorData) return;
    setSaving(true);
    try {
      await api.saveEditor(activeRunDir, editorData);
      setLogs((prev) => [...prev, "[SAVE] documentary_editor.json updated"]);
    } catch (err) {
      alert(`Save failed: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async () => {
    if (!activeRunDir || !editorData) return;
    setSaving(true);
    setLogs([]);
    try {
      await api.saveEditor(activeRunDir, editorData);
      setSaving(false);
      setRerendering(true);
      setLogs(["[START] Connecting to FFmpeg re-render queue…"]);
      const { job_id } = await api.historyRerender({ run_dir: activeRunDir });
      void pollRerender(job_id);
    } catch (err) {
      alert(`Save/Render failed: ${err}`);
      setSaving(false);
      setRerendering(false);
    }
  };

  const handleBack = () => {
    setActiveRunDir(null);
    setEditorData(null);
    onClearRunDir();
    void loadRecentRuns();
  };

  if (activeRunDir && editorData) {
    return (
      <TimelineEditor
        runDir={activeRunDir}
        editorData={editorData}
        editClips={editClips}
        stockClips={stockClips}
        onEditorDataChange={setEditorData}
        onSave={() => void handleSave()}
        onExport={() => void handleExport()}
        onBack={handleBack}
        saving={saving}
        rerendering={rerendering}
        logs={logs}
      />
    );
  }

  return (
    <div style={styles.root}>
      <h2 style={styles.title}>Ghost Editor</h2>
      <p style={styles.subtitle}>Open a completed run to edit clips on the timeline, then export via FFmpeg.</p>
      {loading && <p style={styles.hint}>Loading projects…</p>}
      <div style={styles.list}>
        {recentRuns.map((run) => (
          <button
            key={run.run_dir}
            type="button"
            style={styles.runCard}
            onClick={() => void loadRunEditor(run.run_dir)}
          >
            <span style={styles.runTitle}>{run.title}</span>
            <span style={styles.runMeta}>{run.timestamp} · {run.duration}</span>
          </button>
        ))}
        {!loading && recentRuns.length === 0 && (
          <p style={styles.hint}>No editable runs yet. Finish a pipeline run with stock/video footage (clips_for_edit folder).</p>
        )}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: { padding: 20, height: "100%", overflow: "auto" },
  title: { margin: "0 0 8px", color: theme.textPri, fontSize: 18 },
  subtitle: { margin: "0 0 16px", color: theme.textSec, fontSize: 12 },
  hint: { color: theme.textHint, fontSize: 12 },
  list: { display: "flex", flexDirection: "column", gap: 8, maxWidth: 560 },
  runCard: {
    textAlign: "left",
    padding: "12px 14px",
    background: theme.bgCard,
    border: `1px solid ${theme.border}`,
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  runTitle: { color: theme.textPri, fontWeight: 600, fontSize: 13 },
  runMeta: { color: theme.textHint, fontSize: 11 },
};
