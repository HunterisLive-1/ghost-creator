import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  PipelineMessage,
  ScriptReviewData,
  WorkshopPlan,
} from "../api/client";
import { HexProgress, StepState, DOC_STEPS } from "../components/HexProgress";
import { ScriptReviewModal } from "../components/ScriptReviewModal";
import { usePipelineWebSocket } from "../hooks/usePipelineWebSocket";
import { theme } from "../theme/tokens";
import { SystemState } from "../theme/tokens";

interface Props {
  setSystemState: (s: SystemState) => void;
  onPipelineDone: () => void;
}

const LANGUAGES = [
  { code: "hi", label: "🇮🇳 Hindi" },
  { code: "hinglish", label: "🔀 Hinglish" },
  { code: "en", label: "🇬🇧 English" },
  { code: "mr", label: "🇮🇳 Marathi" },
  { code: "bn", label: "🇮🇳 Bengali" },
  { code: "gu", label: "🇮🇳 Gujarati" },
  { code: "ta", label: "🇮🇳 Tamil" },
  { code: "te", label: "🇮🇳 Telugu" },
  { code: "or", label: "🇮🇳 Odia" },
];

const VOICES = [
  { id: "omnivoice", label: "OmniVoice" },
  { id: "elevenlabs", label: "ElevenLabs" },
  { id: "edge_tts", label: "Edge TTS" },
];

const levelColors: Record<string, string> = {
  INFO: theme.textSec,
  SUCCESS: theme.accentGrn,
  ERROR: theme.accentRed,
  WARNING: theme.accentWarn,
};

