import { useEffect, useRef } from "react";

export interface PipelineLiveState {
  running: boolean;
  step: number;           // 1-6, 0 = idle
  stepName: string;
  progress: number;       // 0..1
  lastMsg: string;
  level: string;          // INFO | SUCCESS | ERROR | WARNING
}

interface Props {
  state: PipelineLiveState;
  onGoToPipeline: () => void;
}

const STEP_ICONS = ["🔍", "📝", "🎙", "🎬", "⚙️", "📤"];

const levelColor: Record<string, string> = {
  ERROR: "#FF4444",
  SUCCESS: "#00CC66",
  WARNING: "#FFB800",
  INFO: "#BCA2E8",
};

export function PipelineLiveBanner({ state, onGoToPipeline }: Props) {
  const { running, step, stepName, progress, lastMsg, level } = state;
  const tickRef = useRef<number>(0);

  // Pulse animation tick
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => { tickRef.current++; }, 500);
    return () => clearInterval(id);
  }, [running]);

  if (!running) return null;

  const pct = Math.round(progress * 100);
  const icon = step >= 1 && step <= 6 ? STEP_ICONS[step - 1] : "⚡";
  const msgColor = levelColor[level] || levelColor.INFO;

  return (
    <div style={styles.wrap}>
      {/* Animated left accent */}
      <div style={styles.accent} />

      {/* Step badge */}
      <div style={styles.stepBadge}>
        <span style={styles.stepIcon}>{icon}</span>
        <div style={styles.stepText}>
          <span style={styles.stepNum}>STEP {step}/6</span>
          <span style={styles.stepName}>{stepName.toUpperCase()}</span>
        </div>
      </div>

      {/* Divider */}
      <div style={styles.divider} />

      {/* Progress section */}
      <div style={styles.progressWrap}>
        <div style={styles.progressBar}>
          <div style={{ ...styles.progressFill, width: `${pct}%` }} />
          {/* Moving shimmer */}
          <div style={{ ...styles.shimmer, left: `${Math.min(pct, 95)}%` }} />
        </div>
        <span style={styles.pct}>{pct}%</span>
      </div>

      {/* Divider */}
      <div style={styles.divider} />

      {/* Last log message */}
      <div style={styles.logWrap}>
        <span style={styles.logDot}>●</span>
        <span style={{ ...styles.logMsg, color: msgColor }}>
          {lastMsg ? (lastMsg.length > 60 ? lastMsg.slice(0, 60) + "…" : lastMsg) : "Pipeline running…"}
        </span>
      </div>

      {/* Go to pipeline button */}
      <button type="button" style={styles.goBtn} onClick={onGoToPipeline}>
        🎬 VIEW PIPELINE →
      </button>

      {/* Spinner */}
      <div style={styles.spinner} />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrap: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "6px 16px",
    background: "linear-gradient(90deg, #0D0518 0%, #140826 50%, #0D0518 100%)",
    borderBottom: "1px solid rgba(191, 0, 255, 0.4)",
    borderTop: "1px solid rgba(191, 0, 255, 0.15)",
    position: "relative",
    overflow: "hidden",
    minHeight: 36,
    animation: "bannerPulse 3s ease-in-out infinite",
  },
  accent: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
    background: "linear-gradient(180deg, #BF00FF, #6600CC)",
    boxShadow: "0 0 8px #BF00FF",
  },
  stepBadge: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    minWidth: 110,
    paddingLeft: 8,
  },
  stepIcon: { fontSize: 16 },
  stepText: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  stepNum: {
    fontSize: 9,
    color: "rgba(191,0,255,0.7)",
    fontFamily: "monospace",
    letterSpacing: 1,
    fontWeight: 700,
  },
  stepName: {
    fontSize: 11,
    color: "#F0E6FF",
    fontFamily: "monospace",
    fontWeight: 700,
    letterSpacing: 0.5,
  },
  divider: {
    width: 1,
    height: 24,
    background: "rgba(191,0,255,0.2)",
    flexShrink: 0,
  },
  progressWrap: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    minWidth: 140,
  },
  progressBar: {
    flex: 1,
    height: 6,
    background: "rgba(191,0,255,0.12)",
    borderRadius: 3,
    overflow: "hidden",
    position: "relative",
    border: "1px solid rgba(191,0,255,0.2)",
  },
  progressFill: {
    height: "100%",
    background: "linear-gradient(90deg, #6600CC, #BF00FF)",
    borderRadius: 3,
    transition: "width 0.6s ease",
    boxShadow: "0 0 6px #BF00FF",
  },
  shimmer: {
    position: "absolute",
    top: 0,
    width: 20,
    height: "100%",
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)",
    animation: "shimmerMove 1.5s ease-in-out infinite",
    transform: "translateX(-50%)",
  },
  pct: {
    fontSize: 11,
    color: "#BF00FF",
    fontFamily: "monospace",
    fontWeight: 700,
    minWidth: 30,
  },
  logWrap: {
    display: "flex",
    alignItems: "center",
    gap: 5,
    flex: 1,
    overflow: "hidden",
  },
  logDot: {
    fontSize: 8,
    color: "#BF00FF",
    animation: "dotPulse 1s ease-in-out infinite",
    flexShrink: 0,
  },
  logMsg: {
    fontSize: 11,
    fontFamily: "monospace",
    overflow: "hidden",
    whiteSpace: "nowrap",
    textOverflow: "ellipsis",
  },
  goBtn: {
    padding: "4px 10px",
    background: "rgba(191,0,255,0.15)",
    border: "1px solid rgba(191,0,255,0.5)",
    color: "#F0E6FF",
    fontSize: 10,
    fontWeight: 700,
    fontFamily: "monospace",
    borderRadius: 2,
    cursor: "pointer",
    whiteSpace: "nowrap",
    letterSpacing: 0.5,
    flexShrink: 0,
    transition: "all 0.2s",
  },
  spinner: {
    width: 14,
    height: 14,
    border: "2px solid rgba(191,0,255,0.2)",
    borderTop: "2px solid #BF00FF",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
    flexShrink: 0,
  },
};
