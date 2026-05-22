import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { theme } from "../theme/tokens";

interface Props {
  onBackendChange: () => void;
}

type ConfigData = Record<string, unknown>;

const TTS_BACKENDS = ["omnivoice", "edge_tts", "elevenlabs"] as const;
const SCRIPT_PROVIDERS = ["gemini", "ollama"] as const;
const UPLOAD_MODES = ["unlisted", "public", "draft"] as const;
const LANGUAGES = [
  { code: "hi", label: "🇮🇳 Hindi" },
  { code: "hinglish", label: "🔀 Hinglish" },
  { code: "en", label: "🇬🇧 English" },
  { code: "mr", label: "Marathi" },
  { code: "bn", label: "Bengali" },
  { code: "gu", label: "Gujarati" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu" },
  { code: "or", label: "Odia" },
];
const EDGE_VOICES = [
  "hi-IN-MadhurNeural", "hi-IN-SwaraNeural", "en-US-GuyNeural", "en-US-JennyNeural",
  "en-GB-RyanNeural", "ta-IN-ValluvarNeural", "te-IN-MohanNeural",
];
const GEMINI_MODELS = [
  { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash (recommended)" },
  { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
  { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
];
const LOGO_POSITIONS = [
  { id: "top_left", label: "Top Left" },
  { id: "top_right", label: "Top Right" },
  { id: "bottom_left", label: "Bottom Left" },
  { id: "bottom_right", label: "Bottom Right" },
];

function getNested(cfg: ConfigData, path: string, fallback: unknown = ""): unknown {
  const parts = path.split(".");
  let cur: unknown = cfg;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in (cur as object)) cur = (cur as Record<string, unknown>)[p];
    else return fallback;
  }
  return cur ?? fallback;
}

export function SettingsTab({ onBackendChange }: Props) {
  const [cfg, setCfg] = useState<ConfigData>({});
  const [saved, setSaved] = useState(false);
  const [showGemini, setShowGemini] = useState(false);
  const [showEleven, setShowEleven] = useState(false);
  const [showMoreKeys, setShowMoreKeys] = useState(false);
  const [showOmni, setShowOmni] = useState(true);
  const [showEdgeEl, setShowEdgeEl] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [envPath, setEnvPath] = useState("");
  const [version, setVersion] = useState("");
  const [ollamaDetail, setOllamaDetail] = useState("");
  const [profiles, setProfiles] = useState<{ name: string; path: string; profile_name: string }[]>([]);
  const [activeProfile, setActiveProfile] = useState(0);

  const load = useCallback(async () => {
    const [c, info] = await Promise.all([
      api.getConfig(),
      api.systemInfo(),
    ]);
    setCfg(c);
    setDeviceName(info.device_name);
    setEnvPath(info.env_local_path);
    setVersion(info.version);
    const profs = (getNested(c, "pipeline.chrome_profiles", []) as typeof profiles) || [];
    setProfiles(Array.isArray(profs) ? profs : []);
    setActiveProfile(Number(getNested(c, "pipeline.active_profile_index", 0)));
    try {
      const oll = await api.probeOllama();
      setOllamaDetail(oll.detail);
    } catch {
      setOllamaDetail("");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const set = (path: string, value: unknown) => {
    setCfg((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as ConfigData;
      const parts = path.split(".");
      let cur = next;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!cur[parts[i]]) cur[parts[i]] = {};
        cur = cur[parts[i]] as ConfigData;
      }
      cur[parts[parts.length - 1]] = value;
      return next;
    });
  };

  const save = async () => {
    const flat: Record<string, unknown> = {};
    const flatten = (obj: ConfigData, prefix = "") => {
      for (const [k, v] of Object.entries(obj)) {
        const key = prefix ? `${prefix}.${k}` : k;
        if (v && typeof v === "object" && !Array.isArray(v)) flatten(v as ConfigData, key);
        else flat[key] = v;
      }
    };
    flatten(cfg);
    await api.patchConfig(flat);
    await api.saveConfig();
    setSaved(true);
    onBackendChange();
    setTimeout(() => setSaved(false), 2000);
  };

  const g = (path: string, fb: unknown = "") => getNested(cfg, path, fb);

  return (
    <div style={styles.scroll}>
      <Section title="Quick Start">
        <p style={styles.hint}>1. Add Gemini API key → 2. Pick TTS backend → 3. Set output folder → 4. Run documentary → 5. Upload</p>
      </Section>

      <Section title="API KEYS">
        <KeyField label="Gemini API Key (required)" path="api_keys.gemini" value={String(g("api_keys.gemini"))} onChange={(v) => set("api_keys.gemini", v)} show={showGemini} onToggleShow={() => setShowGemini(!showGemini)} />
        <button type="button" style={styles.foldLink} onClick={() => setShowMoreKeys(!showMoreKeys)}>
          {showMoreKeys ? "▼" : "▶"} More API keys
        </button>
        {showMoreKeys && (
          <>
            <KeyField label="ElevenLabs API Key" path="api_keys.elevenlabs" value={String(g("api_keys.elevenlabs"))} onChange={(v) => set("api_keys.elevenlabs", v)} show={showEleven} onToggleShow={() => setShowEleven(!showEleven)} />
            <KeyField label="Pexels API Key" path="api_keys.pexels" value={String(g("api_keys.pexels"))} onChange={(v) => set("api_keys.pexels", v)} show={false} onToggleShow={() => {}} />
          </>
        )}
      </Section>

      <Section title="AUDIO SUBROUTINE">
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {TTS_BACKENDS.map((b) => (
            <button key={b} type="button" style={{ ...styles.segBtn, ...(g("tts.backend") === b ? styles.segActive : {}) }} onClick={() => set("tts.backend", b)}>
              {b.toUpperCase()}
            </button>
          ))}
        </div>
        <button type="button" style={styles.foldLink} onClick={() => setShowOmni(!showOmni)}>{showOmni ? "▼" : "▶"} OmniVoice settings</button>
        {showOmni && g("tts.backend") === "omnivoice" && (
          <div style={styles.subPanel}>
            <Row label="Mode">
              <select value={String(g("tts.omnivoice_mode", "clone"))} onChange={(e) => set("tts.omnivoice_mode", e.target.value)}>
                <option value="clone">Voice Cloning</option>
                <option value="design">Sound Design</option>
              </select>
            </Row>
            <Row label="Server path (.bat)">
              <input value={String(g("tts.omnivoice_server_path", ""))} onChange={(e) => set("tts.omnivoice_server_path", e.target.value)} style={{ flex: 1 }} />
            </Row>
            <Row label="Reference audio">
              <input value={String(g("tts.reference_audio", ""))} onChange={(e) => set("tts.reference_audio", e.target.value)} style={{ flex: 1 }} />
            </Row>
            <Row label="Ref voice name">
              <input value={String(g("tts.omnivoice_ref_voice_name", ""))} onChange={(e) => set("tts.omnivoice_ref_voice_name", e.target.value)} style={{ flex: 1 }} />
            </Row>
            <Row label="Ref transcript">
              <input value={String(g("tts.omnivoice_ref_transcript", ""))} onChange={(e) => set("tts.omnivoice_ref_transcript", e.target.value)} style={{ flex: 1 }} />
            </Row>
            <Row label="Model ID">
              <input value={String(g("tts.omnivoice_model_id", "k2-fsa/OmniVoice"))} onChange={(e) => set("tts.omnivoice_model_id", e.target.value)} style={{ flex: 1 }} />
            </Row>
          </div>
        )}
        <button type="button" style={styles.foldLink} onClick={() => setShowEdgeEl(!showEdgeEl)}>{showEdgeEl ? "▼" : "▶"} Edge TTS & ElevenLabs</button>
        {showEdgeEl && (
          <div style={styles.subPanel}>
            <Row label="Edge voice">
              <select value={String(g("tts.edge_tts_voice", "hi-IN-MadhurNeural"))} onChange={(e) => set("tts.edge_tts_voice", e.target.value)}>
                {EDGE_VOICES.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Row>
            <Row label="ElevenLabs voice ID">
              <input value={String(g("tts.elevenlabs_voice_id", ""))} onChange={(e) => set("tts.elevenlabs_voice_id", e.target.value)} style={{ flex: 1 }} />
            </Row>
            <Row label="Stability (0–1)">
              <input type="number" step="0.05" min={0} max={1} value={Number(g("tts.elevenlabs_stability", 0.3))} onChange={(e) => set("tts.elevenlabs_stability", parseFloat(e.target.value))} />
            </Row>
            <Row label="Similarity boost">
              <input type="number" step="0.05" min={0} max={1} value={Number(g("tts.elevenlabs_similarity_boost", 0.85))} onChange={(e) => set("tts.elevenlabs_similarity_boost", parseFloat(e.target.value))} />
            </Row>
            <Row label="Style">
              <input type="number" step="0.05" min={0} max={1} value={Number(g("tts.elevenlabs_style", 0.45))} onChange={(e) => set("tts.elevenlabs_style", parseFloat(e.target.value))} />
            </Row>
          </div>
        )}
      </Section>

      <Section title="RUN BEHAVIOR">
        <div style={styles.grid}>
          <div>
            <label style={styles.checkRow}>
              <input type="checkbox" checked={Boolean(g("script_review_enabled", true))} onChange={(e) => set("script_review_enabled", e.target.checked)} />
              Pause for script review
            </label>
          </div>
          <div>
            <label style={styles.label}>Narration language</label>
            <select value={String(g("pipeline.language", "hi"))} onChange={(e) => set("pipeline.language", e.target.value)}>
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          <div>
            <label style={styles.label}>Output folder</label>
            <input value={String(g("pipeline.output_folder", "output"))} onChange={(e) => set("pipeline.output_folder", e.target.value)} style={{ width: "100%" }} />
          </div>
          <div>
            <label style={styles.checkRow}>
              <input type="checkbox" checked={Boolean(g("pipeline.upload_enabled", true))} onChange={(e) => set("pipeline.upload_enabled", e.target.checked)} />
              YouTube upload enabled
            </label>
            <select value={String(g("pipeline.upload_mode", "unlisted"))} onChange={(e) => set("pipeline.upload_mode", e.target.value)} style={{ marginTop: 4 }}>
              {UPLOAD_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label style={styles.label}>AI script provider</label>
            <div style={{ display: "flex", gap: 4 }}>
              {SCRIPT_PROVIDERS.map((p) => (
                <button key={p} type="button" style={{ ...styles.segBtn, ...(g("script_provider") === p ? styles.segActive : {}) }} onClick={() => set("script_provider", p)}>
                  {p}
                </button>
              ))}
            </div>
            {ollamaDetail && <p style={styles.hint}>{ollamaDetail}</p>}
            {g("script_provider") === "gemini" && (
              <select value={String(g("gemini_model", "gemini-2.5-flash"))} onChange={(e) => set("gemini_model", e.target.value)} style={{ marginTop: 4, width: "100%" }}>
                {GEMINI_MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            )}
            {g("script_provider") === "ollama" && (
              <>
                <input value={String(g("ollama_url", "http://localhost:11434"))} onChange={(e) => set("ollama_url", e.target.value)} placeholder="Ollama URL" style={{ width: "100%", marginTop: 4 }} />
                <input value={String(g("ollama_model", "llama3"))} onChange={(e) => set("ollama_model", e.target.value)} placeholder="Model" style={{ width: "100%", marginTop: 4 }} />
              </>
            )}
          </div>
        </div>
      </Section>

      <Section title="CORE PARAMETERS">
        <p style={styles.hint}>Chrome profiles for YouTube upload</p>
        <select value={activeProfile} onChange={(e) => { setActiveProfile(Number(e.target.value)); set("pipeline.active_profile_index", Number(e.target.value)); }} style={{ width: "100%", marginBottom: 8 }}>
          {profiles.map((p, i) => <option key={i} value={i}>{p.name || p.profile_name || `Profile ${i + 1}`}</option>)}
          {profiles.length === 0 && <option value={0}>No profiles — setup one below</option>}
        </select>
        <button type="button" style={styles.actionBtn} onClick={async () => {
          const name = prompt("Profile name:");
          if (name) {
            const res = await api.chromeProfileSetup(name);
            alert(res.message);
            load();
          }
        }}>+ SETUP NEW PROFILE</button>

        <p style={{ ...styles.sectionTitle, marginTop: 16 }}>LOGO WATERMARK</p>
        <label style={styles.checkRow}>
          <input type="checkbox" checked={Boolean(g("documentary.logo_enabled"))} onChange={(e) => set("documentary.logo_enabled", e.target.checked)} />
          Enable logo watermark
        </label>
        <input value={String(g("documentary.logo_path", ""))} onChange={(e) => set("documentary.logo_path", e.target.value)} placeholder="Logo path" style={{ width: "100%", marginTop: 4 }} />
        <select value={String(g("documentary.logo_position", "bottom_right"))} onChange={(e) => set("documentary.logo_position", e.target.value)} style={{ marginTop: 4 }}>
          {LOGO_POSITIONS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <Row label={`Scale: ${Math.round(Number(g("documentary.logo_scale", 0.15)) * 100)}%`}>
          <input type="range" min={0.05} max={0.5} step={0.01} value={Number(g("documentary.logo_scale", 0.15))} onChange={(e) => set("documentary.logo_scale", parseFloat(e.target.value))} style={{ flex: 1 }} />
        </Row>
        <Row label="Margin (px)">
          <input type="number" value={Number(g("documentary.logo_margin", 24))} onChange={(e) => set("documentary.logo_margin", parseInt(e.target.value, 10))} />
        </Row>
        <Row label={`Opacity: ${Math.round(Number(g("documentary.logo_opacity", 1)) * 100)}%`}>
          <input type="range" min={0} max={1} step={0.05} value={Number(g("documentary.logo_opacity", 1))} onChange={(e) => set("documentary.logo_opacity", parseFloat(e.target.value))} style={{ flex: 1 }} />
        </Row>
      </Section>

      <Section title="ABOUT">
        <p style={styles.hint}>Ghost Creator AI v{version} — free &amp; open source (MIT)</p>
        <p style={styles.hint}>Device: {deviceName}</p>
      </Section>

      <button type="button" style={{ ...styles.saveBtn, ...(saved ? { background: theme.accentGrn } : {}) }} onClick={save}>
        {saved ? "✅ SAVED" : "[ SAVE CONFIG ]"}
      </button>

      <div style={styles.envBar}>
        <span style={styles.hint}>{envPath}</span>
        <button type="button" style={styles.actionBtn} onClick={() => api.openEnvLocal()}>OPEN IN EDITOR</button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>&gt;&gt; [ {title} ]</div>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <span style={{ ...styles.label, minWidth: 140 }}>{label}</span>
      {children}
    </div>
  );
}

function KeyField({ label, value, onChange, show, onToggleShow }: {
  label: string; value: string; onChange: (v: string) => void; show: boolean; onToggleShow: () => void;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={styles.label}>{label}</label>
      <div style={{ display: "flex", gap: 8 }}>
        <input type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} style={{ flex: 1 }} />
        <button type="button" style={styles.actionBtn} onClick={onToggleShow}>{show ? "Hide" : "Show"}</button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  scroll: { height: "100%", overflow: "auto", paddingBottom: 24 },
  section: { background: theme.bgCard, border: `1px solid ${theme.border}`, padding: 16, marginBottom: 12 },
  sectionTitle: { color: theme.accentPri, fontWeight: 700, fontSize: 12, marginBottom: 12, fontFamily: "monospace" },
  hint: { color: theme.textHint, fontSize: 11, lineHeight: 1.5 },
  label: { display: "block", color: theme.textSec, fontSize: 11, marginBottom: 4 },
  checkRow: { display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: theme.textPri },
  segBtn: { padding: "6px 12px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textSec, fontSize: 11 },
  segActive: { borderColor: theme.accentPri, color: theme.accentPri },
  subPanel: { background: theme.bgSec, border: `1px solid ${theme.border}`, padding: 12, marginTop: 8, marginBottom: 8 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16 },
  foldLink: { background: "transparent", border: "none", color: theme.accentSec, fontSize: 11, marginBottom: 4, padding: 0 },
  actionBtn: { padding: "6px 12px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.accentPri, fontSize: 11, marginRight: 8, marginTop: 4 },
  saveBtn: { width: "100%", padding: 14, background: theme.accentPri, color: "#fff", border: "none", fontWeight: 700, marginBottom: 12 },
  envBar: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 12, background: theme.bgSec, border: `1px solid ${theme.border}` },
};