export function DocumentaryTab({ setSystemState, onPipelineDone }: Props) {
  const [mode, setMode] = useState<"short" | "long">("short");
  const [duration, setDuration] = useState(60);
  const [topic, setTopic] = useState("");
  const [autoTopic, setAutoTopic] = useState(false);
  const [language, setLanguage] = useState("hi");
  const [voiceBackend, setVoiceBackend] = useState("omnivoice");
  const [segments, setSegments] = useState("0");
  const [burnSubs, setBurnSubs] = useState(false);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState(0);
  const [steps, setSteps] = useState<StepState[]>(Array(6).fill("idle"));
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<{ level: string; message: string }[]>([]);
  const [outputPath, setOutputPath] = useState("");
  const [retryVisible, setRetryVisible] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [analysing, setAnalysing] = useState(false);
  const [scriptReview, setScriptReview] = useState<ScriptReviewData | null>(null);
  const [workshopOpen, setWorkshopOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState<{ role: string; content: string }[]>([]);
  const [chatThinking, setChatThinking] = useState(false);
  const [lastPlan, setLastPlan] = useState<WorkshopPlan | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const reviewPollRef = useRef<number | null>(null);

  useEffect(() => {
    api.getConfig().then((cfg) => {
      const c = cfg as Record<string, unknown>;
      const doc = (c.documentary || {}) as Record<string, unknown>;
      const pipe = (c.pipeline || {}) as Record<string, unknown>;
      setMode((doc.length_mode as "short" | "long") || "short");
      setDuration(Number(doc.short_duration) || 60);
      setLanguage(String(pipe.language || "hi"));
      setVoiceBackend(String(doc.voice_backend || (c.tts as Record<string, string>)?.backend || "omnivoice"));
      setSegments(String(doc.segments ?? 0));
      setBurnSubs(Boolean(doc.burn_subtitles));
    });
  }, []);

  const appendLog = useCallback((level: string, message: string) => {
    setLogs((prev) => [...prev.slice(-500), { level, message }]);
  }, []);

  const handlePipelineMsg = useCallback(
    (msg: PipelineMessage) => {
      const rid = msg.run_id;
      if (rid !== undefined && rid !== runId) return;

      if (msg.message) appendLog(msg.level || "INFO", msg.message);

      if (msg.step >= 1 && msg.step <= 6) {
        setSteps((prev) => {
          const next = [...prev];
          for (let i = 0; i < msg.step - 1; i++) next[i] = "done";
          if (msg.level === "ERROR") next[msg.step - 1] = "error";
          else if (msg.level === "SUCCESS") next[msg.step - 1] = "done";
          else next[msg.step - 1] = "active";
          return next;
        });
        setProgress((msg.step - 1 + 0.5) / 6);
      }

      if (msg.retry_available) setRetryVisible(true);
      else if (msg.level !== "ERROR") setRetryVisible(false);

      if (msg.level === "ERROR") {
        setErrorMsg(msg.message);
        setSystemState("ERROR");
      }

      if (msg.done) {
        setRunning(false);
        setSystemState(msg.level === "ERROR" ? "ERROR" : "READY");
        if (msg.output_path) setOutputPath(msg.output_path);
        if (msg.level === "SUCCESS") {
          setSteps(Array(6).fill("done") as StepState[]);
          setProgress(1);
          onPipelineDone();
        }
      }
    },
    [runId, appendLog, setSystemState, onPipelineDone]
  );

  usePipelineWebSocket(handlePipelineMsg);

  const pollScriptReview = useCallback(async () => {
    if (!running) return;
    try {
      const res = await api.pipelineScriptReview();
      if (res.waiting && res.data) {
        setScriptReview(res.data);
        return;
      }
    } catch {
      /* ignore */
    }
    reviewPollRef.current = window.setTimeout(pollScriptReview, 500);
  }, [running]);

  const startPipeline = async () => {
    const dur = duration;
    await api.patchConfig({
      "documentary.length_mode": mode,
      "documentary.short_duration": mode === "short" ? dur : undefined,
      "documentary.long_duration": mode === "long" ? dur : undefined,
      target_duration: dur,
      "documentary.voice_backend": voiceBackend,
      "tts.backend": voiceBackend,
      "documentary.segments": parseInt(segments, 10) || 0,
      "documentary.burn_subtitles": burnSubs,
      "pipeline.language": language,
      ...(mode === "long" ? { aspect_ratio: "16:9" } : {}),
    });
    await api.saveConfig();

    const newRunId = runId + 1;
    setRunId(newRunId);
    setRunning(true);
    setSteps(Array(6).fill("idle") as StepState[]);
    setProgress(0);
    setLogs([]);
    setOutputPath("");
    setErrorMsg("");
    setAnalysis("");
    setRetryVisible(false);
    setSystemState("PROCESSING");

    await api.pipelineStart({ topic: autoTopic ? null : topic || null, run_id: newRunId });
    reviewPollRef.current = window.setTimeout(pollScriptReview, 500);
  };

  const stopPipeline = async () => {
    await api.pipelineStop();
    setRunning(false);
    setSystemState("READY");
    appendLog("WARNING", "Pipeline stopped by user");
    if (reviewPollRef.current) clearTimeout(reviewPollRef.current);
  };

  const applyMode = (m: "short" | "long") => {
    setMode(m);
    if (m === "short") setDuration(60);
    else setDuration(600);
  };

  const sendChat = async () => {
    if (!chatInput.trim() || chatThinking) return;
    const userMsg = chatInput.trim();
    setChatInput("");
    const hist = [...chatHistory, { role: "user", content: userMsg }];
    setChatHistory(hist);
    setChatThinking(true);
    try {
      const res = await api.workshopChat({ message: userMsg, history: hist.slice(0, -1) });
      setChatHistory([...hist, { role: "assistant", content: res.reply }]);
      if (res.plan) {
        setLastPlan(res.plan);
        if (res.plan.topic) setTopic(res.plan.topic);
        if (res.plan.format) applyMode(res.plan.format === "short" ? "short" : "long");
      }
    } catch (e) {
      appendLog("ERROR", `Workshop: ${e}`);
    } finally {
      setChatThinking(false);
    }
  };

  const explainError = async () => {
    if (!errorMsg) return;
    setAnalysing(true);
    try {
      const logText = logs.map((l) => l.message).join("\n");
      const res = await api.analyseError({ error_message: logText || errorMsg });
      setAnalysis(res.analysis);
    } finally {
      setAnalysing(false);
    }
  };

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <span style={styles.headerTitle}>🎬 DOCUMENTARY PIPELINE</span>
        <span style={styles.badge}>CINEMATIC MODE</span>
      </div>

      <div style={styles.row}>
        <button type="button" style={{ ...styles.modeCard, ...(mode === "short" ? styles.modeActive : {}) }} onClick={() => applyMode("short")}>
          SHORT<br /><small>30–60s</small>
        </button>
        <button type="button" style={{ ...styles.modeCard, ...(mode === "long" ? styles.modeActive : {}) }} onClick={() => applyMode("long")}>
          LONG<br /><small>3 min – 2 hr</small>
        </button>
      </div>

      <div style={styles.card}>
        <button type="button" style={styles.foldBtn} onClick={() => setWorkshopOpen(!workshopOpen)}>
          💡 Idea Workshop {workshopOpen ? "▼" : "▶"}
        </button>
        {workshopOpen && (
          <div style={{ marginTop: 8 }}>
            <div style={styles.chatLog}>
              {chatHistory.map((m, i) => (
                <div key={i} style={{ color: m.role === "user" ? theme.accentSec : theme.textPri, marginBottom: 4, fontSize: 12 }}>
                  <strong>{m.role === "user" ? "You" : "Gemini"}:</strong> {m.content}
                </div>
              ))}
              {chatThinking && <div style={{ color: theme.textHint }}>Thinking…</div>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Describe your documentary idea…" style={{ flex: 1 }} onKeyDown={(e) => e.key === "Enter" && sendChat()} />
              <button type="button" style={styles.smallBtn} onClick={sendChat}>SEND</button>
              <button type="button" style={styles.smallBtn} onClick={() => lastPlan && startPipeline()}>⚡ CREATE NOW</button>
            </div>
          </div>
        )}
      </div>

      <div style={styles.card}>
        <label style={styles.label}>Subject / Topic</label>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input value={topic} onChange={(e) => setTopic(e.target.value)} disabled={autoTopic} style={{ flex: 1 }} placeholder="Enter topic or use AUTO-SELECT" />
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: theme.textSec }}>
            <input type="checkbox" checked={autoTopic} onChange={(e) => setAutoTopic(e.target.checked)} />
            AUTO-SELECT
          </label>
        </div>
        <label style={{ ...styles.label, marginTop: 12 }}>Duration: {duration}s</label>
        <input
          type="range"
          min={mode === "short" ? 30 : 180}
          max={mode === "short" ? 60 : 7200}
          step={mode === "short" ? 5 : 60}
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
          style={{ width: "100%" }}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 12 }}>
          {LANGUAGES.map((l) => (
            <button key={l.code} type="button" style={{ ...styles.langBtn, ...(language === l.code ? styles.langActive : {}) }} onClick={() => setLanguage(l.code)}>
              {l.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          {VOICES.map((v) => (
            <button key={v.id} type="button" style={{ ...styles.langBtn, ...(voiceBackend === v.id ? styles.langActive : {}) }} onClick={() => setVoiceBackend(v.id)}>
              {v.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 12, alignItems: "center" }}>
          <label style={styles.label}>Clips:</label>
          <select value={segments} onChange={(e) => setSegments(e.target.value)}>
            <option value="0">Auto</option>
            {[3, 5, 8, 10, 15, 20, 30, 50, 100].map((n) => (
              <option key={n} value={String(n)}>{n}</option>
            ))}
          </select>
          {mode === "long" && (
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
              <input type="checkbox" checked={burnSubs} onChange={(e) => setBurnSubs(e.target.checked)} />
              Burn subtitles
            </label>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button type="button" style={styles.runBtn} onClick={startPipeline} disabled={running}>🎬 ROLL FILM</button>
        <button type="button" style={styles.stopBtn} onClick={stopPipeline} disabled={!running}>✂ CUT</button>
        {retryVisible && (
          <button type="button" style={styles.retryBtn} onClick={() => api.pipelineRetry()}>↻ RETRY STEP</button>
        )}
      </div>

      <HexProgress steps={steps} progress={progress} />

      <div style={styles.terminal}>
        {logs.map((l, i) => (
          <div key={i} style={{ color: levelColors[l.level] || theme.textSec, fontSize: 11, fontFamily: "monospace" }}>
            [{l.level}] {l.message}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>

      {errorMsg && (
        <div style={styles.errorPanel}>
          <strong style={{ color: theme.accentRed }}>AI Error Analyst</strong>
          <button type="button" style={styles.smallBtn} onClick={explainError} disabled={analysing}>
            {analysing ? "Analysing…" : "EXPLAIN & FIX"}
          </button>
          {analysis && <pre style={styles.analysis}>{analysis}</pre>}
        </div>
      )}

      {outputPath && (
        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: theme.accentGrn }}>✅ {outputPath}</span>
          <button type="button" style={styles.smallBtn} onClick={() => window.electronAPI?.showItemInFolder(outputPath)}>
            OPEN OUTPUT FOLDER
          </button>
        </div>
      )}

      {scriptReview && (
        <ScriptReviewModal
          data={scriptReview}
          onApprove={async (data) => {
            await api.pipelineScriptApprove(data);
            setScriptReview(null);
            reviewPollRef.current = window.setTimeout(pollScriptReview, 500);
          }}
          onRegenerate={async () => {
            await api.pipelineScriptCancel();
            setScriptReview(null);
            setTimeout(() => startPipeline(), 400);
          }}
          onCancel={async () => {
            await api.pipelineScriptCancel();
            setScriptReview(null);
            stopPipeline();
          }}
        />
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: { height: "100%", overflow: "auto", paddingBottom: 16 },
  header: { display: "flex", alignItems: "center", gap: 12, padding: "12px 0", borderBottom: `1px solid ${theme.border}`, marginBottom: 12 },
  headerTitle: { color: theme.accentPri, fontWeight: 700, fontSize: 14 },
  badge: { border: `1px solid ${theme.accentPri}`, padding: "2px 8px", fontSize: 10, color: theme.accentSec },
  row: { display: "flex", gap: 12, marginBottom: 12 },
  modeCard: { flex: 1, padding: 16, background: theme.bgCard, border: `1px solid ${theme.border}`, color: theme.textSec, textAlign: "center" },
  modeActive: { borderColor: theme.accentPri, color: theme.accentPri, background: theme.bgSec },
  card: { background: theme.bgCard, border: `1px solid ${theme.border}`, padding: 12, marginBottom: 12 },
  foldBtn: { background: "transparent", border: "none", color: theme.accentPri, fontWeight: 600, width: "100%", textAlign: "left" },
  chatLog: { maxHeight: 120, overflow: "auto", background: theme.bgMain, padding: 8, fontSize: 12 },
  label: { fontSize: 11, color: theme.textSec, fontWeight: 600 },
  langBtn: { padding: "4px 8px", fontSize: 11, background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textSec },
  langActive: { borderColor: theme.accentPri, color: theme.accentPri },
  smallBtn: { padding: "6px 12px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.accentPri, fontSize: 11 },
  runBtn: { padding: "10px 20px", background: theme.accentGrn, color: "#000", border: "none", fontWeight: 700 },
  stopBtn: { padding: "10px 20px", background: theme.accentRed, color: "#fff", border: "none", fontWeight: 700 },
  retryBtn: { padding: "10px 20px", background: theme.accentWarn, color: "#000", border: "none", fontWeight: 700 },
  terminal: { background: "#020608", border: `1px solid ${theme.border}`, padding: 10, height: 160, overflow: "auto", marginTop: 8 },
  errorPanel: { background: theme.bgCard, border: `1px solid ${theme.accentRed}`, padding: 12, marginTop: 8 },
  analysis: { whiteSpace: "pre-wrap", fontSize: 11, color: theme.textPri, marginTop: 8, fontFamily: "monospace" },
};
