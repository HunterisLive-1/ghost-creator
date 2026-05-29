import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  EditorReviewData,
  PipelineMessage,
  ScriptReviewData,
  WorkshopPlan,
} from "../api/client";
import { HexProgress, StepState, DOC_STEPS } from "../components/HexProgress";
import { ScriptReviewModal } from "../components/ScriptReviewModal";
import { usePipelineWebSocket } from "../hooks/usePipelineWebSocket";
import { theme } from "../theme/tokens";
import { SystemState } from "../theme/tokens";

interface PipelineLiveState {
  running: boolean;
  step: number;
  stepName: string;
  progress: number;
  lastMsg: string;
  level: string;
}

interface Props {
  setSystemState: (s: SystemState) => void;
  onPipelineDone: () => void;
  onPipelineStateChange?: (s: PipelineLiveState) => void;
  onOpenEditor?: (runDir: string) => void;
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

/** Poll script review while pipeline runs (step 2+). */
const SCRIPT_REVIEW_POLL_MS = 1500;
/** Poll editor review while pipeline runs (step 4+). */
const EDITOR_REVIEW_POLL_MS = 3000;
const EDITOR_REVIEW_POLL_ENABLED = true;

const levelColors: Record<string, string> = {
  INFO: theme.textSec,
  SUCCESS: theme.accentGrn,
  ERROR: theme.accentRed,
  WARNING: theme.accentWarn,
};

export function DocumentaryTab({ setSystemState, onPipelineDone, onPipelineStateChange, onOpenEditor }: Props) {
  const [mode, setMode] = useState<"short" | "long">("short");
  const [pipelineMode, setPipelineMode] = useState<"shorts" | "documentary" | "custom_script">("shorts");
  const [customScriptText, setCustomScriptText] = useState("");
  const [duration, setDuration] = useState(60);
  const [topic, setTopic] = useState("");
  const [autoTopic, setAutoTopic] = useState(false);
  const [language, setLanguage] = useState("hi");
  const [voiceBackend, setVoiceBackend] = useState("omnivoice");
  const [segments, setSegments] = useState("0");
  const [burnSubs, setBurnSubs] = useState(true);
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
  const [editorReview, setEditorReview] = useState<EditorReviewData | null>(null);
  const [workshopOpen, setWorkshopOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [captionsOpen, setCaptionsOpen] = useState(false);
  const [captionLang, setCaptionLang] = useState("voiceover");
  const [captionColor, setCaptionColor] = useState("#FFFFFF");
  const [captionBold, setCaptionBold] = useState(true);
  const [captionItalic, setCaptionItalic] = useState(false);
  const [chatHistory, setChatHistory] = useState<{ role: string; content: string }[]>([]);
  const [chatThinking, setChatThinking] = useState(false);
  const [lastPlan, setLastPlan] = useState<WorkshopPlan | null>(null);
  const [footageSource, setFootageSource] = useState("stock");
  const logEndRef = useRef<HTMLDivElement>(null);
  const reviewPollRef = useRef<number | null>(null);
  const editorPollRef = useRef<number | null>(null);
  const pipelineStepRef = useRef(0);
  const runningRef = useRef(running);
  const runIdRef = useRef(runId);
  runningRef.current = running;
  runIdRef.current = runId;

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
      setAspectRatio(String(c.aspect_ratio || "9:16"));

      const subStyle = (c.subtitle_style || {}) as Record<string, unknown>;
      setCaptionLang(String(subStyle.language || "voiceover"));
      setCaptionColor(String(subStyle.color || "#FFFFFF"));
      setCaptionBold(subStyle.bold !== undefined ? Boolean(subStyle.bold) : true);
      setCaptionItalic(subStyle.italic !== undefined ? Boolean(subStyle.italic) : false);
      setFootageSource(String(doc.footage_source || "stock"));
    });
  }, []);

  const appendLog = useCallback((level: string, message: string) => {
    setLogs((prev) => [...prev.slice(-500), { level, message }]);
  }, []);

  const handlePipelineMsg = useCallback(
    (msg: PipelineMessage) => {
      // Use runIdRef.current (always up-to-date) instead of runId state
      // to avoid stale closure dropping early progress messages
      const rid = msg.run_id;
      console.log("[Pipeline] MSG received: step=", msg.step, "run_id=", rid, "runIdRef=", runIdRef.current, "level=", msg.level, "msg=", msg.message?.slice(0, 50));
      if (rid !== undefined && runIdRef.current !== 0) {
        // rid can be:
        //   - an integer (from pipeline.py _run_graph_in_background after our fix)
        //   - a string like "run_1_abc12345" (from graph nodes via state["run_id"])
        // We accept the message if the integer part of rid matches our runId.
        let parsedRid: number;
        if (typeof rid === "string") {
          // Extract the first numeric segment after "run_"
          const m = rid.match(/^run_(\d+)/);
          parsedRid = m ? parseInt(m[1], 10) : NaN;
        } else {
          parsedRid = Number(rid);
        }
        if (!isNaN(parsedRid) && parsedRid !== runIdRef.current) {
          console.log("[Pipeline] FILTERED OUT: parsedRid=", parsedRid, "!== runIdRef=", runIdRef.current);
          return;
        }
      }

      if (msg.message) appendLog(msg.level || "INFO", msg.message);

      let newProgress = 0;
      if (msg.step >= 1 && msg.step <= 6) {
        pipelineStepRef.current = msg.step;
        setSteps((prev) => {
          const next = [...prev];
          for (let i = 0; i < msg.step - 1; i++) next[i] = "done";
          if (msg.level === "ERROR") next[msg.step - 1] = "error";
          else if (msg.level === "SUCCESS") next[msg.step - 1] = "done";
          else next[msg.step - 1] = "active";
          return next;
        });
        newProgress = (msg.step - 1 + 0.5) / 6;
        setProgress(newProgress);
      }

      if (msg.retry_available) setRetryVisible(true);
      else if (msg.level !== "ERROR") setRetryVisible(false);

      if (msg.level === "ERROR") {
        setErrorMsg(msg.message);
        setSystemState("ERROR");
      }

      // Notify App-level banner
      onPipelineStateChange?.({
        running: !msg.done,
        step: msg.step || 0,
        stepName: msg.step >= 1 && msg.step <= 6 ? DOC_STEPS[msg.step - 1] : "",
        progress: msg.done ? 1 : newProgress,
        lastMsg: msg.message || "",
        level: msg.level || "INFO",
      });

      if (msg.done) {
        setRunning(false);
        runningRef.current = false;
        setScriptReview(null);
        setEditorReview(null);
        setSystemState(msg.level === "ERROR" ? "ERROR" : "READY");
        if (msg.output_path) setOutputPath(msg.output_path);
        if (msg.level === "SUCCESS") {
          setSteps(Array(6).fill("done") as StepState[]);
          setProgress(1);
          onPipelineDone();
        }
      }
    },
    [appendLog, setSystemState, onPipelineDone, onPipelineStateChange]
  );

  usePipelineWebSocket(handlePipelineMsg);

  const pollScriptReview = useCallback(async () => {
    if (!runningRef.current) return;
    try {
      const res = await api.pipelineScriptReview();
      const activeRunId = runIdRef.current;
      if (
        res.waiting &&
        res.data &&
        (res.run_id == null || res.run_id === activeRunId)
      ) {
        setScriptReview(res.data);
        return;
      }
    } catch {
      /* ignore */
    }
    if (runningRef.current) {
      reviewPollRef.current = window.setTimeout(pollScriptReview, SCRIPT_REVIEW_POLL_MS);
    }
  }, []);

  const pollEditorReview = useCallback(async () => {
    if (!EDITOR_REVIEW_POLL_ENABLED || !runningRef.current) return;
    if (pipelineStepRef.current < 4) {
      if (runningRef.current) {
        editorPollRef.current = window.setTimeout(pollEditorReview, EDITOR_REVIEW_POLL_MS);
      }
      return;
    }
    try {
      const res = await api.pipelineEditorReview();
      const activeRunId = runIdRef.current;
      if (
        res.waiting &&
        res.data &&
        (res.run_id == null || res.run_id === activeRunId)
      ) {
        setEditorReview(res.data);
        return;
      }
    } catch {
      /* ignore */
    }
    if (runningRef.current) {
      editorPollRef.current = window.setTimeout(pollEditorReview, EDITOR_REVIEW_POLL_MS);
    }
  }, []);

  const startPipeline = async () => {
    if (pipelineMode === "custom_script" && customScriptText.trim().length < 50) {
      setErrorMsg("Script kam se kam 50 characters ka hona chahiye");
      appendLog("ERROR", "Script kam se kam 50 characters ka hona chahiye");
      return;
    }

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
      aspect_ratio: aspectRatio,
      subtitle_style: {
        language: captionLang,
        color: captionColor,
        bold: captionBold,
        italic: captionItalic,
      }
    });
    await api.saveConfig();

    const newRunId = runId + 1;
    setRunId(newRunId);
    setRunning(true);
    runningRef.current = true;
    pipelineStepRef.current = 1; // Start at step 1 — don't wait for WS to gate review poll
    setSteps(Array(6).fill("idle") as StepState[]);
    setProgress(0);
    setLogs([]);
    setOutputPath("");
    setErrorMsg("");
    setAnalysis("");
    setRetryVisible(false);
    setScriptReview(null);
    setEditorReview(null);
    setSystemState("PROCESSING");
    onPipelineStateChange?.({
      running: true, step: 1, stepName: DOC_STEPS[0],
      progress: 0, lastMsg: "Pipeline started…", level: "INFO"
    });

    if (reviewPollRef.current) clearTimeout(reviewPollRef.current);
    if (editorPollRef.current) clearTimeout(editorPollRef.current);

    const res = await api.pipelineStart({
      topic: autoTopic ? null : topic || null,
      run_id: newRunId,
      mode: pipelineMode,
      custom_script: pipelineMode === "custom_script" ? customScriptText : ""
    });
    if (!res.ok) {
      setRunning(false);
      runningRef.current = false;
      setSystemState("READY");
      const err = res.error || "Failed to start pipeline";
      setErrorMsg(err);
      appendLog("ERROR", err);
      onPipelineStateChange?.({
        running: false, step: 0, stepName: "",
        progress: 0, lastMsg: err, level: "ERROR"
      });
      return;
    }

    const startedRunId = res.run_id ?? newRunId;
    setRunId(startedRunId);
    runIdRef.current = startedRunId;
    reviewPollRef.current = window.setTimeout(pollScriptReview, SCRIPT_REVIEW_POLL_MS);
    if (EDITOR_REVIEW_POLL_ENABLED) {
      editorPollRef.current = window.setTimeout(pollEditorReview, EDITOR_REVIEW_POLL_MS);
    }
  };

  const stopPipeline = async () => {
    await api.pipelineStop();
    setRunning(false);
    runningRef.current = false;
    setScriptReview(null);
    setEditorReview(null);
    setSystemState("READY");
    appendLog("WARNING", "Pipeline stopped by user");
    if (reviewPollRef.current) clearTimeout(reviewPollRef.current);
    if (editorPollRef.current) clearTimeout(editorPollRef.current);
    onPipelineStateChange?.({
      running: false, step: 0, stepName: "",
      progress: 0, lastMsg: "Pipeline stopped by user", level: "WARNING"
    });
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

  const formatDuration = (secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    const parts: string[] = [];
    if (h > 0) parts.push(`${h} Hr`);
    if (m > 0) parts.push(`${m} Min`);
    if (s > 0 || parts.length === 0) parts.push(`${s} Sec`);
    return parts.join(" ");
  };

  const footageLabel =
    footageSource === "meta_ai"
      ? "Meta AI"
      : footageSource === "grok"
        ? "Grok"
        : footageSource === "ai_images"
          ? "AI Images"
          : "Stock";

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={styles.headerTitle}>🎬 DOCUMENTARY ENGINE</span>
          <span style={styles.headerSubtitle}>
            OmniVoice narration · {footageLabel} visuals · FFmpeg assembly
          </span>
        </div>
        <span style={styles.badge}>CINEMATIC MODE</span>
        <span style={styles.footageBadge}>
          Footage: {footageLabel}
        </span>
      </div>

      <div style={styles.row}>
        <div
          style={{
            ...styles.modeCard,
            ...(mode === "short" ? styles.modeActive : {}),
          }}
          onClick={() => applyMode("short")}
        >
          <div style={{ fontSize: 13, fontWeight: 700, color: purpleTheme.accentPri }}>✦ SHORT FORM</div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#FFB800", marginTop: 4 }}>30 – 180 seconds</div>
          <div style={{ fontSize: 11, color: purpleTheme.textSec, marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
            <div>• Quick 30–180s, output size: Settings → Video format (9:16 or 16:9)</div>
            <div>• Auto: several short clips / cuts</div>
            <div>• Fast narration, punchy cuts</div>
          </div>
        </div>
        <div
          style={{
            ...styles.modeCard,
            ...(mode === "long" ? styles.modeActive : {}),
          }}
          onClick={() => applyMode("long")}
        >
          <div style={{ fontSize: 13, fontWeight: 700, color: purpleTheme.accentPri }}>Ⅱ LONG FORM</div>
          <div style={{ fontSize: 12, fontWeight: 600, color: purpleTheme.textSec, marginTop: 4 }}>3 min – 2 hours</div>
          <div style={{ fontSize: 11, color: purpleTheme.textSec, marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
            <div>• Full feature documentary</div>
            <div>• More clips on longer runs (auto), up to 100</div>
            <div>• Deep narration, chapter-style flow</div>
          </div>
        </div>
      </div>

      {/* ASPECT RATIO POSITIONED DIRECTLY BELOW SHORT/LONG MODE CARDS */}
      <div style={{ ...styles.card, display: "flex", alignItems: "center", gap: 16, marginBottom: 12 }}>
        <span style={{ fontSize: 11, color: purpleTheme.textSec, fontWeight: 700, fontFamily: "monospace" }}>📹 VIDEO FORMAT (ASPECT RATIO):</span>
        <div style={{ display: "flex", gap: 8 }}>
          {["9:16", "16:9"].map((ar) => (
            <button
              key={ar}
              type="button"
              style={{
                ...styles.langBtn,
                ...(aspectRatio === ar ? styles.langActive : {}),
                padding: "6px 16px",
                fontWeight: 700,
              }}
              onClick={() => setAspectRatio(ar)}
            >
              {ar === "9:16" ? "📱 9:16 (Vertical/Shorts)" : "🖥️ 16:9 (Horizontal/Long)"}
            </button>
          ))}
        </div>
      </div>

      {/* PIPELINE MODE SELECTOR */}
      <div style={{ ...styles.card, display: "flex", alignItems: "center", gap: 16, marginBottom: 12 }}>
        <span style={{ fontSize: 11, color: purpleTheme.textSec, fontWeight: 700, fontFamily: "monospace" }}>🚀 PIPELINE MODE:</span>
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { id: "shorts", label: "🤖 AI Shorts", hint: footageSource === "ai_images" ? "Gemini images" : `${footageLabel} video` },
            { id: "documentary", label: "🎬 AI Documentary", hint: `${footageLabel} video` },
            { id: "custom_script", label: "✍️ My Script", hint: footageSource === "ai_images" ? "Gemini images" : `${footageLabel} video` }
          ].map((m) => (
            <button
              key={m.id}
              type="button"
              style={{
                ...styles.langBtn,
                ...(pipelineMode === m.id ? styles.langActive : {}),
                padding: "6px 16px",
                fontWeight: 700,
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
                gap: 2,
              }}
              onClick={() => setPipelineMode(m.id as "shorts" | "documentary" | "custom_script")}
            >
              <span>{m.label}</span>
              <span style={{ fontSize: 9, fontWeight: 500, color: purpleTheme.textHint }}>{m.hint}</span>
            </button>
          ))}
        </div>
      </div>

      <div style={styles.card}>
        <button type="button" style={styles.foldBtn} onClick={() => setWorkshopOpen(!workshopOpen)}>
          <span>▶ [GHOST AI] — Idea Workshop + Chat with your AI director</span>
          <span style={{ fontSize: 10, color: "#00CC66", display: "flex", alignItems: "center", gap: 4 }}>
            GHOST AI <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#00CC66", boxShadow: "0 0 6px #00CC66" }} /> ONLINE
          </span>
        </button>
        {workshopOpen && (
          <div style={{ marginTop: 8 }}>
            <div style={styles.chatLog}>
              {chatHistory.map((m, i) => (
                <div key={i} style={{ color: m.role === "user" ? purpleTheme.accentSec : purpleTheme.textPri, marginBottom: 4, fontSize: 12 }}>
                  <strong>{m.role === "user" ? "You" : "Gemini"}:</strong> {m.content}
                </div>
              ))}
              {chatThinking && <div style={{ color: purpleTheme.textHint }}>Thinking…</div>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Describe your documentary idea…" style={{ flex: 1, background: purpleTheme.bgSec, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textPri, padding: 8 }} onKeyDown={(e) => e.key === "Enter" && sendChat()} />
              <button type="button" style={styles.smallBtn} onClick={sendChat}>SEND</button>
              <button type="button" style={styles.smallBtn} onClick={() => lastPlan && startPipeline()}>⚡ CREATE NOW</button>
            </div>
          </div>
        )}
      </div>

      <div style={styles.card}>
        <label style={styles.label}>
          {pipelineMode === "custom_script" ? "🎙 VIDEO TOPIC (OPTIONAL, FOR RESEARCH CONTEXT):" : "🎙 DOCUMENTARY SUBJECT:"}
        </label>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input value={topic} onChange={(e) => setTopic(e.target.value)} disabled={autoTopic && pipelineMode !== "custom_script"} style={{ flex: 1, background: purpleTheme.bgSec, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textPri, padding: 8 }} placeholder={pipelineMode === "custom_script" ? "Enter topic/context (optional)" : "Enter topic — or leave blank for auto-trending"} />
          {pipelineMode !== "custom_script" && (
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: purpleTheme.textSec, cursor: "pointer" }}>
              <input type="checkbox" checked={autoTopic} onChange={(e) => setAutoTopic(e.target.checked)} style={{ accentColor: purpleTheme.accentPri }} />
              AUTO-SELECT
            </label>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16, marginBottom: 6 }}>
          <label style={{ ...styles.label, margin: 0 }}>⏱ DURATION: {mode === "short" ? "30s - 3m" : "3m - 2h"}</label>
          <span style={{ fontSize: 12, fontWeight: 700, color: purpleTheme.accentSec }}>
            {formatDuration(duration)} ({duration}s)
          </span>
        </div>
        <input
          type="range"
          min={mode === "short" ? 30 : 180}
          max={mode === "short" ? 180 : 7200}
          step={mode === "short" ? 5 : 60}
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
          style={{ width: "100%", accentColor: purpleTheme.accentPri }}
        />

        <label style={{ ...styles.label, marginTop: 16 }}>🗣 VOICE ENGINE:</label>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {VOICES.map((v) => (
              <button key={v.id} type="button" style={{ ...styles.langBtn, ...(voiceBackend === v.id ? styles.langActive : {}) }} onClick={() => setVoiceBackend(v.id)}>
                {v.label}
              </button>
            ))}
          </div>
          <span style={{ fontSize: 11, color: purpleTheme.textSec, marginLeft: 8 }}>
            Local AI — zero-shot clone · TTS: पूरी स्क्रिप्ट एक pass में, Settings → HTTP read timeout
          </span>
        </div>

        <label style={{ ...styles.label, marginTop: 16 }}>🎬 FOOTAGE SETTINGS:</label>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: purpleTheme.textSec }}>Clips:</span>
          <select value={segments} onChange={(e) => setSegments(e.target.value)} style={{ background: purpleTheme.bgSec, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textPri, padding: "4px 8px" }}>
            <option value="0">Auto</option>
            {[3, 5, 8, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000].map((n) => (
              <option key={n} value={String(n)}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      {/* MY SCRIPT TEXTAREA CARD */}
      {pipelineMode === "custom_script" && (
        <div style={styles.card}>
          <label style={styles.label}>✍️ MY SCRIPT:</label>
          <textarea
            value={customScriptText}
            onChange={(e) => setCustomScriptText(e.target.value)}
            placeholder="Apna script yahan likho... Koi bhi language chalega. AI isko polish karke video banana..."
            rows={12}
            maxLength={5000}
            style={{
              width: "100%",
              boxSizing: "border-box",
              background: purpleTheme.bgSec,
              border: `1px solid ${purpleTheme.border}`,
              color: purpleTheme.textPri,
              padding: 8,
              fontFamily: "inherit",
              fontSize: 12,
              resize: "vertical",
              borderRadius: 4
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 11, color: purpleTheme.textSec }}>
            <span>{customScriptText.length} / 5000</span>
            {customScriptText.trim().length > 0 && customScriptText.trim().length < 50 && (
              <span style={{ color: "#FF4444" }}>Script must be at least 50 characters</span>
            )}
          </div>
          <div style={{
            marginTop: 12,
            padding: 12,
            background: "rgba(191, 0, 255, 0.05)",
            border: `1px dashed ${purpleTheme.border}`,
            borderRadius: 4,
            fontSize: 11,
            lineHeight: 1.5,
            color: purpleTheme.textSec
          }}>
            ✍️ <strong>Apne Script Se Video Banao</strong><br />
            Tumhara likha hua script AI ke through polish hoga — hook strong hoga, TTS-friendly banega — aur phir automatically video ban jayega. Script ka core message bilkul change nahi hoga.
          </div>
        </div>
      )}

      {/* AUTO CAPTION COLLAPSIBLE SETTINGS SECTION */}
      <div style={styles.card}>
        <button type="button" style={styles.foldBtn} onClick={() => setCaptionsOpen(!captionsOpen)}>
          <span>📝 Auto Caption Settings {captionsOpen ? "▼" : "▶"}</span>
          <span style={{ fontSize: 11, color: burnSubs ? theme.accentGrn : theme.textHint, fontWeight: 700 }}>
            {burnSubs ? "● ON (BURN-IN)" : "○ OFF"}
          </span>
        </button>
        {captionsOpen && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 12 }}>
            <label style={styles.checkRow}>
              <input type="checkbox" checked={burnSubs} onChange={(e) => setBurnSubs(e.target.checked)} style={{ accentColor: purpleTheme.accentPri }} />
              Burn-in subtitles directly on the video
            </label>
            
            <Row label="Caption Language">
              <select value={captionLang} onChange={(e) => setCaptionLang(e.target.value)} style={{ background: purpleTheme.bgSec, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textPri, padding: "4px 8px" }}>
                <option value="voiceover">Same as Voiceover Language</option>
                <option value="en">English (Translation)</option>
              </select>
            </Row>

            <Row label="Subtitle Color">
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {["#FFFFFF", "#FFFF00", "#FF00FF", "#00FFFF", "#00FF00"].map((color) => (
                  <button
                    key={color}
                    type="button"
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: "50%",
                      background: color,
                      border: captionColor === color ? `2px solid ${purpleTheme.accentSec}` : `1px solid ${purpleTheme.border}`,
                      cursor: "pointer",
                      boxShadow: captionColor === color ? `0 0 6px ${color}` : "none",
                    }}
                    onClick={() => setCaptionColor(color)}
                  />
                ))}
                <span style={{ fontSize: 11, color: purpleTheme.textSec }}>({captionColor})</span>
              </div>
            </Row>

            <Row label="Text Formatting">
              <div style={{ display: "flex", gap: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", fontSize: 12 }}>
                  <input type="checkbox" checked={captionBold} onChange={(e) => setCaptionBold(e.target.checked)} style={{ accentColor: purpleTheme.accentPri }} />
                  Bold Text
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", fontSize: 12 }}>
                  <input type="checkbox" checked={captionItalic} onChange={(e) => setCaptionItalic(e.target.checked)} style={{ accentColor: purpleTheme.accentPri }} />
                  Italic Text
                </label>
              </div>
            </Row>
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <button type="button" style={styles.runBtn} onClick={startPipeline} disabled={running}>🎬 ROLL FILM</button>
        <button type="button" style={styles.stopBtn} onClick={stopPipeline} disabled={!running}>✂ CUT</button>
        
        {errorMsg && (
          <span style={{ color: "#FF4444", fontSize: 11, fontWeight: 700, fontFamily: "monospace", marginLeft: 8 }}>
            ERROR X
          </span>
        )}

        {(retryVisible || errorMsg) && (
          <button 
            type="button" 
            style={{ ...styles.retryBtn, marginLeft: "auto" }} 
            onClick={async () => {
              try {
                await api.pipelineRetry();
              } catch (e) {
                console.error(e);
              }
              explainError();
            }}
          >
            ↻ AI FIX & RETRY
          </button>
        )}
      </div>

      <HexProgress steps={steps} progress={progress} progressColor={purpleTheme.accentPri} activeColor={purpleTheme.accentPri} />

      <div style={styles.terminal}>
        {logs.map((l, i) => (
          <div key={i} style={{ color: levelColors[l.level] || purpleTheme.textSec, fontSize: 11, fontFamily: "monospace" }}>
            [{l.level}] {l.message}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>

      {errorMsg && (
        <div style={styles.errorPanel}>
          <strong style={{ color: "#FF4444" }}>AI Error Analyst</strong>
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

      {editorReview && (
        <div style={styles.editorPauseBanner}>
          <div>
            <strong style={{ color: theme.accentPri }}>Editor pause</strong>
            <span style={{ marginLeft: 8, fontSize: 12, color: theme.textSec }}>
              {editorReview.title} — {editorReview.segment_count} clips ready. Edit in Ghost Editor, save, then continue.
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {onOpenEditor && (
              <button
                type="button"
                style={styles.smallBtn}
                onClick={() => onOpenEditor(editorReview.run_dir)}
              >
                OPEN EDITOR
              </button>
            )}
            <button
              type="button"
              style={styles.runBtn}
              onClick={async () => {
                await api.pipelineEditorContinue();
                setEditorReview(null);
                if (EDITOR_REVIEW_POLL_ENABLED) {
                  editorPollRef.current = window.setTimeout(pollEditorReview, EDITOR_REVIEW_POLL_MS);
                }
              }}
            >
              CONTINUE PIPELINE
            </button>
            <button
              type="button"
              style={styles.stopBtn}
              onClick={async () => {
                await api.pipelineEditorCancel();
                setEditorReview(null);
                stopPipeline();
              }}
            >
              CANCEL
            </button>
          </div>
        </div>
      )}

      {scriptReview && (
        <ScriptReviewModal
          data={scriptReview}
          onApprove={async (data) => {
            await api.pipelineScriptApprove(data);
            setScriptReview(null);
            reviewPollRef.current = window.setTimeout(pollScriptReview, SCRIPT_REVIEW_POLL_MS);
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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <span style={{ ...styles.label, minWidth: 140, margin: 0 }}>{label}</span>
      {children}
    </div>
  );
}

const purpleTheme = {
  accentPri: "#BF00FF",
  accentSec: "#D400FF",
  border: "rgba(191, 0, 255, 0.25)",
  borderActive: "#BF00FF",
  bgCard: "#0E071A",
  bgSec: "#170E28",
  textPri: "#F5F0FF",
  textSec: "#BCA2E8",
  textHint: "#6E5A8E",
};

const styles: Record<string, React.CSSProperties> = {
  root: { height: "100%", overflow: "auto", paddingBottom: 16, color: purpleTheme.textPri },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", background: purpleTheme.bgCard, border: `1px solid ${purpleTheme.accentPri}`, borderRadius: 4, marginBottom: 12 },
  headerTitle: { color: purpleTheme.textPri, fontWeight: 700, fontSize: 14, fontFamily: "monospace" },
  headerSubtitle: { color: purpleTheme.textSec, fontSize: 11, marginLeft: 12 },
  badge: { border: `1px solid ${purpleTheme.accentPri}`, background: "rgba(191,0,255,0.15)", padding: "4px 10px", fontSize: 10, color: purpleTheme.textPri, cursor: "pointer", fontWeight: 700, borderRadius: 2, fontFamily: "monospace" },
  footageBadge: { border: `1px solid ${purpleTheme.border}`, padding: "4px 10px", fontSize: 10, color: purpleTheme.textSec, borderRadius: 2, fontFamily: "monospace" },
  row: { display: "flex", gap: 12, marginBottom: 12 },
  modeCard: { flex: 1, padding: 16, background: purpleTheme.bgCard, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textSec, textAlign: "left", borderRadius: 4, transition: "all 0.3s ease", cursor: "pointer" },
  modeActive: { borderColor: purpleTheme.accentPri, boxShadow: `0 0 12px rgba(191, 0, 255, 0.4)`, background: purpleTheme.bgSec, color: purpleTheme.textPri },
  card: { background: purpleTheme.bgCard, border: `1px solid ${purpleTheme.border}`, padding: 12, marginBottom: 12, borderRadius: 4 },
  foldBtn: { background: "transparent", border: "none", color: purpleTheme.textPri, fontWeight: 600, width: "100%", textAlign: "left", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" },
  chatLog: { maxHeight: 120, overflow: "auto", background: "#050209", padding: 8, fontSize: 12, border: `1px solid ${purpleTheme.border}` },
  label: { fontSize: 11, color: purpleTheme.textSec, fontWeight: 600, fontFamily: "monospace", display: "block", marginBottom: 6 },
  langBtn: { padding: "6px 12px", fontSize: 11, background: purpleTheme.bgSec, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textSec, borderRadius: 2, cursor: "pointer" },
  langActive: { borderColor: purpleTheme.accentPri, background: "rgba(191,0,255,0.15)", color: purpleTheme.textPri },
  smallBtn: { padding: "6px 12px", background: purpleTheme.bgSec, border: `1px solid ${purpleTheme.border}`, color: purpleTheme.textPri, fontSize: 11, borderRadius: 2, cursor: "pointer" },
  runBtn: { padding: "10px 24px", background: "rgba(191,0,255,0.1)", color: purpleTheme.textPri, border: `1px solid ${purpleTheme.accentPri}`, fontWeight: 700, borderRadius: 2, cursor: "pointer", letterSpacing: 0.5 },
  stopBtn: { padding: "10px 24px", background: "rgba(255,68,68,0.1)", color: "#FF4444", border: `1px solid #FF4444`, fontWeight: 700, borderRadius: 2, cursor: "pointer", letterSpacing: 0.5 },
  retryBtn: { padding: "10px 24px", background: "rgba(255,184,0,0.15)", color: "#FFB800", border: `1px solid #FFB800`, fontWeight: 700, borderRadius: 2, cursor: "pointer", letterSpacing: 0.5 },
  editorPauseBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap",
    padding: 12,
    marginBottom: 12,
    background: "rgba(0,230,118,0.08)",
    border: "1px solid rgba(0,230,118,0.4)",
    borderRadius: 4,
  },
  terminal: { background: "#040207", border: `1px solid ${purpleTheme.border}`, padding: 10, height: 160, overflow: "auto", marginTop: 8, borderRadius: 4 },
  errorPanel: { background: purpleTheme.bgCard, border: `1px solid #FF4444`, padding: 12, marginTop: 8, borderRadius: 4 },
  analysis: { whiteSpace: "pre-wrap", fontSize: 11, color: purpleTheme.textPri, marginTop: 8, fontFamily: "monospace" },
};
