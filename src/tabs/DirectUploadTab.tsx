import { useEffect, useState } from "react";
import { api } from "../api/client";
import { theme } from "../theme/tokens";

interface Props {
  prefill: { path: string; title?: string } | null;
  onPrefillConsumed: () => void;
}

export function DirectUploadTab({ prefill, onPrefillConsumed }: Props) {
  const [videoPath, setVideoPath] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [visibility, setVisibility] = useState("Unlisted");
  const [logs, setLogs] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (prefill) {
      setVideoPath(prefill.path);
      if (prefill.title) setTitle(prefill.title);
      onPrefillConsumed();
    }
  }, [prefill, onPrefillConsumed]);

  const browse = async () => {
    const paths = await window.electronAPI?.openFile({
      title: "Select Video to Upload",
      filters: [{ name: "Video", extensions: ["mp4", "mov", "avi", "webm"] }],
    });
    if (paths?.[0]) setVideoPath(paths[0]);
  };

  const aiFill = async () => {
    if (!videoPath) return;
    appendLog("🤖 Asking Gemini to generate metadata…");
    try {
      const res = await api.uploadAiFill({ video_path: videoPath });
      if (res.title) setTitle(res.title);
      if (res.description) setDescription(res.description);
      if (res.tags) setTags(res.tags);
      appendLog("✅ Metadata filled by AI!");
    } catch (e) {
      appendLog(`❌ AI Fill failed: ${e}`);
    }
  };

  const appendLog = (msg: string) => setLogs((prev) => [...prev, msg]);

  const startUpload = async () => {
    if (!videoPath || uploading) return;
    setUploading(true);
    appendLog("🚀 Starting upload to YouTube Studio…");
    try {
      const { job_id } = await api.uploadStart({
        video_path: videoPath,
        title,
        description,
        tags,
        visibility,
      });
      pollJob(job_id);
    } catch (e) {
      appendLog(`❌ ${e}`);
      setUploading(false);
    }
  };

  const pollJob = async (jobId: string, offset = 0) => {
    try {
      const res = await fetch(`${(await import("../api/client")).getApiBaseUrl()}/api/upload/job/${jobId}?offset=${offset}`);
      const data = await res.json();
      for (const log of data.logs || []) {
        appendLog(log.message);
      }
      if (!data.done) {
        setTimeout(() => pollJob(jobId, offset + (data.logs?.length || 0)), 500);
      } else {
        setUploading(false);
      }
    } catch {
      setUploading(false);
    }
  };

  return (
    <div style={styles.root}>
      <div style={styles.header}>[ 📤 DIRECT UPLOAD — GHOST UPLOADER ]</div>

      <div style={styles.card}>
        <label style={styles.label}>SELECT VIDEO</label>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={videoPath} onChange={(e) => setVideoPath(e.target.value)} style={{ flex: 1 }} />
          <button type="button" style={styles.btn} onClick={browse}>BROWSE</button>
        </div>
      </div>

      <div style={styles.card}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <label style={styles.label}>METADATA</label>
          <button type="button" style={styles.aiBtn} onClick={aiFill}>🤖 AI FILL (Gemini)</button>
        </div>
        <label style={styles.label}>Title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <label style={styles.label}>Description</label>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} style={{ width: "100%", marginBottom: 8 }} />
        <label style={styles.label}>Tags (comma separated)</label>
        <input value={tags} onChange={(e) => setTags(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <label style={styles.label}>Visibility</label>
        <select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
          {["Public", "Unlisted", "Private", "Draft"].map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      <div style={styles.logBox}>
        {logs.map((l, i) => (
          <div key={i} style={{ fontSize: 11, fontFamily: "monospace", color: theme.textSec }}>&gt; {l}</div>
        ))}
      </div>

      <button type="button" style={styles.uploadBtn} onClick={startUpload} disabled={uploading || !videoPath}>
        {uploading ? "⏳ UPLOADING…" : "▶ START UPLOAD"}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: { height: "100%", overflow: "auto", paddingBottom: 16 },
  header: { color: theme.accentPri, fontWeight: 700, padding: 16, border: `1px solid ${theme.accentPri}`, textAlign: "center", marginBottom: 12 },
  card: { background: theme.bgCard, border: `1px solid ${theme.border}`, padding: 12, marginBottom: 12 },
  label: { display: "block", fontSize: 11, color: theme.textSec, marginBottom: 4, fontWeight: 600 },
  btn: { padding: "8px 16px", background: theme.accentPri, color: "#fff", border: "none" },
  aiBtn: { padding: "4px 12px", background: "#330044", color: theme.textPri, border: `1px solid #A020F0`, fontSize: 11 },
  logBox: { background: "#020608", border: `1px solid ${theme.border}`, padding: 10, minHeight: 120, maxHeight: 200, overflow: "auto", marginBottom: 12 },
  uploadBtn: { padding: "12px 24px", background: theme.accentGrn, color: "#000", border: "none", fontWeight: 700 },
};
