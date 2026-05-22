import { useCallback, useEffect, useState } from "react";
import { api, setApiBaseUrl } from "./api/client";
import { theme, SystemState, stateColors } from "./theme/tokens";
import { StatusBar } from "./components/StatusBar";
import { DocumentaryTab } from "./tabs/DocumentaryTab";
import { DirectUploadTab } from "./tabs/DirectUploadTab";
import { SettingsTab } from "./tabs/SettingsTab";
import { HistoryTab } from "./tabs/HistoryTab";

type TabId = "documentary" | "upload" | "settings" | "history";

const TABS: { id: TabId; label: string }[] = [
  { id: "documentary", label: "🎬 DOCUMENTARY" },
  { id: "upload", label: "📤 UPLOAD" },
  { id: "settings", label: "⚙ SETTINGS" },
  { id: "history", label: "📋 HISTORY" },
];

export default function App() {
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<TabId>("documentary");
  const [systemState, setSystemState] = useState<SystemState>("READY");
  const [version, setVersion] = useState("4.2.2");
  const [ttsBackend, setTtsBackend] = useState("OMNIVOICE");
  const [uploadPrefill, setUploadPrefill] = useState<{ path: string; title?: string } | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  useEffect(() => {
    const init = async (baseUrl: string) => {
      setApiBaseUrl(baseUrl);
      try {
        const health = await api.health();
        setVersion(health.version);
        const cfg = await api.getConfig() as { tts?: { backend?: string } };
        setTtsBackend((cfg.tts?.backend || "omnivoice").toUpperCase());
      } catch {
        /* API unavailable — UI still loads */
      }
      setReady(true);
    };

    if (window.electronAPI) {
      window.electronAPI.onApiReady(({ baseUrl }) => init(baseUrl));
    } else {
      init("http://127.0.0.1:8766");
    }
  }, []);

  const refreshBackendLabel = useCallback(async () => {
    const cfg = await api.getConfig();
    const tts = cfg as { tts?: { backend?: string } };
    setTtsBackend((tts.tts?.backend || "omnivoice").toUpperCase());
  }, []);

  const openDirectUpload = useCallback((videoPath: string, titleHint?: string) => {
    setUploadPrefill({ path: videoPath, title: titleHint });
    setTab("upload");
  }, []);

  const onPipelineDone = useCallback(() => {
    setHistoryRefreshKey((k) => k + 1);
  }, []);

  if (!ready) {
    return (
      <div style={styles.loading}>
        <span style={{ color: theme.accentPri }}>Initializing Neural Interface…</span>
      </div>
    );
  }

  return (
    <div style={styles.root}>
      <header style={styles.topBar}>
        <span style={styles.brand}>👻 GHOST CREATOR AI</span>
        <span style={styles.badge}>v{version} ▋</span>
        <div style={styles.statusWrap}>
          <span style={{ color: theme.textSec, fontFamily: "monospace", fontSize: 12 }}>
            {systemState === "READY" ? "SYSTEM READY" : systemState === "PROCESSING" ? "PROCESSING" : "SYSTEM ERROR"}
          </span>
          <span style={{ ...styles.dot, background: stateColors[systemState] }} />
        </div>
      </header>
      <div style={styles.accentLine} />

      <nav style={styles.tabs}>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            style={{ ...styles.tabBtn, ...(tab === t.id ? styles.tabActive : {}) }}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main style={styles.content}>
        {tab === "documentary" && (
          <DocumentaryTab
            setSystemState={setSystemState}
            onPipelineDone={onPipelineDone}
          />
        )}
        {tab === "upload" && (
          <DirectUploadTab prefill={uploadPrefill} onPrefillConsumed={() => setUploadPrefill(null)} />
        )}
        {tab === "settings" && (
          <SettingsTab onBackendChange={refreshBackendLabel} />
        )}
        {tab === "history" && (
          <HistoryTab
            refreshKey={historyRefreshKey}
            onOpenUpload={openDirectUpload}
          />
        )}
      </main>

      <StatusBar ttsBackend={ttsBackend} />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: { display: "flex", flexDirection: "column", height: "100%", background: theme.bgMain },
  loading: { display: "flex", alignItems: "center", justifyContent: "center", height: "100%" },
  topBar: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 20px",
    background: theme.bgMain,
  },
  brand: { color: theme.accentPri, fontWeight: 700, fontSize: 16, letterSpacing: 1 },
  badge: {
    border: `1px solid ${theme.accentPri}`,
    background: theme.bgSec,
    color: theme.accentPri,
    padding: "2px 10px",
    fontSize: 11,
    fontWeight: 700,
  },
  statusWrap: { marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 },
  dot: { width: 10, height: 10, borderRadius: "50%", display: "inline-block" },
  accentLine: { height: 2, background: theme.accentPri },
  tabs: {
    display: "flex",
    gap: 4,
    padding: "8px 15px 0",
    background: theme.bgMain,
  },
  tabBtn: {
    background: theme.bgMain,
    border: "none",
    color: theme.accentPri,
    padding: "10px 16px",
    fontSize: 12,
    fontWeight: 600,
  },
  tabActive: { background: theme.border, borderRadius: "4px 4px 0 0" },
  content: { flex: 1, overflow: "hidden", padding: "0 15px 5px" },
};
