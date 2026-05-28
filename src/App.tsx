import { useCallback, useEffect, useState } from "react";
import { api, setApiBaseUrl } from "./api/client";
import { theme, SystemState, stateColors } from "./theme/tokens";
import { StatusBar } from "./components/StatusBar";
import { PipelineLiveBanner, PipelineLiveState } from "./components/PipelineLiveBanner";
import { DocumentaryTab } from "./tabs/DocumentaryTab";
import { DirectUploadTab } from "./tabs/DirectUploadTab";
import { SettingsTab } from "./tabs/SettingsTab";
import { HistoryTab } from "./tabs/HistoryTab";
import { EditorTab } from "./tabs/EditorTab";

type TabId = "documentary" | "upload" | "settings" | "history" | "editor";

const TABS: { id: TabId; label: string }[] = [
  { id: "documentary", label: "🎬 DOCUMENTARY" },
  { id: "upload", label: "📤 UPLOAD" },
  { id: "settings", label: "⚙ SETTINGS" },
  { id: "history", label: "📋 HISTORY" },
  { id: "editor", label: "✂️ EDITOR" },
];

const IDLE_PIPELINE: PipelineLiveState = {
  running: false, step: 0, stepName: "", progress: 0, lastMsg: "", level: "INFO",
};

export default function App() {
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<TabId>("documentary");
  const [systemState, setSystemState] = useState<SystemState>("READY");
  const [version, setVersion] = useState("4.2.2");
  const [ttsBackend, setTtsBackend] = useState("OMNIVOICE");
  const [uploadPrefill, setUploadPrefill] = useState<{ path: string; title?: string } | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [editorRunDir, setEditorRunDir] = useState<string | null>(null);

  // Global pipeline live state — persists across tab switches
  const [pipelineLive, setPipelineLive] = useState<PipelineLiveState>(IDLE_PIPELINE);

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
      init("");
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

  const openInEditor = useCallback((runDir: string) => {
    setEditorRunDir(runDir);
    setTab("editor");
  }, []);

  const onPipelineDone = useCallback(() => {
    setHistoryRefreshKey((k) => k + 1);
  }, []);

  const handlePipelineStateChange = useCallback((state: PipelineLiveState) => {
    setPipelineLive(state);
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
      {/* ── CSS animations ── */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes dotPulse { 0%,100% { opacity:0.4; } 50% { opacity:1; } }
        @keyframes shimmerMove { 0% { opacity:0; transform:translateX(-100%); } 50% { opacity:1; } 100% { opacity:0; transform:translateX(200%); } }
        @keyframes bannerPulse { 0%,100% { box-shadow: inset 0 0 40px rgba(191,0,255,0.03); } 50% { box-shadow: inset 0 0 40px rgba(191,0,255,0.08); } }
      `}</style>

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
            style={{
              ...styles.tabBtn,
              ...(tab === t.id ? styles.tabActive : {}),
              // Highlight documentary tab with pulse when pipeline running and we're elsewhere
              ...(t.id === "documentary" && pipelineLive.running && tab !== "documentary"
                ? styles.tabPulse : {}),
            }}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {/* Live dot on documentary tab when running and on another tab */}
            {t.id === "documentary" && pipelineLive.running && tab !== "documentary" && (
              <span style={styles.liveDot} />
            )}
          </button>
        ))}
      </nav>

      {/* ── PERSISTENT PIPELINE BANNER — visible on ALL tabs ── */}
      <PipelineLiveBanner
        state={pipelineLive}
        onGoToPipeline={() => setTab("documentary")}
      />

      {/* ── TABS — all kept mounted, hidden via display:none ── */}
      <main style={styles.content}>
        {/* Documentary always mounted so pipeline & WebSocket never unmount */}
        <div style={{ display: tab === "documentary" ? "block" : "none", height: "100%" }}>
          <DocumentaryTab
            setSystemState={setSystemState}
            onPipelineDone={onPipelineDone}
            onPipelineStateChange={handlePipelineStateChange}
            onOpenEditor={openInEditor}
          />
        </div>

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
            onOpenEditor={openInEditor}
          />
        )}
        {tab === "editor" && (
          <EditorTab
            runDir={editorRunDir}
            onClearRunDir={() => setEditorRunDir(null)}
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
    position: "relative",
    cursor: "pointer",
  },
  tabActive: { background: theme.border, borderRadius: "4px 4px 0 0" },
  tabPulse: {
    animation: "tabGlow 1.5s ease-in-out infinite",
  },
  liveDot: {
    position: "absolute",
    top: 6,
    right: 4,
    width: 6,
    height: 6,
    borderRadius: "50%",
    background: "#BF00FF",
    boxShadow: "0 0 6px #BF00FF",
    animation: "dotPulse 1s ease-in-out infinite",
  },
  content: { flex: 1, overflow: "hidden", padding: "0 15px 5px" },
};
