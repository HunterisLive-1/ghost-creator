import { useCallback, useEffect, useState } from "react";
import { api, getApiBaseUrl } from "../api/client";
import { theme } from "../theme/tokens";

interface Props {
  onBackendChange: () => void;
}

type ConfigData = Record<string, unknown>;

const TTS_BACKENDS = ["omnivoice", "edge_tts", "elevenlabs"] as const;
const SCRIPT_PROVIDERS = ["gemini", "groq", "ollama"] as const;
const UPLOAD_MODES = ["unlisted", "public", "private", "draft"] as const;
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
  { id: "gemini-3.1-flash-lite", label: "gemini-3.1-flash-lite  ·  15rpm/500rpd · Free ✅ BEST" },
  { id: "gemini-3.5-flash", label: "gemini-3.5-flash  ·  5rpm/20rpd · Free ✅ LATEST" },
  { id: "gemini-3-flash", label: "gemini-3-flash  ·  5rpm/20rpd · Free ✅" },
  { id: "gemini-2.5-flash", label: "gemini-2.5-flash  ·  5rpm/20rpd · Free ✅" },
  { id: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite  ·  10rpm/20rpd · Free ✅" },
];
const GROQ_MODELS = [
  { id: "llama-3.3-70b-versatile", label: "llama-3.3-70b-versatile  ·  30rpm/1K rpd · Free ✅ BEST" },
  { id: "meta-llama/llama-4-scout-17b-16e-instruct", label: "llama-4-scout-17b  ·  30rpm/1K rpd · Free ✅ FAST" },
  { id: "qwen/qwen3-32b", label: "qwen3-32b  ·  60rpm/1K rpd · Free ✅ HIGH RPM" },
  { id: "llama-3.1-8b-instant", label: "llama-3.1-8b-instant  ·  30rpm/14.4K rpd · Free ✅ MOST REQUESTS" },
  { id: "openai/gpt-oss-120b", label: "gpt-oss-120b  ·  30rpm/1K rpd · Free ✅ SMART" },
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

function generateSparklinePoints(name: string, metric: string) {
  let hash = 0;
  const str = name + metric;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const absHash = Math.abs(hash);
  
  const points: number[] = [];
  let current = 20 + (absHash % 40);
  for (let i = 0; i < 12; i++) {
    const change = ((absHash + i * 37) % 31) - 15;
    current = Math.max(5, Math.min(100, current + change));
    points.push(current);
  }
  return points;
}

function Sparkline({ points, color }: { points?: number[]; color: string }) {
  const width = 80;
  const height = 24;
  
  if (!points || points.length === 0) {
    const y = height / 2;
    const pathD = `M 0 ${y} L ${width} ${y}`;
    return (
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible", marginTop: 4 }}>
        <path d={pathD} fill="none" stroke="rgba(255, 255, 255, 0.15)" strokeWidth="1" strokeDasharray="3,3" strokeLinecap="round" />
      </svg>
    );
  }
  
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const denominator = points.length > 1 ? points.length - 1 : 1;
  
  const coords = points.map((p, i) => {
    const x = (i / denominator) * width;
    const y = height - ((p - min) / range) * (height - 4) - 2;
    return { x, y };
  });
  
  let pathD = `M ${coords[0].x} ${coords[0].y}`;
  for (let i = 0; i < coords.length - 1; i++) {
    const curr = coords[i];
    const next = coords[i + 1];
    const cp1x = curr.x + (next.x - curr.x) / 3;
    const cp1y = curr.y;
    const cp2x = curr.x + 2 * (next.x - curr.x) / 3;
    const cp2y = next.y;
    pathD += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${next.x} ${next.y}`;
  }
  
  const fillD = `${pathD} L ${width} ${height} L 0 ${height} Z`;
  const gradId = `spark-grad-${Math.random().toString(36).substr(2, 9)}`;
  
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible", marginTop: 4 }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0.0" />
        </linearGradient>
      </defs>
      <path d={fillD} fill={`url(#${gradId})`} />
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={coords[coords.length - 1].x} cy={coords[coords.length - 1].y} r="2.5" fill={color} />
    </svg>
  );
}

interface AnalyticsChartProps {
  points?: number[];
  metricName: "views" | "subs" | "earnings";
  color: string;
  channelName: string;
}

function AnalyticsChart({ points, metricName, color, channelName }: AnalyticsChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  const labelMap = {
    views: "Views",
    subs: "Subscribers",
    earnings: "Estimated Revenue (USD)"
  };

  const chartHeight = 160;
  const paddingLeft = 45;
  const paddingRight = 15;
  const paddingTop = 20;
  const paddingBottom = 25;
  const chartWidth = 950;

  const totalWidth = chartWidth + paddingLeft + paddingRight;
  const totalHeight = chartHeight + paddingTop + paddingBottom;

  if (!points || points.length === 0) {
    return (
      <div style={{
        marginTop: 20,
        background: "rgba(255, 255, 255, 0.01)",
        border: `1px dashed ${theme.border}`,
        borderRadius: 6,
        padding: "32px 16px",
        textAlign: "center",
        color: theme.textHint,
        fontSize: 12,
        fontFamily: "monospace"
      }}>
        📊 NO REAL-TIME ANALYTICS SYNCED FOR "{channelName.toUpperCase()}"
        <div style={{ fontSize: 10, marginTop: 6, opacity: 0.8 }}>
          Connect Google Account and click Sync to display real-time analytics graphs here.
        </div>
      </div>
    );
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const denominator = points.length > 1 ? points.length - 1 : 1;

  const getCoords = (val: number, idx: number) => {
    const x = paddingLeft + (idx / denominator) * chartWidth;
    const y = paddingTop + chartHeight - ((val - min) / range) * chartHeight;
    return { x, y };
  };

  const coords = points.map((p, i) => getCoords(p, i));

  let pathD = `M ${coords[0].x} ${coords[0].y}`;
  for (let i = 0; i < coords.length - 1; i++) {
    const curr = coords[i];
    const next = coords[i + 1];
    const cp1x = curr.x + (next.x - curr.x) / 3;
    const cp1y = curr.y;
    const cp2x = curr.x + 2 * (next.x - curr.x) / 3;
    const cp2y = next.y;
    pathD += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${next.x} ${next.y}`;
  }

  const fillD = `${pathD} L ${coords[coords.length - 1].x} ${paddingTop + chartHeight} L ${paddingLeft} ${paddingTop + chartHeight} Z`;
  const gradId = `main-chart-grad-${metricName}`;

  const gridLines = [0, 0.33, 0.66, 1];

  const generateDates = (len: number) => {
    const dates: string[] = [];
    const today = new Date();
    for (let i = len - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const day = d.getDate();
      const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      dates.push(`${day} ${monthNames[d.getMonth()]}`);
    }
    return dates;
  };
  const dateLabels = generateDates(points.length);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const clientY = e.clientY - rect.top;

    const viewBoxX = (clientX / rect.width) * totalWidth;
    const viewBoxY = (clientY / rect.height) * totalHeight;

    let closestIdx = 0;
    let minDiff = Infinity;
    coords.forEach((coord, idx) => {
      const diff = Math.abs(coord.x - viewBoxX);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = idx;
      }
    });

    setHoverIndex(closestIdx);
    setMousePos({ x: clientX, y: clientY });
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  const formatYValue = (val: number) => {
    if (metricName === "earnings") {
      return `$${val.toFixed(2)}`;
    }
    if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
    if (val >= 1000) {
      const kVal = val / 1000;
      return kVal % 1 === 0 ? `${kVal}K` : `${kVal.toFixed(1)}K`;
    }
    return Math.round(val).toString();
  };

  const selectedPoint = hoverIndex !== null ? points[hoverIndex] : null;
  const selectedCoord = hoverIndex !== null ? coords[hoverIndex] : null;
  const selectedDate = hoverIndex !== null ? dateLabels[hoverIndex] : null;

  return (
    <div style={{
      marginTop: 20,
      background: "rgba(18, 9, 33, 0.3)",
      border: `1px solid ${theme.border}`,
      borderRadius: 6,
      padding: 16,
      position: "relative",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: theme.accentSec, letterSpacing: 0.5, fontFamily: "monospace" }}>
          📊 28-DAY ANALYTICS: {labelMap[metricName].toUpperCase()}
        </span>
        <span style={{ fontSize: 10, color: theme.textHint, fontFamily: "monospace" }}>
          Channel: <span style={{ color: theme.textPri }}>{channelName}</span>
        </span>
      </div>

      <div style={{ position: "relative" }}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${totalWidth} ${totalHeight}`}
          style={{ overflow: "visible", cursor: "crosshair" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.25" />
              <stop offset="100%" stopColor={color} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {gridLines.map((ratio, idx) => {
            const y = paddingTop + ratio * chartHeight;
            const val = max - ratio * range;
            return (
              <g key={idx}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={paddingLeft + chartWidth}
                  y2={y}
                  stroke="rgba(255, 255, 255, 0.05)"
                  strokeWidth="1"
                  strokeDasharray="4,4"
                />
                <text
                  x={paddingLeft - 8}
                  y={y + 4}
                  fill="rgba(255, 255, 255, 0.4)"
                  fontSize="9"
                  fontFamily="monospace"
                  textAnchor="end"
                >
                  {formatYValue(val)}
                </text>
              </g>
            );
          })}

          {(() => {
            const labelIndices = coords.length > 0 
              ? Array.from(new Set([0, Math.floor((coords.length - 1) / 2), coords.length - 1]))
              : [];
            return labelIndices.map((idx) => {
              const coord = coords[idx];
              if (!coord) return null;
              return (
                <text
                  key={idx}
                  x={coord.x}
                  y={paddingTop + chartHeight + 16}
                  fill="rgba(255, 255, 255, 0.4)"
                  fontSize="9"
                  fontFamily="monospace"
                  textAnchor="middle"
                >
                  {dateLabels[idx]}
                </text>
              );
            });
          })()}

          <path d={fillD} fill={`url(#${gradId})`} />

          <path
            d={pathD}
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {selectedCoord && (
            <g>
              <line
                x1={selectedCoord.x}
                y1={paddingTop}
                x2={selectedCoord.x}
                y2={paddingTop + chartHeight}
                stroke="rgba(255, 255, 255, 0.2)"
                strokeWidth="1.5"
                strokeDasharray="3,3"
              />
              <circle
                cx={selectedCoord.x}
                cy={selectedCoord.y}
                r="4.5"
                fill={color}
                stroke="#090514"
                strokeWidth="1.5"
              />
            </g>
          )}
        </svg>

        {hoverIndex !== null && selectedPoint !== null && selectedCoord && (
          <div style={{
            position: "absolute",
            left: mousePos.x + 15,
            top: mousePos.y - 45,
            background: "rgba(10, 5, 20, 0.95)",
            border: `1px solid ${color}`,
            borderRadius: 4,
            padding: "6px 10px",
            color: "#fff",
            fontSize: 11,
            pointerEvents: "none",
            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
            zIndex: 10,
            fontFamily: "monospace"
          }}>
            <div style={{ color: theme.textHint, fontSize: 9, marginBottom: 2 }}>{selectedDate}</div>
            <div style={{ fontWeight: 700 }}>
              {metricName === "earnings" ? "$" : ""}
              {selectedPoint.toLocaleString()}
              {metricName === "views" ? " views" : metricName === "subs" ? " subscribers" : ""}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface ChromeProfile {
  name: string;
  path: string;
  profile_name: string;
  views_28d?: number;
  subs_28d?: number;
  earnings_28d?: number;
  logo_path?: string;
  views_growth?: string;
  subs_growth?: string;
  earnings_growth?: string;
  channel_url?: string;
  channel_id?: string;
  views_series?: number[];
  subs_series?: number[];
  earnings_series?: number[];
}

interface ProfileAvatarProps {
  logoPath?: string;
  name: string;
  isActive: boolean;
  theme: any;
}

const ProfileAvatar = ({ logoPath, name, isActive, theme }: ProfileAvatarProps) => {
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    setImgError(false);
  }, [logoPath]);

  const initials = name ? name.substring(0, 2).toUpperCase() : "?";

  if (logoPath && !imgError) {
    const srcUrl = logoPath.startsWith("http")
      ? logoPath
      : `${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(logoPath)}`;
    return (
      <img
        src={srcUrl}
        alt={name}
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          objectFit: "cover",
          border: `2px solid ${isActive ? theme.accentPri : theme.border}`,
        }}
        onError={() => setImgError(true)}
      />
    );
  }

  return (
    <div
      style={{
        width: 44,
        height: 44,
        borderRadius: "50%",
        background: isActive
          ? "linear-gradient(135deg, #BF00FF, #D400FF)"
          : "linear-gradient(135deg, #251442, #120921)",
        border: `2px solid ${isActive ? theme.accentPri : theme.border}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontWeight: 700,
        fontSize: 16,
        fontFamily: "monospace",
      }}
    >
      {initials}
    </div>
  );
};

const LogoPreview = ({ path, opacity, theme }: { path: string; opacity: number; theme: any }) => {
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setHasError(false);
  }, [path]);

  if (hasError) {
    return (
      <div style={{ marginTop: 8, marginBottom: 12, display: "flex", gap: 8, alignItems: "center", color: "#FF5252", fontSize: 11, fontWeight: 600 }}>
        <span>⚠️ Image file not found or invalid path</span>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 8, marginBottom: 12, display: "flex", gap: 12, alignItems: "center" }}>
      <span style={{ fontSize: 11, color: theme.textSec, fontWeight: 600 }}>IMAGE PREVIEW:</span>
      <img
        src={`${getApiBaseUrl()}/api/local-file?path=${encodeURIComponent(path)}`}
        alt="Logo preview"
        style={{
          maxHeight: 60,
          maxWidth: 150,
          objectFit: "contain",
          border: `1px solid ${theme.border}`,
          background: "#020608",
          padding: 4,
          opacity: opacity,
          boxShadow: "0 0 8px rgba(0,0,0,0.5)",
          borderRadius: 2,
        }}
        onError={() => setHasError(true)}
      />
    </div>
  );
};

export function SettingsTab({ onBackendChange }: Props) {
  const [cfg, setCfg] = useState<ConfigData>({});
  const [saved, setSaved] = useState(false);
  const [showGemini, setShowGemini] = useState(false);
  const [showEleven, setShowEleven] = useState(false);
  const [showMoreKeys, setShowMoreKeys] = useState(false);
  const [showOmni, setShowOmni] = useState(false);
  const [showEdgeEl, setShowEdgeEl] = useState(false);
  const [showAiFootageSettings, setShowAiFootageSettings] = useState(false);
  const [showAiProfileSetup, setShowAiProfileSetup] = useState(false);
  const [showAnalyticsChart, setShowAnalyticsChart] = useState(false);
  const [showLogoPresets, setShowLogoPresets] = useState(false);
  const [showVoiceReferences, setShowVoiceReferences] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [envPath, setEnvPath] = useState("");
  const [version, setVersion] = useState("");
  const [ollamaDetail, setOllamaDetail] = useState("");
  const [profiles, setProfiles] = useState<ChromeProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState(0);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editViews, setEditViews] = useState(0);
  const [editSubs, setEditSubs] = useState(0);
  const [editEarnings, setEditEarnings] = useState(0);
  const [editLogoPath, setEditLogoPath] = useState("");
  const [editChannelUrl, setEditChannelUrl] = useState("");
  const [editChannelId, setEditChannelId] = useState("");
  const [editProfilePath, setEditProfilePath] = useState("");
  const [resolvingChannel, setResolvingChannel] = useState(false);
  const [syncingIndex, setSyncingIndex] = useState<number | null>(null);
  const [ytConnected, setYtConnected] = useState<boolean[]>([]);
  const [ytConnectingIndex, setYtConnectingIndex] = useState<number | null>(null);
  const [initialSynced, setInitialSynced] = useState(false);
  const [autoSync, setAutoSync] = useState(true);
  const [nextSyncIn, setNextSyncIn] = useState(60);
  const [selectedMetric, setSelectedMetric] = useState<"views" | "subs" | "earnings">("views");
  const [newProfileName, setNewProfileName] = useState("");

  // Check connection status for all profiles on load
  useEffect(() => {
    if (profiles.length === 0) return;
    const checkAll = async () => {
      const results = await Promise.all(
        profiles.map((_, i) => api.ytAnalyticsStatus(i).then(r => r.connected).catch(() => false))
      );
      setYtConnected(results);
    };
    void checkAll();
  }, [profiles.length]);

  useEffect(() => {
    let intervalId: any = null;
    if (autoSync && profiles.length > 0 && activeProfile < profiles.length && syncingIndex === null) {
      intervalId = setInterval(() => {
        setNextSyncIn((prev) => {
          if (prev <= 1) {
            // Use Analytics API if connected, else fall back to scraper
            const useAnalytics = ytConnected[activeProfile];
            const syncFn = useAnalytics
              ? api.ytAnalyticsSync(activeProfile)
              : api.chromeProfileSync(activeProfile);
            void syncFn.then((res: any) => {
              if (res.ok && res.views !== undefined && res.subs !== undefined && res.earnings !== undefined) {
                setProfiles((prevProfs) => {
                  const nextProfs = [...prevProfs];
                  if (nextProfs[activeProfile]) {
                    nextProfs[activeProfile] = {
                      ...nextProfs[activeProfile],
                      views_28d: res.views,
                      subs_28d: res.subs,
                      earnings_28d: res.earnings,
                      views_series: res.views_series,
                      subs_series: res.subs_series,
                      earnings_series: res.earnings_series,
                      views_growth: res.views_growth,
                      subs_growth: res.subs_growth,
                      earnings_growth: res.earnings_growth,
                    };
                  }
                  return nextProfs;
                });
              }
            }).catch((err) => console.error("Auto sync failed:", err));
            return 60;
          }
          return prev - 1;
        });
      }, 1000);
    } else {
      setNextSyncIn(60);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [autoSync, activeProfile, profiles, syncingIndex, ytConnected]);

  const syncRealStats = async (index: number) => {
    setSyncingIndex(index);
    try {
      // Prefer YouTube Analytics API if connected, else scraper fallback
      const useAnalytics = ytConnected[index];
      const res: any = useAnalytics
        ? await api.ytAnalyticsSync(index)
        : await api.chromeProfileSync(index);

      if (res.ok && res.views !== undefined && res.subs !== undefined && res.earnings !== undefined) {
        setProfiles((prev) => {
          const next = [...prev];
          if (next[index]) {
            next[index] = {
              ...next[index],
              views_28d: res.views,
              subs_28d: res.subs,
              earnings_28d: res.earnings,
              views_series: res.views_series,
              subs_series: res.subs_series,
              earnings_series: res.earnings_series,
              views_growth: res.views_growth,
              subs_growth: res.subs_growth,
              earnings_growth: res.earnings_growth,
            };
          }
          return next;
        });
        const source = useAnalytics ? "YouTube Analytics API" : "YouTube Studio Scraper";
        alert(`✅ Data synced from ${source}!\nViews: ${res.views?.toLocaleString()} | Subs: +${res.subs?.toLocaleString()} | Earnings: $${res.earnings?.toFixed(2)}`);
      } else {
        alert(`❌ Sync failed: ${res.error || "Unknown error."}`);
      }
    } catch (err) {
      alert(`❌ Sync error: ${err}`);
    } finally {
      setSyncingIndex(null);
    }
  };

  const connectGoogleAccount = async (index: number) => {
    setYtConnectingIndex(index);
    try {
      const res = await api.ytAnalyticsConnect(index);
      if (res.ok) {
        setYtConnected((prev) => { const n = [...prev]; n[index] = true; return n; });
        alert(`✅ Google Account connected! Now click "📊 Sync Analytics" to fetch real data.`);
      } else {
        alert(`❌ Connection failed:\n${res.error}`);
      }
    } catch (err) {
      alert(`❌ Could not connect: ${err}`);
    } finally {
      setYtConnectingIndex(null);
    }
  };

  const disconnectGoogleAccount = async (index: number) => {
    if (!confirm(`Disconnect Google Account for "${profiles[index]?.name}"?`)) return;
    try {
      await api.ytAnalyticsDisconnect(index);
      setYtConnected((prev) => { const n = [...prev]; n[index] = false; return n; });
    } catch (err) {
      alert(`Error: ${err}`);
    }
  };

  const browseProfileLogo = async () => {
    if (!window.electronAPI) {
      alert("यह ब्राउज़ फ़ीचर सिर्फ Electron Desktop App में काम करेगा।");
      return;
    }
    try {
      const paths = await window.electronAPI.openFile({
        title: "Select Channel Logo Image",
        filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp"] }],
      });
      if (paths?.[0]) {
        setEditLogoPath(paths[0]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const browseProfilePath = async () => {
    if (!window.electronAPI) {
      alert("यह ब्राउज़ फ़ीचर सिर्फ Electron Desktop App में काम करेगा।");
      return;
    }
    try {
      const path = await window.electronAPI.openDirectory({
        title: "Select Chrome Profile Folder",
      });
      if (path) {
        setEditProfilePath(path);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleAutoFillChannel = async () => {
    if (!editChannelUrl.trim()) {
      alert("कृपया पहले YouTube Channel/Studio URL पेस्ट करें।");
      return;
    }
    setResolvingChannel(true);
    try {
      const res = await api.ytAnalyticsResolveChannel(editChannelUrl.trim());
      if (res.ok && res.channel_id) {
        setEditChannelId(res.channel_id);
        if (res.channel_name) setEditName(res.channel_name);
        if (res.avatar_url) setEditLogoPath(res.avatar_url);
        alert(`✅ Channel resolved successfully!\nName: ${res.channel_name}\nID: ${res.channel_id}`);
      } else {
        alert(`❌ URL resolve नहीं हो पाया: ${res.error || "Unknown error."}`);
      }
    } catch (err) {
      alert(`❌ Error resolving channel URL: ${err}`);
    } finally {
      setResolvingChannel(false);
    }
  };

  const saveProfileChanges = async (index: number) => {
    const updated = [...profiles];
    updated[index] = {
      ...updated[index],
      name: editName,
      views_28d: editViews,
      subs_28d: editSubs,
      earnings_28d: editEarnings,
      logo_path: editLogoPath,
      channel_url: editChannelUrl,
      channel_id: editChannelId,
      path: editProfilePath,
    };
    setProfiles(updated);
    set("pipeline.chrome_profiles", updated);
    setEditingIndex(null);
    
    // Save to configuration immediately
    cfg.pipeline = cfg.pipeline || {};
    (cfg.pipeline as Record<string, unknown>).chrome_profiles = updated;
    await api.patchConfig({ "pipeline.chrome_profiles": updated });
    await api.saveConfig();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const load = useCallback(async () => {
    const [c, info] = await Promise.all([
      api.getConfig(),
      api.systemInfo(),
    ]);
    const tts = ((c.tts || (c.tts = {})) as Record<string, unknown>);
    if (tts.active_voice_index === undefined) {
      tts.active_voice_index = 1;
    }
    if (tts.voice_1_audio === undefined && tts.reference_audio) {
      tts.voice_1_audio = tts.reference_audio;
      tts.voice_1_name = tts.omnivoice_ref_voice_name || "";
      tts.voice_1_transcript = tts.omnivoice_ref_transcript || "";
      tts.voice_1_label = "Voice Preset 1";
    }
    for (const idx of [1, 2, 3]) {
      if (tts[`voice_${idx}_audio`] === undefined) tts[`voice_${idx}_audio`] = "";
      if (tts[`voice_${idx}_name`] === undefined) tts[`voice_${idx}_name`] = "";
      if (tts[`voice_${idx}_transcript`] === undefined) tts[`voice_${idx}_transcript`] = "";
      if (tts[`voice_${idx}_label`] === undefined) tts[`voice_${idx}_label`] = "";
    }

    const doc = ((c.documentary || (c.documentary = {})) as Record<string, unknown>);
    if (doc.active_logo_index === undefined) {
      doc.active_logo_index = 1;
    }
    if (doc.logo_1_path === undefined && doc.logo_path) {
      doc.logo_1_path = doc.logo_path;
      doc.logo_1_position = doc.logo_position || "bottom_right";
      doc.logo_1_scale = doc.logo_scale !== undefined ? doc.logo_scale : 0.15;
      doc.logo_1_margin = doc.logo_margin !== undefined ? doc.logo_margin : 24;
      doc.logo_1_opacity = doc.logo_opacity !== undefined ? doc.logo_opacity : 1.0;
      doc.logo_1_label = "Logo Preset 1";
    }
    for (const idx of [1, 2, 3]) {
      if (doc[`logo_${idx}_path`] === undefined) doc[`logo_${idx}_path`] = "";
      if (doc[`logo_${idx}_position`] === undefined) doc[`logo_${idx}_position`] = "bottom_right";
      if (doc[`logo_${idx}_scale`] === undefined) doc[`logo_${idx}_scale`] = 0.15;
      if (doc[`logo_${idx}_margin`] === undefined) doc[`logo_${idx}_margin`] = 24;
      if (doc[`logo_${idx}_opacity`] === undefined) doc[`logo_${idx}_opacity`] = 1.0;
      if (doc[`logo_${idx}_label`] === undefined) doc[`logo_${idx}_label`] = "";
    }

    setCfg(c);
    setDeviceName(info.device_name);
    setEnvPath(info.env_local_path);
    setVersion(info.version);
    const profs = (getNested(c, "pipeline.chrome_profiles", []) as ChromeProfile[]) || [];
    const initializedProfs = Array.isArray(profs) ? profs : [];
    setProfiles(initializedProfs);
    setActiveProfile(Number(getNested(c, "pipeline.active_profile_index", 0)));
    if (c.pipeline) {
      (c.pipeline as Record<string, unknown>).chrome_profiles = initializedProfs;
    }
    try {
      const oll = await api.probeOllama();
      setOllamaDetail(oll.detail);
    } catch {
      setOllamaDetail("");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (profiles.length > 0 && !initialSynced) {
      setInitialSynced(true);
      void api.chromeProfileSync(activeProfile).then((res) => {
        if (res.ok && res.views !== undefined && res.subs !== undefined && res.earnings !== undefined) {
          setProfiles((prev) => {
            const next = [...prev];
            if (next[activeProfile]) {
              next[activeProfile] = {
                ...next[activeProfile],
                views_28d: res.views,
                subs_28d: res.subs,
                earnings_28d: res.earnings,
              };
            }
            return next;
          });
        }
      }).catch(err => console.error("Initial sync failed:", err));
    }
  }, [profiles, initialSynced, activeProfile]);

  const set = (path: string, value: unknown) => {
    setCfg((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as ConfigData;
      const parts = path.split(".");
      let cur = next;
      for (let i = 0; i < parts.length - 1; i++) {
        if (!cur[parts[i]]) cur[parts[i]] = {};
        cur = cur[parts[i]] as ConfigData;
      }
      let cleanVal = value;
      if (typeof value === "string") {
        cleanVal = value.replace(/^['"]|['"]$/g, "");
      }
      cur[parts[parts.length - 1]] = cleanVal;
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

  const browseFile = async (title: string, extensions: string[], configKey: string) => {
    if (!window.electronAPI) {
      alert("यह ब्राउज़ फ़ीचर सिर्फ Electron Desktop App में काम करेगा। अगर आप सामान्य Chrome/Edge ब्राउज़र में हैं, तो सीधे फ़ाइल का पाथ कॉपी करके इनपुट बॉक्स में पेस्ट करें।");
      return;
    }
    try {
      const paths = await window.electronAPI.openFile({
        title,
        filters: [{ name: "Files", extensions }],
      });
      if (paths?.[0]) set(configKey, paths[0]);
    } catch (err) {
      console.error(err);
    }
  };

  const browseDirectory = async (title: string, configKey: string) => {
    if (!window.electronAPI) {
      alert("यह ब्राउज़ फ़ीचर सिर्फ Electron Desktop App में काम करेगा। अगर आप सामान्य Chrome/Edge ब्राउज़र में हैं, तो सीधे फ़ोल्डर का पाथ कॉपी करके इनivat बॉक्स में पेस्ट करें।");
      return;
    }
    try {
      const path = await window.electronAPI.openDirectory({ title });
      if (path) set(configKey, path);
    } catch (err) {
      console.error(err);
    }
  };

  const selectActiveVoice = (voiceIndex: 1 | 2 | 3) => {
    set("tts.active_voice_index", voiceIndex);
    
    const audioVal = String(g(`tts.voice_${voiceIndex}_audio`) || (voiceIndex === 1 ? g("tts.reference_audio") : ""));
    const nameVal = String(g(`tts.voice_${voiceIndex}_name`) || (voiceIndex === 1 ? g("tts.omnivoice_ref_voice_name") : ""));
    const transcriptVal = String(g(`tts.voice_${voiceIndex}_transcript`) || (voiceIndex === 1 ? g("tts.omnivoice_ref_transcript") : ""));
    
    set("tts.reference_audio", audioVal);
    set("tts.omnivoice_ref_voice_name", nameVal);
    set("tts.omnivoice_ref_transcript", transcriptVal);
  };

  const setVoiceField = (voiceIndex: 1 | 2 | 3, field: "audio" | "name" | "transcript" | "label", value: string) => {
    set(`tts.voice_${voiceIndex}_${field}`, value);
    
    const activeIndex = Number(g("tts.active_voice_index", 1));
    if (activeIndex === voiceIndex && field !== "label") {
      const mainKey = field === "audio" 
        ? "tts.reference_audio" 
        : field === "name" 
          ? "tts.omnivoice_ref_voice_name" 
          : "tts.omnivoice_ref_transcript";
      set(mainKey, value);
    }
  };

  const browseVoiceAudio = async (voiceIndex: 1 | 2 | 3) => {
    if (!window.electronAPI) {
      alert("यह ब्राउज़ फ़ीचर सिर्फ Electron Desktop App में काम करेगा। अगर आप सामान्य Chrome/Edge ब्राउज़र में हैं, तो सीधे फ़ाइल का पाथ कॉपी करके इनपुट बॉक्स में पेस्ट करें।");
      return;
    }
    try {
      const paths = await window.electronAPI.openFile({
        title: `Select Reference Audio WAV for Voice ${voiceIndex}`,
        filters: [{ name: "Audio Files", extensions: ["wav", "mp3", "m4a", "ogg"] }],
      });
      if (paths?.[0]) {
        setVoiceField(voiceIndex, "audio", paths[0]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const selectActiveLogo = (logoIndex: 1 | 2 | 3) => {
    set("documentary.active_logo_index", logoIndex);
    
    const pathVal = String(g(`documentary.logo_${logoIndex}_path`) || (logoIndex === 1 ? g("documentary.logo_path") : ""));
    const posVal = String(g(`documentary.logo_${logoIndex}_position`) || (logoIndex === 1 ? g("documentary.logo_position") : "bottom_right"));
    const scaleVal = Number(g(`documentary.logo_${logoIndex}_scale`) !== "" ? g(`documentary.logo_${logoIndex}_scale`) : (logoIndex === 1 ? g("documentary.logo_scale") : 0.15));
    const marginVal = Number(g(`documentary.logo_${logoIndex}_margin`) !== "" ? g(`documentary.logo_${logoIndex}_margin`) : (logoIndex === 1 ? g("documentary.logo_margin") : 24));
    const opacityVal = Number(g(`documentary.logo_${logoIndex}_opacity`) !== "" ? g(`documentary.logo_${logoIndex}_opacity`) : (logoIndex === 1 ? g("documentary.logo_opacity") : 1.0));
    
    set("documentary.logo_path", pathVal);
    set("documentary.logo_position", posVal);
    set("documentary.logo_scale", scaleVal);
    set("documentary.logo_margin", marginVal);
    set("documentary.logo_opacity", opacityVal);
  };

  const setLogoField = (logoIndex: 1 | 2 | 3, field: "path" | "position" | "scale" | "margin" | "opacity" | "label", value: unknown) => {
    set(`documentary.logo_${logoIndex}_${field}`, value);
    
    const activeIndex = Number(g("documentary.active_logo_index", 1));
    if (activeIndex === logoIndex && field !== "label") {
      const mainKey = `documentary.logo_${field}`;
      set(mainKey, value);
    }
  };

  const browseLogoFile = async (logoIndex: 1 | 2 | 3) => {
    if (!window.electronAPI) {
      alert("यह ब्राउज़ फ़ीचर सिर्फ Electron Desktop App में काम करेगा। अगर आप सामान्य Chrome/Edge ब्राउज़र में हैं, तो सीधे फ़ाइल का पाथ कॉपी करके इनपुट बॉक्स में पेस्ट करें।");
      return;
    }
    try {
      const paths = await window.electronAPI.openFile({
        title: `Select Logo Watermark Image for Logo ${logoIndex}`,
        filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp"] }],
      });
      if (paths?.[0]) {
        setLogoField(logoIndex, "path", paths[0]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const footageSource = String(g("documentary.footage_source", "stock"));
  const isAiFootage = footageSource === "meta_ai" || footageSource === "grok";

  return (
    <div style={styles.scroll}>
      <Section title="YOUTUBE CHANNELS OVERVIEW (LAST 28 DAYS)">
        {profiles.length > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, background: "rgba(191, 0, 255, 0.04)", border: `1px solid ${theme.border}`, padding: "8px 12px", borderRadius: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                id="auto-sync-toggle"
                checked={autoSync}
                onChange={(e) => setAutoSync(e.target.checked)}
                style={{ accentColor: theme.accentPri, cursor: "pointer", width: 16, height: 16 }}
              />
              <label htmlFor="auto-sync-toggle" style={{ fontSize: 12, fontWeight: 700, color: theme.textPri, cursor: "pointer", userSelect: "none", fontFamily: "monospace" }}>
                🔄 ENABLE AUTO-SYNC (EVERY 60s)
              </label>
            </div>
            {autoSync && (
              <span style={{ fontSize: 11, color: theme.accentSec, fontWeight: 700, fontFamily: "monospace" }}>
                NEXT REFRESH IN: <span style={{ color: "#FFB800" }}>{nextSyncIn}s</span>
              </span>
            )}
          </div>
        )}
        {profiles.length === 0 ? (
          <div style={{ padding: 16, textAlign: "center", color: theme.textSec }}>
            No YouTube channels configured yet. Create a profile below under Core Parameters.
          </div>
        ) : (
          <div style={styles.channelsGrid}>
            {profiles.map((p, i) => {
              const isActive = activeProfile === i;
              const isEditing = editingIndex === i;
              
              if (isEditing) {
                return (
                  <div key={i} style={{ ...styles.channelCard, borderColor: theme.accentPri }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: theme.accentPri, marginBottom: 12 }}>
                      ⚙️ EDITING CHANNEL: {p.name}
                    </div>
                    
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, color: theme.textSec, width: 90 }}>Channel URL:</span>
                        <input
                          value={editChannelUrl}
                          onChange={(e) => setEditChannelUrl(e.target.value.replace(/^['"]|['"]$/g, ""))}
                          placeholder="e.g., https://studio.youtube.com/channel/UC..."
                          style={{ flex: 1, padding: "6px 8px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri }}
                        />
                        <button
                          type="button"
                          style={{
                            ...styles.actionBtn,
                            background: resolvingChannel ? "#444" : theme.accentPri,
                            color: "#fff",
                            cursor: resolvingChannel ? "not-allowed" : "pointer",
                            margin: 0,
                            padding: "6px 10px",
                          }}
                          onClick={handleAutoFillChannel}
                          disabled={resolvingChannel}
                        >
                          {resolvingChannel ? "⏳ FETCHING..." : "🔍 AUTO-FILL"}
                        </button>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, color: theme.textSec, width: 90 }}>Channel ID:</span>
                        <input
                          value={editChannelId}
                          onChange={(e) => setEditChannelId(e.target.value)}
                          placeholder="Resolved automatically"
                          style={{ flex: 1, padding: "6px 8px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri }}
                        />
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, color: theme.textSec, width: 90 }}>Chrome Path:</span>
                        <input
                          value={editProfilePath}
                          onChange={(e) => setEditProfilePath(e.target.value.replace(/^['"]|['"]$/g, ""))}
                          placeholder="e.g., C:/ChromeProfiles/GhostCreator_..."
                          style={{ flex: 1, padding: "6px 8px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri }}
                        />
                        <button type="button" style={styles.actionBtn} onClick={browseProfilePath}>BROWSE</button>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, color: theme.textSec, width: 90 }}>Name:</span>
                        <input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          style={{ flex: 1, padding: "6px 8px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri }}
                        />
                      </div>
                      
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 11, color: theme.textSec, width: 90 }}>Logo Path / URL:</span>
                        <input
                          value={editLogoPath}
                          onChange={(e) => setEditLogoPath(e.target.value.replace(/^['"]|['"]$/g, ""))}
                          style={{ flex: 1, padding: "6px 8px", background: theme.bgSec, border: `1px solid ${theme.border}`, color: theme.textPri }}
                        />
                        <button type="button" style={styles.actionBtn} onClick={browseProfileLogo}>BROWSE</button>
                      </div>

                      {editLogoPath && (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4, paddingLeft: 98 }}>
                          <span style={{ fontSize: 10, color: theme.textSec, fontWeight: 600 }}>PREVIEW:</span>
                          <ProfileAvatar logoPath={editLogoPath} name={editName} isActive={true} theme={theme} />
                        </div>
                      )}

                      {/* Views, Subscribers, and Earnings are fetched in real-time and cannot be edited manually */}
                      
                      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                        <button
                          type="button"
                          style={{ ...styles.actionBtn, background: theme.accentPri, color: "#fff", flex: 1, margin: 0 }}
                          onClick={() => saveProfileChanges(i)}
                        >
                          SAVE
                        </button>
                        <button
                          type="button"
                          style={{ ...styles.actionBtn, flex: 1, margin: 0 }}
                          onClick={() => setEditingIndex(null)}
                        >
                          CANCEL
                        </button>
                      </div>
                    </div>
                  </div>
                );
              }
              
              const formatNum = (num: number) => {
                if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
                if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
                return num.toString();
              };

              return (
                <div
                  key={i}
                  style={{
                    ...styles.channelCard,
                    ...(isActive ? styles.channelCardActive : {}),
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                    <ProfileAvatar logoPath={p.logo_path} name={p.name} isActive={isActive} theme={theme} />
                    
                    <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: theme.textPri }}>{p.name.toUpperCase()}</span>
                      <span style={{ fontSize: 10, color: theme.textHint }}>Profile: {p.profile_name}</span>
                    </div>

                    {isActive ? (
                      <span style={styles.activeBadge}>● ACTIVE</span>
                    ) : (
                      <button
                        type="button"
                        style={styles.selectBtn}
                        onClick={async () => {
                          setActiveProfile(i);
                          set("pipeline.active_profile_index", i);
                          await api.patchConfig({ "pipeline.active_profile_index": i });
                          await api.saveConfig();
                        }}
                      >
                        SELECT
                      </button>
                    )}
                  </div>

                  <div style={{ borderBottom: `1px solid rgba(191, 0, 255, 0.1)`, marginBottom: 12 }} />

                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
                    <div
                      style={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        cursor: isActive ? "pointer" : "default",
                        padding: "6px 4px",
                        borderRadius: 4,
                        background: isActive && selectedMetric === "views" ? "rgba(74, 222, 128, 0.08)" : "transparent",
                        border: isActive && selectedMetric === "views" ? `1px solid rgba(74, 222, 128, 0.2)` : "1px solid transparent",
                        transition: "all 0.2s"
                      }}
                      onClick={() => isActive && setSelectedMetric("views")}
                    >
                      <div style={{ fontSize: 9, color: theme.textSec, fontWeight: 600 }}>VIEWS</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPri, margin: "2px 0" }}>
                        {p.views_28d !== undefined && p.views_28d !== null ? `+${formatNum(p.views_28d)}` : "—"}
                      </div>
                      <div style={{ fontSize: 9, color: theme.accentGrn, fontWeight: 600, marginBottom: 4 }}>
                        {p.views_28d !== undefined && p.views_28d !== null && p.views_growth ? p.views_growth : "—"}
                      </div>
                      <Sparkline points={p.views_series} color={theme.accentGrn} />
                    </div>
                    
                    <div
                      style={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        cursor: isActive ? "pointer" : "default",
                        padding: "6px 4px",
                        borderRadius: 4,
                        background: isActive && selectedMetric === "subs" ? "rgba(191, 0, 255, 0.08)" : "transparent",
                        border: isActive && selectedMetric === "subs" ? `1px solid rgba(191, 0, 255, 0.2)` : "1px solid transparent",
                        transition: "all 0.2s"
                      }}
                      onClick={() => isActive && setSelectedMetric("subs")}
                    >
                      <div style={{ fontSize: 9, color: theme.textSec, fontWeight: 600 }}>SUBSCRIBERS</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: theme.textPri, margin: "2px 0" }}>
                        {p.subs_28d !== undefined && p.subs_28d !== null ? `+${formatNum(p.subs_28d)}` : "—"}
                      </div>
                      <div style={{ fontSize: 9, color: theme.accentGrn, fontWeight: 600, marginBottom: 4 }}>
                        {p.subs_28d !== undefined && p.subs_28d !== null && p.subs_growth ? p.subs_growth : "—"}
                      </div>
                      <Sparkline points={p.subs_series} color={theme.accentPri} />
                    </div>

                    <div
                      style={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        cursor: isActive ? "pointer" : "default",
                        padding: "6px 4px",
                        borderRadius: 4,
                        background: isActive && selectedMetric === "earnings" ? "rgba(255, 184, 0, 0.08)" : "transparent",
                        border: isActive && selectedMetric === "earnings" ? `1px solid rgba(255, 184, 0, 0.2)` : "1px solid transparent",
                        transition: "all 0.2s"
                      }}
                      onClick={() => isActive && setSelectedMetric("earnings")}
                    >
                      <div style={{ fontSize: 9, color: theme.textSec, fontWeight: 600 }}>EARNINGS</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: theme.accentWarn, margin: "2px 0" }}>
                        {p.earnings_28d !== undefined && p.earnings_28d !== null ? `$${p.earnings_28d.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
                      </div>
                      <div style={{ fontSize: 9, color: theme.accentGrn, fontWeight: 600, marginBottom: 4 }}>
                        {p.earnings_28d !== undefined && p.earnings_28d !== null && p.earnings_growth ? p.earnings_growth : "—"}
                      </div>
                      <Sparkline points={p.earnings_series} color="#FFB800" />
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                    {/* Google Account Connection Status */}
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "5px 8px",
                      background: ytConnected[i] ? "rgba(0, 204, 102, 0.08)" : "rgba(255, 184, 0, 0.08)",
                      border: `1px solid ${ytConnected[i] ? theme.accentGrn : theme.accentWarn}`,
                      borderRadius: 3,
                    }}>
                      <span style={{ fontSize: 11 }}>{ytConnected[i] ? "🟢" : "🔴"}</span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: ytConnected[i] ? theme.accentGrn : theme.accentWarn, flex: 1 }}>
                        {ytConnected[i] ? "YouTube Analytics API Connected" : "Google Account Not Connected"}
                      </span>
                      {ytConnected[i] ? (
                        <button
                          type="button"
                          style={{ fontSize: 9, color: "#ef4444", background: "none", border: "none", cursor: "pointer", padding: "2px 4px", fontWeight: 700 }}
                          onClick={() => disconnectGoogleAccount(i)}
                          title="Disconnect Google Account"
                        >
                          ✕ Disconnect
                        </button>
                      ) : (
                        <button
                          type="button"
                          style={{
                            fontSize: 10,
                            color: "#fff",
                            background: "linear-gradient(135deg, #4285F4, #34A853)",
                            border: "none",
                            padding: "3px 8px",
                            borderRadius: 2,
                            cursor: ytConnectingIndex !== null ? "not-allowed" : "pointer",
                            fontWeight: 700,
                            opacity: ytConnectingIndex !== null ? 0.6 : 1,
                          }}
                          onClick={() => connectGoogleAccount(i)}
                          disabled={ytConnectingIndex !== null}
                          title="Connect Google Account to use YouTube Analytics API"
                        >
                          {ytConnectingIndex === i ? "⏳ Connecting..." : "🔑 Connect Google"}
                        </button>
                      )}
                    </div>

                    {/* Sync + Edit buttons */}
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        type="button"
                        style={{
                          flex: 1,
                          fontSize: 10,
                          color: ytConnected[i] ? theme.accentGrn : theme.accentPri,
                          background: ytConnected[i] ? "rgba(0, 204, 102, 0.08)" : "rgba(191, 0, 255, 0.08)",
                          border: `1px solid ${ytConnected[i] ? theme.accentGrn : theme.accentPri}`,
                          padding: "5px 8px",
                          borderRadius: 2,
                          cursor: syncingIndex !== null ? "not-allowed" : "pointer",
                          fontWeight: 700,
                          opacity: syncingIndex !== null ? 0.6 : 1,
                          transition: "all 0.2s",
                        }}
                        onClick={() => syncRealStats(i)}
                        disabled={syncingIndex !== null}
                        title={ytConnected[i] ? "Sync from YouTube Analytics API" : "Sync from YouTube Studio scraper"}
                      >
                        {syncingIndex === i ? "⏳ Syncing..." : (ytConnected[i] ? "📊 Sync Analytics" : "🔄 Sync Studio")}
                      </button>
                      <button
                        type="button"
                        style={{ ...styles.cardEditBtn, flex: 1, margin: 0 }}
                        onClick={() => {
                          setEditingIndex(i);
                          setEditName(p.name);
                          setEditViews(p.views_28d || 0);
                          setEditSubs(p.subs_28d || 0);
                          setEditEarnings(p.earnings_28d || 0);
                          setEditLogoPath(p.logo_path || "");
                          setEditChannelUrl(p.channel_url || "");
                          setEditChannelId(p.channel_id || "");
                          setEditProfilePath(p.path || "");
                        }}
                      >
                        ⚙️ Setup Channel
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {profiles.length > 0 && activeProfile < profiles.length && (
          <>
            <button
              type="button"
              style={{ ...styles.foldLink, marginTop: 12 }}
              onClick={() => setShowAnalyticsChart(!showAnalyticsChart)}
            >
              {showAnalyticsChart ? "▼" : "▶"} 28-day analytics chart — {profiles[activeProfile].name}
            </button>
            {showAnalyticsChart && (
              <AnalyticsChart
                points={
                  selectedMetric === "views"
                    ? profiles[activeProfile].views_series
                    : selectedMetric === "subs"
                    ? profiles[activeProfile].subs_series
                    : profiles[activeProfile].earnings_series
                }
                metricName={selectedMetric}
                color={
                  selectedMetric === "views"
                    ? theme.accentGrn
                    : selectedMetric === "subs"
                    ? theme.accentPri
                    : theme.accentWarn
                }
                channelName={profiles[activeProfile].name}
              />
            )}
          </>
        )}
      </Section>

      <Section title="Quick Start">
        <p style={styles.hint}>1. Add Gemini API key → 2. Pick TTS backend → 3. Set output folder → 4. Run documentary → 5. Upload</p>
      </Section>

      <Section title="API KEYS">
        <KeyField label="Gemini API Key (required)" value={String(g("api_keys.gemini"))} onChange={(v) => set("api_keys.gemini", v)} show={showGemini} onToggleShow={() => setShowGemini(!showGemini)} />
        <button type="button" style={styles.foldLink} onClick={() => setShowMoreKeys(!showMoreKeys)}>
          {showMoreKeys ? "▼" : "▶"} More API keys
        </button>
        {showMoreKeys && (
          <>
            <KeyField label="ElevenLabs API Key" value={String(g("api_keys.elevenlabs"))} onChange={(v) => set("api_keys.elevenlabs", v)} show={showEleven} onToggleShow={() => setShowEleven(!showEleven)} />
            <KeyField label="Pexels API Key" value={String(g("api_keys.pexels"))} onChange={(v) => set("api_keys.pexels", v)} show={false} onToggleShow={() => {}} />
          </>
        )}
      </Section>

      <Section title="FOOTAGE SOURCE">
        <p style={styles.hint}>
          Applies to all pipeline modes (AI Shorts, Documentary, My Script). Stock B-roll (Pexels + YouTube),
          Meta AI / Grok browser clips, or Gemini AI Images slideshow. Uses one shared Chrome profile for Meta AI and Grok.
        </p>
        <Row label="Source">
          <select
            value={footageSource}
            onChange={(e) => set("documentary.footage_source", e.target.value)}
            style={{ flex: 1 }}
          >
            <option value="stock">Stock — Pexels + YouTube (yt-dlp)</option>
            <option value="meta_ai">Meta AI — browser automation</option>
            <option value="grok">Grok — browser automation</option>
            <option value="ai_images">AI Images — Gemini slideshow (no stock footage)</option>
          </select>
        </Row>

        <button
          type="button"
          style={styles.foldLink}
          onClick={() => setShowAiProfileSetup(!showAiProfileSetup)}
        >
          {showAiProfileSetup ? "▼" : "▶"} Meta & Grok profile setup (one-time login)
        </button>
        {showAiProfileSetup && (
          <div style={styles.subPanel}>
            <p style={{ ...styles.cardHint, marginBottom: 10 }}>
              Same Chrome profile for Meta AI and Grok. Run setup once, log in on both tabs, then close Chrome.
            </p>
            <Row label="Chrome profile path">
              <div style={{ display: "flex", gap: 8, flex: 1 }}>
                <input
                  value={String(g("meta_ai.chrome_profile_path", ""))}
                  onChange={(e) => set("meta_ai.chrome_profile_path", e.target.value)}
                  placeholder="C:\ChromeProfiles\GhostCreator_MetaAI"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  style={styles.actionBtn}
                  onClick={() => browseDirectory("Select AI Browser Chrome Profile Folder", "meta_ai.chrome_profile_path")}
                >
                  BROWSE
                </button>
              </div>
            </Row>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                style={{ ...styles.actionBtn, background: theme.accentPri, color: theme.textPri, borderColor: theme.accentPri }}
                onClick={async () => {
                  const res = await api.metaAiSetupProfile();
                  alert(res.message || (res.ok ? "Profile setup done" : "Setup failed"));
                  if (res.profile_path) set("meta_ai.chrome_profile_path", res.profile_path);
                  await save();
                }}
              >
                SETUP META + GROK PROFILE
              </button>
              <button
                type="button"
                style={styles.actionBtn}
                onClick={async () => {
                  const res = await api.metaAiTestLogin();
                  alert(res.message || (res.ok ? "Meta logged in" : "Meta not logged in"));
                }}
              >
                TEST META LOGIN
              </button>
              <button
                type="button"
                style={styles.actionBtn}
                onClick={async () => {
                  const res = await api.grokAiTestLogin();
                  alert(res.message || (res.ok ? "Grok logged in" : "Grok not logged in"));
                }}
              >
                TEST GROK LOGIN
              </button>
            </div>
            <div style={{ ...styles.cardHint, marginTop: 8 }}>
              Setup opens two tabs: meta.ai and grok.com. Grok video may need SuperGrok subscription.
            </div>
          </div>
        )}

        {isAiFootage && (
          <>
            <button
              type="button"
              style={styles.foldLink}
              onClick={() => setShowAiFootageSettings(!showAiFootageSettings)}
            >
              {showAiFootageSettings ? "▼" : "▶"} Advanced AI settings ({footageSource === "grok" ? "Grok" : "Meta AI"})
            </button>
            {showAiFootageSettings && (
          <div style={styles.subPanel}>
            {footageSource === "meta_ai" && (
              <Row label="Meta AI URL">
                <input
                  value={String(g("meta_ai.base_url", "https://www.meta.ai/"))}
                  onChange={(e) => set("meta_ai.base_url", e.target.value)}
                  style={{ flex: 1 }}
                />
              </Row>
            )}
            {footageSource === "grok" && (
              <Row label="Grok URL">
                <input
                  value={String(g("grok.base_url", "https://grok.com/imagine"))}
                  onChange={(e) => set("grok.base_url", e.target.value)}
                  style={{ flex: 1 }}
                />
              </Row>
            )}
            <label style={styles.checkRow}>
              <input
                type="checkbox"
                checked={Boolean(
                  footageSource === "grok"
                    ? g("grok.headless", g("meta_ai.headless", false))
                    : g("meta_ai.headless", false)
                )}
                onChange={(e) => {
                  const key = footageSource === "grok" ? "grok.headless" : "meta_ai.headless";
                  set(key, e.target.checked);
                }}
              />
              Headless browser (not recommended — login/captcha often fails)
            </label>
            <label style={{ ...styles.checkRow, marginTop: 8 }}>
              <input
                type="checkbox"
                checked={
                  (footageSource === "grok"
                    ? g("grok.fallback_to_stock", true)
                    : g("meta_ai.fallback_to_stock", true)) !== false &&
                  (footageSource === "grok"
                    ? g("grok.fallback_to_stock", true)
                    : g("meta_ai.fallback_to_stock", true)) !== 0
                }
                onChange={(e) => {
                  const key = footageSource === "grok" ? "grok.fallback_to_stock" : "meta_ai.fallback_to_stock";
                  set(key, e.target.checked);
                }}
              />
              Fallback to stock footage if AI clip fails
            </label>
            <Row label="Timeout per clip (ms)">
              <input
                type="number"
                min={60000}
                step={60000}
                value={Number(
                  footageSource === "grok"
                    ? g("grok.generation_timeout_ms", 600000)
                    : g("meta_ai.generation_timeout_ms", 600000)
                )}
                onChange={(e) => {
                  const key =
                    footageSource === "grok" ? "grok.generation_timeout_ms" : "meta_ai.generation_timeout_ms";
                  set(key, parseInt(e.target.value, 10) || 600000);
                }}
                style={{ width: 140 }}
              />
            </Row>
            <Row label="Delay between clips (sec)">
              <input
                type="number"
                min={0}
                step={1}
                value={Number(
                  footageSource === "grok"
                    ? g("grok.clip_delay_sec", 5)
                    : g("meta_ai.clip_delay_sec", 5)
                )}
                onChange={(e) => {
                  const key = footageSource === "grok" ? "grok.clip_delay_sec" : "meta_ai.clip_delay_sec";
                  set(key, parseFloat(e.target.value) || 5);
                }}
                style={{ width: 80 }}
              />
            </Row>
          </div>
            )}
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
        {showOmni && (
          <div style={styles.subPanel}>
            <Row label="Server path (.bat)">
              <div style={{ display: "flex", gap: 8, flex: 1 }}>
                <input value={String(g("tts.omnivoice_server_path", ""))} onChange={(e) => set("tts.omnivoice_server_path", e.target.value)} style={{ flex: 1 }} />
                <button type="button" style={styles.actionBtn} onClick={() => browseFile("Select OmniVoice Server Start Script (.bat)", ["bat", "cmd", "sh", "exe"], "tts.omnivoice_server_path")}>BROWSE</button>
              </div>
            </Row>
            <Row label="Mode">
              <select value={String(g("tts.omnivoice_mode", "clone"))} onChange={(e) => set("tts.omnivoice_mode", e.target.value)}>
                <option value="clone">Voice Cloning</option>
                <option value="design">Sound Design</option>
              </select>
            </Row>
            <Row label="Model ID">
              <input value={String(g("tts.omnivoice_model_id", "k2-fsa/OmniVoice"))} onChange={(e) => set("tts.omnivoice_model_id", e.target.value)} style={{ flex: 1 }} />
            </Row>

            {g("tts.omnivoice_mode", "clone") === "clone" && (
              <div style={{ marginTop: 16 }}>
                <button
                  type="button"
                  style={styles.foldLink}
                  onClick={() => setShowVoiceReferences(!showVoiceReferences)}
                >
                  {showVoiceReferences ? "▼" : "▶"} Voice clone references (3 slots)
                </button>
                {showVoiceReferences && ([1, 2, 3] as const).map((idx) => {
                  const isActive = Number(g("tts.active_voice_index", 1)) === idx;
                  return (
                    <div key={idx} style={styles.voiceCard}>
                      <div style={styles.voiceCardHeader}>
                        <div style={{ display: "flex", alignItems: "center" }}>
                          <span style={styles.voiceCardNumber}>{idx}</span>
                          <span style={styles.voiceCardTitle}>VOICE REFERENCE {idx}</span>
                        </div>
                        <button
                          type="button"
                          style={{
                            ...styles.toggleBtn,
                            ...(isActive ? styles.toggleBtnActive : styles.toggleBtnInactive),
                          }}
                          onClick={() => selectActiveVoice(idx)}
                        >
                          {isActive ? "● ACTIVE (ON)" : "○ INACTIVE (OFF)"}
                        </button>
                      </div>
                      <Row label="Voice Preset Name">
                        <input
                          value={String(g(`tts.voice_${idx}_label`, ""))}
                          onChange={(e) => setVoiceField(idx, "label", e.target.value)}
                          style={{ flex: 1 }}
                          placeholder={`Voice ${idx} Label (e.g. Channel A Voice)`}
                        />
                      </Row>
                      
                      <Row label="Reference audio (.wav)">
                        <div style={{ display: "flex", gap: 8, flex: 1 }}>
                          <input
                            value={String(g(`tts.voice_${idx}_audio`, ""))}
                            onChange={(e) => setVoiceField(idx, "audio", e.target.value)}
                            style={{ flex: 1 }}
                            placeholder="Select reference WAV path"
                          />
                          <button
                            type="button"
                            style={styles.actionBtn}
                            onClick={() => browseVoiceAudio(idx)}
                          >
                            BROWSE
                          </button>
                        </div>
                      </Row>
                      
                      <Row label="Ref voice name">
                        <input
                          value={String(g(`tts.voice_${idx}_name`, ""))}
                          onChange={(e) => setVoiceField(idx, "name", e.target.value)}
                          style={{ flex: 1 }}
                          placeholder="e.g. voice_1"
                        />
                      </Row>
                      
                      <Row label="Ref transcript">
                        <input
                          value={String(g(`tts.voice_${idx}_transcript`, ""))}
                          onChange={(e) => setVoiceField(idx, "transcript", e.target.value)}
                          style={{ flex: 1 }}
                          placeholder="Transcript of the reference WAV"
                        />
                      </Row>
                    </div>
                  );
                })}
              </div>
            )}
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
        <div style={styles.runBehaviorGrid}>
          {/* Card 1: Pipeline Behavior */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>PIPELINE BEHAVIOR</div>
            <label style={styles.checkRow}>
              <input type="checkbox" checked={Boolean(g("script_review_enabled", true))} onChange={(e) => set("script_review_enabled", e.target.checked)} />
              Pause for script review
            </label>
            <div style={styles.cardHint}>Uncheck for fully automated / unattended runs</div>
            <label style={{ ...styles.checkRow, marginTop: 8 }}>
              <input type="checkbox" checked={g("pipeline_mode", "normal") === "editor"} onChange={(e) => set("pipeline_mode", e.target.checked ? "editor" : "normal")} />
              Pause for Ghost Editor (before assembly)
            </label>
            <div style={styles.cardHint}>Opens Ghost Editor after downloads so you can trim clips before the final render</div>
          </div>

          {/* Card 2: Narration Language */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>NARRATION LANGUAGE</div>
            <select value={String(g("pipeline.language", "hi"))} onChange={(e) => set("pipeline.language", e.target.value)} style={{ width: "100%" }}>
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            <div style={styles.cardHint}>Script + voiceover isi language mein generate hoga</div>
          </div>

          {/* Card 3: Output Folder */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>OUTPUT FOLDER</div>
            <div style={{ display: "flex", gap: 8 }}>
              <input value={String(g("pipeline.output_folder", "output"))} onChange={(e) => set("pipeline.output_folder", e.target.value)} style={{ flex: 1 }} />
              <button type="button" style={{ ...styles.actionBtn, margin: 0, padding: "6px 10px" }} onClick={() => browseDirectory("Select Output Folder", "pipeline.output_folder")}>...</button>
            </div>
            <div style={styles.cardHint}>Relative (e.g. output) or full path — folder created automatically</div>
          </div>

          {/* Card 4: YouTube Upload */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>YOUTUBE UPLOAD</div>
            <label style={styles.checkRow}>
              <input type="checkbox" checked={Boolean(g("pipeline.upload_enabled", true))} onChange={(e) => set("pipeline.upload_enabled", e.target.checked)} />
              Enable YouTube upload after render
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
              <span style={{ fontSize: 11, color: theme.textSec }}>Mode:</span>
              <select value={String(g("pipeline.upload_mode", "unlisted"))} onChange={(e) => set("pipeline.upload_mode", e.target.value)} style={{ flex: 1 }}>
                {UPLOAD_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div style={styles.cardHint}>unlisted = link-only | public = all | private = only you | draft = save only</div>
          </div>

          {/* Card 5: AI Script Provider */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>AI SCRIPT PROVIDER</div>
            <div style={{ display: "flex", gap: 4 }}>
              {SCRIPT_PROVIDERS.map((p) => (
                <button key={p} type="button" style={{ ...styles.segBtn, ...(g("script_provider") === p ? styles.segActive : {}), flex: 1 }} onClick={() => set("script_provider", p)}>
                  {p.toUpperCase()}
                </button>
              ))}
            </div>
            {g("script_provider") === "gemini" && (
              <>
                {g("api_keys.gemini") ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: theme.accentGrn }}>
                    <span style={{ fontSize: 14 }}>●</span> Key configured
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: theme.accentRed }}>
                    <span style={{ fontSize: 14 }}>●</span> Not found
                  </div>
                )}
                <select value={String(g("gemini_model", "gemini-3.1-flash-lite"))} onChange={(e) => set("gemini_model", e.target.value)} style={{ width: "100%" }}>
                  {GEMINI_MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </>
            )}
            {g("script_provider") === "groq" && (
              <>
                {g("groq_api_key") ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: theme.accentGrn }}>
                    <span style={{ fontSize: 14 }}>●</span> Groq key configured · ⚡ Ultra-fast inference
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: theme.accentRed }}>
                    <span style={{ fontSize: 14 }}>●</span> Groq API key not set
                  </div>
                )}
                <input
                  type="password"
                  value={String(g("groq_api_key", ""))}
                  onChange={(e) => set("groq_api_key", e.target.value)}
                  placeholder="gsk_…  (get free key at console.groq.com)"
                  style={{ width: "100%", marginTop: 4 }}
                />
                <select
                  value={String(g("groq_model", "llama-3.3-70b-versatile"))}
                  onChange={(e) => set("groq_model", e.target.value)}
                  style={{ width: "100%", marginTop: 4 }}
                >
                  {GROQ_MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </>
            )}
            {g("script_provider") === "ollama" && (
              <>
                {ollamaDetail && (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: ollamaDetail.toLowerCase().includes("not found") ? theme.accentRed : theme.accentGrn }}>
                    <span style={{ fontSize: 14 }}>●</span> {ollamaDetail}
                  </div>
                )}
                <input value={String(g("ollama_url", "http://localhost:11434"))} onChange={(e) => set("ollama_url", e.target.value)} placeholder="Ollama URL" style={{ width: "100%", marginTop: 4 }} />
                <input value={String(g("ollama_model", "llama3"))} onChange={(e) => set("ollama_model", e.target.value)} placeholder="Model" style={{ width: "100%", marginTop: 4 }} />
              </>
            )}
          </div>

          {/* Card 6: Pipeline Notes */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>PIPELINE NOTES</div>
            <ul style={{ margin: 0, paddingLeft: 12, listStyleType: "disc", fontSize: 11, color: theme.textHint, display: "flex", flexDirection: "column", gap: 4 }}>
              <li>Script review pause —&gt; edit narration before footage download</li>
              <li>Video preview pause —&gt; watch final video before upload</li>
              <li>Uncheck both for fully automated overnight runs</li>
              <li>Language applies to script + voiceover (Edge TTS + OmniVoice)</li>
              <li>Output folder is relative to project root unless full path given</li>
            </ul>
          </div>
        </div>
      </Section>

      <Section title="AGENTIC PIPELINE">
        <div style={styles.runBehaviorGrid}>
          {/* Card 1: Agent Review & Auto-Approve */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>SCRIPT REVIEW & AUTO-APPROVE</div>
            <label style={styles.checkRow}>
              <input
                type="checkbox"
                checked={Boolean(g("pipeline.skip_human_review", false))}
                onChange={(e) => set("pipeline.skip_human_review", e.target.checked)}
              />
              Auto-approve scripts (skip human review)
            </label>
            {Boolean(g("pipeline.skip_human_review", false)) && (
              <div style={{ marginTop: 8 }}>
                <label style={styles.label}>
                  Auto-approve Threshold: {Number(g("pipeline.auto_approve_threshold", 8.0)).toFixed(1)}
                </label>
                <input
                  type="range"
                  min={6.0}
                  max={10.0}
                  step={0.1}
                  value={Number(g("pipeline.auto_approve_threshold", 8.0))}
                  onChange={(e) => set("pipeline.auto_approve_threshold", parseFloat(e.target.value))}
                  style={{ width: "100%" }}
                />
                <div style={styles.cardHint}>Critic score must exceed this for auto-approval</div>
              </div>
            )}
            <div style={styles.cardHint}>Uses the critic agent to score scripts and auto-approves if criteria are met.</div>
          </div>

          {/* Card 2: SEO Optimization */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>SEO OPTIMIZATION</div>
            <label style={styles.checkRow}>
              <input
                type="checkbox"
                checked={Boolean(g("pipeline.seo_enabled", true))}
                onChange={(e) => set("pipeline.seo_enabled", e.target.checked)}
              />
              Enable SEO Optimization Agent
            </label>
            <div style={styles.cardHint}>Automatically rewrites and optimizes title, description, and tags after script approval.</div>
          </div>

          {/* Card 3: Error Recovery */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>ERROR RECOVERY</div>
            <label style={styles.checkRow}>
              <input
                type="checkbox"
                checked={Boolean(g("pipeline.error_recovery_enabled", true))}
                onChange={(e) => set("pipeline.error_recovery_enabled", e.target.checked)}
              />
              Enable Error Recovery Agent
            </label>
            <div style={styles.cardHint}>Autonomously heals temporary API timeouts or network errors, and falls back if needed.</div>
          </div>

          {/* Card 4: Tavily Research API Key */}
          <div style={styles.runBehaviorCard}>
            <div style={styles.cardTitle}>TAVILY RESEARCH KEY</div>
            <label style={styles.label}>Tavily Search API Key</label>
            <input
              type="password"
              value={String(g("api_keys.tavily", ""))}
              onChange={(e) => set("api_keys.tavily", e.target.value)}
              placeholder="tvly-..."
              style={{ width: "100%", padding: "6px", background: theme.bgMain, color: theme.textPri, border: `1px solid ${theme.border}`, borderRadius: 4 }}
            />
            <div style={styles.cardHint}>Optional. Get a free key at tavily.com for better search and research quality.</div>
          </div>
        </div>
      </Section>

      <Section title="CORE PARAMETERS">
        <p style={styles.hint}>Chrome profiles for YouTube upload</p>
        <select value={activeProfile} onChange={(e) => { setActiveProfile(Number(e.target.value)); set("pipeline.active_profile_index", Number(e.target.value)); }} style={{ width: "100%", marginBottom: 8 }}>
          {profiles.map((p, i) => <option key={i} value={i}>{p.name || p.profile_name || `Profile ${i + 1}`}</option>)}
          {profiles.length === 0 && <option value={0}>No profiles — setup one below</option>}
        </select>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <input
            type="text"
            placeholder="New profile name (e.g. MyChannel)"
            value={newProfileName}
            onChange={(e) => setNewProfileName(e.target.value)}
            style={{
              flex: 1,
              padding: "6px",
              background: "rgba(255, 255, 255, 0.05)",
              color: "#fff",
              border: `1px solid ${theme.border}`,
              borderRadius: 4,
              fontSize: "12px",
              fontFamily: "monospace"
            }}
          />
          <button type="button" style={{ ...styles.actionBtn, marginTop: 0 }} onClick={async () => {
            if (!newProfileName.trim()) {
              alert("Please enter a profile name first.");
              return;
            }
            const res = await api.chromeProfileSetup(newProfileName.trim());
            alert(res.message);
            setNewProfileName("");
            load();
          }}>+ SETUP PROFILE</button>
        </div>

        <p style={{ ...styles.sectionTitle, marginTop: 16 }}>LOGO WATERMARK</p>
        <label style={styles.checkRow}>
          <input type="checkbox" checked={Boolean(g("documentary.logo_enabled"))} onChange={(e) => set("documentary.logo_enabled", e.target.checked)} />
          Enable logo watermark
        </label>
        
        {Boolean(g("documentary.logo_enabled")) && (
          <>
            <button
              type="button"
              style={{ ...styles.foldLink, marginTop: 8 }}
              onClick={() => setShowLogoPresets(!showLogoPresets)}
            >
              {showLogoPresets ? "▼" : "▶"} Logo presets (3 slots)
            </button>
            {showLogoPresets && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: theme.textSec, marginBottom: 8, fontWeight: 600, letterSpacing: 0.5 }}>LOGO PRESETS</div>
            {([1, 2, 3] as const).map((idx) => {
              const isActive = Number(g("documentary.active_logo_index", 1)) === idx;
              const logoPath = String(g(`documentary.logo_${idx}_path`, ""));
              const logoPos = String(g(`documentary.logo_${idx}_position`, "bottom_right"));
              return (
                <div key={idx} style={styles.voiceCard}>
                  <div style={styles.voiceCardHeader}>
                    <div style={{ display: "flex", alignItems: "center" }}>
                      <span style={styles.voiceCardNumber}>{idx}</span>
                      <span style={styles.voiceCardTitle}>
                        {String(g(`documentary.logo_${idx}_label`)) || `LOGO PRESET ${idx}`}
                      </span>
                    </div>
                    <button
                      type="button"
                      style={{
                        ...styles.toggleBtn,
                        ...(isActive ? styles.toggleBtnActive : styles.toggleBtnInactive),
                      }}
                      onClick={() => selectActiveLogo(idx)}
                    >
                      {isActive ? "● ACTIVE (ON)" : "○ INACTIVE (OFF)"}
                    </button>
                  </div>
                  
                  <Row label="Logo Preset Name">
                    <input
                      value={String(g(`documentary.logo_${idx}_label`, ""))}
                      onChange={(e) => setLogoField(idx, "label", e.target.value)}
                      style={{ flex: 1 }}
                      placeholder={`Logo ${idx} Label (e.g. Channel A Logo)`}
                    />
                  </Row>
                  
                  <Row label="Logo path">
                    <div style={{ display: "flex", gap: 8, flex: 1 }}>
                      <input
                        value={logoPath}
                        onChange={(e) => setLogoField(idx, "path", e.target.value)}
                        placeholder="Logo image file path"
                        style={{ flex: 1 }}
                      />
                      <button
                        type="button"
                        style={styles.actionBtn}
                        onClick={() => browseLogoFile(idx)}
                      >
                        BROWSE
                      </button>
                    </div>
                  </Row>

                  {logoPath && (
                    <LogoPreview
                      path={logoPath}
                      opacity={Number(g(`documentary.logo_${idx}_opacity`, 1.0))}
                      theme={theme}
                    />
                  )}
                  
                  <Row label="Position">
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
                      <select
                        value={logoPos}
                        onChange={(e) => setLogoField(idx, "position", e.target.value)}
                        style={{ flex: 1 }}
                      >
                        {LOGO_POSITIONS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                      </select>
                      <PositionPreview position={logoPos} />
                    </div>
                  </Row>
                  
                  <Row label={`Scale: ${Math.round(Number(g(`documentary.logo_${idx}_scale`, 0.15)) * 100)}%`}>
                    <input
                      type="range"
                      min={0.05}
                      max={0.5}
                      step={0.01}
                      value={Number(g(`documentary.logo_${idx}_scale`, 0.15))}
                      onChange={(e) => setLogoField(idx, "scale", parseFloat(e.target.value))}
                      style={{ flex: 1 }}
                    />
                  </Row>
                  
                  <Row label="Margin (px)">
                    <input
                      type="number"
                      value={Number(g(`documentary.logo_${idx}_margin`, 24))}
                      onChange={(e) => setLogoField(idx, "margin", parseInt(e.target.value, 10) || 0)}
                    />
                  </Row>
                  
                  <Row label={`Opacity: ${Math.round(Number(g(`documentary.logo_${idx}_opacity`, 1)) * 100)}%`}>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={Number(g(`documentary.logo_${idx}_opacity`, 1))}
                      onChange={(e) => setLogoField(idx, "opacity", parseFloat(e.target.value))}
                      style={{ flex: 1 }}
                    />
                  </Row>
                </div>
              );
            })}
          </div>
            )}
          </>
        )}
      </Section>

      <Section title="ABOUT">
        <p style={styles.hint}>Ghost Creator AI v{version} — free &amp; open source (MIT)</p>
        <p style={styles.hint}>Device: {deviceName}</p>
        <button
          type="button"
          style={styles.actionBtn}
          onClick={() => {
            const url = `${getApiBaseUrl()}/guide`;
            if (window.electronAPI?.openExternal) {
              void window.electronAPI.openExternal(url);
            } else {
              window.open(url, "_blank");
            }
          }}
        >
          OPEN DOCUMENTATION
        </button>
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

function PositionPreview({ position }: { position: string }) {
  const corners: Record<string, React.CSSProperties> = {
    top_left: { top: 4, left: 4 },
    top_right: { top: 4, right: 4 },
    bottom_left: { bottom: 4, left: 4 },
    bottom_right: { bottom: 4, right: 4 }
  };
  const activeStyle = corners[position] || corners.bottom_right;
  return (
    <div style={{
      width: 48,
      height: 32,
      border: `1px solid ${theme.border}`,
      background: "#020608",
      position: "relative",
      borderRadius: 2,
      display: "inline-block",
      marginLeft: 8,
      verticalAlign: "middle"
    }}>
      <div style={{
        width: 6,
        height: 6,
        background: theme.accentPri,
        borderRadius: "50%",
        position: "absolute",
        boxShadow: `0 0 6px ${theme.accentPri}`,
        ...activeStyle
      }} />
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
  subPanel: {
    background: theme.bgMain,
    border: `1px solid ${theme.border}`,
    borderRadius: 4,
    padding: 12,
    marginTop: 8,
    marginBottom: 8,
  },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16 },
  foldLink: {
    background: "transparent",
    border: "none",
    color: theme.accentSec,
    fontSize: 11,
    marginBottom: 4,
    marginTop: 4,
    padding: "4px 0",
    textAlign: "left" as const,
    cursor: "pointer",
  },
  actionBtn: {
    padding: "6px 12px",
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    color: theme.accentPri,
    fontSize: 11,
    marginRight: 8,
    marginTop: 4,
    borderRadius: 4,
  },
  saveBtn: { width: "100%", padding: 14, background: theme.accentPri, color: theme.textPri, border: "none", fontWeight: 700, marginBottom: 12, borderRadius: 4 },
  envBar: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 12, background: theme.bgSec, border: `1px solid ${theme.border}` },
  runBehaviorGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: 12,
    marginTop: 8,
  },
  runBehaviorCard: {
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    padding: 12,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minHeight: 150,
  },
  cardTitle: {
    fontSize: 10,
    fontWeight: 700,
    color: theme.accentSec,
    letterSpacing: 0.5,
    marginBottom: 4,
    fontFamily: "monospace",
  },
  cardHint: {
    fontSize: 11,
    color: theme.textHint,
    lineHeight: 1.4,
    marginTop: 2,
  },
  voiceCard: {
    background: theme.bgMain,
    border: `1px solid ${theme.border}`,
    borderRadius: 4,
    padding: 12,
    marginBottom: 12,
    marginTop: 8,
  },
  voiceCardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 10,
    borderBottom: `1px solid ${theme.border}`,
    paddingBottom: 6,
  },
  voiceCardNumber: {
    background: theme.accentSec,
    color: "#000",
    fontWeight: "bold",
    fontSize: 10,
    width: 18,
    height: 18,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 8,
    fontFamily: "monospace",
  },
  voiceCardTitle: {
    color: theme.textPri,
    fontWeight: 600,
    fontSize: 11,
    flex: 1,
    fontFamily: "monospace",
  },
  toggleBtn: {
    padding: "4px 8px",
    fontSize: 10,
    fontWeight: 700,
    border: "1px solid",
    borderRadius: 2,
    cursor: "pointer",
    fontFamily: "monospace",
    transition: "all 0.2s ease",
  },
  toggleBtnActive: {
    background: "rgba(0, 204, 102, 0.15)",
    color: theme.accentGrn,
    borderColor: theme.accentGrn,
  },
  toggleBtnInactive: {
    background: theme.bgMain,
    color: theme.textSec,
    borderColor: theme.border,
  },
  channelsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: 16,
    marginTop: 8,
    alignItems: "start",
  },
  channelCard: {
    background: theme.bgSec,
    border: `1px solid ${theme.border}`,
    borderRadius: 6,
    padding: 16,
    transition: "all 0.3s ease",
    display: "flex",
    flexDirection: "column",
    position: "relative",
  },
  channelCardActive: {
    borderColor: theme.accentPri,
    boxShadow: `0 0 12px rgba(191, 0, 255, 0.3)`,
    background: "rgba(191, 0, 255, 0.03)",
  },
  activeBadge: {
    fontSize: 9,
    fontWeight: 700,
    color: theme.accentGrn,
    background: "rgba(0, 204, 102, 0.15)",
    border: `1px solid ${theme.accentGrn}`,
    padding: "3px 8px",
    borderRadius: 2,
    fontFamily: "monospace",
  },
  selectBtn: {
    fontSize: 9,
    fontWeight: 700,
    color: theme.textPri,
    background: theme.bgCard,
    border: `1px solid ${theme.border}`,
    padding: "3px 8px",
    borderRadius: 2,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  cardEditBtn: {
    fontSize: 9,
    color: theme.textSec,
    background: "transparent",
    border: "none",
    cursor: "pointer",
    padding: 0,
    textDecoration: "underline",
    marginTop: 4,
  },
};
