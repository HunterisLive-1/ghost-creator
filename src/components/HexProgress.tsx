import { theme } from "../theme/tokens";

export const DOC_STEPS = ["Research", "Script", "Voice", "Footage", "Assembly", "Upload"];

export type StepState = "idle" | "active" | "done" | "error";

interface Props {
  steps: StepState[];
  progress: number;
}

export function HexProgress({ steps, progress }: Props) {
  const pct = Math.round(progress * 100);
  return (
    <div style={{ padding: "12px 0" }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        {DOC_STEPS.map((label, i) => {
          const st = steps[i] || "idle";
          const color =
            st === "done" ? theme.accentGrn :
            st === "error" ? theme.accentRed :
            st === "active" ? theme.accentWarn :
            theme.border;
          return (
            <div
              key={label}
              style={{
                flex: "1 1 120px",
                minWidth: 100,
                padding: "8px 10px",
                border: `2px solid ${color}`,
                background: st === "active" ? theme.bgCard : theme.bgSec,
                textAlign: "center",
                fontSize: 10,
                fontWeight: 700,
                color: st === "idle" ? theme.textHint : theme.textPri,
                clipPath: "polygon(10% 0%, 90% 0%, 100% 50%, 90% 100%, 10% 100%, 0% 50%)",
              }}
            >
              {i + 1}. {label.toUpperCase()}
            </div>
          );
        })}
      </div>
      <div style={{ height: 6, background: theme.border, borderRadius: 3 }}>
        <div
          style={{
            height: "100%",
            width: `${pct}%`,
            background: theme.accentPri,
            borderRadius: 3,
            transition: "width 0.3s",
          }}
        />
      </div>
      <div style={{ textAlign: "right", fontSize: 11, color: theme.textSec, marginTop: 4 }}>{pct}%</div>
    </div>
  );
}
