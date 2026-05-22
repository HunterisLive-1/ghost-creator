import { useCallback, useEffect, useState } from "react";
import { api, HistoryEntry } from "../api/client";
import { theme } from "../theme/tokens";

interface Props {
  refreshKey: number;
  onOpenUpload: (path: string, title?: string) => void;
}

export function HistoryTab({ refreshKey, onOpenUpload }: Props) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [rerendering, setRerendering] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getHistory();
      setEntries(res.entries);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, refreshKey]);

  const pollRerender = async (jobId: string, runDir: string, offset = 0) => {
    const res = await fetch(`${(await import("../api/client")).getApiBaseUrl()}/api/history/job/${jobId}?offset=${offset}`);
    const data = await res.json();
    if (data.done) {
      setRerendering(null);
      refresh();
      const result = data.logs?.find((l: { result?: { video_path?: string } }) => l.result)?.result;
      if (result?.video_path) {
        const entry = entries.find((e) => e.run_dir === runDir);
        onOpenUpload(result.video_path, entry?.title);
      }
    } else {
      setTimeout(() => pollRerender(jobId, runDir, offset + (data.logs?.length || 0)), 500);
    }
  };

  const rerender = async (runDir: string) => {
    setRerendering(runDir);
    const { job_id } = await api.historyRerender({ run_dir: runDir });
    pollRerender(job_id, runDir);
  };

  return (
    <div style={styles.root}>
      <div style={styles.toolbar}>
        <span style={styles.title}>📋 RUN HISTORY</span>
        <span style={{ color: theme.textHint, fontSize: 11 }}>
          {entries.length} recent run{entries.length !== 1 ? "s" : ""} (newest 10)
        </span>
        <button type="button" style={styles.refreshBtn} onClick={refresh} disabled={loading}>
          ↻ REFRESH
        </button>
      </div>

      <div style={styles.list}>
        {entries.length === 0 && (
          <div style={styles.empty}>
            [ NO RUNS RECORDED ]<br /><br />
            Complete a documentary run in the 🎬 DOCUMENTARY tab and it will appear here.
          </div>
        )}
        {entries.map((e) => (
          <div key={e.run_dir} style={styles.card}>
            <div style={styles.cardTitle}>{e.title}</div>
            <div style={{ fontSize: 11, color: theme.textHint, marginBottom: 4 }}>{e.timestamp}</div>
            {e.topic && <div style={{ fontSize: 12, color: theme.textSec }}>Topic: {e.topic}</div>}
            {e.description && <div style={{ fontSize: 11, color: theme.textHint, marginTop: 4 }}>{e.description.slice(0, 200)}</div>}
            {e.duration && <div style={{ fontSize: 11, color: theme.accentSec, marginTop: 4 }}>Duration: {e.duration}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <button type="button" style={styles.actionBtn} onClick={() => window.electronAPI?.showItemInFolder(e.run_dir)}>
                Open Folder
              </button>
              {e.can_rerender && (
                <button
                  type="button"
                  style={styles.actionBtn}
                  onClick={() => rerender(e.run_dir)}
                  disabled={rerendering === e.run_dir}
                >
                  {rerendering === e.run_dir ? "Re-rendering…" : "Re-render (FFmpeg)"}
                </button>
              )}
              {e.video_path && (
                <button type="button" style={styles.actionBtn} onClick={() => window.electronAPI?.openPath(e.video_path)}>
                  Play Video
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: { height: "100%", display: "flex", flexDirection: "column" },
  toolbar: { display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: `1px solid ${theme.border}` },
  title: { color: "#B060FF", fontWeight: 700, fontSize: 16 },
  refreshBtn: { marginLeft: "auto", padding: "6px 12px", background: "transparent", border: `1px solid ${theme.accentPri}`, color: theme.accentPri, fontSize: 12 },
  list: { flex: 1, overflow: "auto", paddingTop: 12 },
  empty: { textAlign: "center", color: theme.textHint, padding: 80, fontFamily: "monospace", fontSize: 14 },
  card: { background: theme.bgCard, border: `1px solid ${theme.border}`, padding: 16, marginBottom: 8 },
  cardTitle: { color: theme.textPri, fontWeight: 700, fontSize: 14, marginBottom: 4 },
  actionBtn: { padding: "6px 12px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.accentPri, fontSize: 11 },
};
